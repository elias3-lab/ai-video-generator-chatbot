from pathlib import Path

from core.cinematic_audio import CinematicAudioGenerator


def test_transition_sfx_builds_command(monkeypatch, tmp_path):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        Path(command[-1]).write_bytes(b"audio")

        class Result:
            returncode = 0
            stderr = ""

        return Result()

    monkeypatch.setattr("core.cinematic_audio.subprocess.run", fake_run)
    path = CinematicAudioGenerator.generate_transition_sfx(tmp_path / "transition.mp3")
    assert Path(path).exists()
    assert "aevalsrc=" in " ".join(captured["command"])


def test_default_layers_create_music_and_transition_clips(monkeypatch, tmp_path):
    monkeypatch.setattr(
        CinematicAudioGenerator,
        "generate_music",
        lambda output_path, duration: Path(output_path).write_bytes(b"music") or str(output_path),
    )
    monkeypatch.setattr(
        CinematicAudioGenerator,
        "generate_transition_sfx",
        lambda output_path: Path(output_path).write_bytes(b"sfx") or str(output_path),
    )
    music, sfx = CinematicAudioGenerator.build_default_layers(tmp_path, 180, 3)
    assert Path(music).exists()
    assert len(sfx) == 2
    assert sfx[0].start == 60
    assert sfx[1].start == 120
