from core.narration import NarrationPlanner
from core.scene_planner import plan_scenes
from core.subtitles import SubtitlePlanner


def test_subtitle_cues_follow_scene_timeline():
    scenes = plan_scenes(30, preferred_scene_duration=10)
    segments = NarrationPlanner.build_segments("ancient India", scenes)
    cues = SubtitlePlanner.build_cues(segments)

    assert len(cues) == 3
    assert [cue.start for cue in cues] == [0.0, 10.0, 20.0]
    assert [cue.end for cue in cues] == [10.0, 20.0, 30.0]
    assert cues[0].text.startswith("We begin our journey")


def test_srt_timestamp_format():
    scenes = plan_scenes(30, preferred_scene_duration=15)
    segments = NarrationPlanner.build_segments("the ocean", scenes)
    srt = SubtitlePlanner.to_srt(SubtitlePlanner.build_cues(segments))

    assert "1\n00:00:00,000 --> 00:00:15,000" in srt
    assert "2\n00:00:15,000 --> 00:00:30,000" in srt


def test_empty_subtitles_are_rejected():
    try:
        SubtitlePlanner.build_cues([])
    except ValueError as exc:
        assert "at least one" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
