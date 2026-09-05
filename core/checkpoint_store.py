"""Filesystem checkpoints with optional Dropbox persistence."""

from __future__ import annotations

import os
from pathlib import Path

from .dropbox_storage import storage
from .project_state import ProjectState

STORAGE_ROOT = Path(os.getenv("STORAGE_ROOT", ".")).expanduser()


class CheckpointStore:
    """Save/load project checkpoints and mirror them to Dropbox when enabled."""

    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir).expanduser() if root_dir else STORAGE_ROOT / "projects"
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, project_id: str) -> Path:
        return self.root_dir / project_id / "state.json"

    def _remote(self, project_id: str) -> str:
        return f"projects/{project_id}/state.json"

    def save(self, state: ProjectState) -> Path:
        path = self.path_for(state.project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        state.save(path)
        if storage.enabled:
            storage.upload_file(path, self._remote(state.project_id))
        return path

    def load(self, project_id: str) -> ProjectState:
        path = self.path_for(project_id)
        if not path.exists() and storage.enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            storage.download_file(self._remote(project_id), path)
        return ProjectState.load(path)

    def exists(self, project_id: str) -> bool:
        path = self.path_for(project_id)
        if path.exists():
            return True
        if storage.enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            return storage.download_file(self._remote(project_id), path)
        return False

    def resume(self, project_id: str) -> ProjectState:
        state = self.load(project_id)
        next_scene = state.next_pending_scene()
        state.resume_from_scene = next_scene
        if next_scene:
            state.current_scene = next_scene
        return state
