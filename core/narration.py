"""Scene-aware narration planning for cinematic documentary projects."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from utils.errors import AudioProcessingError


@dataclass(frozen=True)
class NarrationSegment:
    """Narration assigned to one planned scene."""

    scene_id: str
    order: int
    duration_seconds: int
    text: str


@dataclass(frozen=True)
class NarrationAudioSegment:
    """Generated audio for one narration segment with measured duration."""

    segment: NarrationSegment
    path: str
    duration_seconds: float


class NarrationPlanner:
    """Create deterministic first-pass narration and audio timing."""

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
        if not segments:
            raise ValueError("Cannot join an empty narration")
        return " ".join(segment.text for segment in segments)


def probe_audio_duration(path: str) -> float:
    """Measure an audio file using ffprobe without decoding the complete file."""
    if not os.path.exists(path):
        raise AudioProcessingError(f"Audio file not found: {path}")
    command = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AudioProcessingError(f"Unable to measure audio duration: {result.stderr[:300]}")
    try:
        duration = float(result.stdout.strip())
    except ValueError as exc:
        raise AudioProcessingError(f"Invalid audio duration returned for {path}") from exc
    if duration <= 0:
        raise AudioProcessingError(f"Audio duration must be positive: {path}")
    return duration


def concatenate_audio_segments(segments: Sequence[NarrationAudioSegment], output_path: str) -> str:
    """Concatenate generated scene audio in order and return the final track path."""
    if not segments:
        raise AudioProcessingError("Cannot concatenate empty narration audio")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = output.with_suffix(".concat.txt")
    try:
        lines = []
        for item in segments:
            path = Path(item.path).resolve()
            if not path.exists():
                raise AudioProcessingError(f"Narration audio does not exist: {path}")
            safe_path = str(path).replace("'", "'\\''")
            lines.append(f"file '{safe_path}'")
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        command = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c:a", "libmp3lame", "-b:a", "128k", str(output)]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise AudioProcessingError(f"Narration concatenation failed: {result.stderr[:300]}")
        if not output.exists() or output.stat().st_size == 0:
            raise AudioProcessingError("Narration concatenation produced no audio")
        return str(output)
    finally:
        if manifest.exists():
            manifest.unlink()
