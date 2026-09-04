"""Resolve an ElevenLabs voice that is usable by the current API plan."""

from __future__ import annotations

from typing import Any, Dict, Optional

from utils.api_client import APIClient


class ElevenLabsVoiceResolver:
    """Discover account-accessible non-community/default voices at runtime."""

    VOICES_ENDPOINT = "/v2/voices"

    def __init__(self, client: APIClient):
        self.client = client

    @staticmethod
    def _score(voice: Dict[str, Any]) -> int:
        text = " ".join(
            str(value).lower()
            for value in (
                voice.get("name", ""),
                voice.get("description", ""),
                voice.get("category", ""),
                *(voice.get("labels", {}) or {}).values(),
            )
        )
        score = 0
        for term, points in {
            "narrator": 10,
            "storyteller": 9,
            "documentary": 8,
            "deep": 5,
            "grounded": 5,
            "warm": 4,
            "calm": 3,
            "professional": 2,
        }.items():
            if term in text:
                score += points
        return score

    def resolve(self, language: str = "en") -> Optional[str]:
        # non-community excludes Voice Library copies and covers personal/workspace
        # voices. If none are available, default voices are a safe free-plan fallback.
        candidates = []
        for params in (
            {"page_size": 100, "voice_type": "non-community"},
            {"page_size": 100, "voice_type": "default"},
        ):
            try:
                response = self.client.get(self.VOICES_ENDPOINT, params=params)
                payload = response.json()
            except Exception:
                continue

            for voice in payload.get("voices", []):
                if not voice.get("voice_id"):
                    continue

                tiers = {str(t).lower() for t in (voice.get("available_for_tiers") or [])}
                if tiers and not ({"free", "free_trial"} & tiers):
                    continue

                verified = voice.get("verified_languages") or []
                if verified and language:
                    languages = {
                        str(item.get("language_code", "")).lower()
                        for item in verified
                        if isinstance(item, dict)
                    }
                    if languages and language.lower() not in languages:
                        continue

                candidates.append(voice)

            if candidates:
                break

        if not candidates:
            return None

        candidates.sort(key=self._score, reverse=True)
        return str(candidates[0]["voice_id"])
