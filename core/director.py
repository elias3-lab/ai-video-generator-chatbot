"""Deterministic cinematic Director layer for story beats and visual direction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class DirectorBeat:
    order: int
    name: str
    objective: str
    camera: str
    pacing: str


class DirectorPlanner:
    """Turn a user idea into consistent documentary/film scene direction.

    This layer is intentionally provider-neutral: it produces prompts that can
    be sent to MiniMax, Runway, or a future generative Director/LLM.
    """

    BEATS = ("Hook", "Journey", "Discovery", "Ending")
    CAMERAS = (
        "wide establishing shot, 24mm lens, slow push-in",
        "medium tracking shot, 35mm lens, controlled handheld movement",
        "intimate detail shot, 50mm lens, shallow depth of field",
        "wide closing composition, 35mm lens, slow pull-back",
    )

    @classmethod
    def beat_for(cls, order: int, total: int) -> DirectorBeat:
        if order < 1 or order > total or total < 1:
            raise ValueError("Invalid scene order")
        if total == 1:
            index = 0
        elif order == 1:
            index = 0
        elif order == total:
            index = 3
        else:
            index = 1 if order <= (total + 1) // 2 else 2
        name = cls.BEATS[index]
        objectives = {
            "Hook": "establish the central question and immediately create visual curiosity",
            "Journey": "move the story forward through place, people, action, and context",
            "Discovery": "reveal a meaningful detail, contrast, tradition, or unexpected insight",
            "Ending": "resolve the visual journey and leave the audience with a memorable final image",
        }
        pacing = {
            "Hook": "deliberate and intriguing",
            "Journey": "fluid and observational",
            "Discovery": "patient and intimate",
            "Ending": "reflective and conclusive",
        }
        return DirectorBeat(order, name, objectives[name], cls.CAMERAS[index], pacing[name])

    @classmethod
    def visual_prompt(
        cls,
        story: str,
        order: int,
        total: int,
        style: str,
        visual_dna: str = "",
    ) -> str:
        beat = cls.beat_for(order, total)
        dna = f" Visual DNA: {visual_dna.strip()}." if visual_dna.strip() else ""
        return (
            f"{beat.name} beat. {beat.objective}. Story subject: {story.strip()}. "
            f"{style.strip()}. {beat.camera}. Pacing: {beat.pacing}. "
            "Cinematic documentary realism, natural light, physically plausible motion, "
            "consistent geography and wardrobe, no text, no logos, no watermarks."
            f"{dna}"
        )

    @classmethod
    def build_storyboard(cls, story: str, scenes: Sequence[object], style: str, visual_dna: str = "") -> list[str]:
        if not story.strip() or not scenes:
            raise ValueError("Director requires a story and at least one scene")
        total = len(scenes)
        return [
            cls.visual_prompt(story, index, total, style, visual_dna)
            for index, _scene in enumerate(scenes, start=1)
        ]
