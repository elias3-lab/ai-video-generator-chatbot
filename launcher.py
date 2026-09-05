"""Render-safe launcher with automatic recovery of interrupted video jobs."""

from __future__ import annotations

import logging
import time

import app
from core.job_manager import get_video_job, list_video_jobs, start_video_job, update_video_job
from core.orchestrator import PipelineOrchestrator


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
LOGGER = logging.getLogger("castelou.launcher")


def _duration_label(project_id: str) -> str:
    state = PipelineOrchestrator().checkpoints.load(project_id)
    seconds = sum(float(scene.target_duration or 0) for scene in state.scenes)
    return min(app.DURATION_OPTIONS, key=lambda label: abs(app.DURATION_OPTIONS[label] - seconds))


def _prompt(project_id: str) -> str:
    state = PipelineOrchestrator().checkpoints.load(project_id)
    # Scene prompts contain the persisted story context after a Render restart.
    return next((scene.prompt for scene in state.scenes if scene.prompt), "Continue the saved documentary project.")


def recover_interrupted_jobs() -> None:
    """Resume queued/running jobs that were interrupted by a process restart."""
    jobs = list_video_jobs(50)
    for job in jobs:
        if job.status not in {"queued", "running"} or not job.project_id:
            continue
        try:
            project_id = job.project_id
            duration_label = _duration_label(project_id)
            prompt = _prompt(project_id)
            # Reuse the same job ID so the existing phone UI keeps polling it.
            LOGGER.info("Recovering interrupted job %s (project %s)", job.job_id, project_id)
            start_video_job(
                lambda progress, pid=project_id, p=prompt, d=duration_label: app._run_project(
                    pid, p, d, app.DEFAULT_CONTENT_TYPE, app.DEFAULT_VIDEO_FORMAT, progress
                ),
                project_id=project_id,
                job_id=job.job_id,
            )
        except Exception as exc:
            LOGGER.exception("Could not recover job %s: %s", job.job_id, exc)
            try:
                update_video_job(job.job_id, status="failed", phase="Recovery failed", diagnostics=f"Automatic recovery failed: {exc}")
            except Exception:
                LOGGER.exception("Could not persist recovery failure for %s", job.job_id)


if __name__ == "__main__":
    # Give Gradio/app import time to finish before recovery starts. This also
    # keeps startup deterministic on Render while Dropbox is being contacted.
    time.sleep(2)
    recover_interrupted_jobs()
    app.demo.launch(server_name=app.SERVER_NAME, server_port=app.SERVER_PORT)
