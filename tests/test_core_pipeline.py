from core.orchestrator import PipelineOrchestrator, SceneResult
from core.scene_decision import SceneContext, SceneMediaMode, decide_scene_media
from core.scene_planner import plan_scenes, validate_target_duration
from core.provider_fallback import AllProvidersFailed, run_with_fallback
from core.checkpoint_store import CheckpointStore
from core.visual_dna import VisualDNA


def test_provider_fallback_uses_next_provider():
    calls = []
    def operation(provider):
        calls.append(provider)
        if provider == "minimax": raise RuntimeError("quota")
        return "ok"
    result = run_with_fallback(("minimax", "runway", "free_media"), operation)
    assert result.value == "ok"
    assert result.provider == "runway"
    assert calls == ["minimax", "runway"]
    assert result.attempts[0].error == "quota"
    assert result.attempts[1].success is True


def test_provider_fallback_reports_all_failures():
    def operation(provider): raise RuntimeError(f"{provider} failed")
    try:
        run_with_fallback(("minimax", "runway"), operation)
        assert False, "expected AllProvidersFailed"
    except AllProvidersFailed as exc:
        assert [attempt.provider for attempt in exc.attempts] == ["minimax", "runway"]
        assert all(not attempt.success for attempt in exc.attempts)


def test_orchestrator_persists_provider_attempt_history(tmp_path):
    store = CheckpointStore(tmp_path)
    orchestrator = PipelineOrchestrator(checkpoint_store=store, ai_providers=("minimax", "runway"))
    orchestrator.create_project("diagnostics", 30)
    calls = []
    def provider_executor(scene, provider):
        calls.append(provider)
        if provider == "minimax": raise RuntimeError("quota exceeded")
        return SceneResult(output_path=f"{scene.scene_id}.mp4", provider=provider, media_mode="ai_video")
    state = orchestrator.run("diagnostics", provider_executor=provider_executor, scene_context=lambda scene: SceneContext(prompt="cinematic documentary scene", visual_priority=0.9, stock_likelihood=0.1))
    scene = state.scene("scene_001")
    assert calls[:2] == ["minimax", "runway"]
    assert scene.status.value == "completed"
    assert scene.attempts == 2
    assert [a.provider for a in scene.provider_attempts] == ["minimax", "runway"]
    assert scene.provider_attempts[0].success is False
    assert scene.provider_attempts[0].error == "quota exceeded"
    assert scene.provider_attempts[1].success is True
    reloaded = store.load("diagnostics")
    assert [a.provider for a in reloaded.scene("scene_001").provider_attempts] == ["minimax", "runway"]


def test_orchestrator_records_all_provider_failures(tmp_path):
    store = CheckpointStore(tmp_path)
    orchestrator = PipelineOrchestrator(checkpoint_store=store, ai_providers=("minimax", "runway"))
    orchestrator.create_project("failed", 30)
    def provider_executor(scene, provider): raise RuntimeError(f"{provider} unavailable")
    state = orchestrator.run("failed", provider_executor=provider_executor, scene_context=lambda scene: SceneContext(prompt="cinematic documentary scene", visual_priority=0.9, stock_likelihood=0.1))
    scene = state.scene("scene_001")
    assert scene.status.value == "failed"
    assert scene.attempts == 3
    assert [a.provider for a in scene.provider_attempts] == ["minimax", "runway", "free_media"]
    assert all(not a.success for a in scene.provider_attempts)
    assert scene.provider_attempts[-1].error == "free_media unavailable"
    assert state.diagnostics()["current_scene"] == "scene_001"
    assert state.diagnostics()["resume_from_scene"] == "scene_001"


def test_scene_planner_supported_durations_and_exact_total():
    assert validate_target_duration(30) == 30
    assert validate_target_duration(180) == 180
    assert validate_target_duration(240) == 240
    assert validate_target_duration(300) == 300
    scenes = plan_scenes(240)
    assert len(scenes) == 24
    assert sum(scene.duration_seconds for scene in scenes) == 240
    assert scenes[0].scene_id == "scene_001"
    assert scenes[-1].scene_id == "scene_024"


def test_scene_decision_prefers_stock_when_stock_is_strong():
    decision = decide_scene_media(SceneContext(prompt="Indian railway station", visual_priority=0.5, stock_likelihood=0.9))
    assert decision.mode == SceneMediaMode.FREE_MEDIA


def test_scene_decision_prefers_ai_for_high_visual_priority():
    decision = decide_scene_media(SceneContext(prompt="cinematic reenactment", visual_priority=0.9, stock_likelihood=0.1))
    assert decision.mode == SceneMediaMode.AI_VIDEO


def test_visual_dna_id_is_deterministic_and_changes_with_content():
    first = VisualDNA(style="cinematic documentary", characters=("traveler",)).stable_id()
    second = VisualDNA(style="cinematic documentary", characters=("traveler",)).stable_id()
    changed = VisualDNA(style="cinematic documentary", characters=("historian",)).stable_id()
    assert first == second
    assert first != changed
