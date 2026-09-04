"""Local Kokoro ONNX text-to-speech provider."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import soundfile as sf
from kokoro_onnx import Kokoro

from utils.errors import AudioProcessingError, FileValidationError, VoiceOverGenerationError
from utils.logger import logger


class KokoroProvider:
    """Generate English narration locally with the open-weight Kokoro model."""

    MODEL_PATH = Path("/app/models/kokoro-v1.0.int8.onnx")
    VOICES_PATH = Path("/app/models/voices-v1.0.bin")
    DEFAULT_VOICE = "af_sarah"
    DEFAULT_LANGUAGE = "en-us"
    DEFAULT_SPEED = 1.0

    _engine: Optional[Kokoro] = None

    def __init__(self, voice: Optional[str] = None, speed: float = DEFAULT_SPEED):
        self.voice = voice or os.getenv("KOKORO_VOICE", self.DEFAULT_VOICE)
        self.speed = speed
        self._ensure_models()

    @classmethod
    def _ensure_models(cls) -> None:
        if not cls.MODEL_PATH.exists():
            raise VoiceOverGenerationError(f"Kokoro model not found: {cls.MODEL_PATH}")
        if not cls.VOICES_PATH.exists():
            raise VoiceOverGenerationError(f"Kokoro voices not found: {cls.VOICES_PATH}")

    @classmethod
    def _get_engine(cls) -> Kokoro:
        if cls._engine is None:
            logger.info("Loading local Kokoro ONNX TTS model")
            cls._engine = Kokoro(str(cls.MODEL_PATH), str(cls.VOICES_PATH))
        return cls._engine

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
                "Kokoro provider currently supports English narration only (en/en-us/en-gb)."
            )

        selected_voice = voice_id or self.voice
        selected_speed = float(speed if speed is not None else self.speed)
        if selected_speed <= 0:
            raise VoiceOverGenerationError("Kokoro speed must be positive")

        try:
            engine = self._get_engine()
            samples, sample_rate = engine.create(
                text.strip(),
                voice=selected_voice,
                speed=selected_speed,
                lang="en-us" if language != "en-gb" else "en-gb",
            )
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            sf.write(output_path, samples, sample_rate)
            self.validate_audio(output_path)
            logger.info(
                "Kokoro TTS: voice=%s language=%s chars=%s output=%s",
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
