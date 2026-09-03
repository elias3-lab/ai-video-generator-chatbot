"""Pipeline orchestration primitives with checkpoint-aware scene execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from .checkpoint_store import CheckpointStore
from .project_state import ProjectState, SceneState
from .scene_planner import ScenePlan, plan_scenes


@dataclass(frozen=True)
class SceneResult:
    output_path: Optional[str] = None
    asset_id: Optional[str] = None


class PipelineOrchestrator:
    """Coordinate scene execution while persisting progress after each step."""

    def __init__(self, checkpoint_store: Optional[CheckpointStore] = None) -> None:
        self.checkpoints = checkpoint_store or CheckpointStore()

    def create_project(self, project_id: str, duration_seconds: int) -> ProjectState:
        plans = plan_scenes(duration_seconds)
        state = ProjectState(
            project_id=project_id,
            scenes=[
                {
                    "scene_id": plan.scene_id,
                }
                for plan in plans
            ],
        )
        self.checkpoints.save(state)
        return state

    def run(
        self,
        project_id: str,
        executor: Callable[[SceneState], SceneResult],
    ) -> ProjectState:
        """Run only incomplete scenes and checkpoint after every scene.

        The executor owns provider calls, media search, QC, and rendering.
        This keeps resume/failure behavior independent from any provider.
        """
        state = self.checkpoints.resume(project_id)
        state.status = "running"
        self.checkpoints.save(state)

        for scene in state.scenes:
            if scene.status.value == "completed":
                continue

            state.start_scene(scene.scene_id, stage="scene_execution")
            self.checkpoints.save(state)
            try:
                result = executor(scene)
                state.complete_scene(
                    scene.scene_id,
                    output_path=result.output_path,
                    asset_id=result.asset_id,
                )
                self.checkpoints.save(state)
            except Exception as exc:
                state.fail_scene(scene.scene_id, reason=str(exc))
                self.checkpoints.save(state)
                break

        return state
