from core.scene_planner import plan_scenes


def test_supported_durations_are_segmented():
    for duration in (30, 180, 240, 300):
        scenes = plan_scenes(duration)
        assert sum(scene.duration_seconds for scene in scenes) == duration
        assert all(scene.duration_seconds <= 120 for scene in scenes)


def test_four_minute_plan_has_24_ten_second_scenes():
    scenes = plan_scenes(240)
    assert len(scenes) == 24
    assert all(scene.duration_seconds == 10 for scene in scenes)
