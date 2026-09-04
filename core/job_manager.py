"""Server-side video job state with persisted progress metadata."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from threading import Lock, Thread
from typing import Callable, Optional
import json
import time
import uuid


JOB_DIR = Path("checkpoints") / "jobs"


@dataclass
class VideoJob:
    job_id: str
    status: str = "queued"
    phase: str = "Queued"
    progress: int = 0
    scenes_completed: int = 0
    total_scenes: int = 0
    voice_completed: int = 0
    total_voice: int = 0
    elapsed_seconds: float = 0.0
    video_path: Optional[str] = None
    diagnostics: str = ""
    updated_at: float = 0.0


_lock = Lock()
_jobs: dict[str, VideoJob] = {}


def _path(job_id: str) -> Path:
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    return JOB_DIR / f"{job_id}.json"


def _save(job: VideoJob) -> None:
    job.updated_at = time.time()
    destination = _path(job.job_id)
    tmp = destination.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(job), indent=2), encoding="utf-8")
    tmp.replace(destination)


def _load(job_id: str) -> Optional[VideoJob]:
    source = _path(job_id)
    if not source.exists():
        return None
    try:
        return VideoJob(**json.loads(source.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return None


def update_video_job(job_id: str, **changes: object) -> VideoJob:
    with _lock:
        job = _jobs.get(job_id) or _load(job_id)
        if job is None:
            job = VideoJob(job_id=job_id)
        for key, value in changes.items():
            if hasattr(job, key):
                setattr(job, key, value)
        _jobs[job_id] = job
        _save(job)
        return VideoJob(**asdict(job))


def start_video_job(fn: Callable[[Callable[..., None]], tuple[object, str]]) -> str:
    """Start generation in a server-side thread and persist live job state."""
    job_id = uuid.uuid4().hex[:12]
    job = VideoJob(
        job_id=job_id,
        status="queued",
        phase="Queued",
        diagnostics="Queued on server. You can close the phone while generation continues.",
    )
    with _lock:
        _jobs[job_id] = job
        _save(job)

    started = time.monotonic()

    def progress(**changes: object) -> None:
        changes["elapsed_seconds"] = round(time.monotonic() - started, 1)
        update_video_job(job_id, **changes)

    def run() -> None:
        progress(status="running", phase="Planning", progress=2, diagnostics="Processing on Render server...")
        try:
            video_path, diagnostics = fn(progress)
            progress(
                status="completed" if video_path else "failed",
                phase="Completed" if video_path else "Failed",
                progress=100 if video_path else job.progress,
                video_path=str(video_path) if video_path else None,
                diagnostics=diagnostics,
            )
        except Exception as exc:
            progress(status="failed", phase="Failed", diagnostics=f"VIDEO GENERATION FAILED\n\n{exc}")

    Thread(target=run, name=f"video-job-{job_id}", daemon=True).start()
    return job_id


def get_video_job(job_id: str) -> VideoJob:
    normalized = (job_id or "").strip()
    with _lock:
        job = _jobs.get(normalized) or _load(normalized)
        if job is None:
            return VideoJob(job_id=normalized, status="missing", diagnostics="Job not found on this server instance.")
        return VideoJob(**asdict(job))
