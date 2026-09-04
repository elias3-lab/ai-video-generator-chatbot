"""Application provider registry for AI video and free-media execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from config import settings
from core.provider_engine import ProviderEngine
from core.orchestrator import SceneResult
from media.free_media import FreeMediaSearch
from providers.minimax import MiniMaxProvider
from providers.runway import RunwayProvider


class ProviderRegistry:
    """Build a lazy, credential-safe registry of available providers."""

    def __init__(self, *, media_search: Optional[FreeMediaSearch] = None) -> None:
        self.media_search = media_search or FreeMediaSearch(
            pexels_api_key=settings.pexels_api_key,
            pixabay_api_key=settings.pixabay_api_key,
        )
        self.engine = ProviderEngine()
        self._register()

    def _output_path(self, filename: str) -> Path:
        output_dir = Path(settings.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / filename

    def _register(self) -> None:
        self.engine.register("minimax", self._minimax)
        self.engine.register("runway", self._runway)
        self.engine.register("free_media", self._free_media)

    def _minimax(self, *, scene: Any) -> SceneResult:
        provider = MiniMaxProvider()
        output = self._output_path(f"{scene.scene_id}_minimax.mp4")
        result = provider.generate_and_download(
            scene.visual_prompt or scene.prompt or scene.scene_id,
            str(output),
            duration=10 if getattr(scene, "target_duration", 10) >= 10 else 6,
        )
        return SceneResult(output_path=result["output_path"], media_mode="ai_video", provider="minimax")

    def _runway(self, *, scene: Any) -> SceneResult:
        provider = RunwayProvider()
        output = self._output_path(f"{scene.scene_id}_runway.mp4")
        duration = max(2, min(10, int(getattr(scene, "target_duration", 5))))
        task_id = provider.generate_video(
            scene.visual_prompt or scene.prompt or scene.scene_id,
            ratio="1280:720",
            duration=duration,
        )
        output_url = provider.wait_for_completion(task_id)
        provider.download_video(output_url, str(output))
        provider.validate_video(str(output))
        return SceneResult(output_path=str(output), media_mode="ai_video", provider="runway")

    def _free_media(self, *, scene: Any) -> SceneResult:
        query = scene.prompt or scene.scene_id
        output = self._output_path(f"{scene.scene_id}_stock.mp4")
        asset, path = self.media_search.search_and_download(
            query, output, target_duration=getattr(scene, "target_duration", None)
        )
        return SceneResult(
            output_path=path,
            asset_id=asset.asset_id,
            asset_metadata=asset.metadata(),
            media_mode="free_media",
            decision_reason="Free stock media selected/downloaded.",
            provider="free_media",
        )
