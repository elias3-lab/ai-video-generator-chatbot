"""Pipeline orchestration with routing, fallback, checkpoints, and continuity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from .checkpoint_store import CheckpointStore
from .project_state import ProjectState, SceneState, ProjectStatus
from .scene_decision import SceneContext, decide_scene_media
from .provider_engine import ProviderEngine
from .scene_planner import plan_scenes
from .visual_dna import ContinuityState, VisualDNA


@dataclass(frozen=True)
class SceneResult:
    output_path: Optional[str] = None
    asset_id: Optional[str] = None
    media_mode: Optional[str] = None
    decision_reason: Optional[str] = None
    visual_prompt: Optional[str] = None
    visual_dna_id: Optional[str] = None
    character_refs: tuple[str, ...] = ()
    location_ref: Optional[str] = None
    provider: Optional[str] = None


class PipelineOrchestrator:
    """Coordinate scene execution while persisting progress after each step."""

    def __init__(
        self,
        checkpoint_store: Optional[CheckpointStore] = None,
        *,
        visual_dna: Optional[VisualDNA] = None,
        ai_providers: Sequence[str] = ("minimax", "runway"),
        provider_engine: Optional[ProviderEngine] = None,
    ) -> None:
        self.checkpoints = checkpoint_store or CheckpointStore()
        self.visual_dna = visual_dna or VisualDNA()
        self.ai_providers = tuple(dict.fromkeys(p for p in ai_providers if p))
        self.provider_engine = provider_engine

    def create_project(self, project_id: str, duration_seconds: int) -> ProjectState:
        plans = plan_scenes(duration_seconds)
        state = ProjectState(
            project_id=project_id,
            visual_dna={
                "style": self.visual_dna.style,
                "camera_language": self.visual_dna.camera_language,
                "color_language": self.visual_dna.color_language,
                "aspect_ratio": self.visual_dna.aspect_ratio,
                "characters": list(self.visual_dna.characters),
                "locations": list(self.visual_dna.locations),
                "wardrobe": list(self.visual_dna.wardrobe),
                "recurring_objects": list(self.visual_dna.recurring_objects),
                "negative_constraints": list(self.visual_dna.negative_constraints),
            },
            scenes=[{"scene_id": plan.scene_id} for plan in plans],
        )
        self.checkpoints.save(state)
        return state

    def run(
        self,
        project_id: str,
        executor: Optional[Callable[[SceneState], SceneResult]] = None,
        *,
        scene_context: Optional[Callable[[SceneState], SceneContext]] = None,
        provider_executor: Optional[Callable[[SceneState, str], SceneResult]] = None,
    ) -> ProjectState:
        """Run incomplete scenes with provider-aware fallback.

        ``provider_executor`` receives the actual provider selected by the
        fallback engine. The legacy ``executor`` remains supported for callers
        that supply their own fallback-aware implementation.
        """
        if executor is None and provider_executor is None and self.provider_engine is None:
            raise ValueError("Provide executor, provider_executor, or provider_engine")

        state = self.checkpoints.resume(project_id)
        state.status = ProjectStatus.RUNNING
        continuity = ContinuityState(dna=self.visual_dna)
        self.checkpoints.save(state)

        for scene in state.scenes:
            if scene.status.value == "completed":
                continuity.mark_completed(scene.scene_id)
                continue

            context = scene_context(scene) if scene_context else SceneContext(prompt=scene.prompt or scene.scene_id)
            decision = decide_scene_media(context)
            visual_prompt = continuity.context_for_scene(context.prompt)
            scene.prompt = context.prompt
            scene.visual_prompt = visual_prompt
            scene.media_mode = decision.mode.value
            scene.decision_reason = decision.reason
            scene.visual_dna_id = self.visual_dna.stable_id()
            scene.character_refs = list(self.visual_dna.characters)
            scene.location_ref = self.visual_dna.locations[0] if self.visual_dna.locations else None

            providers = self.ai_providers if decision.mode.value == "ai_video" else ("free_media",)
            state.start_scene(scene.scene_id, stage="scene_execution", provider=providers[0] if providers else None)
            self.checkpoints.save(state)

            try:
                if provider_executor is not None:
                    def execute(provider: str) -> SceneResult:
                        scene.stage = f"{provider}_generation" if provider != "free_media" else "free_media_search"
                        scene.provider = provider
                        scene.attempts += 1
                        self.checkpoints.save(state)
                        return provider_executor(scene, provider)

                    from .provider_fallback import run_with_fallback
                    fallback = run_with_fallback(providers, execute)
                    result = fallback.value
                    actual_provider = fallback.provider
                elif self.provider_engine is not None:
                    def execute_registered(provider: str) -> SceneResult:
                        scene.stage = f"{provider}_generation" if provider != "free_media" else "free_media_search"
                        scene.provider = provider
                        scene.attempts += 1
                        self.checkpoints.save(state)
                        operation = self.provider_engine.operations[provider]
                        return operation(scene=scene)

                    from .provider_fallback import run_with_fallback
                    fallback = run_with_fallback(providers, execute_registered)
                    result = fallback.value
                    actual_provider = fallback.provider
                else:
                    result = executor(scene)  # type: ignore[misc]
                    actual_provider = result.provider or providers[0]

                scene.provider = result.provider or actual_provider
                state.complete_scene(
                    scene.scene_id,
                    output_path=result.output_path,
                    asset_id=result.asset_id,
                )
                scene.media_mode = result.media_mode or decision.mode.value
                scene.decision_reason = result.decision_reason or decision.reason
                scene.visual_prompt = result.visual_prompt or visual_prompt
                scene.visual_dna_id = result.visual_dna_id or self.visual_dna.stable_id()
                scene.character_refs = list(result.character_refs or self.visual_dna.characters)
                scene.location_ref = result.location_ref or scene.location_ref
                continuity.mark_completed(
                    scene.scene_id,
                    location=scene.location_ref,
                    characters=scene.character_refs,
                )
                self.checkpoints.save(state)
            except Exception as exc:
                state.fail_scene(scene.scene_id, reason=str(exc))
                self.checkpoints.save(state)
                break

        return state
