"""CASTELOU AI Documentary Studio Gradio application."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import re
import uuid

import gradio as gr

from config import settings
from core.audio_plan import AudioPlanner
from core.cinematic_audio import CinematicAudioGenerator
from core.director import DirectorPlanner
from core.final_render import FinalRenderer
from core.job_manager import get_video_job, start_video_job
from core.narration import NarrationAudioSegment, NarrationPlanner, concatenate_audio_segments, probe_audio_duration
from core.orchestrator import PipelineOrchestrator
from core.subtitles import SubtitlePlanner
from providers.kokoro import KokoroProvider
from providers.registry import ProviderRegistry
from core.scene_decision import SceneContext

DURATION_OPTIONS = {"30s": 30, "3 min": 180, "4 min": 240, "5 min": 300}
CONTENT_TYPES = ("Documentary", "Film")
VIDEO_FORMATS = ("YouTube 16:9", "Shorts 9:16")
DEFAULT_DURATION = "4 min"
DEFAULT_CONTENT_TYPE = "Documentary"
DEFAULT_VIDEO_FORMAT = "YouTube 16:9"
SERVER_NAME = "0.0.0.0"
SERVER_PORT = 7860


def _duration_seconds(label: str) -> int:
    try:
        return DURATION_OPTIONS[label]
    except KeyError as exc:
        raise ValueError("Unsupported duration. Choose 30s, 3 min, 4 min, or 5 min.") from exc


def _content_style(content_type: str) -> str:
    if content_type == "Documentary":
        return "cinematic educational documentary, factual visual storytelling, naturalistic performances"
    if content_type == "Film":
        return "cinematic narrative film, dramatic visual storytelling, naturalistic performances"
    raise ValueError("Unsupported content type. Choose Documentary or Film.")


def _video_dimensions(video_format: str) -> tuple[int, int]:
    if video_format == "YouTube 16:9":
        return 1920, 1080
    if video_format == "Shorts 9:16":
        return 1080, 1920
    raise ValueError("Unsupported video format. Choose YouTube 16:9 or Shorts 9:16.")


def _generate_voice_over(prompt: str, content_type: str, scenes, output_path: str) -> tuple[str | None, str, list]:
    planned = NarrationPlanner.build_segments(prompt, scenes, content_type)
    provider = KokoroProvider(voice=settings.kokoro_voice, speed=settings.kokoro_speed)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    generated: list[NarrationAudioSegment] = []
    for segment in planned:
        scene_path = output.parent / f"{output.stem}_{segment.order:03d}.wav"
        provider.generate_voice_over(segment.text, str(scene_path), language=settings.default_language)
        measured = probe_audio_duration(str(scene_path))
        generated.append(NarrationAudioSegment(segment, str(scene_path), measured))
    concatenate_audio_segments(generated, str(output))
    measured_segments = [replace(item.segment, duration_seconds=item.duration_seconds) for item in generated]
    total_duration = sum(item.duration_seconds for item in generated)
    status = f"Voice-over: generated locally with Kokoro ({settings.kokoro_voice}, {len(generated)} scene tracks, {total_duration:.1f}s measured)."
    return str(output), status, measured_segments


def _sanitize_error(value: object) -> str:
    text = str(value or "").replace("\\n", " ").replace("\n", " ").strip()
    text = re.sub(r"(?i)(api[_-]?key|token|authorization|bearer|secret|password)=?[^\s,;]+", r"\1=[REDACTED]", text)
    text = re.sub(r"(?i)([?&](?:key|token|api_key)=)[^&\s]+", r"\1[REDACTED]", text)
    return text[:700]


def _diagnostic_report(state, duration_label: str, content_type: str, video_format: str) -> str:
    completed = sum(scene.status.value == "completed" for scene in state.scenes)
    current = state.current_scene or state.resume_from_scene or "unknown"
    report = ["VIDEO GENERATION PAUSED", "", f"Progress: {completed}/{len(state.scenes)} scenes completed", f"Current scene: {current}", f"Stage: {state.current_stage or 'unknown'}", f"Requested: {duration_label} | {content_type} | {video_format}", "", "PROVIDER ATTEMPTS:"]
    scene = None
    for candidate in reversed(state.scenes):
        if candidate.scene_id == current or candidate.error_message or candidate.provider_attempts:
            scene = candidate
            if candidate.error_message:
                break
    attempts = scene.provider_attempts if scene else []
    if attempts:
        for attempt in attempts:
            status = "OK" if attempt.success else "FAILED"
            detail = f" — {_sanitize_error(attempt.error)}" if attempt.error else ""
            report.append(f"• {attempt.provider}: {status}{detail}")
    else:
        report.append("• No provider attempt was recorded.")
    if scene and scene.error_message:
        report.extend(["", "FINAL ERROR:", _sanitize_error(scene.error_message)])
    report.extend(["", f"Checkpoint: {'available' if state.resume_from_scene else 'not available'}", f"Resume from: {state.resume_from_scene or 'none'}", "", "The pipeline stopped before final render because the current scene did not complete."])
    return "\n".join(report)


def _create_video_sync(prompt: str, duration_label: str, content_type: str, video_format: str):
    prompt = (prompt or "").strip()
    duration_seconds = _duration_seconds(duration_label)
    style = _content_style(content_type)
    width, height = _video_dimensions(video_format)
    project_id = f"castelou-{uuid.uuid4().hex[:10]}"
    registry = ProviderRegistry()
    orchestrator = PipelineOrchestrator(provider_engine=registry.engine)
    state = orchestrator.create_project(project_id, duration_seconds)
    scene_order = {scene.scene_id: index for index, scene in enumerate(state.scenes, start=1)}
    total_scenes = len(state.scenes)

    def scene_context(scene):
        director_prompt = DirectorPlanner.visual_prompt(prompt, scene_order[scene.scene_id], total_scenes, style, orchestrator.visual_dna.prompt_prefix())
        return SceneContext(prompt=f"{director_prompt} Output format: {video_format}.", consistency_required=True, visual_priority=0.8)

    state = orchestrator.run(project_id, scene_context=scene_context)
    completed = [scene for scene in state.scenes if scene.status.value == "completed" and scene.output_path]
    if len(completed) != len(state.scenes):
        return None, _diagnostic_report(state, duration_label, content_type, video_format)

    scene_paths = [scene.output_path for scene in completed if scene.output_path]
    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        voice_over_path, voice_status, narration_segments = _generate_voice_over(prompt, content_type, completed, str(output_dir / f"{project_id}_voice.mp3"))
        audio_cues = AudioPlanner.build_cues(completed, content_type=content_type)
        music_cues = AudioPlanner.music_cues(audio_cues)
        sfx_cues = AudioPlanner.sfx_cues(audio_cues)
        music_path, generated_sfx = CinematicAudioGenerator.build_default_layers(output_dir / project_id, duration_seconds, len(completed))
        subtitle_cues = SubtitlePlanner.build_cues(narration_segments)
        subtitles_path = output_dir / f"{project_id}.srt"
        subtitles_path.write_text(SubtitlePlanner.to_srt(subtitle_cues), encoding="utf-8")
        output_path = output_dir / f"{project_id}.mp4"
        final_path = FinalRenderer.render(scene_paths, str(output_path), voice_over=voice_over_path, music=music_path, sfx=generated_sfx, duration=duration_seconds, width=width, height=height, subtitles_path=str(subtitles_path))
    except Exception as exc:
        return None, f"FINAL RENDER FAILED\n\n{_sanitize_error(exc)}"

    diagnostics = (f"Status: {state.status.value}\nCompleted: {len(completed)} / {len(state.scenes)} scenes\nType: {content_type}\nFormat: {video_format} ({width}x{height})\nDirector: Hook → Journey → Discovery → Ending\nAudio plan: {len(music_cues)} music cues + {len(sfx_cues)} SFX cues\nGenerated audio: cinematic music + {len(generated_sfx)} transition SFX\nSubtitles: {len(subtitle_cues)} measured narration cues attached\n{voice_status}\nProject: {project_id}")
    return final_path, diagnostics


def create_video(prompt: str, duration_label: str, content_type: str = DEFAULT_CONTENT_TYPE, video_format: str = DEFAULT_VIDEO_FORMAT):
    prompt = (prompt or "").strip()
    if not prompt:
        raise gr.Error("Tell CASTELOU what story to create first.")
    job_id = start_video_job(lambda: _create_video_sync(prompt, duration_label, content_type, video_format))
    return None, f"Job queued: {job_id}\n\nProcessing on the Render server. You can close the phone and reopen the app later to check the job."


def check_video_job(job_id: str):
    job = get_video_job((job_id or "").strip())
    if job.status == "completed":
        return job.video_path, f"Job {job.job_id}: COMPLETED\n\n{job.diagnostics}"
    return None, f"Job {job.job_id}: {job.status.upper()}\n\n{job.diagnostics}"


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
        gr.HTML("""<div class="castelou-title"><h1>CASTELOU</h1><p>AI DOCUMENTARY STUDIO</p></div>""")
        with gr.Group(elem_classes=["castelou-card"]):
            gr.Markdown("### Type")
            content_type = gr.Radio(list(CONTENT_TYPES), value=DEFAULT_CONTENT_TYPE, label=None, interactive=True)
            gr.Markdown("### Duration")
            duration = gr.Radio(list(DURATION_OPTIONS.keys()), value=DEFAULT_DURATION, label=None, interactive=True)
            gr.Markdown("### Format")
            video_format = gr.Radio(list(VIDEO_FORMATS), value=DEFAULT_VIDEO_FORMAT, label=None, interactive=True)
            prompt = gr.Textbox(label="Prompt", placeholder="Tell me a story about...", lines=5, elem_id="prompt")
            create = gr.Button("CREATE VIDEO", variant="primary", elem_id="create")
        video = gr.Video(label="Final MP4", autoplay=False)
        diagnostics = gr.Textbox(label="Pipeline Diagnostics", lines=16, interactive=False)
        create.click(fn=create_video, inputs=[prompt, duration, content_type, video_format], outputs=[video, diagnostics])
        job_id = gr.Textbox(label="Job ID", interactive=True, placeholder="Paste the Job ID returned after starting a video")
        check = gr.Button("CHECK JOB")
        check.click(fn=check_video_job, inputs=[job_id], outputs=[video, diagnostics])
    return demo


if __name__ == "__main__":
    build_ui().launch(server_name=SERVER_NAME, server_port=SERVER_PORT)
