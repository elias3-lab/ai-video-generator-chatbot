"""Scene-aware narration planning and measured audio timing."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from utils.errors import AudioProcessingError


@dataclass(frozen=True)
class NarrationSegment:
    scene_id: str
    order: int
    duration_seconds: float
    text: str


@dataclass(frozen=True)
class NarrationAudioSegment:
    segment: NarrationSegment
    path: str
    duration_seconds: float


class NarrationPlanner:
    """Create coherent documentary narration from story content, not metadata."""

    @staticmethod
    def _clean_story(prompt: str) -> str:
        text = re.sub(r"\s+", " ", (prompt or "").strip())
        text = re.sub(r"(?i),?\s*(realistic documentary style|natural lighting|consistent visual DNA|smooth cinematic camera movement|english narration|cinematic documentary|realistic style)\.?", "", text)
        text = re.sub(r"(?i)\s*(?:English narration|voice[- ]?over)\.?$", "", text)
        return text.strip(" .")

    @staticmethod
    def _subjects(story: str) -> list[str]:
        text = NarrationPlanner._clean_story(story)
        match = re.search(r"(?i)\b(?:show|showing|include|including|featuring|cover)\s+(.+?)(?:\.|$)", text)
        if not match:
            return [text] if text else []
        parts = [p.strip(" .") for p in re.split(r",|\band\b", match.group(1), flags=re.IGNORECASE)]
        return [p for p in parts if p]

    @staticmethod
    def _location(story: str) -> str:
        for name in ("Tunisia", "Tunis", "Sidi Bou Said", "Djerba", "Kairouan", "Carthage"):
            if re.search(rf"(?i)\b{re.escape(name)}\b", story or ""):
                return name
        return ""

    @classmethod
    def build_segments(cls, prompt: str, scenes: Sequence[object], content_type: str = "Documentary") -> list[NarrationSegment]:
        story = cls._clean_story(prompt)
        if not story:
            raise ValueError("Narration requires a non-empty story")
        if not scenes:
            raise ValueError("Narration requires at least one scene")
        if content_type not in {"Documentary", "Film"}:
            raise ValueError("Unsupported content type")

        subjects = cls._subjects(story) or [story]
        location = cls._location(story)
        segments: list[NarrationSegment] = []
        total = len(scenes)
        for index, scene in enumerate(scenes, start=1):
            scene_id = str(scene.scene_id)
            raw_duration = getattr(scene, "duration_seconds", None)
            if raw_duration is None:
                raw_duration = getattr(scene, "target_duration", None)
            if raw_duration is None:
                raise ValueError(f"Scene {scene_id} has no planned duration")
            duration = float(raw_duration)
            if duration <= 0:
                raise ValueError("Scene duration must be positive")

            n = len(subjects)
            start = ((index - 1) * n) // max(1, total)
            end = (index * n) // max(1, total)
            if index == total:
                end = n
            end = max(start + 1, min(n, end))
            subject = ", ".join(subjects[start:end])
            if location and not re.search(rf"(?i)\b{re.escape(location)}\b", subject):
                subject = f"{location}'s {subject}"

            if content_type == "Documentary":
                if index == 1:
                    text = f"Our journey begins in {location or 'this place'}, where {subject} reveals the character of the story." if location else f"Our journey begins with {subject}, revealing the character of the story."
                elif index == total:
                    text = f"We end with {subject}, a final glimpse that brings the journey into focus."
                else:
                    text = f"Along the way, {subject} reveals another side of this story, shaped by the people and places around it."
            else:
                if index == 1:
                    text = f"The story begins with {subject}, setting the journey in motion."
                elif index == total:
                    text = f"The journey closes with {subject}, bringing the story to its final moment."
                else:
                    text = f"The story moves forward through {subject}, carrying the journey into its next moment."
            segments.append(NarrationSegment(scene_id, index, duration, text))
        return segments

    @staticmethod
    def join(segments: Sequence[NarrationSegment]) -> str:
        if not segments:
            raise ValueError("Cannot join an empty narration")
        return " ".join(segment.text for segment in segments)


def probe_audio_duration(path: str) -> float:
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


def concatenate_audio_segments(segments: Sequence[NarrationAudioSegment], output_path: str, target_duration: float | None = None) -> str:
    if not segments:
        raise AudioProcessingError("Cannot concatenate empty narration audio")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = output.with_suffix(".concat.txt")
    wav_output = output.with_suffix(".wav")
    try:
        lines = []
        for item in segments:
            path = Path(item.path).resolve()
            if not path.exists():
                raise AudioProcessingError(f"Narration audio does not exist: {path}")
            safe_path = str(path).replace("'", "'\\''")
            lines.append(f"file '{safe_path}'")
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        command = ["ffmpeg", "-y", "-threads", "1", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c:a", "pcm_s16le", str(wav_output)]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise AudioProcessingError(f"Narration concatenation failed: {result.stderr[:300]}")
        if not wav_output.exists() or wav_output.stat().st_size == 0:
            raise AudioProcessingError("Narration concatenation produced no audio")
        final_command = ["ffmpeg", "-y", "-threads", "1", "-i", str(wav_output)]
        if target_duration is not None:
            final_command += ["-af", f"apad=pad_dur=0.15,atrim=duration={float(target_duration):g},asetpts=N/SR/TB"]
        final_command += ["-c:a", "libmp3lame", "-b:a", "160k", str(output)]
        result = subprocess.run(final_command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise AudioProcessingError(f"Narration finalization failed: {result.stderr[:300]}")
        if not output.exists() or output.stat().st_size == 0:
            raise AudioProcessingError("Narration finalization produced no audio")
        return str(output)
    finally:
        if manifest.exists():
            manifest.unlink()
        if wav_output.exists():
            wav_output.unlink()
