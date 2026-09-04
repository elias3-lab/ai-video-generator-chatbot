"""In-process background job manager for long-running video generation."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock, Thread
from typing import Callable, Optional
import uuid


@dataclass
class VideoJob:
    job_id: str
    status: str = "queued"
    video_path: Optional[str] = None
    diagnostics: str = ""


_lock = Lock()
_jobs: dict[str, VideoJob] = {}


def start_video_job(fn: Callable[[], tuple[object, str]]) -> str:
    """Start generation in a server-side thread and return immediately."""
    job_id = uuid.uuid4().hex[:12]
    job = VideoJob(job_id=job_id, status="queued", diagnostics="Queued on server. You can close the phone while generation continues.")
    with _lock:
        _jobs[job_id] = job

    def run() -> None:
        with _lock:
            job.status = "running"
            job.diagnostics = "Processing on Render server..."
        try:
            video_path, diagnostics = fn()
            with _lock:
                job.video_path = str(video_path) if video_path else None
                job.diagnostics = diagnostics
                job.status = "completed" if video_path else "failed"
        except Exception as exc:
            with _lock:
                job.status = "failed"
                job.diagnostics = f"VIDEO GENERATION FAILED\n\n{exc}"

    Thread(target=run, name=f"video-job-{job_id}", daemon=True).start()
    return job_id


def get_video_job(job_id: str) -> VideoJob:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return VideoJob(job_id=job_id, status="missing", diagnostics="Job not found on this server instance.")
        return VideoJob(**job.__dict__)
