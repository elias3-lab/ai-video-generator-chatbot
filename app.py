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
from core.job_manager import get_video_job, list_video_jobs, persistence_status, start_video_job
from core.narration import NarrationAudioSegment, NarrationPlanner, concatenate_audio_segments, probe_audio_duration
from core.orchestrator import PipelineOrchestrator
from core.dropbox_storage import storage
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


def _generate_voice_over(prompt: str, content_type: str, scenes, output_path: str, progress=None) -> tuple[str | None, str, list]:
    planned = NarrationPlanner.build_segments(prompt, scenes, content_type)
    provider = KokoroProvider(voice=settings.kokoro_voice, speed=settings.kokoro_speed)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    generated: list[NarrationAudioSegment] = []
    total = len(planned)
    for index, segment in enumerate(planned, start=1):
        if progress:
            progress(phase="Voice-over", progress=55 + int(20 * (index - 1) / max(1, total)), voice_completed=index - 1, total_voice=total, diagnostics=f"Generating voice-over {index - 1}/{total}...")
        scene_path = output.parent / f"{output.stem}_{segment.order:03d}.wav"
        provider.generate_voice_over(segment.text, str(scene_path), language=settings.default_language)
        measured = probe_audio_duration(str(scene_path))
        generated.append(NarrationAudioSegment(segment, str(scene_path), measured))
        if progress:
            progress(phase="Voice-over", progress=55 + int(20 * index / max(1, total)), voice_completed=index, total_voice=total, diagnostics=f"Voice-over {index}/{total} complete.")
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


def _persist_final_video(project_id: str, output_path: str | Path) -> str:
    path = Path(output_path)
    if storage.enabled and path.exists():
        return storage.upload_file(path, f"projects/{project_id}/final/{path.name}")
    return ""


def _restore_final_video(project_id: str, output_path: str | Path) -> bool:
    path = Path(output_path)
    if path.exists() or not storage.enabled:
        return path.exists()
    return storage.download_file(f"projects/{project_id}/final/{path.name}", path)


