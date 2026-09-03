"""CASTELOU AI Documentary Studio Gradio application."""

from __future__ import annotations

from pathlib import Path
import uuid

import gradio as gr

from core.final_render import FinalRenderer
from core.orchestrator import PipelineOrchestrator
from core.project_state import ProjectStatus
from providers.registry import ProviderRegistry
from core.scene_decision import SceneContext

DURATION_OPTIONS = {
    "30s": 30,
    "3 min": 180,
    "4 min": 240,
    "5 min": 300,
}
DEFAULT_DURATION = "4 min"
SERVER_NAME = "0.0.0.0"
SERVER_PORT = 7860


def _duration_seconds(label: str) -> int:
    try:
        return DURATION_OPTIONS[label]
    except KeyError as exc:
        raise ValueError("Unsupported duration. Choose 30s, 3 min, 4 min, or 5 min.") from exc


def create_video(prompt: str, duration_label: str):
    """Run the existing pipeline and render completed scenes into one MP4."""
    prompt = (prompt or "").strip()
    if not prompt:
        raise gr.Error("Tell CASTELOU what story to create first.")

    duration_seconds = _duration_seconds(duration_label)
    project_id = f"castelou-{uuid.uuid4().hex[:10]}"
    registry = ProviderRegistry()
    orchestrator = PipelineOrchestrator(provider_engine=registry.engine)

    def scene_context(scene):
        return SceneContext(prompt=f"{prompt}\nScene {scene.scene_id}: cinematic documentary coverage.")

    state = orchestrator.create_project(project_id, duration_seconds)
    state = orchestrator.run(project_id, scene_context=scene_context)

    completed = [scene for scene in state.scenes if scene.status.value == "completed" and scene.output_path]
    if not completed:
        reason = state.scenes[state.resume_from_scene - 1].failure_reason if state.scenes and state.resume_from_scene else "No scene completed."
        raise gr.Error(f"VIDEO GENERATION PAUSED\n{reason or 'No scene completed.'}")

    scene_paths = [scene.output_path for scene in completed if scene.output_path]
    output_path = Path("outputs") / f"{project_id}.mp4"
    final_path = FinalRenderer.render(scene_paths, str(output_path))

    diagnostics = (
        f"Status: {state.status.value}\n"
        f"Completed: {len(completed)} / {len(state.scenes)} scenes\n"
        f"Resume point: {state.resume_from_scene}\n"
        f"Project: {project_id}"
    )
    if state.status != ProjectStatus.COMPLETED:
        diagnostics += "\n\nRecovery: resume from the saved checkpoint."

    return final_path, diagnostics


CSS = """
:root { --castelou-gold: #b9975b; --castelou-bg: #0b0b0d; }
.gradio-container { max-width: 1100px !important; background: var(--castelou-bg) !important; }
.castelou-title { text-align: center; margin: 28px 0 34px; }
.castelou-title h1 { letter-spacing: .12em; font-weight: 700; margin-bottom: 8px; }
.castelou-title p { opacity: .65; letter-spacing: .08em; }
.castelou-card { border: 1px solid rgba(185,151,91,.22); border-radius: 18px; padding: 22px; background: rgba(255,255,255,.025); }
#prompt textarea { min-height: 150px; }
#create button { border-radius: 14px; font-weight: 700; letter-spacing: .04em; }
"""


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="CASTELOU AI DOCUMENTARY STUDIO", css=CSS) as demo:
        gr.HTML(
            """
            <div class="castelou-title">
              <h1>CASTELOU</h1>
              <p>AI DOCUMENTARY STUDIO</p>
            </div>
            """
        )

        with gr.Group(elem_classes=["castelou-card"]):
            gr.Markdown("### Type")
            content_type = gr.Radio(
                ["Documentary", "Film"],
                value="Documentary",
                label=None,
                interactive=True,
            )

            gr.Markdown("### Duration")
            duration = gr.Radio(
                list(DURATION_OPTIONS.keys()),
                value=DEFAULT_DURATION,
                label=None,
                interactive=True,
            )

            gr.Markdown("### Format")
            video_format = gr.Radio(
                ["YouTube 16:9", "Shorts 9:16"],
                value="YouTube 16:9",
                label=None,
                interactive=True,
            )

            prompt = gr.Textbox(
                label="Prompt",
                placeholder="Tell me a story about...",
                lines=5,
                elem_id="prompt",
            )
            create = gr.Button("CREATE VIDEO", variant="primary", elem_id="create")

        video = gr.Video(label="Final MP4", autoplay=False)
        diagnostics = gr.Textbox(label="Pipeline Diagnostics", lines=7, interactive=False)

        create.click(
            fn=create_video,
            inputs=[prompt, duration],
            outputs=[video, diagnostics],
        )

    return demo


if __name__ == "__main__":
    build_ui().launch(server_name=SERVER_NAME, server_port=SERVER_PORT)
