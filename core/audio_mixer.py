"""Cinematic audio timeline planning and FFmpeg filter construction."""

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class AudioClip:
    """An audio asset placed on the project timeline."""

    path: str
    start: float = 0.0
    volume: float = 1.0
    fade_in: float = 0.0
    fade_out: float = 0.0
    kind: str = "sfx"


@dataclass(frozen=True)
class AudioTimeline:
    """Resolved audio layers for a video project."""

    voice_over: Optional[AudioClip]
    music: Optional[AudioClip]
    sfx: Tuple[AudioClip, ...] = ()
    duration: Optional[float] = None


class AudioMixer:
    """Build deterministic FFmpeg audio-mixing commands."""

    VOICE_VOLUME = 1.0
    MUSIC_VOLUME = 0.18
    SFX_VOLUME = 0.55
    DUCKED_MUSIC_VOLUME = 0.06

    @staticmethod
    def build_timeline(
        *,
        voice_over: Optional[str] = None,
        music: Optional[str] = None,
        sfx: Sequence[AudioClip] = (),
        duration: Optional[float] = None,
    ) -> AudioTimeline:
        """Create a normalized project timeline from available audio assets."""
        voice = AudioClip(voice_over, volume=AudioMixer.VOICE_VOLUME, kind="voice") if voice_over else None
        music_clip = AudioClip(music, volume=AudioMixer.MUSIC_VOLUME, kind="music") if music else None
        normalized_sfx = tuple(
            AudioClip(
                clip.path,
                start=max(0.0, clip.start),
                volume=clip.volume if clip.volume > 0 else AudioMixer.SFX_VOLUME,
                fade_in=max(0.0, clip.fade_in),
                fade_out=max(0.0, clip.fade_out),
                kind="sfx",
            )
            for clip in sfx
        )
        return AudioTimeline(voice, music_clip, normalized_sfx, duration)

    @staticmethod
    def build_filter_complex(
        timeline: AudioTimeline,
        *,
        input_offset: int = 0,
    ) -> Tuple[str, str]:
        """Return FFmpeg filter_complex and final audio label.

        ``input_offset`` is the number of non-audio inputs that precede the
        audio files. A video input therefore uses offset=1.
        """
        clips: List[AudioClip] = []
        if timeline.voice_over:
            clips.append(timeline.voice_over)
        if timeline.music:
            clips.append(timeline.music)
        clips.extend(timeline.sfx)
        if not clips:
            raise ValueError("At least one audio clip is required")
        if input_offset < 0:
            raise ValueError("input_offset cannot be negative")

        filters: List[str] = []
        labels: List[str] = []
        has_voice = timeline.voice_over is not None

        for index, clip in enumerate(clips):
            input_index = index + input_offset
            label = f"a{index}"
            chain = [f"aresample=48000"]
            volume = clip.volume
            if clip.kind == "music" and has_voice:
                volume = AudioMixer.DUCKED_MUSIC_VOLUME
            chain.append(f"volume={volume:g}")
            if clip.start > 0:
                chain.append(f"adelay={int(round(clip.start * 1000))}:all=1")
            if clip.fade_in > 0:
                chain.append(f"afade=t=in:st={clip.start:g}:d={clip.fade_in:g}")
            if clip.fade_out > 0 and timeline.duration:
                fade_start = max(0.0, timeline.duration - clip.fade_out)
                chain.append(f"afade=t=out:st={fade_start:g}:d={clip.fade_out:g}")
            filters.append(f"[{input_index}:a]" + ",".join(chain) + f"[{label}]")
            labels.append(f"[{label}]")

        mix = "".join(labels) + f"amix=inputs={len(labels)}:duration=longest:dropout_transition=2,loudnorm=I=-16:TP=-1.5:LRA=11[outa]"
        filters.append(mix)
        return ";".join(filters), "[outa]"

    @staticmethod
    def build_ffmpeg_command(
        timeline: AudioTimeline,
        output_path: str,
        *,
        video_path: Optional[str] = None,
    ) -> List[str]:
        """Build an FFmpeg command for audio-only or video+audio output."""
        clips: List[AudioClip] = []
        if timeline.voice_over:
            clips.append(timeline.voice_over)
        if timeline.music:
            clips.append(timeline.music)
        clips.extend(timeline.sfx)
        if not clips:
            raise ValueError("At least one audio clip is required")

        command = ["ffmpeg"]
        if video_path:
            command += ["-i", video_path]
        for clip in clips:
            command += ["-i", clip.path]

        filter_complex, final_label = AudioMixer.build_filter_complex(
            timeline,
            input_offset=1 if video_path else 0,
        )
        command += ["-filter_complex", filter_complex, "-map", final_label]
        if video_path:
            command += ["-map", "0:v:0", "-c:v", "copy"]
        command += ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-y", output_path]
        return command
