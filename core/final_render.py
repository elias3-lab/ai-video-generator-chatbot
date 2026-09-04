"""Final project rendering: normalize scenes, concatenate, and mix audio."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional, Sequence

from .audio_mixer import AudioClip, AudioMixer
from utils.errors import VideoProcessingError


class FinalRenderer:
    """Render completed scene videos into one consistent final MP4."""

    @staticmethod
    def _concat_scenes(scene_paths: Sequence[str], output_path: str, *, width: int = 1920, height: int = 1080) -> None:
        """Normalize mixed scene inputs and concatenate them with FFmpeg."""
        if not scene_paths:
            raise VideoProcessingError("No completed scene videos to render")
        if width <= 0 or height <= 0:
            raise VideoProcessingError("Final render dimensions must be positive")
        for path in scene_paths:
            if not os.path.exists(path):
                raise VideoProcessingError(f"Scene video does not exist: {path}")

        inputs: list[str] = []
        filter_parts: list[str] = []
        labels: list[str] = []
        for index, path in enumerate(scene_paths):
            inputs.extend(["-i", path])
            label = f"v{index}"
            labels.append(f"[{label}]")
            filter_parts.append(
                f"[{index}:v:0]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p,setpts=PTS-STARTPTS[{label}]"
            )
        filter_parts.append("".join(labels) + f"concat=n={len(scene_paths)}:v=1:a=0[vout]")

        command = ["ffmpeg", "-y"] + inputs + [
            "-filter_complex", ";".join(filter_parts), "-map", "[vout]", "-an",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", output_path,
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise VideoProcessingError(f"Scene concatenation failed: {result.stderr[:300]}")

    @staticmethod
    def _attach_subtitles(video_path: str, subtitles_path: str, output_path: str) -> None:
        """Mux an SRT file as a selectable MP4 subtitle track."""
        if not os.path.exists(subtitles_path):
            raise VideoProcessingError(f"Subtitle file does not exist: {subtitles_path}")
        command = [
            "ffmpeg", "-y", "-i", video_path, "-i", subtitles_path,
            "-map", "0:v:0", "-map", "0:a?", "-map", "1:0",
            "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text",
            "-metadata:s:s:0", "language=eng", output_path,
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise VideoProcessingError(f"Subtitle mux failed: {result.stderr[:300]}")

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
        except TypeError as exc:
            if "unexpected keyword argument 'width'" not in str(exc) and "unexpected keyword argument 'height'" not in str(exc):
                raise
            FinalRenderer._concat_scenes(scene_paths, video_only)

        if voice_over or music or sfx:
            timeline = AudioMixer.build_timeline(voice_over=voice_over, music=music, sfx=sfx, duration=duration)
            command = AudioMixer.build_ffmpeg_command(timeline, audio_video, video_path=video_only)
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                if os.path.exists(video_only):
                    os.remove(video_only)
                raise VideoProcessingError(f"Final audio render failed: {result.stderr[:300]}")
            source_for_subtitles = audio_video
        else:
            source_for_subtitles = video_only

        if subtitles_path:
            try:
                FinalRenderer._attach_subtitles(source_for_subtitles, subtitles_path, str(output))
            finally:
                for path in (video_only, audio_video):
                    if os.path.exists(path):
                        os.remove(path)
            return str(output)

        if source_for_subtitles != str(output):
            os.replace(source_for_subtitles, output)
        return str(output)
