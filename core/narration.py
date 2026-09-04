"""Scene-aware narration planning for cinematic documentary projects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class NarrationSegment:
    """Narration assigned to one planned scene."""

    scene_id: str
    order: int
    duration_seconds: int
    text: str


class NarrationPlanner:
    """Create a deterministic first-pass narration script from scene plans.

    This is intentionally provider-agnostic: a future LLM Director can replace
    the text generation while keeping the same segment contract for TTS.
    """

    @staticmethod
    def build_segments(prompt: str, scenes: Sequence[object], content_type: str = "Documentary") -> list[NarrationSegment]:
        prompt = (prompt or "").strip()
        if not prompt:
            raise ValueError("Narration requires a non-empty prompt")
        if not scenes:
            raise ValueError("Narration requires at least one scene")
        if content_type not in {"Documentary", "Film"}:
            raise ValueError("Unsupported content type")

        segments: list[NarrationSegment] = []
        total = len(scenes)
        for index, scene in enumerate(scenes, start=1):
            scene_id = str(scene.scene_id)
            duration = int(scene.duration_seconds)
            if duration <= 0:
                raise ValueError("Scene duration must be positive")

            if content_type == "Documentary":
                if index == 1:
                    text = f"We begin our journey into {prompt}."
                elif index == total:
                    text = f"And this is where the story of {prompt} leaves us—with a deeper view of what makes it remarkable."
                else:
                    text = f"As the journey continues, we discover another side of {prompt}."
            else:
                if index == 1:
                    text = f"The story begins with {prompt}."
                elif index == total:
                    text = f"The journey reaches its final moment, revealing what {prompt} has become."
                else:
                    text = f"The story moves forward, uncovering another chapter of {prompt}."

            segments.append(NarrationSegment(scene_id, index, duration, text))
        return segments

    @staticmethod
    def join(segments: Sequence[NarrationSegment]) -> str:
        """Join scene narration into the single TTS track used by the renderer."""
        if not segments:
            raise ValueError("Cannot join an empty narration")
        return " ".join(segment.text for segment in segments)
