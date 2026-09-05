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
    """Turn a user idea into scene-specific cinematic direction."""

    BEATS = ("Hook", "Journey", "Discovery", "Ending")
    CAMERAS = (
        "wide establishing shot, 24mm lens, slow push-in",
        "medium tracking shot, 35mm lens, controlled handheld movement",
        "intimate detail shot, 50mm lens, shallow depth of field",
        "wide closing composition, 35mm lens, slow pull-back",
    )
    ACTIONS = (
        "begin with a living environment and visible activity; the camera observes the place rather than circling one person",
        "follow a clear human or environmental action from beginning to end, with foreground, middle ground, and background movement",
        "focus on a meaningful physical detail or craft process, showing hands, tools, textures, and the surrounding place in motion",
        "resolve the journey with a changing landscape or people naturally moving through the environment; end on a memorable visual beat",
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
    def _clean(text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip()).strip(" .")

    @classmethod
    def _location_anchor(cls, story: str) -> str:
        text = cls._clean(story)
        match = re.search(r"(?i)\babout\s+the\s+(.+?)(?:\.|$)", text)
        if match:
            subject = match.group(1).strip()
            location_words = re.findall(
                r"(?i)\b(?:Tunisia|Tunis|Sidi Bou Said|Djerba|Kairouan|Carthage|Mediterranean|Morocco|Egypt|Algeria|Turkey|India|Japan|Italy|France|Spain|Portugal|Greece)\b",
                subject,
            )
            if location_words:
                return location_words[0]
        for name in ("Tunisia", "Tunis", "Sidi Bou Said", "Djerba", "Kairouan", "Carthage"):
            if re.search(rf"(?i)\b{re.escape(name)}\b", text):
                return name
        return ""

    @classmethod
    def _story_subjects(cls, story: str) -> list[str]:
        text = cls._clean(story)
        if not text:
            return []
        match = re.search(r"(?i)\b(?:show|showing|include|including|featuring|cover)\s+(.+?)(?:\.|$)", text)
        if match:
            raw = match.group(1)
            parts = [p.strip(" .") for p in re.split(r",|\band\b", raw, flags=re.IGNORECASE)]
            subjects = [p for p in parts if p]
            if subjects:
                return subjects
        match = re.search(r"(?i)\babout\s+(.+?)(?:\.|$)", text)
        if match:
            subject = match.group(1).strip(" .")
            if subject:
                return [subject]
        sentences = [s.strip(" .") for s in re.split(r"[.!?]", text) if s.strip()]
        blocked = re.compile(r"(?i)^(?:realistic|cinematic|natural lighting|consistent|smooth camera|english narration|voice-over|voiceover)")
        return [s for s in sentences if not blocked.search(s)] or [text]

    @classmethod
    def scene_subject(cls, story: str, order: int, total: int) -> str:
        subjects = cls._story_subjects(story)
        if not subjects:
            raise ValueError("Director requires story content")
        n = len(subjects)
        start = ((order - 1) * n) // max(1, total)
        end = (order * n) // max(1, total)
        if order == total:
            end = n
        end = max(start + 1, min(n, end))
        selected = subjects[start:end]
        anchor = cls._location_anchor(story)
        if anchor and not re.search(rf"(?i)\b{re.escape(anchor)}\b", ", ".join(selected)):
            return f"{anchor}: {', '.join(selected)}"
        return ", ".join(selected)

    @classmethod
    def visual_prompt(cls, story: str, order: int, total: int, style: str, visual_dna: str = "") -> str:
        beat = cls.beat_for(order, total)
        subject = cls.scene_subject(story, order, total)
        anchor = cls._location_anchor(story)
        location = f" Location anchor: {anchor}." if anchor else ""
        dna = f" Visual DNA: {visual_dna.strip()}." if visual_dna.strip() else ""
        action = cls.ACTIONS[3 if beat.name == "Ending" else 2 if beat.name == "Discovery" else 1 if beat.name == "Journey" else 0]
        return (
            f"{beat.name} beat. {beat.objective}. Scene subject: {subject}."
            f"{location} {style.strip()}. {beat.camera}. Pacing: {beat.pacing}. "
            f"Action direction: {action}. "
            "Create a genuine moving documentary shot, not a still image or slideshow. "
            "The shot must contain purposeful camera movement AND meaningful subject/environment movement. "
            "Vary composition from previous scenes; do not repeat the same people, group arrangement, or camera orbit. "
            "Never make the whole shot consist of three people standing together while the camera circles them. "
            "Show only visuals directly related to the scene subject and location anchor. "
            "Cinematic documentary realism, natural light, physically plausible motion, authentic local architecture and culture, "
            "no unrelated locations, no unrelated countries, no unrelated people, no generic stock-looking scene, "
            "no musicians unless explicitly requested, no text, no logos, no watermarks."
            f"{dna}"
        )

    @classmethod
    def build_storyboard(cls, story: str, scenes: Sequence[object], style: str, visual_dna: str = "") -> list[str]:
        if not story.strip() or not scenes:
            raise ValueError("Director requires a story and at least one scene")
        total = len(scenes)
        return [cls.visual_prompt(story, index, total, style, visual_dna) for index, _scene in enumerate(scenes, start=1)]
