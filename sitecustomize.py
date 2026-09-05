"""Startup UI patch for persistent completed-video history in Gradio."""

from __future__ import annotations

import sys
from pathlib import Path


def _install_completed_history() -> None:
    try:
        import gradio as gr
    except Exception:
        return

    launch = getattr(gr.Blocks, "launch", None)
    if launch is None or getattr(launch, "_castelou_history_patch", False):
        return

    def _find_app_module():
        module = sys.modules.get("app")
        if module is not None and hasattr(module, "demo"):
            return module
        for candidate in list(sys.modules.values()):
            if candidate is not None and getattr(candidate, "__name__", "") == "app" and hasattr(candidate, "demo"):
                return candidate
        return None

    def _history_data(app):
        try:
            jobs = [
                job for job in app.list_video_jobs(50)
                if job.status == "completed" and job.video_path
            ]
            items = []
            for job in jobs:
                path = Path(job.video_path)
                if path.exists() and path.is_file():
                    label = f"{job.job_id} — {job.project_id or 'project'}"
                    items.append((label, job.job_id))
            return jobs, items
        except Exception:
            return [], []

    def _load_history(selection=""):
        app = _find_app_module()
        if app is None:
            return gr.update(choices=[], value=None), None, "No completed videos found.", ""
        jobs, items = _history_data(app)
        selected = selection.strip() if isinstance(selection, str) else ""
        chosen = next((job for job in jobs if job.job_id == selected), None)
        if chosen is None and jobs:
            chosen = jobs[0]
        value = chosen.job_id if chosen else None
        video = chosen.video_path if chosen and Path(chosen.video_path).exists() else None
        if chosen:
            status = f"🟢 **Completed video:** `{chosen.job_id}`\n\nProject: `{chosen.project_id}`"
        else:
            status = "No completed videos found yet."
        return gr.update(choices=items, value=value), video, status, value or ""

    def _load_selected(selection):
        app = _find_app_module()
        if app is None or not selection:
            return None, "Select a completed video first."
        job = app.get_video_job(selection)
        if job.status != "completed" or not job.video_path:
            return None, f"Job `{selection}` is not completed or its video path is unavailable."
        path = Path(job.video_path)
        if not path.exists():
            return None, f"Job `{selection}` is completed, but the MP4 is no longer present on this Render instance."
        return str(path), f"🟢 **Loaded:** `{selection}`\n\n{job.diagnostics}"

    def _patched_launch(self, *args, **kwargs):
        app = _find_app_module()
        if app is not None and getattr(self, "_castelou_history_ui_added", False) is False:
            try:
                with self:
                    gr.Markdown("### 🎬 Completed Videos\nYour completed videos remain listed here when you leave and return to the site.")
                    history = gr.Dropdown(label="Video History", choices=[], value=None, interactive=True)
                    with gr.Row():
                        load_history_btn = gr.Button("▶️ Load Selected Video")
                        refresh_history_btn = gr.Button("🔄 Refresh History")
                    history_status = gr.Markdown("Loading completed videos...")

                    history.load(
                        _load_history,
                        inputs=None,
                        outputs=[history, app.video_output, history_status, app.job_id],
                    )
                    refresh_history_btn.click(
                        _load_history,
                        inputs=history,
                        outputs=[history, app.video_output, history_status, app.job_id],
                    )
                    load_history_btn.click(
                        _load_selected,
                        inputs=history,
                        outputs=[app.video_output, history_status],
                    )
                self._castelou_history_ui_added = True
            except Exception:
                # Never prevent the main video generator from launching if the
                # optional history panel cannot be attached.
                pass
        return launch(self, *args, **kwargs)

    _patched_launch._castelou_history_patch = True
    gr.Blocks.launch = _patched_launch


_install_completed_history()
