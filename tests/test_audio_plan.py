from core.audio_plan import AudioPlanner
from core.scene_planner import plan_scenes


def test_audio_cues_follow_scene_timeline():
    scenes = plan_scenes(30, preferred_scene_duration=10)
    cues = AudioPlanner.build_cues(scenes)
    music = AudioPlanner.music_cues(cues)
    sfx = AudioPlanner.sfx_cues(cues)

    assert len(music) == len(scenes)
    assert len(sfx) == len(scenes) - 1
    assert [cue.scene_id for cue in music] == [scene.scene_id for scene in scenes]
    assert [cue.start for cue in music] == [0.0, 10.0, 20.0]
    assert music[-1].mood == "reflective"


def test_audio_planner_supports_film_moods():
    scenes = plan_scenes(30, preferred_scene_duration=15)
    cues = AudioPlanner.build_cues(scenes, content_type="Film")

    assert AudioPlanner.music_cues(cues)[0].mood == "anticipation"
    assert AudioPlanner.music_cues(cues)[-1].mood == "resolution"


def test_sfx_resolution_skips_missing_assets():
    scenes = plan_scenes(30, preferred_scene_duration=10)
    cues = AudioPlanner.build_cues(scenes)
    clips = AudioPlanner.to_mixer_sfx(cues, asset_paths={})

    assert clips == ()
