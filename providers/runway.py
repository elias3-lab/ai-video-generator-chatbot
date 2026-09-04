"""
Runway ML video generation provider.

Official API documentation:
- API Reference: https://docs.dev.runwayml.com/api/
- Getting Started: https://docs.dev.runwayml.com/guides/using-the-api/
"""

import time
import os
import requests
from typing import Optional
from utils.errors import APIError, VideoGenerationError, VideoDownloadError, PollingError, TimeoutError as VideoTimeoutError, InvalidVideoError
from utils.logger import logger
from utils.api_client import APIClient
from utils.video_processor import VideoProcessor
from config import settings


class RunwayProvider:
    BASE_URL = "https://api.dev.runwayml.com"
    CREATE_ENDPOINT = "/v1/image_to_video"
    TASK_DETAIL_ENDPOINT = "/v1/tasks"
    MODEL = "gen4.5"
    API_VERSION = "2024-11-06"
    DEFAULT_RATIO = "1280:720"
    DEFAULT_DURATION = 5
    SUPPORTED_RATIOS = {"1280:720", "720:1280"}
    MIN_DURATION = 2
    MAX_DURATION = 10
    MAX_PROMPT_LENGTH = 1000

    def __init__(self):
        self.api_key = settings.runway_api_key
        if not self.api_key:
            raise APIError("RUNWAY_API_KEY not configured")
        self.client = APIClient(api_key=self.api_key, base_url=self.BASE_URL, timeout=settings.request_timeout_seconds)

    def generate_video(self, prompt: str, ratio: str = DEFAULT_RATIO, duration: int = DEFAULT_DURATION) -> str:
        if not prompt or not prompt.strip():
            raise VideoGenerationError("Prompt cannot be empty")
        if ratio not in self.SUPPORTED_RATIOS:
            raise VideoGenerationError(f"Unsupported ratio: {ratio}. Supported: {self.SUPPORTED_RATIOS}")
        if duration < self.MIN_DURATION or duration > self.MAX_DURATION:
            raise VideoGenerationError(f"Invalid duration {duration}s. Gen-4.5 supports {self.MIN_DURATION}-{self.MAX_DURATION}s")
        prompt = prompt.strip()[: self.MAX_PROMPT_LENGTH]
        try:
            headers = {"Authorization": f"Bearer {self.api_key}", "X-Runway-Version": self.API_VERSION, "Content-Type": "application/json"}
            payload = {"model": self.MODEL, "promptText": prompt, "ratio": ratio, "duration": duration}
            logger.info(f"Runway: Submitting text-to-video request: Gen-4.5 {ratio} {duration}s")
            response = self.client.post(self.CREATE_ENDPOINT, headers=headers, json=payload)
            data = response.json()
            if "id" not in data:
                raise VideoGenerationError(f"Invalid Runway response: missing id. Response: {data}")
            task_id = data["id"]
            logger.info(f"Runway: Task created: {task_id}")
            return task_id
        except APIError:
            raise
        except Exception as e:
            logger.error(f"Runway: Video generation failed: {e}")
            raise VideoGenerationError(f"Failed to submit video generation: {e}")

    def get_task_status(self, task_id: str) -> dict:
        try:
            headers = {"Authorization": f"Bearer {self.api_key}", "X-Runway-Version": self.API_VERSION}
            response = self.client.get(f"{self.TASK_DETAIL_ENDPOINT}/{task_id}", headers=headers)
            data = response.json()
            return {"id": data.get("id"), "status": data.get("status"), "output": data.get("output")}
        except APIError:
            raise
        except Exception as e:
            logger.error(f"Runway: Query task failed: {e}")
            raise APIError(f"Failed to query task status: {e}")

    def wait_for_completion(self, task_id: str, timeout: Optional[int] = None) -> str:
        timeout = timeout or settings.polling_timeout_seconds
        interval = settings.polling_interval_seconds
        start_time = time.time()
        while True:
            if time.time() - start_time > timeout:
                raise VideoTimeoutError(f"Runway task {task_id} did not complete within {timeout}s")
            try:
                status_data = self.get_task_status(task_id)
                if status_data["status"] == "SUCCEEDED":
                    output = status_data.get("output")
                    if not output:
                        raise PollingError("Task succeeded but no output returned")
                    return output[0]
                if status_data["status"] == "FAILED":
                    raise PollingError("Runway task failed")
                if status_data["status"] == "CANCELED":
                    raise PollingError("Runway task was canceled")
                time.sleep(interval)
            except (VideoTimeoutError, PollingError):
                raise
            except Exception as e:
                logger.error(f"Runway: Error polling task: {e}")
                time.sleep(interval)

    def download_video(self, output_url: str, output_path: str) -> None:
        try:
            response = requests.get(output_url, timeout=settings.request_timeout_seconds * 5)
            response.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(response.content)
        except Exception as e:
            raise VideoDownloadError(f"Failed to download video: {e}")

    def validate_video(self, file_path: str) -> dict:
        if not os.path.exists(file_path):
            raise InvalidVideoError(f"Video file not found: {file_path}")
        if os.path.getsize(file_path) == 0:
            raise InvalidVideoError(f"Video file is empty: {file_path}")
        try:
            return VideoProcessor.validate_video_file(file_path)
        except Exception as e:
            raise InvalidVideoError(f"Video validation failed: {e}")
