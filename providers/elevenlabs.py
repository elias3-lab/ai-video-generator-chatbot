"""Backward-compatible TTS provider backed by local Kokoro ONNX."""

from __future__ import annotations

import os
from typing import Optional

from providers.kokoro import KokoroProvider
from utils.errors import AudioProcessingError, FileValidationError, VoiceOverGenerationError


class ElevenLabsProvider:
    """Compatibility facade; narration is generated locally with Kokoro."""

    def __init__(self, voice_id: Optional[str] = None):
        self.voice_id = voice_id or os.getenv("KOKORO_VOICE", KokoroProvider.DEFAULT_VOICE)
        self.provider = KokoroProvider(voice=self.voice_id)

    @staticmethod
    def validate_language(language: str) -> str:
        language = (language or "en").lower().strip()
        if language not in {"en", "en-us", "en-gb"}:
            raise VoiceOverGenerationError(
                "Local Kokoro TTS currently supports English narration only."
            )
        return language

    def generate_voice_over(
        self,
        text: str,
        output_path: str,
        voice_id: Optional[str] = None,
        model_id: Optional[str] = None,
        output_format: Optional[str] = None,
        language: Optional[str] = None,
    ) -> None:
        self.provider.generate_voice_over(
            text=text,
            output_path=output_path,
            voice_id=voice_id or self.voice_id,
            language=self.validate_language(language or "en"),
        )

    @staticmethod
    def validate_audio(output_path: str) -> bool:
        if not os.path.exists(output_path):
            raise FileValidationError(f"Audio file not found: {output_path}")
        if os.path.getsize(output_path) == 0:
            raise AudioProcessingError(f"Audio file is empty: {output_path}")
        return True
