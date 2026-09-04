"""Subtitle planning from scene-aware narration segments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from core.narration import NarrationSegment


@dataclass(frozen=True)
class SubtitleCue:
    """One subtitle cue positioned on the planned scene timeline."""

    index: int
    start: float
    end: float
    text: str


class SubtitlePlanner:
    """Create deterministic SRT cues without requiring speech recognition."""

    @staticmethod
    def build_cues(segments: Sequence[NarrationSegment]) -> list[SubtitleCue]:
        if not segments:
            raise ValueError("Subtitles require at least one narration segment")

        cues: list[SubtitleCue] = []
        cursor = 0.0
        for index, segment in enumerate(segments, start=1):
            duration = float(segment.duration_seconds)
            if duration <= 0:
                raise ValueError("Narration segment duration must be positive")
            text = segment.text.strip()
            if not text:
                raise ValueError("Subtitle text cannot be empty")
            cues.append(SubtitleCue(index, cursor, cursor + duration, text))
            cursor += duration
        return cues

    @staticmethod
    def _timestamp(seconds: float) -> str:
        total_ms = max(0, int(round(seconds * 1000)))
        hours, remainder = divmod(total_ms, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        secs, millis = divmod(remainder, 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    @classmethod
    def to_srt(cls, cues: Sequence[SubtitleCue]) -> str:
        if not cues:
            raise ValueError("Cannot render empty subtitle cues")
        blocks = []
        for cue in cues:
            blocks.append(
                f"{cue.index}\n"
                f"{cls._timestamp(cue.start)} --> {cls._timestamp(cue.end)}\n"
                f"{cue.text}\n"
            )
        return "\n".join(blocks)
