"""Deterministic scene planning and duration segmentation.

Long projects are represented as multiple short scenes. The global
MAX_VIDEO_DURATION remains the maximum duration of a single generated segment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


SUPPORTED_DURATIONS = {30: "30s", 180: "3 min", 240: "4 min", 300: "5 min"}


@dataclass(frozen=True)
class ScenePlan:
    scene_id: str
    duration_seconds: int
    order: int
    purpose: str


def validate_target_duration(duration_seconds: int) -> int:
    """Validate one of the supported Create Video durations."""
    if duration_seconds not in SUPPORTED_DURATIONS:
        raise ValueError(
            "Unsupported duration. Choose 30s, 3 min, 4 min, or 5 min."
        )
    return duration_seconds


def plan_scenes(
    duration_seconds: int,
    *,
    max_segment_duration: int = 120,
    preferred_scene_duration: int = 10,
) -> List[ScenePlan]:
    """Split a project into renderable scenes without exceeding segment limits.

    The planner favors ~10-second scenes for cinematic editing while allowing
    the final scene to be shorter. No individual scene can exceed the global
    generation limit passed by the caller.
    """
    validate_target_duration(duration_seconds)
    if max_segment_duration <= 0 or preferred_scene_duration <= 0:
        raise ValueError("Scene duration limits must be positive")
    if preferred_scene_duration > max_segment_duration:
        preferred_scene_duration = max_segment_duration

    scenes: List[ScenePlan] = []
    remaining = duration_seconds
    order = 1
    while remaining > 0:
        duration = min(preferred_scene_duration, max_segment_duration, remaining)
        scenes.append(
            ScenePlan(
                scene_id=f"scene_{order:03d}",
                duration_seconds=duration,
                order=order,
                purpose="story beat",
            )
        )
        remaining -= duration
        order += 1
    return scenes
