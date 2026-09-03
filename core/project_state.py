"""Persistent project state, scene checkpoints, and diagnostics.

The state model is intentionally provider-agnostic so the pipeline can resume
without being coupled to a specific video generation service.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class ProjectStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class SceneStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class SceneState(BaseModel):
    scene_id: str
    status: SceneStatus = SceneStatus.PENDING
    stage: Optional[str] = None
    provider: Optional[str] = None
    attempts: int = 0
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    output_path: Optional[str] = None
    asset_id: Optional[str] = None


class ProjectState(BaseModel):
    project_id: str
    status: ProjectStatus = ProjectStatus.PENDING
    current_stage: Optional[str] = None
    current_scene: Optional[str] = None
    last_completed_scene: Optional[str] = None
    failure_reason: Optional[str] = None
    resume_from_scene: Optional[str] = None
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    scenes: list[SceneState] = Field(default_factory=list)

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def scene(self, scene_id: str) -> SceneState:
        for scene in self.scenes:
            if scene.scene_id == scene_id:
                return scene
        raise KeyError(f"Unknown scene: {scene_id}")

    def start_scene(self, scene_id: str, stage: str, provider: Optional[str] = None) -> SceneState:
        scene = self.scene(scene_id)
        scene.status = SceneStatus.RUNNING
        scene.stage = stage
        scene.provider = provider
        scene.attempts += 1
        scene.error_code = None
        scene.error_message = None
        scene.started_at = self.now()
        self.status = ProjectStatus.RUNNING
        self.current_stage = stage
        self.current_scene = scene_id
        self.failure_reason = None
        self.resume_from_scene = scene_id
        self.updated_at = self.now()
        return scene

    def complete_scene(
        self,
        scene_id: str,
        output_path: Optional[str] = None,
        asset_id: Optional[str] = None,
    ) -> SceneState:
        scene = self.scene(scene_id)
        scene.status = SceneStatus.COMPLETED
        scene.completed_at = self.now()
        scene.output_path = output_path
        scene.asset_id = asset_id
        self.last_completed_scene = scene_id
        self.resume_from_scene = self.next_pending_scene()
        self.current_scene = self.resume_from_scene
        self.updated_at = self.now()
        if self.resume_from_scene is None:
            self.status = ProjectStatus.COMPLETED
            self.current_stage = None
        return scene

    def fail_scene(
        self,
        scene_id: str,
        reason: str,
        error_code: Optional[str] = None,
    ) -> SceneState:
        scene = self.scene(scene_id)
        scene.status = SceneStatus.FAILED
        scene.error_message = reason
        scene.error_code = error_code
        self.status = ProjectStatus.PAUSED
        self.current_scene = scene_id
        self.resume_from_scene = scene_id
        self.failure_reason = reason
        self.updated_at = self.now()
        return scene

    def next_pending_scene(self) -> Optional[str]:
        for scene in self.scenes:
            if scene.status in {SceneStatus.PENDING, SceneStatus.FAILED}:
                return scene.scene_id
        return None

    def diagnostics(self) -> dict:
        scene = self.scene(self.current_scene) if self.current_scene else None
        completed = sum(s.status == SceneStatus.COMPLETED for s in self.scenes)
        return {
            "project_id": self.project_id,
            "status": self.status.value,
            "current_stage": self.current_stage,
            "current_scene": self.current_scene,
            "provider": scene.provider if scene else None,
            "error_reason": self.failure_reason or (scene.error_message if scene else None),
            "timestamp": self.updated_at,
            "retry_count": scene.attempts if scene else 0,
            "completed_scenes": completed,
            "total_scenes": len(self.scenes),
            "remaining_scenes": max(0, len(self.scenes) - completed),
            "resume_from_scene": self.resume_from_scene,
        }

    def save(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.updated_at = self.now()
        destination.write_text(
            json.dumps(self.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "ProjectState":
        source = Path(path)
        return cls.model_validate(json.loads(source.read_text(encoding="utf-8")))
