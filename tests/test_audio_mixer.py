from core.audio_mixer import AudioClip, AudioMixer


def test_audio_timeline_uses_cinematic_default_levels():
    timeline = AudioMixer.build_timeline(
        voice_over="voice.mp3",
        music="music.mp3",
        sfx=(AudioClip("impact.wav", start=12, volume=0.7),),
        duration=30,
    )

    assert timeline.voice_over.volume == 1.0
    assert timeline.music.volume == 0.18
    assert timeline.sfx[0].start == 12
    assert timeline.sfx[0].volume == 0.7


def test_music_is_ducked_when_voice_over_exists():
    timeline = AudioMixer.build_timeline(voice_over="voice.mp3", music="music.mp3", duration=30)
    filter_complex, output = AudioMixer.build_filter_complex(timeline)

    assert "volume=0.06" in filter_complex
    assert "atrim=duration=30" in filter_complex
    assert "amix=inputs=2" in filter_complex
    assert "loudnorm=I=-16:TP=-1.5:LRA=11" in filter_complex
    assert output == "[outa]"


def test_video_command_offsets_audio_inputs_after_video():
    timeline = AudioMixer.build_timeline(
        voice_over="voice.mp3",
        music="music.mp3",
        sfx=(AudioClip("door.wav", start=4.5, fade_in=0.2),),
        duration=20,
    )
    command = AudioMixer.build_ffmpeg_command(timeline, "final.mp4", video_path="video.mp4")
    filter_complex = command[command.index("-filter_complex") + 1]

    assert command[0] == "ffmpeg"
    assert "adelay=4500:all=1" in filter_complex
    assert "[1:a]aresample=48000" in filter_complex
    assert "[2:a]aresample=48000" in filter_complex
    assert "[3:a]aresample=48000" in filter_complex
    assert "0:v:0" in command
    assert "-shortest" in command
    assert command[-2:] == ["-y", "final.mp4"]
