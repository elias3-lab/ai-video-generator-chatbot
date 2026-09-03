from core.provider_fallback import AllProvidersFailed, run_with_fallback
from core.scene_decision import SceneContext, SceneMediaMode, decide_scene_media
from core.scene_planner import plan_scenes, validate_target_duration
from core.visual_dna import VisualDNA


def test_provider_fallback_uses_next_provider():
    calls = []

    def operation(provider):
        calls.append(provider)
        if provider == "minimax":
            raise RuntimeError("quota")
        return "ok"

    result = run_with_fallback(("minimax", "runway", "free_media"), operation)
    assert result.value == "ok"
    assert result.provider == "runway"
    assert calls == ["minimax", "runway"]
    assert len(result.attempts) == 2
    assert result.attempts[0].success is False
    assert result.attempts[1].success is True


def test_provider_fallback_reports_all_failures():
    def operation(provider):
        raise RuntimeError(f"{provider} failed")

    try:
        run_with_fallback(("minimax", "runway"), operation)
        assert False, "expected AllProvidersFailed"
    except AllProvidersFailed as exc:
        assert [a.provider for a in exc.attempts] == ["minimax", "runway"]
        assert all(not a.success for a in exc.attempts)


def test_scene_planner_supported_durations_and_exact_total():
    assert validate_target_duration(240) == 240
    plans = plan_scenes(240, preferred_scene_duration=10)
    assert len(plans) == 24
    assert sum(scene.duration_seconds for scene in plans) == 240
    assert max(scene.duration_seconds for scene in plans) <= 120


def test_scene_decision_prefers_stock_when_stock_is_strong():
    decision = decide_scene_media(
        SceneContext(
            prompt="Indian railway station",
            visual_priority=0.5,
            stock_likelihood=0.9,
        )
    )
    assert decision.mode == SceneMediaMode.FREE_MEDIA


def test_scene_decision_prefers_ai_for_high_visual_priority():
    decision = decide_scene_media(
        SceneContext(
            prompt="cinematic reenactment",
            visual_priority=0.9,
            stock_likelihood=0.1,
        )
    )
    assert decision.mode == SceneMediaMode.AI_VIDEO


def test_visual_dna_id_is_deterministic_and_changes_with_dna():
    dna = VisualDNA(characters=("Traveler",), locations=("Delhi",))
    same = VisualDNA(characters=("Traveler",), locations=("Delhi",))
    changed = VisualDNA(characters=("Traveler",), locations=("Mumbai",))
    assert dna.stable_id() == same.stable_id()
    assert dna.stable_id() != changed.stable_id()
