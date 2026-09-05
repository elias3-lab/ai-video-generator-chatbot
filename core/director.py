"""Deterministic cinematic Director layer for story beats and visual direction."""

from __future__ import annotations

import re
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
    """Turn a user idea into scene-specific cinematic direction.

    The important rule here is that every scene receives a different piece of
    the actual story content. The original request is treated as input data,
    not as a video prompt to repeat for every shot.
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
            "Hook": "establish the central subject and create immediate visual curiosity",
            "Journey": "move the story forward through a specific place, people, action, and context",
            "Discovery": "reveal a meaningful detail, contrast, tradition, or unexpected insight",
            "Ending": "resolve the visual journey with the final story subject and a memorable image",
        }
        pacing = {
            "Hook": "deliberate and intriguing",
            "Journey": "fluid and observational",
            "Discovery": "patient and intimate",
            "Ending": "reflective and conclusive",
        }
        return DirectorBeat(order, name, objectives[name], cls.CAMERAS[index], pacing[name])

    @staticmethod
    def _story_subjects(story: str) -> list[str]:
        text = re.sub(r"\s+", " ", (story or "").strip())
        if not text:
            return []

        # Prefer explicit visual content introduced by Show/Include/Featuring.
        match = re.search(r"(?i)\b(?:show|showing|include|including|featuring|cover)\s+(.+?)(?:\.|$)", text)
        if match:
            raw = match.group(1)
            parts = [p.strip(" .") for p in re.split(r",|\band\b", raw, flags=re.IGNORECASE)]
            subjects = [p for p in parts if p]
            if subjects:
                return subjects

        # Otherwise use the sentence after "about" as the main subject.
        match = re.search(r"(?i)\babout\s+(.+?)(?:\.|$)", text)
        if match:
            subject = match.group(1).strip(" .")
            if subject:
                return [subject]

        # Fallback: split ordinary sentences and ignore obvious production instructions.
        sentences = [s.strip(" .") for s in re.split(r"[.!?]", text) if s.strip()]
        blocked = re.compile(r"(?i)^(?:realistic|cinematic|natural lighting|consistent|smooth camera|english narration|voice-over|voiceover)")
        return [s for s in sentences if not blocked.search(s)] or [text]

    @classmethod
    def scene_subject(cls, story: str, order: int, total: int) -> str:
        subjects = cls._story_subjects(story)
        if not subjects:
            raise ValueError("Director requires story content")
        index = min(len(subjects) - 1, ((order - 1) * len(subjects)) // max(1, total))
        start = index
        end = min(len(subjects), ((order) * len(subjects) + total - 1) // max(1, total))
        selected = subjects[start:end] or [subjects[index]]
        return ", ".join(selected)

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
        subject = cls.scene_subject(story, order, total)
        dna = f" Visual DNA: {visual_dna.strip()}." if visual_dna.strip() else ""
        return (
            f"{beat.name} beat. {beat.objective}. Scene subject: {subject}. "
            f"{style.strip()}. {beat.camera}. Pacing: {beat.pacing}. "
            "Show only visuals directly related to the scene subject. "
            "Cinematic documentary realism, natural light, physically plausible motion, "
            "consistent geography and visual language, no unrelated locations, no unrelated people, "
            "no musicians unless the scene subject explicitly asks for them, no text, no logos, no watermarks."
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
