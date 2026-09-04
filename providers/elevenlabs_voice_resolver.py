"""Resolve an ElevenLabs voice that is usable by the current API plan."""

from __future__ import annotations

from typing import Any, Dict, Optional

from utils.api_client import APIClient


class ElevenLabsVoiceResolver:
    """Discover account-accessible voices at runtime."""

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
        # APIClient does not inject provider-specific authentication headers.
        # The List Voices endpoint therefore must receive xi-api-key explicitly.
        headers = {
            "xi-api-key": self.client.api_key,
            "Content-Type": "application/json",
        }

        # non-community excludes Voice Library copies and covers personal/workspace
        # voices. Default voices are tried afterward for older accounts that still
        # have access to them. The endpoint itself is account-scoped, so we do not
        # reject a voice merely because available_for_tiers is absent or incomplete.
        candidates = []
        for params in (
            {"page_size": 100, "voice_type": "non-community"},
            {"page_size": 100, "voice_type": "default"},
        ):
            try:
                response = self.client.get(
                    self.VOICES_ENDPOINT,
                    headers=headers,
                    params=params,
                )
                payload = response.json()
            except Exception:
                continue

            for voice in payload.get("voices", []):
                if not voice.get("voice_id"):
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
