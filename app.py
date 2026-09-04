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
from core.job_manager import get_video_job, list_video_jobs, start_video_job
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
    return DURATION_OPTIONS.get(label, DEFAULT_DURATION and 240)


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


# Existing application helpers and UI remain below.
