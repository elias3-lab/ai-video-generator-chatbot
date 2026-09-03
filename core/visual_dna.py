"""Visual DNA and continuity state shared across documentary scenes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Iterable, Optional


@dataclass(frozen=True)
class VisualDNA:
    """Stable visual constraints that should be injected into every scene."""

    style: str = "cinematic documentary, realistic, natural light"
    camera_language: str = "consistent cinematic camera language"
    color_language: str = "natural cinematic color grade"
    aspect_ratio: str = "16:9"
    characters: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    wardrobe: tuple[str, ...] = ()
    recurring_objects: tuple[str, ...] = ()
    negative_constraints: tuple[str, ...] = ()

    def prompt_prefix(self) -> str:
        parts = [self.style, self.camera_language, self.color_language]
        if self.characters:
            parts.append("Characters: " + "; ".join(self.characters))
        if self.locations:
            parts.append("Locations: " + "; ".join(self.locations))
        if self.wardrobe:
            parts.append("Wardrobe: " + "; ".join(self.wardrobe))
        if self.recurring_objects:
            parts.append("Recurring objects: " + "; ".join(self.recurring_objects))
        if self.negative_constraints:
            parts.append("Avoid: " + "; ".join(self.negative_constraints))
        return ". ".join(parts) + "."

    def stable_id(self) -> str:
        """Return a deterministic ID for this exact Visual DNA configuration."""
        payload = {
            "style": self.style,
            "camera_language": self.camera_language,
            "color_language": self.color_language,
            "aspect_ratio": self.aspect_ratio,
            "characters": self.characters,
            "locations": self.locations,
            "wardrobe": self.wardrobe,
            "recurring_objects": self.recurring_objects,
            "negative_constraints": self.negative_constraints,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class ContinuityState:
    """Project-level continuity memory updated after successful scenes."""

    dna: VisualDNA
    completed_scene_ids: list[str] = field(default_factory=list)
    last_location: Optional[str] = None
    active_characters: tuple[str, ...] = ()

    def context_for_scene(self, scene_prompt: str) -> str:
        continuity = []
        if self.last_location:
            continuity.append(f"Continue from location: {self.last_location}")
        if self.active_characters:
            continuity.append("Keep characters consistent: " + "; ".join(self.active_characters))
        base = self.dna.prompt_prefix()
        return base + (" " + " ".join(continuity) if continuity else "") + f" Scene: {scene_prompt}"

    def mark_completed(
        self,
        scene_id: str,
        *,
        location: Optional[str] = None,
        characters: Optional[Iterable[str]] = None,
    ) -> None:
        if scene_id not in self.completed_scene_ids:
            self.completed_scene_ids.append(scene_id)
        if location:
            self.last_location = location
        if characters:
            self.active_characters = tuple(dict.fromkeys(characters))
