"""Filesystem-backed checkpoint store for resumable video projects."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from .project_state import ProjectState


class CheckpointStore:
    """Save and load project checkpoints as JSON files."""

    def __init__(self, root_dir: str | Path | None = None) -> None:
        # On Render, STORAGE_ROOT points at the Persistent Disk. Locally this
        # remains the repository's projects/ directory.
        self.root_dir = Path(root_dir or os.getenv("PROJECTS_DIR", "projects")).expanduser()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, project_id: str) -> Path:
        return self.root_dir / project_id / "state.json"

    def save(self, state: ProjectState) -> Path:
        path = self.path_for(state.project_id)
        state.save(path)
        return path

    def load(self, project_id: str) -> ProjectState:
        path = self.path_for(project_id)
        return ProjectState.load(path)

    def exists(self, project_id: str) -> bool:
        return self.path_for(project_id).exists()

    def resume(self, project_id: str) -> ProjectState:
        """Load a project and point it at the first incomplete scene."""
        state = self.load(project_id)
        next_scene = state.next_pending_scene()
        state.resume_from_scene = next_scene
        if next_scene:
            state.current_scene = next_scene
        return state
