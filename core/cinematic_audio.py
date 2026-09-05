"""Always-available cinematic music and transition SFX generated locally with FFmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .audio_mixer import AudioClip
from utils.errors import VideoProcessingError


class CinematicAudioGenerator:
    """Generate a richer ambient score and subtle transition effects locally."""

    @staticmethod
    def _run(command: list[str], output: Path) -> str:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0 or not output.exists() or output.stat().st_size == 0:
            detail = result.stderr.strip()[-800:]
            raise VideoProcessingError(f"Cinematic audio generation failed: {detail}")
        return str(output)

    @classmethod
    def generate_music(cls, output_path: str | Path, duration: float) -> str:
        """Create a warm four-chord documentary score for the exact duration."""
        if duration <= 0:
            raise ValueError("duration must be positive")
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        quarter = duration / 4.0
        chords = (
            (110.0, 164.81, 220.0, 329.63),
            (87.31, 130.81, 174.61, 261.63),
            (65.41, 98.00, 130.81, 196.00),
            (98.00, 146.83, 196.00, 293.66),
        )
        parts: list[str] = []
        for chord in chords:
            inputs: list[str] = []
            filters: list[str] = []
            labels: list[str] = []
            for index, frequency in enumerate(chord):
                inputs += ["-f", "lavfi", "-i", f"sine=frequency={frequency:g}:duration={quarter:g}:sample_rate=48000"]
                label = f"c{len(parts)}_{index}"
                labels.append(f"[{label}]")
                filters.append(
                    f"[{index}:a]volume=0.055,lowpass=f=3200,"
                    f"tremolo=f=0.09:d=0.18,asetpts=PTS-STARTPTS[{label}]"
                )
            filters.append("".join(labels) + f"amix=inputs=4:duration=longest:dropout_transition=1,afade=t=in:d=0.8,afade=t=out:st={max(0.0, quarter-1.0):g}:d=1.0[out]")
            part_path = output.with_name(f"{output.stem}_part{len(parts)+1}.wav")
            command = ["ffmpeg", "-y"] + inputs + ["-filter_complex", ";".join(filters), "-map", "[out]", "-c:a", "pcm_s16le", str(part_path)]
            cls._run(command, part_path)
            parts.append(str(part_path))

        manifest = output.with_suffix(".music.txt")
        try:
            manifest.write_text("".join(f"file '{Path(p).resolve().as_posix()}'\n" for p in parts), encoding="utf-8")
            command = ["ffmpeg", "-y", "-threads", "1", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c:a", "libmp3lame", "-b:a", "192k", str(output)]
            return cls._run(command, output)
        finally:
            manifest.unlink(missing_ok=True)
            for part in parts:
                Path(part).unlink(missing_ok=True)

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
    def build_default_layers(cls, output_dir: str | Path, duration: float, scene_count: int) -> tuple[str, tuple[AudioClip, ...]]:
        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)
        music = cls.generate_music(root / "cinematic_music.mp3", duration)
        if scene_count < 2:
            return music, ()
        sfx_path = cls.generate_transition_sfx(root / "scene_transition.mp3")
        spacing = duration / scene_count
        clips = tuple(
            AudioClip(path=sfx_path, start=max(0.0, spacing * index), volume=0.18, fade_in=0.02, fade_out=0.18, kind="sfx")
            for index in range(1, scene_count)
        )
        return music, clips
