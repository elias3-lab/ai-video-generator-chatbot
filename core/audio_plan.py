"""Deterministic scene-aware planning for cinematic music and sound effects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from core.audio_mixer import AudioClip
from core.scene_planner import ScenePlan


@dataclass(frozen=True)
class AudioCue:
    """A semantic cue that can later be resolved to a real audio asset."""

    scene_id: str
    start: float
    duration: float
    kind: str
    mood: str
    description: str
    volume: float


class AudioPlanner:
    """Create stable music/SFX cues from the existing scene timeline."""

    @staticmethod
    def build_cues(scenes: Sequence[ScenePlan], *, content_type: str = "Documentary") -> list[AudioCue]:
        if not scenes:
            raise ValueError("At least one scene is required")
        if content_type not in {"Documentary", "Film"}:
            raise ValueError("content_type must be Documentary or Film")

        cues: list[AudioCue] = []
        cursor = 0.0
        last_index = len(scenes) - 1
        for index, scene in enumerate(scenes):
            if index == 0:
                mood = "curious" if content_type == "Documentary" else "anticipation"
                description = "opening atmosphere"
            elif index == last_index:
                mood = "reflective" if content_type == "Documentary" else "resolution"
                description = "closing atmosphere"
            else:
                mood = "discovery" if content_type == "Documentary" else "forward motion"
                description = "transition atmosphere"

            cues.append(
                AudioCue(
                    scene_id=scene.scene_id,
                    start=cursor,
                    duration=float(scene.duration_seconds),
                    kind="music",
                    mood=mood,
                    description=description,
                    volume=0.18,
                )
            )
            if index > 0:
                cues.append(
                    AudioCue(
                        scene_id=scene.scene_id,
                        start=cursor,
                        duration=min(1.5, float(scene.duration_seconds)),
                        kind="sfx",
                        mood=mood,
                        description="subtle scene transition",
                        volume=0.55,
                    )
                )
            cursor += float(scene.duration_seconds)
        return cues

    @staticmethod
    def music_cues(cues: Sequence[AudioCue]) -> list[AudioCue]:
        return [cue for cue in cues if cue.kind == "music"]

    @staticmethod
    def sfx_cues(cues: Sequence[AudioCue]) -> list[AudioCue]:
        return [cue for cue in cues if cue.kind == "sfx"]

    @staticmethod
    def to_mixer_sfx(cues: Sequence[AudioCue], *, asset_paths: dict[str, str]) -> tuple[AudioClip, ...]:
        """Resolve semantic SFX cues to local assets without requiring an API."""
        clips: list[AudioClip] = []
        for cue in AudioPlanner.sfx_cues(cues):
            path = asset_paths.get(cue.description)
            if not path:
                continue
            clips.append(AudioClip(path=path, start=cue.start, volume=cue.volume, fade_in=0.05, fade_out=0.15, kind="sfx"))
        return tuple(clips)
