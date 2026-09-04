from __future__ import annotations

import json


def test_video_job_round_trip_without_video_generation(tmp_path, monkeypatch):
    """Verify job state survives a fresh in-process load without generating media."""
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))

    import core.job_manager as jm

    # Keep this test isolated from module-level state created by other tests.
    jm._jobs.clear()
    jm.STORAGE_ROOT = tmp_path
    jm.JOB_DIR = tmp_path / "checkpoints" / "jobs"

    job = jm.update_video_job(
        "persistence-test",
        project_id="persistence-project",
        status="failed",
        phase="Paused",
        progress=42,
        scenes_completed=2,
        total_scenes=5,
        diagnostics="Persistence test checkpoint",
    )

    assert job.status == "failed"
    assert job.progress == 42
    assert (jm.JOB_DIR / "persistence-test.json").exists()

    # Simulate a fresh server process by clearing the in-memory cache.
    jm._jobs.clear()
    restored = jm.get_video_job("persistence-test")

    assert restored.job_id == "persistence-test"
    assert restored.project_id == "persistence-project"
    assert restored.status == "failed"
    assert restored.progress == 42
    assert restored.scenes_completed == 2


def test_final_mp4_is_never_selected_for_dropbox_persistence(monkeypatch):
    monkeypatch.delenv("DROPBOX_ACCESS_TOKEN", raising=False)

    import core.dropbox_storage as ds

    storage = ds.DropboxStorage()
    assert storage._is_final_path("projects/demo/final/video.mp4") is True
    assert storage._is_final_path("projects/demo/assets/scene-01.mp4") is False
