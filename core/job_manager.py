"""Server-side video job state with optional Dropbox persistence."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from threading import Lock, Thread
from typing import Callable, Optional
import json
import os
import time
import uuid

from .dropbox_storage import storage

STORAGE_ROOT = Path(os.getenv("STORAGE_ROOT", ".")).expanduser()
JOB_DIR = STORAGE_ROOT / "checkpoints" / "jobs"


@dataclass
class VideoJob:
    job_id: str
    project_id: Optional[str] = None
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


def _remote(job_id: str) -> str:
    return f"jobs/{job_id}.json"


def _save(job: VideoJob) -> None:
    job.updated_at = time.time()
    destination = _path(job.job_id)
    tmp = destination.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(job), indent=2), encoding="utf-8")
    tmp.replace(destination)
    if storage.enabled:
        storage.upload_file(destination, _remote(job.job_id))


def _load(job_id: str) -> Optional[VideoJob]:
    source = _path(job_id)
    if not source.exists() and storage.enabled:
        storage.download_file(_remote(job_id), source)
    if not source.exists():
        return None
    try:
        return VideoJob(**json.loads(source.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return None


def _load_all() -> list[VideoJob]:
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    if storage.enabled:
        for remote in storage.list_files("jobs"):
            if remote.startswith("jobs/") and remote.endswith(".json"):
                _load(Path(remote).stem)
    jobs: list[VideoJob] = []
    for source in JOB_DIR.glob("*.json"):
        try:
            jobs.append(VideoJob(**json.loads(source.read_text(encoding="utf-8"))))
        except (OSError, ValueError, TypeError):
            continue
    return sorted(jobs, key=lambda item: item.updated_at, reverse=True)


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


def list_video_jobs(limit: int = 10) -> list[VideoJob]:
    with _lock:
        merged = {job.job_id: job for job in _load_all()}
        merged.update(_jobs)
        return sorted(merged.values(), key=lambda item: item.updated_at, reverse=True)[:limit]


def _format_eta(progress: int, elapsed_seconds: float) -> str:
    if progress <= 0 or elapsed_seconds <= 0:
        return "Calculating..."
    remaining = max(0.0, elapsed_seconds * (100 - progress) / progress)
    if remaining < 60:
        return f"~{max(1, round(remaining))}s"
    minutes = remaining / 60
    if minutes < 60:
        return f"~{max(1, round(minutes))} min"
    hours = minutes / 60
    return f"~{hours:.1f} h"


def _progress_diagnostics(job: VideoJob, base: str) -> str:
    if job.status in {"completed", "failed", "missing"}:
        return base
    remaining = max(0, job.total_scenes - job.scenes_completed) if job.total_scenes else 0
    eta = _format_eta(job.progress, job.elapsed_seconds)
    return (
        f"{base}\n\n"
        f"Current stage: 🎬 {job.phase}\n"
        f"Completed: {job.scenes_completed} / {job.total_scenes} scenes\n"
        f"Remaining: {remaining} scenes\n"
        f"Estimated remaining: {eta}\n"
        f"Server: 🟢 ONLINE"
    )


def start_video_job(
    fn: Callable[[Callable[..., None]], tuple[object, str]],
    *,
    project_id: Optional[str] = None,
    job_id: Optional[str] = None,
) -> str:
    job_id = job_id or uuid.uuid4().hex[:12]
    job = VideoJob(job_id=job_id, project_id=project_id, status="queued", phase="Queued", diagnostics="Queued on server. You can close the phone while generation continues.")
    with _lock:
        _jobs[job_id] = job
        _save(job)

    started = time.monotonic()

    def progress(**changes: object) -> None:
        changes["elapsed_seconds"] = round(time.monotonic() - started, 1)
        current = _jobs.get(job_id) or _load(job_id) or job
        for key, value in changes.items():
            if hasattr(current, key):
                setattr(current, key, value)
        current.diagnostics = _progress_diagnostics(current, str(changes.get("diagnostics", current.diagnostics)))
        update_video_job(job_id, **asdict(current))

    def run() -> None:
        progress(status="running", phase="Planning", progress=2, diagnostics="Processing on Render server...")
        try:
            video_path, diagnostics = fn(progress)
            progress(status="completed" if video_path else "failed", phase="Completed" if video_path else "Failed", progress=100 if video_path else 0, video_path=str(video_path) if video_path else None, diagnostics=diagnostics)
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
