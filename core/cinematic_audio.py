"""Always-available cinematic music and transition SFX generated locally with FFmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .audio_mixer import AudioClip
from utils.errors import VideoProcessingError


class CinematicAudioGenerator:
    """Generate a royalty-free ambient bed and subtle transition effects without an external API."""

    @staticmethod
    def _run(command: list[str], output: Path) -> str:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0 or not output.exists() or output.stat().st_size == 0:
            detail = result.stderr.strip()[-800:]
            raise VideoProcessingError(f"Cinematic audio generation failed: {detail}")
        return str(output)

    @classmethod
    def generate_music(cls, output_path: str | Path, duration: float) -> str:
        """Create a restrained cinematic ambient soundtrack for the exact project duration."""
        if duration <= 0:
            raise ValueError("duration must be positive")
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        duration_text = f"{duration:g}"
        # Layer low drones and gentle upper harmonics; keep the bed deliberately quiet
        # because AudioMixer ducks it further under narration.
        sources = [
            ("55", "0.12"),
            ("82.41", "0.08"),
            ("110", "0.06"),
            ("164.81", "0.035"),
        ]
        inputs: list[str] = []
        filters: list[str] = []
        labels: list[str] = []
        for index, (frequency, volume) in enumerate(sources):
            inputs += ["-f", "lavfi", "-i", f"sine=frequency={frequency}:duration={duration_text}:sample_rate=48000"]
            label = f"m{index}"
            labels.append(f"[{label}]")
            filters.append(f"[{index}:a]volume={volume},lowpass=f=1800,asetpts=PTS-STARTPTS[{label}]")
        filters.append("".join(labels) + f"amix=inputs={len(labels)}:duration=longest:dropout_transition=3,"
                       f"afade=t=in:d=2,afade=t=out:st={max(0.0, duration - 3):g}:d=3,loudnorm=I=-24:TP=-2:LRA=7[out]")
        command = ["ffmpeg", "-y"] + inputs + [
            "-filter_complex", ";".join(filters), "-map", "[out]",
            "-c:a", "libmp3lame", "-b:a", "128k", str(output),
        ]
        return cls._run(command, output)

    @classmethod
    def generate_transition_sfx(cls, output_path: str | Path) -> str:
        """Create a short non-verbal cinematic whoosh used between scenes."""
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        expression = "0.18*sin(2*PI*(220+700*t)*t)*exp(-2.8*t)"
        command = [
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            f"aevalsrc={expression}:duration=1.2:sample_rate=48000",
            "-af", "loudnorm=I=-28:TP=-3:LRA=7",
            "-c:a", "libmp3lame", "-b:a", "96k", str(output),
        ]
        return cls._run(command, output)

    @classmethod
    def build_default_layers(
        cls, output_dir: str | Path, duration: float, scene_count: int,
    ) -> tuple[str, tuple[AudioClip, ...]]:
        """Return a guaranteed music bed and scene-transition SFX clips."""
        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)
        music = cls.generate_music(root / "cinematic_music.mp3", duration)
        if scene_count < 2:
            return music, ()
        sfx_path = cls.generate_transition_sfx(root / "scene_transition.mp3")
        spacing = duration / scene_count
        clips = tuple(
            AudioClip(path=sfx_path, start=max(0.0, spacing * index), volume=0.32,
                      fade_in=0.02, fade_out=0.18, kind="sfx")
            for index in range(1, scene_count)
        )
        return music, clips
