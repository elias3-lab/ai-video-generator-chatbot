"""Local text-to-speech provider with a Render-safe fallback."""

from __future__ import annotations

import gc
import os
import subprocess
from pathlib import Path
from typing import Optional

import onnxruntime as ort
import soundfile as sf
from kokoro_onnx import Kokoro

from utils.errors import AudioProcessingError, FileValidationError, VoiceOverGenerationError
from utils.logger import logger


class KokoroProvider:
    """Generate English narration locally, with a low-memory safe fallback."""

    MODEL_PATH = Path("/app/models/kokoro-v1.0.int8.onnx")
    VOICES_PATH = Path("/app/models/voices-v1.0.bin")
    DEFAULT_VOICE = "am_michael"
    DEFAULT_LANGUAGE = "en-us"
    DEFAULT_SPEED = 1.0

    _engine: Optional[Kokoro] = None

    def __init__(self, voice: Optional[str] = None, speed: float = DEFAULT_SPEED):
        self.voice = voice or os.getenv("KOKORO_VOICE", self.DEFAULT_VOICE)
        self.speed = speed
        self.mode = os.getenv("KOKORO_MODE", "safe").strip().lower()
        self._ensure_models()

    @classmethod
    def _ensure_models(cls) -> None:
        # The model files are still shipped so Kokoro can be enabled later.
        # Safe mode does not load them, which avoids a large ONNX memory spike.
        if cls.MODEL_PATH.exists() and cls.VOICES_PATH.exists():
            return
        if os.getenv("KOKORO_MODE", "safe").strip().lower() == "kokoro":
            if not cls.MODEL_PATH.exists():
                raise VoiceOverGenerationError(f"Kokoro model not found: {cls.MODEL_PATH}")
            if not cls.VOICES_PATH.exists():
                raise VoiceOverGenerationError(f"Kokoro voices not found: {cls.VOICES_PATH}")

    @classmethod
    def _get_engine(cls) -> Kokoro:
        if cls._engine is None:
            logger.info("Loading local Kokoro ONNX TTS model with low-memory CPU settings")
            session_options = ort.SessionOptions()
            session_options.intra_op_num_threads = 1
            session_options.inter_op_num_threads = 1
            session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED
            session_options.enable_mem_pattern = False
            session_options.enable_cpu_mem_arena = False
            session = ort.InferenceSession(
                str(cls.MODEL_PATH),
                sess_options=session_options,
                providers=["CPUExecutionProvider"],
            )
            cls._engine = Kokoro.from_session(session, str(cls.VOICES_PATH))
            logger.info("Kokoro ONNX TTS model loaded successfully")
        return cls._engine

    def _generate_safe_tts(self, text: str, output_path: str, language: str) -> None:
        """Generate narration through the system espeak-ng binary.

        This path is intentionally the default on Render: it is lightweight,
        deterministic, and cannot trigger the large ONNX model memory spike.
        """
        voice = "en-gb" if language == "en-gb" else "en-us"
        speed_wpm = max(100, min(220, round(165 * self.speed)))
        command = [
            "espeak-ng",
            "-v", voice,
            "-s", str(speed_wpm),
            "-w", output_path,
            text.strip(),
        ]
        logger.info(
            "Safe local TTS generation started: voice=%s chars=%s output=%s",
            voice,
            len(text),
            output_path,
        )
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=120)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "unknown espeak-ng error").strip()
            raise VoiceOverGenerationError(f"Safe local TTS failed: {detail[:400]}")
        self.validate_audio(output_path)
        logger.info("Safe local TTS generation completed: output=%s", output_path)

    def generate_voice_over(
        self,
        text: str,
        output_path: str,
        voice_id: Optional[str] = None,
        language: str = DEFAULT_LANGUAGE,
        speed: Optional[float] = None,
    ) -> None:
        if not text or not text.strip():
            raise VoiceOverGenerationError("Text cannot be empty")
        language = (language or self.DEFAULT_LANGUAGE).lower().strip()
        if language not in {"en", "en-us", "en-gb"}:
            raise VoiceOverGenerationError(
                "Local TTS provider currently supports English narration only (en/en-us/en-gb)."
            )

        selected_voice = voice_id or self.voice
        selected_speed = float(speed if speed is not None else self.speed)
        if selected_speed <= 0:
            raise VoiceOverGenerationError("TTS speed must be positive")

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        try:
            if self.mode != "kokoro":
                self._generate_safe_tts(text, output_path, language)
                return

            engine = self._get_engine()
            logger.info(
                "Kokoro TTS generation started: voice=%s chars=%s output=%s",
                selected_voice,
                len(text),
                output_path,
            )
            samples, sample_rate = engine.create(
                text.strip(),
                voice=selected_voice,
                speed=selected_speed,
                lang="en-us" if language != "en-gb" else "en-gb",
            )
            sf.write(output_path, samples, sample_rate)
            del samples
            gc.collect()
            self.validate_audio(output_path)
            logger.info(
                "Kokoro TTS generation completed: voice=%s language=%s chars=%s output=%s",
                selected_voice,
                language,
                len(text),
                output_path,
            )
        except VoiceOverGenerationError:
            raise
        except Exception as exc:
            logger.error("Kokoro TTS failed: %s", exc)
            raise VoiceOverGenerationError(f"Failed to generate voice-over with Kokoro: {exc}") from exc

    @staticmethod
    def validate_audio(output_path: str) -> bool:
        if not os.path.exists(output_path):
            raise FileValidationError(f"Audio file not found: {output_path}")
        if os.path.getsize(output_path) == 0:
            raise AudioProcessingError(f"Audio file is empty: {output_path}")
        return True
