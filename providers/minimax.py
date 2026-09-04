"""MiniMax video-generation provider using the current official API."""

from __future__ import annotations

import os
import time
from typing import Optional

import requests

from config import settings
from utils.errors import APIError, InvalidVideoError, VideoDownloadError, VideoGenerationError, PollingError
from utils.logger import logger
from utils.video_processor import VideoProcessor


class MiniMaxProvider:
    BASE_URL = "https://api.minimax.io"
    CREATE_ENDPOINT = "/v1/video_generation"
    QUERY_ENDPOINT = "/v1/query/video_generation"
    FILE_ENDPOINT = "/v1/files/retrieve"
    MODEL = "MiniMax-Hailuo-2.3"
    DEFAULT_DURATION = 6
    DEFAULT_RESOLUTION = "1080P"

    def __init__(self) -> None:
        self.api_key = settings.minimax_api_key
        if not self.api_key:
            raise APIError("MINIMAX_API_KEY not configured")

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def generate_video(self, prompt: str, duration: int = DEFAULT_DURATION, resolution: str = DEFAULT_RESOLUTION) -> str:
        if not prompt or not prompt.strip():
            raise VideoGenerationError("Prompt cannot be empty")
        if duration not in (6, 10):
            raise VideoGenerationError("MiniMax video duration must be 6 or 10 seconds")
        if resolution not in ("768P", "1080P"):
            raise VideoGenerationError("MiniMax resolution must be 768P or 1080P")
        # Hailuo 2.3 does not support the 10s + 1080P combination.
        if duration == 10 and resolution == "1080P":
            resolution = "768P"
        try:
            response = requests.post(
                f"{self.BASE_URL}{self.CREATE_ENDPOINT}",
                headers=self.headers,
                json={"model": self.MODEL, "prompt": prompt[:2000], "duration": duration, "resolution": resolution},
                timeout=settings.request_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            task_id = data.get("task_id")
            if not task_id:
                raise VideoGenerationError(f"MiniMax response missing task_id: {data}")
            return str(task_id)
        except VideoGenerationError:
            raise
        except requests.RequestException as exc:
            raise APIError(f"MiniMax create task failed: {exc}") from exc

    def get_task_status(self, task_id: str) -> dict:
        try:
            response = requests.get(f"{self.BASE_URL}{self.QUERY_ENDPOINT}", headers={"Authorization": f"Bearer {self.api_key}"}, params={"task_id": task_id}, timeout=settings.request_timeout_seconds)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise APIError(f"MiniMax task query failed: {exc}") from exc

    def wait_for_completion(self, task_id: str, timeout: Optional[int] = None) -> str:
        timeout = timeout or settings.polling_timeout_seconds
        interval = max(settings.polling_interval_seconds, 5)
        started = time.time()
        while time.time() - started <= timeout:
            data = self.get_task_status(task_id)
            status = str(data.get("status", "")).lower()
            if status == "success":
                file_id = data.get("file_id")
                if not file_id:
                    raise PollingError("MiniMax task succeeded without file_id")
                return str(file_id)
            if status in {"failed", "fail"}:
                raise PollingError(f"MiniMax task failed: {data.get('base_resp', {}).get('status_msg', 'unknown error')}")
            time.sleep(interval)
        raise PollingError(f"MiniMax task {task_id} timed out after {timeout}s")

    def get_download_url(self, file_id: str) -> str:
        try:
            response = requests.get(f"{self.BASE_URL}{self.FILE_ENDPOINT}", headers={"Authorization": f"Bearer {self.api_key}"}, params={"file_id": file_id}, timeout=settings.request_timeout_seconds)
            response.raise_for_status()
            data = response.json()
            url = data.get("file", {}).get("download_url")
            if not url:
                raise VideoDownloadError(f"MiniMax file response missing download_url: {data}")
            return url
        except VideoDownloadError:
            raise
        except requests.RequestException as exc:
            raise VideoDownloadError(f"MiniMax file retrieval failed: {exc}") from exc

    def download_video(self, download_url: str, output_path: str) -> None:
        try:
            response = requests.get(download_url, timeout=settings.request_timeout_seconds * 5)
            response.raise_for_status()
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "wb") as file:
                file.write(response.content)
        except Exception as exc:
            raise VideoDownloadError(f"MiniMax video download failed: {exc}") from exc

    def validate_video(self, file_path: str) -> dict:
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            raise InvalidVideoError(f"Invalid MiniMax video file: {file_path}")
        try:
            return VideoProcessor.validate_video_file(file_path)
        except Exception as exc:
            raise InvalidVideoError(f"MiniMax video validation failed: {exc}") from exc

    def generate_and_download(self, prompt: str, output_path: str, duration: int = DEFAULT_DURATION, resolution: str = DEFAULT_RESOLUTION) -> dict:
        task_id = self.generate_video(prompt, duration, resolution)
        file_id = self.wait_for_completion(task_id)
        url = self.get_download_url(file_id)
        self.download_video(url, output_path)
        metadata = self.validate_video(output_path)
        logger.info("MiniMax video completed: task=%s file=%s", task_id, file_id)
        return {"task_id": task_id, "file_id": file_id, "output_path": output_path, "metadata": metadata}
