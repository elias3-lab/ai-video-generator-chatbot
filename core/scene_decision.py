"""Deterministic scene-level media decisions for the documentary pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SceneMediaMode(str, Enum):
    AI_VIDEO = "ai_video"
    FREE_MEDIA = "free_media"


@dataclass(frozen=True)
class SceneContext:
    """Signals used by the router; no provider credentials belong here."""

    prompt: str
    visual_priority: float = 0.5
    stock_likelihood: float = 0.5
    consistency_required: bool = False
    prefer_stock: bool = False


@dataclass(frozen=True)
class SceneDecision:
    mode: SceneMediaMode
    reason: str


def decide_scene_media(context: SceneContext) -> SceneDecision:
    """Select AI or stock using explicit, testable rules.

    AI is preferred for character continuity, stylized/rare visuals, or when
    the prompt is strongly unsuitable for ordinary stock footage. Stock is
    preferred when requested or when likely stock coverage is high.
    """
    if context.prefer_stock:
        return SceneDecision(SceneMediaMode.FREE_MEDIA, "Stock explicitly preferred.")

    if context.consistency_required or context.visual_priority >= 0.75:
        return SceneDecision(SceneMediaMode.AI_VIDEO, "Visual continuity/priority favors AI generation.")

    if context.stock_likelihood >= 0.70 and context.visual_priority < 0.70:
        return SceneDecision(SceneMediaMode.FREE_MEDIA, "Likely stock coverage makes free media preferable.")

    return SceneDecision(SceneMediaMode.AI_VIDEO, "AI selected as the default cinematic path.")
