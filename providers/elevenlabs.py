"""
ElevenLabs text-to-speech provider.

Official API documentation:
- TTS Convert: https://elevenlabs.io/docs/api-reference/text-to-speech/convert
- Authentication: https://elevenlabs.io/docs/api-reference/authentication

Current verified TTS API:
- Endpoint: POST /v1/text-to-speech/{voice_id}
- Base URL: https://api.elevenlabs.io
- Authentication: xi-api-key header
- Model: eleven_multilingual_v2 (default)
- Output format: mp3_44100_128 (default)
"""

import os
from typing import Optional
from utils.errors import (
    APIError,
    VoiceOverGenerationError,
    AudioProcessingError,
    FileValidationError,
)
from utils.logger import logger
from utils.api_client import APIClient
from config import settings


class ElevenLabsProvider:
    """
    ElevenLabs text-to-speech provider using official TTS API.

    Model: eleven_multilingual_v2 (default)
    Output format: mp3_44100_128 (default)
    Voice ID: from ELEVENLABS_VOICE_ID configuration (never hard-coded)
    Response: Binary audio file (no URL)
    """

    BASE_URL = "https://api.elevenlabs.io"
    TTS_ENDPOINT = "/v1/text-to-speech"

    # Official default model
    DEFAULT_MODEL = "eleven_multilingual_v2"

    # Official default output format
    DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"

    def __init__(self, voice_id: Optional[str] = None):
        """
        Initialize ElevenLabs provider.

        Args:
            voice_id: Voice ID to use (defaults from settings)

        Raises:
            APIError: If API key or voice ID not configured
        """
        self.api_key = settings.elevenlabs_api_key

        if not self.api_key:
            raise APIError("ELEVENLABS_API_KEY not configured")

        # Use provided voice_id or fall back to settings
        self.voice_id = voice_id or settings.elevenlabs_voice_id

        if not self.voice_id:
            raise APIError(
                "ELEVENLABS_VOICE_ID not configured in settings or provided"
            )

        self.client = APIClient(
            api_key=self.api_key,
            base_url=self.BASE_URL,
            timeout=settings.request_timeout_seconds,
        )

    def generate_voice_over(
        self,
        text: str,
        output_path: str,
        voice_id: Optional[str] = None,
        model_id: Optional[str] = None,
        output_format: Optional[str] = None,
    ) -> None:
        """
        Generate voice-over audio from text.

        Response is binary audio data saved directly to disk.

        Args:
            text: Text to synthesize
            output_path: Path to save audio file
            voice_id: Override voice ID (defaults to settings)
            model_id: Override model (default: eleven_multilingual_v2)
            output_format: Override output format (default: mp3_44100_128)

        Raises:
            VoiceOverGenerationError: If synthesis fails
            AudioProcessingError: If audio processing fails
        """
        if not text or len(text.strip()) == 0:
            raise VoiceOverGenerationError("Text cannot be empty")

        voice_id = voice_id or self.voice_id
        model_id = model_id or self.DEFAULT_MODEL
        output_format = output_format or self.DEFAULT_OUTPUT_FORMAT

        try:
            logger.info(
                f"ElevenLabs: Generating TTS: {len(text)} chars, "
                f"model={model_id}, voice={voice_id}"
            )

            headers = {
                "xi-api-key": self.api_key,
                "Content-Type": "application/json",
            }

            # Official request schema
            payload = {
                "text": text,
                "model_id": model_id,
            }

            # Construct endpoint with voice_id
            endpoint = f"{self.TTS_ENDPOINT}/{voice_id}"

            # Official output_format as query parameter
            params = {"output_format": output_format}

            response = self.client.post(
                endpoint,
                headers=headers,
                json=payload,
                params=params,
            )

            # Official response is binary audio (HTTP 200)
            if response.status_code != 200:
                error_msg = (
                    f"ElevenLabs API error: {response.status_code} - "
                    f"{response.text[:200]}"
                )
                logger.error(error_msg)
                raise VoiceOverGenerationError(error_msg)

            # Save binary audio response directly
            with open(output_path, "wb") as f:
                f.write(response.content)

            logger.info(f"ElevenLabs: Voice-over generated: {output_path}")

        except VoiceOverGenerationError:
            raise
        except Exception as e:
            logger.error(f"ElevenLabs: Voice-over generation failed: {e}")
            raise VoiceOverGenerationError(f"Failed to generate voice-over: {e}")

    def validate_audio(self, output_path: str) -> bool:
        """
        Validate generated audio file.

        Args:
            output_path: Path to audio file

        Returns:
            True if valid

        Raises:
            FileValidationError: If validation fails
            AudioProcessingError: If file is empty
        """
        if not os.path.exists(output_path):
            raise FileValidationError(f"Audio file not found: {output_path}")

        file_size = os.path.getsize(output_path)
        if file_size == 0:
            raise AudioProcessingError(f"Audio file is empty: {output_path}")

        logger.info(f"ElevenLabs: Audio file validated ({file_size} bytes)")
        return True