def _run_project(project_id: str, prompt: str, duration_label: str, content_type: str, video_format: str, progress=None):
    duration_seconds = _duration_seconds(duration_label)
    style = _content_style(content_type)
    width, height = _video_dimensions(video_format)
    registry = ProviderRegistry()
    orchestrator = PipelineOrchestrator(provider_engine=registry.engine)
    existing = orchestrator.checkpoints.load(project_id)
    total_scenes = len(existing.scenes)
    scene_order = {scene.scene_id: index for index, scene in enumerate(existing.scenes, start=1)}
    if progress:
        completed_now = sum(scene.status.value == "completed" for scene in existing.scenes)
        progress(phase="Resume", progress=min(50, 5 + completed_now * 45 // max(1, total_scenes)), scenes_completed=completed_now, total_scenes=total_scenes, diagnostics=f"Resuming project {project_id} from checkpoint...")

    def scene_context(scene):
        order = scene_order[scene.scene_id]
        subject = DirectorPlanner.scene_subject(prompt, order, total_scenes)
        return SceneContext(prompt=subject, consistency_required=True, visual_priority=0.8)

    state = orchestrator.run(project_id, scene_context=scene_context)
    completed = [scene for scene in state.scenes if scene.status.value == "completed" and scene.output_path]
    if progress:
        progress(phase="Scenes", progress=50, scenes_completed=len(completed), total_scenes=total_scenes, diagnostics=f"Scenes complete: {len(completed)}/{total_scenes}.")
    if len(completed) != len(state.scenes):
        return None, _diagnostic_report(state, duration_label, content_type, video_format)

    scene_paths = [scene.output_path for scene in completed if scene.output_path]
    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        voice_over_path, voice_status, narration_segments = _generate_voice_over(prompt, content_type, completed, str(output_dir / f"{project_id}_voice.mp3"), progress)
        if progress:
            progress(phase="Audio", progress=78, diagnostics="Building music, SFX, and subtitles...")
        audio_cues = AudioPlanner.build_cues(completed, content_type=content_type)
        music_cues = AudioPlanner.music_cues(audio_cues)
        sfx_cues = AudioPlanner.sfx_cues(audio_cues)
        music_path, generated_sfx = CinematicAudioGenerator.build_default_layers(output_dir / project_id, duration_seconds, len(completed))
        subtitle_cues = SubtitlePlanner.build_cues(narration_segments)
        subtitles_path = output_dir / f"{project_id}.srt"
        subtitles_path.write_text(SubtitlePlanner.to_srt(subtitle_cues), encoding="utf-8")
        if progress:
            progress(phase="Final Render", progress=88, diagnostics="Rendering final MP4...")
        output_path = output_dir / f"{project_id}.mp4"
        final_path = FinalRenderer.render(scene_paths, str(output_path), voice_over=voice_over_path, music=music_path, sfx=generated_sfx, duration=duration_seconds, width=width, height=height, subtitles_path=str(subtitles_path))
    except Exception as exc:
        return None, f"FINAL RENDER FAILED\n\n{_sanitize_error(exc)}"

    _persist_final_video(project_id, final_path)
    diagnostics = (f"Status: {state.status.value}\nCompleted: {len(completed)} / {len(state.scenes)} scenes\nType: {content_type}\nFormat: {video_format} ({width}x{height})\nDirector: Hook → Journey → Discovery → Ending\nAudio plan: {len(music_cues)} music cues + {len(sfx_cues)} SFX cues\nGenerated audio: cinematic music + {len(generated_sfx)} transition SFX\nSubtitles: {len(subtitle_cues)} measured narration cues attached\n{voice_status}\nProject: {project_id}")
    return final_path, diagnostics


def _create_video_sync(project_id: str, prompt: str, duration_label: str, content_type: str, video_format: str, progress=None):
    return _run_project(project_id, prompt, duration_label, content_type, video_format, progress)


def create_video(prompt: str, duration_label: str, content_type: str = DEFAULT_CONTENT_TYPE, video_format: str = DEFAULT_VIDEO_FORMAT):
    prompt = (prompt or "").strip()
    if not prompt:
        raise gr.Error("Tell CASTELOU what story to create first.")
    project_id = f"castelou-{uuid.uuid4().hex[:10]}"
    orchestrator = PipelineOrchestrator()
    try:
        orchestrator.create_project(project_id, _duration_seconds(duration_label))
    except Exception as exc:
        raise gr.Error(f"Could not create project checkpoint: {_sanitize_error(exc)}")
    job_id = start_video_job(lambda progress: _run_project(project_id, prompt, duration_label, content_type, video_format, progress), project_id=project_id)
    return None, f"Job queued: {job_id}\nProject: {project_id}\n\n{persistence_status()}\n\nProcessing on the Render server. You can close the phone while generation continues.\n\nLive progress will refresh automatically every 5 seconds.", None, job_id


def resume_video(job_id: str):
    job = get_video_job((job_id or "").strip())
    if job.status == "missing":
        raise gr.Error(f"Job not found. {persistence_status()} Start a new job only after durable persistence is configured if you need Resume after a Render restart.")
    if not job.project_id:
        raise gr.Error("This job has no resumable project ID.")
    project_id = job.project_id
    try:
        state = PipelineOrchestrator().checkpoints.load(project_id)
    except Exception as exc:
        raise gr.Error(f"Checkpoint unavailable: {_sanitize_error(exc)}")
    prompt = next((scene.prompt for scene in state.scenes if scene.prompt), "Continue the saved project from its checkpoint.")
    duration_seconds = sum(scene.target_duration or 0 for scene in state.scenes) or 180
    duration_label = min(DURATION_OPTIONS, key=lambda label: abs(DURATION_OPTIONS[label] - duration_seconds))
    new_job_id = start_video_job(lambda progress: _run_project(project_id, prompt, duration_label, DEFAULT_CONTENT_TYPE, DEFAULT_VIDEO_FORMAT, progress), project_id=project_id)
    return f"Resume started. Job: {new_job_id}\nProject: {project_id}\n\n{persistence_status()}"


def _format_job(job) -> str:
    spinner = "◐ ◓ ◑ ◒" if job.status == "running" else ""
    bar_width = 20
    filled = max(0, min(bar_width, round(job.progress / 100 * bar_width)))
    bar = "█" * filled + "░" * (bar_width - filled)
    if job.status == "completed":
        return f"Job {job.job_id}: COMPLETED\n\n🟢 Video ready\n\n{job.diagnostics}"
    if job.status == "failed":
        return f"Job {job.job_id}: FAILED\n\n🔴 {job.phase}\n\n{job.diagnostics}"
    if job.status == "missing":
        return f"Job {job.job_id}: MISSING\n\n{job.diagnostics}\n\n{persistence_status()}"
    return (f"🎬 VIDEO GENERATION — {job.job_id}\n\n🟢 {job.status.upper()}  {spinner}\n\n"
            f"Phase: {job.phase}\n\n{bar} {job.progress}%\n\n"
            f"🎥 Scenes: {job.scenes_completed}/{job.total_scenes}\n"
            f"🎙️ Voice-over: {job.voice_completed}/{job.total_voice}\n"
            f"⏱️ Elapsed: {job.elapsed_seconds:.1f}s\n"
            f"🟢 Render Server: ONLINE\n"
            f"🔃 Live update: every 5s\n\n{job.diagnostics}")


def check_video_job(job_id: str):
    normalized = (job_id or "").strip()
    if not normalized:
        return None, "Waiting for a video job...", None
    job = get_video_job(normalized)
    if job.status == "completed":
        if job.video_path:
            _restore_final_video(job.project_id or "", job.video_path)
        return job.video_path, _format_job(job), job.video_path
    return None, _format_job(job), None


def recent_resumable_jobs():
    jobs = [job for job in list_video_jobs(20) if job.project_id and job.status in {"failed", "queued", "running"}]
    if not jobs:
        return "No resumable jobs found on this server instance."
    return "\n".join(f"Job: {job.job_id} | Project: {job.project_id} | {job.status.upper()} | {job.phase} | {job.progress}%" for job in jobs)


CSS = """
:root { --castelou-gold: #b9975b; --castelou-bg: #0b0b0d; }
.gradio-container { max-width: 1100px !important; background: var(--castelou-bg) !important; }
.castelou-title { text-align: center; margin: 28px 0 34px; }
.castelou-title h1 { letter-spacing: .12em; font-weight: 700; margin-bottom: 8px; }
.castelou-title p { opacity: .65; letter-spacing: .08em; }
.castelou-card { border: 1px solid rgba(185,151,91,.22); border-radius: 18px; padding: 22px; background: rgba(255,255,255,.025); }
#prompt textarea { min-height: 180px; }
"""

with gr.Blocks(title="CASTELOU AI Documentary Studio", css=CSS) as demo:
    gr.Markdown("# CASTELOU AI DOCUMENTARY STUDIO\n### Cinematic AI video generation", elem_classes="castelou-title")
    with gr.Group(elem_classes="castelou-card"):
        prompt = gr.Textbox(label="Story / Prompt", elem_id="prompt", placeholder="Describe the documentary story you want to create...")
        with gr.Row():
            duration = gr.Dropdown(list(DURATION_OPTIONS), value=DEFAULT_DURATION, label="Duration")
            content_type = gr.Dropdown(list(CONTENT_TYPES), value=DEFAULT_CONTENT_TYPE, label="Content")
            video_format = gr.Dropdown(list(VIDEO_FORMATS), value=DEFAULT_VIDEO_FORMAT, label="Format")
        create_btn = gr.Button("🎬 CREATE VIDEO", variant="primary")
        video_output = gr.Video(label="Final Video")
        status_output = gr.Markdown("Ready.")
        job_id = gr.Textbox(label="Job ID", interactive=True)
        with gr.Row():
            check_btn = gr.Button("🔄 Check / Refresh")
            resume_btn = gr.Button("▶️ Resume Job")
        recent_output = gr.Markdown()
        timer = gr.Timer(5)

    create_btn.click(create_video, inputs=[prompt, duration, content_type, video_format], outputs=[video_output, status_output, recent_output, job_id])
    check_btn.click(check_video_job, inputs=job_id, outputs=[video_output, status_output, recent_output])
    resume_btn.click(resume_video, inputs=job_id, outputs=status_output)
    timer.tick(check_video_job, inputs=job_id, outputs=[video_output, status_output, recent_output])


if __name__ == "__main__":
    demo.launch(server_name=SERVER_NAME, server_port=SERVER_PORT)
