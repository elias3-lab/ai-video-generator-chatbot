"""Minimal resumable orchestration layer for scene-based generation."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from .checkpoint_store import CheckpointStore
from .media_router import MediaMode, SmartMediaRouter
from .project_state import ProjectState, SceneState
from .scene_planner import plan_scenes


SceneExecutor = Callable[[SceneState, object], str]


class PipelineOrchestrator:
    """Coordinate scene planning, routing, execution and checkpoints.

    Provider-specific API calls are injected through ``scene_executor`` so the
    pipeline remains testable and does not expose credentials to the UI.
    """

    def __init__(
        self,
        checkpoint_store: Optional[CheckpointStore] = None,
        router: Optional[SmartMediaRouter] = None,
    ) -> None:
        self.checkpoints = checkpoint_store or CheckpointStore()
        self.router = router or SmartMediaRouter(("minimax", "runway"))

    def create_project(self, project_id: str, duration_seconds: int) -> ProjectState:
        plans = plan_scenes(duration_seconds, max_segment_duration=120)
        state = ProjectState(
            project_id=project_id,
            scenes=[
                SceneState(scene_id=plan.scene_id)
                for plan in plans
            ],
            resume_from_scene=plans[0].scene_id if plans else None,
            current_scene=plans[0].scene_id if plans else None,
        )
        self.checkpoints.save(state)
        return state

    def run(
        self,
        project_id: str,
        scene_executor: SceneExecutor,
        *,
        prefer_stock: bool = False,
    ) -> ProjectState:
        state = self.checkpoints.resume(project_id)
        for scene in state.scenes:
            if scene.status.value == "completed":
                continue

            decision = self.router.decide(prefer_stock=prefer_stock)
            state.start_scene(
                scene.scene_id,
                stage="media_generation" if decision.mode == MediaMode.AI_VIDEO else "free_media",
                provider=decision.providers[0],
            )
            self.checkpoints.save(state)

            try:
                output_path = scene_executor(scene, decision)
                state.complete_scene(scene.scene_id, output_path=output_path)
            except Exception as exc:
                state.fail_scene(scene.scene_id, reason=str(exc))
                self.checkpoints.save(state)
                raise

            self.checkpoints.save(state)

        return state
