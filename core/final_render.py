"""Final project rendering: normalize scenes, concatenate, and mix audio."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional, Sequence

from .audio_mixer import AudioClip, AudioMixer
from utils.errors import VideoProcessingError

LOGGER = logging.getLogger(__name__)


class FinalRenderer:
    """Render completed scene videos into one consistent final MP4."""

    @staticmethod
    def _run_ffmpeg(command: list[str], stage: str) -> subprocess.CompletedProcess[str]:
        LOGGER.info("Final render stage started: %s", stage)
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "FFmpeg returned no diagnostic output").strip()
            LOGGER.error("Final render stage failed: %s: %s", stage, detail[:1200])
            raise VideoProcessingError(f"{stage} failed: {detail[:500]}")
        LOGGER.info("Final render stage completed: %s", stage)
        return result

    @staticmethod
    def _normalize_scene(path: str, output_path: str, *, width: int, height: int, index: int, total: int) -> None:
        if not os.path.exists(path):
            raise VideoProcessingError(f"Scene video does not exist: {path}")
        LOGGER.info("Normalizing scene %s/%s: %s", index, total, path)
        command = [
            "ffmpeg", "-y", "-threads", "1", "-i", path,
            "-vf", (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p,setpts=PTS-STARTPTS"
            ),
            "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", output_path,
        ]
        FinalRenderer._run_ffmpeg(command, f"Scene {index}/{total} normalization")
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise VideoProcessingError(f"Scene {index} normalization produced no output")

    @staticmethod
    def _concat_scenes(scene_paths: Sequence[str], output_path: str, *, width: int = 1920, height: int = 1080) -> None:
        """Normalize scenes one at a time, then concatenate by stream copy.

        The previous implementation decoded every scene simultaneously through one
        large filter graph. That is unnecessarily memory-hungry on Render's small
        free instance and could terminate the process during final rendering.
        """
        if not scene_paths:
            raise VideoProcessingError("No completed scene videos to render")
        if width <= 0 or height <= 0:
            raise VideoProcessingError("Final render dimensions must be positive")

        output = Path(output_path)
        work_dir = output.parent / f".{output.stem}_scene_cache"
        work_dir.mkdir(parents=True, exist_ok=True)
        normalized: list[str] = []
        try:
            total = len(scene_paths)
            for index, path in enumerate(scene_paths, start=1):
                normalized_path = work_dir / f"scene_{index:03d}.mp4"
                FinalRenderer._normalize_scene(path, str(normalized_path), width=width, height=height, index=index, total=total)
                normalized.append(str(normalized_path))

            concat_list = work_dir / "concat.txt"
            with concat_list.open("w", encoding="utf-8") as handle:
                for path in normalized:
                    safe_path = Path(path).resolve().as_posix().replace("'", "'\\''")
                    handle.write(f"file '{safe_path}'\n")

            command = [
                "ffmpeg", "-y", "-threads", "1", "-f", "concat", "-safe", "0",
                "-i", str(concat_list), "-an", "-c", "copy", "-movflags", "+faststart", output_path,
            ]
            FinalRenderer._run_ffmpeg(command, "Scene concatenation")
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                raise VideoProcessingError("Scene concatenation produced no video output")
        finally:
            for path in normalized:
                try:
                    os.remove(path)
                except OSError:
                    pass
            try:
                (work_dir / "concat.txt").unlink(missing_ok=True)
                work_dir.rmdir()
            except OSError:
                LOGGER.warning("Could not fully clean scene cache: %s", work_dir)

    @staticmethod
    def _attach_subtitles(video_path: str, subtitles_path: str, output_path: str) -> None:
        """Mux an SRT file as a selectable MP4 subtitle track."""
        if not os.path.exists(subtitles_path):
            raise VideoProcessingError(f"Subtitle file does not exist: {subtitles_path}")
        command = [
            "ffmpeg", "-y", "-threads", "1", "-i", video_path, "-i", subtitles_path,
            "-map", "0:v:0", "-map", "0:a?", "-map", "1:0",
            "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text",
            "-metadata:s:s:0", "language=eng", "-movflags", "+faststart", output_path,
        ]
        FinalRenderer._run_ffmpeg(command, "Subtitle attachment")
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise VideoProcessingError("Subtitle attachment produced no final video")

    @staticmethod
    def render(
        scene_paths: Sequence[str], output_path: str, *, voice_over: Optional[str] = None,
        music: Optional[str] = None, sfx: Sequence[AudioClip] = (), duration: Optional[float] = None,
        width: int = 1920, height: int = 1080, subtitles_path: Optional[str] = None,
    ) -> str:
        """Concatenate scenes, mix audio, then optionally attach subtitles."""
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        video_only = str(output.with_name(output.stem + ".video.mp4"))
        audio_video = str(output.with_name(output.stem + ".audio.mp4"))
        try:
            FinalRenderer._concat_scenes(scene_paths, video_only, width=width, height=height)

            if voice_over or music or sfx:
                timeline = AudioMixer.build_timeline(voice_over=voice_over, music=music, sfx=sfx, duration=duration)
                command = AudioMixer.build_ffmpeg_command(timeline, audio_video, video_path=video_only)
                command[1:1] = ["-threads", "1"]
                FinalRenderer._run_ffmpeg(command, "Audio mix")
                source_for_subtitles = audio_video
            else:
                source_for_subtitles = video_only

            if subtitles_path:
                FinalRenderer._attach_subtitles(source_for_subtitles, subtitles_path, str(output))
            else:
                if source_for_subtitles != str(output):
                    os.replace(source_for_subtitles, output)

            if not output.exists() or output.stat().st_size == 0:
                raise VideoProcessingError("Final render produced no MP4")
            LOGGER.info("Final MP4 completed: path=%s bytes=%s", output, output.stat().st_size)
            return str(output)
        finally:
            for path in (video_only, audio_video):
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        LOGGER.warning("Could not remove temporary render file: %s", path)
