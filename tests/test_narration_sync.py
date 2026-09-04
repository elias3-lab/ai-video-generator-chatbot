from dataclasses import dataclass, replace
from pathlib import Path

import pytest

import app
from core.narration import NarrationAudioSegment, NarrationPlanner, concatenate_audio_segments, probe_audio_duration
from core.subtitles import SubtitlePlanner


@dataclass
class FakeScene:
    scene_id: str
    duration_seconds: int | None = None
    target_duration: int | None = None


def test_probe_audio_duration_returns_measured_float(tmp_path, monkeypatch):
    audio = tmp_path / "scene.mp3"
    audio.write_bytes(b"fake")

    class Result:
        returncode = 0
        stdout = "7.25\n"
        stderr = ""

    monkeypatch.setattr("core.narration.subprocess.run", lambda *args, **kwargs: Result())
    assert probe_audio_duration(str(audio)) == pytest.approx(7.25)


def test_probe_audio_duration_rejects_invalid_duration(tmp_path, monkeypatch):
    audio = tmp_path / "scene.mp3"
    audio.write_bytes(b"fake")

    class Result:
        returncode = 0
        stdout = "not-a-duration"
        stderr = ""

    monkeypatch.setattr("core.narration.subprocess.run", lambda *args, **kwargs: Result())
    with pytest.raises(Exception, match="Invalid audio duration"):
        probe_audio_duration(str(audio))


def test_concatenate_audio_segments_writes_ordered_manifest(tmp_path, monkeypatch):
    first = tmp_path / "scene_001.mp3"
    second = tmp_path / "scene_002.mp3"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    output = tmp_path / "voice.mp3"
    captured = {}

    def fake_run(command, **kwargs):
        captured["manifest"] = Path(command[command.index("-i") + 1]).read_text(encoding="utf-8")
        output.write_bytes(b"combined")

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr("core.narration.subprocess.run", fake_run)
    segments = [
        NarrationAudioSegment(NarrationPlanner.build_segments("test story", [FakeScene("s1", 10)])[0], str(first), 4.2),
        NarrationAudioSegment(NarrationPlanner.build_segments("test story", [FakeScene("s2", 10)])[0], str(second), 5.8),
    ]

    assert concatenate_audio_segments(segments, str(output)) == str(output)
    assert output.read_bytes() == b"combined"
    assert captured["manifest"].splitlines() == [
        f"file '{first.resolve()}'",
        f"file '{second.resolve()}'",
    ]
    assert not output.with_suffix(".concat.txt").exists()


def test_narration_uses_scene_target_duration_when_duration_seconds_is_absent():
    scenes = [FakeScene("s1", target_duration=10), FakeScene("s2", target_duration=20)]
    planned = NarrationPlanner.build_segments("test story", scenes)
    assert [segment.duration_seconds for segment in planned] == [10.0, 20.0]


def test_generate_voice_over_uses_measured_scene_durations(monkeypatch, tmp_path):
    scenes = [FakeScene("s1", 10), FakeScene("s2", 10)]
    generated = []
    measured = iter([4.2, 6.8])

    class FakeProvider:
        def __init__(self):
            pass

        def generate_voice_over(self, text, output_path, language=None):
            Path(output_path).write_bytes(b"fake-audio")
            generated.append((text, output_path, language))

    monkeypatch.setattr(app.settings, "elevenlabs_api_key", "test-key")
    monkeypatch.setattr(app.settings, "elevenlabs_voice_id", "test-voice")
    monkeypatch.setattr(app, "ElevenLabsProvider", FakeProvider)
    monkeypatch.setattr(app, "probe_audio_duration", lambda path: next(measured))

    concatenated = {}

    def fake_concat(segments, output_path):
        concatenated["segments"] = list(segments)
        Path(output_path).write_bytes(b"combined")
        return output_path

    monkeypatch.setattr(app, "concatenate_audio_segments", fake_concat)

    output = tmp_path / "voice.mp3"
    path, status, narration_segments = app._generate_voice_over(
        "a journey through India", "Documentary", scenes, str(output)
    )

    assert path == str(output)
    assert "2 scene tracks" in status
    assert "11.0s measured" in status
    assert [segment.duration_seconds for segment in narration_segments] == pytest.approx([4.2, 6.8])
    assert [item.duration_seconds for item in concatenated["segments"]] == pytest.approx([4.2, 6.8])
    assert [item[2] for item in generated] == [app.settings.default_language, app.settings.default_language]


def test_subtitles_follow_measured_narration_timeline():
    planned = NarrationPlanner.build_segments(
        "a journey through India", [FakeScene("s1", 10), FakeScene("s2", 10)]
    )
    measured = [replace(planned[0], duration_seconds=4.2), replace(planned[1], duration_seconds=6.8)]
    cues = SubtitlePlanner.build_cues(measured)

    assert [(cue.start, cue.end) for cue in cues] == pytest.approx([(0.0, 4.2), (4.2, 11.0)])
    assert "00:00:04,200 --> 00:00:11,000" in SubtitlePlanner.to_srt(cues)
