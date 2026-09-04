"""Resolve an ElevenLabs voice that is usable by the current API plan."""

from __future__ import annotations

from typing import Any

from config import settings
from utils.api_client import APIClient
from utils.errors import VoiceOverGenerationError


class ElevenLabsVoiceResolver:
    """Find a non-community voice explicitly available to the current account."""

    BASE_URL = "https://api.elevenlabs.io"
    VOICES_ENDPOINT = "/v2/voices"

    def __init__(self) -> None:
        if not settings.elevenlabs_api_key:
            raise VoiceOverGenerationError("ELEVENLABS_API_KEY not configured")
        self.client = APIClient(
            api_key=settings.elevenlabs_api_key,
            base_url=self.BASE_URL,
            timeout=settings.request_timeout_seconds,
        )

    def resolve(self, preferred_voice_id: str | None = None) -> tuple[str, str]:
        """Return (voice_id, voice_name) for a voice available to this account.

        A configured voice is used only when the API reports it is available.
        Otherwise we choose an available non-community English voice, preferring
        documentary/storyteller-style labels when present.
        """
        response = self.client.get(
            self.VOICES_ENDPOINT,
            params={
                "page_size": 100,
                "language": ["en"],
                "voice_type": "non-community",
            },
        )
        if response.status_code != 200:
            raise VoiceOverGenerationError(
                f"Unable to discover ElevenLabs voices: {response.status_code} - {response.text[:300]}"
            )

        data = response.json()
        voices = data.get("voices", []) if isinstance(data, dict) else []
        available = [voice for voice in voices if self._available_on_free_api(voice)]
        if not available:
            raise VoiceOverGenerationError(
                "No ElevenLabs voice available to the current API plan. "
                "The configured Voice Library voice requires a paid plan."
            )

        if preferred_voice_id:
            for voice in available:
                if voice.get("voice_id") == preferred_voice_id:
                    return str(voice["voice_id"]), str(voice.get("name") or "Available voice")

        def score(voice: dict[str, Any]) -> tuple[int, str]:
            text = " ".join(
                str(voice.get(key, "")) for key in ("name", "description")
            ).lower()
            labels = voice.get("labels") or {}
            text += " " + " ".join(str(value) for value in labels.values()).lower()
            keywords = ("narrator", "storyteller", "documentary", "warm", "grounded", "deep")
            return (-sum(keyword in text for keyword in keywords), str(voice.get("name") or ""))

        selected = sorted(available, key=score)[0]
        return str(selected["voice_id"]), str(selected.get("name") or "Available voice")

    @staticmethod
    def _available_on_free_api(voice: dict[str, Any]) -> bool:
        """Use explicit tier metadata when present; never assume library access."""
        tiers = voice.get("available_for_tiers")
        if tiers is None:
            # Non-community voices are personal/default/workspace voices, so the
            # account-level API response is the authority when tier metadata is absent.
            return voice.get("voice_type") in {"personal", "default", "workspace"} or voice.get("category") == "premade"
        normalized = {str(tier).lower() for tier in tiers}
        return "free" in normalized or "free_trial" in normalized
