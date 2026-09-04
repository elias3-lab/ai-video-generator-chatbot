from dataclasses import dataclass

from core.director import DirectorPlanner


@dataclass
class Scene:
    scene_id: str
    duration_seconds: int


def test_director_has_four_story_beats():
    scenes = [Scene(f"scene_{i:03d}", 10) for i in range(1, 13)]
    prompts = DirectorPlanner.build_storyboard(
        "a six-month journey across India",
        scenes,
        "cinematic educational documentary",
        "cinematic documentary, realistic, natural light",
    )
    assert len(prompts) == 12
    assert "Hook beat" in prompts[0]
    assert "Ending beat" in prompts[-1]
    assert "Visual DNA" in prompts[0]
    assert "24mm lens" in prompts[0]
    assert "Output format" not in prompts[0]


def test_director_middle_scenes_evolve_from_journey_to_discovery():
    first = DirectorPlanner.beat_for(2, 8)
    later = DirectorPlanner.beat_for(7, 8)
    assert first.name == "Journey"
    assert later.name == "Discovery"
    assert first.camera != later.camera


def test_single_scene_is_a_complete_hook():
    beat = DirectorPlanner.beat_for(1, 1)
    assert beat.name == "Hook"
