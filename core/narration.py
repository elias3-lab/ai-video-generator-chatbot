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
                    text = f"Our journey begins in {location or 'this place'}, where {subject} opens a window onto the character of the story."
                elif index == total:
                    text = f"And as the journey comes to a close, {subject} leaves us with a final glimpse of what makes this place unforgettable."
                else:
                    text = f"Moving deeper into the journey, we discover {subject}, where everyday details reveal another side of this story."
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
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
    if result.returncode != 0:
        raise AudioProcessingError(f"Unable to measure audio duration: {result.stderr[:500]}")
    try:
        duration = float(result.stdout.strip())
    except ValueError as exc:
        raise AudioProcessingError(f"Invalid audio duration returned for {path}: {result.stdout[:200]}") from exc
    if duration <= 0:
        raise AudioProcessingError(f"Audio duration must be positive: {path}")
    return duration


def concatenate_audio_segments(segments: Sequence[NarrationAudioSegment], output_path: str, target_duration: float | None = None) -> str:
    if not segments:
        raise AudioProcessingError("Cannot concatenate empty narration audio")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    wav_output = output.with_suffix(".wav")
    try:
        # Normalize every TTS file to a conservative PCM WAV format. Keep this
        # command deliberately simple: some TTS WAV headers are unusual, and
        # complex filters can make FFmpeg reject an otherwise valid file.
        normalized: list[str] = []
        for index, item in enumerate(segments, start=1):
            path = Path(item.path).resolve()
            if not path.exists():
                raise AudioProcessingError(f"Narration audio does not exist: {path}")
            if path.stat().st_size == 0:
                raise AudioProcessingError(f"Narration audio is empty: {path}")
            # Validate the source before attempting conversion so the real
            # filename and FFmpeg diagnostic are preserved in the error.
            try:
                source_duration = probe_audio_duration(str(path))
            except Exception as exc:
                raise AudioProcessingError(f"Narration source validation failed for {path}: {exc}") from exc
            if source_duration <= 0:
                raise AudioProcessingError(f"Narration source has invalid duration: {path}")

            normalized_path = output.with_name(f"{output.stem}_narr_{index:03d}.wav")
            normalize = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-threads", "1",
                "-i", str(path), "-vn", "-ac", "1", "-ar", "48000",
                "-c:a", "pcm_s16le", str(normalized_path),
            ]
            try:
                result = subprocess.run(normalize, capture_output=True, text=True, check=False, timeout=120)
            except subprocess.TimeoutExpired as exc:
                raise AudioProcessingError(f"Narration normalization timed out for {path}") from exc
            if result.returncode != 0 or not normalized_path.exists() or normalized_path.stat().st_size == 0:
                detail = (result.stderr or result.stdout or "FFmpeg returned no diagnostic output").strip()
                raise AudioProcessingError(f"Narration normalization failed for {path}: {detail[:1000]}")
            normalized.append(str(normalized_path))

        # Crossfade short overlaps between narration segments so scene changes
        # sound continuous instead of like unrelated recordings.
        current = normalized[0]
        for index, next_path in enumerate(normalized[1:], start=1):
            merged = output.with_name(f"{output.stem}_cross_{index:03d}.wav")
            command = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-threads", "1",
                "-i", current, "-i", next_path,
                "-filter_complex", "[0:a][1:a]acrossfade=d=0.12:c1=tri:c2=tri[a]",
                "-map", "[a]", "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(merged),
            ]
            try:
                result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=120)
            except subprocess.TimeoutExpired as exc:
                raise AudioProcessingError(f"Narration crossfade timed out at segment {index + 1}") from exc
            if result.returncode != 0 or not merged.exists() or merged.stat().st_size == 0:
                detail = (result.stderr or result.stdout or "FFmpeg returned no diagnostic output").strip()
                raise AudioProcessingError(f"Narration crossfade failed at segment {index + 1}: {detail[:1000]}")
            Path(current).unlink(missing_ok=True)
            current = str(merged)

        final_command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-threads", "1", "-i", current]
        if target_duration is not None:
            final_command += ["-af", f"apad=pad_dur=0.15,atrim=duration={float(target_duration):g},asetpts=N/SR/TB"]
        final_command += ["-vn", "-ac", "2", "-ar", "48000", "-c:a", "libmp3lame", "-b:a", "192k", str(output)]
        try:
            result = subprocess.run(final_command, capture_output=True, text=True, check=False, timeout=120)
        except subprocess.TimeoutExpired as exc:
            raise AudioProcessingError("Narration finalization timed out") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "FFmpeg returned no diagnostic output").strip()
            raise AudioProcessingError(f"Narration finalization failed: {detail[:1000]}")
        if not output.exists() or output.stat().st_size == 0:
            raise AudioProcessingError("Narration finalization produced no audio")
        return str(output)
    finally:
        for candidate in output.parent.glob(f"{output.stem}_narr_*.wav"):
            candidate.unlink(missing_ok=True)
        for candidate in output.parent.glob(f"{output.stem}_cross_*.wav"):
            candidate.unlink(missing_ok=True)
        if wav_output.exists():
            wav_output.unlink()
