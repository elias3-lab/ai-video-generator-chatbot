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
    def _concat_scenes(scene_paths: Sequence[str], output_path: str) -> None:
        """Normalize mixed scene inputs and concatenate them with FFmpeg."""
        if not scene_paths:
            raise VideoProcessingError("No completed scene videos to render")
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
                f"[{index}:v:0]scale=1920:1080:force_original_aspect_ratio=decrease,"
                f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p,setpts=PTS-STARTPTS[{label}]"
            )
        filter_parts.append("".join(labels) + f"concat=n={len(scene_paths)}:v=1:a=0[vout]")

        command = ["ffmpeg", "-y"] + inputs + [
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "[vout]",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            output_path,
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise VideoProcessingError(f"Scene concatenation failed: {result.stderr[:300]}")

    @staticmethod
    def render(
        scene_paths: Sequence[str],
        output_path: str,
        *,
        voice_over: Optional[str] = None,
        music: Optional[str] = None,
        sfx: Sequence[AudioClip] = (),
        duration: Optional[float] = None,
    ) -> str:
        """Concatenate scenes, then optionally mix VO/music/SFX into the final MP4."""
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        video_only = str(output.with_name(output.stem + ".video.mp4"))
        FinalRenderer._concat_scenes(scene_paths, video_only)

        if not voice_over and not music and not sfx:
            os.replace(video_only, output)
            return str(output)

        timeline = AudioMixer.build_timeline(
            voice_over=voice_over,
            music=music,
            sfx=sfx,
            duration=duration,
        )
        command = AudioMixer.build_ffmpeg_command(timeline, str(output), video_path=video_only)
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            if os.path.exists(video_only):
                os.remove(video_only)
            raise VideoProcessingError(f"Final audio render failed: {result.stderr[:300]}")
        if os.path.exists(video_only):
            os.remove(video_only)
        return str(output)
