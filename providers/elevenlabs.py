"""ElevenLabs text-to-speech provider with explicit project language support."""

from __future__ import annotations

import os
from typing import Optional

from config import settings
from providers.elevenlabs_voice_resolver import ElevenLabsVoiceResolver
from utils.api_client import APIClient
from utils.errors import (
    APIError,
    AudioProcessingError,
    FileValidationError,
    VoiceOverGenerationError,
)
from utils.logger import logger


class ElevenLabsProvider:
    """Generate multilingual voice-over through the official ElevenLabs TTS API."""

    BASE_URL = "https://api.elevenlabs.io"
    TTS_ENDPOINT = "/v1/text-to-speech"
    DEFAULT_MODEL = "eleven_multilingual_v2"
    DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"

    def __init__(self, voice_id: Optional[str] = None):
        self.api_key = settings.elevenlabs_api_key
        if not self.api_key:
            raise VoiceOverGenerationError("ELEVENLABS_API_KEY not configured")

        self.voice_id = voice_id or settings.elevenlabs_voice_id
        if not self.voice_id:
            raise VoiceOverGenerationError("ELEVENLABS_VOICE_ID not configured")

        self.client = APIClient(
            api_key=self.api_key,
            base_url=self.BASE_URL,
            timeout=settings.request_timeout_seconds,
        )
        self.voice_resolver = ElevenLabsVoiceResolver(self.client)

    @staticmethod
    def validate_language(language: str) -> str:
        language = language.lower().strip()
        if language not in settings.supported_languages:
            supported = ", ".join(settings.supported_languages)
            raise VoiceOverGenerationError(
                f"Unsupported language '{language}'. Supported: {supported}"
            )
        return language

    def _request_tts(self, text: str, voice_id: str, model_id: str, output_format: str, language: str):
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {"text": text, "model_id": model_id}
        endpoint = f"{self.TTS_ENDPOINT}/{voice_id}"
        params = {"output_format": output_format}
        if model_id != self.DEFAULT_MODEL:
            params["language_code"] = language
        return self.client.post(endpoint, headers=headers, json=payload, params=params)

    @staticmethod
    def _is_paid_library_voice_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return (
            "402" in message
            and (
                "paid_plan_required" in message
                or "library voice" in message
                or "not available for free" in message
            )
        )

    def _request_with_free_voice_fallback(
        self,
        text: str,
        selected_voice: str,
        model_id: str,
        output_format: str,
        language: str,
    ):
        try:
            return self._request_tts(
                text, selected_voice, model_id, output_format, language
            )
        except APIError as exc:
            # APIClient raises on every HTTP >= 400, so a 402 never reaches
            # response.status_code handling. Resolve an account-accessible voice
            # here and retry once only for the specific paid Voice Library error.
            if not self._is_paid_library_voice_error(exc):
                raise

            fallback_voice = self.voice_resolver.resolve(language)
            if not fallback_voice or fallback_voice == selected_voice:
                raise VoiceOverGenerationError(
                    "Configured ElevenLabs voice requires a paid plan, and no free "
                    "API-accessible voice was found for this account."
                ) from exc

            logger.warning(
                "Configured ElevenLabs voice is unavailable on this plan; "
                "using an account-accessible voice discovered at runtime."
            )
            return self._request_tts(
                text, fallback_voice, model_id, output_format, language
            )

    def generate_voice_over(
        self,
        text: str,
        output_path: str,
        voice_id: Optional[str] = None,
        model_id: Optional[str] = None,
        output_format: Optional[str] = None,
        language: Optional[str] = None,
    ) -> None:
        if not text or not text.strip():
            raise VoiceOverGenerationError("Text cannot be empty")

        language = self.validate_language(language or settings.default_language)
        selected_voice = voice_id or self.voice_id
        model_id = model_id or self.DEFAULT_MODEL
        output_format = output_format or self.DEFAULT_OUTPUT_FORMAT

        try:
            logger.info(
                "ElevenLabs TTS: language=%s model=%s voice=%s chars=%s",
                language,
                model_id,
                selected_voice,
                len(text),
            )
            response = self._request_with_free_voice_fallback(
                text, selected_voice, model_id, output_format, language
            )

            if response.status_code != 200:
                raise VoiceOverGenerationError(
                    f"ElevenLabs API error: {response.status_code} - "
                    f"{response.text[:300]}"
                )

            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "wb") as audio_file:
                audio_file.write(response.content)
            self.validate_audio(output_path)
        except VoiceOverGenerationError:
            raise
        except Exception as exc:
            logger.error("ElevenLabs TTS failed: %s", exc)
            raise VoiceOverGenerationError(f"Failed to generate voice-over: {exc}") from exc

    def validate_audio(self, output_path: str) -> bool:
        if not os.path.exists(output_path):
            raise FileValidationError(f"Audio file not found: {output_path}")
        size = os.path.getsize(output_path)
        if size == 0:
            raise AudioProcessingError(f"Audio file is empty: {output_path}")
        return True
