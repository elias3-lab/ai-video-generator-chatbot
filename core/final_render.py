"""Final project rendering: concatenate scenes and apply the audio timeline."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional, Sequence

from .audio_mixer import AudioClip, AudioMixer
from utils.errors import VideoProcessingError


class FinalRenderer:
    """Render completed scene videos into one final MP4 with mixed audio."""

    @staticmethod
    def _concat_scenes(scene_paths: Sequence[str], output_path: str) -> None:
        if not scene_paths:
            raise VideoProcessingError("No completed scene videos to render")
        concat_file = f"{output_path}.concat.txt"
        try:
            with open(concat_file, "w", encoding="utf-8") as handle:
                for path in scene_paths:
                    if not os.path.exists(path):
                        raise VideoProcessingError(f"Scene video does not exist: {path}")
                    handle.write(f"file '{os.path.abspath(path)}'\n")
            result = subprocess.run(
                ["ffmpeg", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", "-y", output_path],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise VideoProcessingError(f"Scene concatenation failed: {result.stderr[:300]}")
        finally:
            if os.path.exists(concat_file):
                os.remove(concat_file)

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
            raise VideoProcessingError(f"Final audio render failed: {result.stderr[:300]}")
        if os.path.exists(video_only):
            os.remove(video_only)
        return str(output)
