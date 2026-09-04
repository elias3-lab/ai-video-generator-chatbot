from core.narration import NarrationPlanner
from core.scene_planner import plan_scenes


def test_narration_matches_scene_plan():
    scenes = plan_scenes(30, preferred_scene_duration=10)
    segments = NarrationPlanner.build_segments("ancient traditions in India", scenes)

    assert len(segments) == len(scenes)
    assert [segment.scene_id for segment in segments] == [scene.scene_id for scene in scenes]
    assert [segment.duration_seconds for segment in segments] == [scene.duration_seconds for scene in scenes]
    assert segments[0].text.startswith("We begin our journey")
    assert "leaves us" in segments[-1].text


def test_narration_supports_film_style():
    scenes = plan_scenes(30, preferred_scene_duration=15)
    segments = NarrationPlanner.build_segments("a journey through the desert", scenes, "Film")

    assert segments[0].text.startswith("The story begins")
    assert "final moment" in segments[-1].text


def test_join_creates_single_tts_script():
    scenes = plan_scenes(30, preferred_scene_duration=10)
    segments = NarrationPlanner.build_segments("hidden places", scenes)
    script = NarrationPlanner.join(segments)

    assert script.count(".") >= len(segments)
    assert "hidden places" in script
