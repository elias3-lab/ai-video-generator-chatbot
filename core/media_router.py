"""Provider-agnostic routing decisions for each planned scene."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence


class MediaMode(str, Enum):
    AI_VIDEO = "ai_video"
    FREE_MEDIA = "free_media"


@dataclass(frozen=True)
class RouteDecision:
    mode: MediaMode
    providers: tuple[str, ...]
    reason: str


class SmartMediaRouter:
    """Choose AI generation first, with explicit fallback providers.

    Provider execution is intentionally outside this class. The orchestrator
    can try providers in order and fall back to free media when all fail.
    """

    def __init__(self, ai_providers: Sequence[str], free_media_provider: str = "free_media") -> None:
        self.ai_providers = tuple(dict.fromkeys(p for p in ai_providers if p))
        self.free_media_provider = free_media_provider

    def decide(self, *, prefer_stock: bool = False) -> RouteDecision:
        if prefer_stock or not self.ai_providers:
            return RouteDecision(
                mode=MediaMode.FREE_MEDIA,
                providers=(self.free_media_provider,),
                reason="Stock media selected for this scene.",
            )
        return RouteDecision(
            mode=MediaMode.AI_VIDEO,
            providers=self.ai_providers + (self.free_media_provider,),
            reason="AI generation selected with automatic provider/stock fallback.",
        )
