from pathlib import Path

from core.audio_mixer import AudioClip, AudioMixer
from core.final_render import FinalRenderer


def test_final_renderer_builds_audio_enabled_render_command(monkeypatch, tmp_path):
    captured = {}

    def fake_concat(paths, output):
        Path(output).write_bytes(b"video")

    def fake_run(command, **kwargs):
        captured["command"] = command
        output = command[-1]
        Path(output).write_bytes(b"final")

        class Result:
            returncode = 0
            stderr = ""

        return Result()

    monkeypatch.setattr(FinalRenderer, "_concat_scenes", fake_concat)
    monkeypatch.setattr("core.final_render.subprocess.run", fake_run)

    output = tmp_path / "final.mp4"
    result = FinalRenderer.render(
        [str(tmp_path / "scene.mp4")],
        str(output),
        voice_over="voice.mp3",
        music="music.mp3",
        sfx=(AudioClip("sfx.wav", start=2),),
        duration=10,
    )

    command_text = " ".join(captured["command"])
    assert result == str(output)
    assert "-filter_complex" in captured["command"]
    assert "music.mp3" in command_text
    assert "voice.mp3" in command_text
    assert "sfx.wav" in command_text
    assert output.exists()
