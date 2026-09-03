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

    def _register(self) -> None:
        # Factories are wrapped so a missing/invalid credential only fails the
        # current provider attempt and allows the fallback chain to continue.
        self.engine.register("minimax", self._minimax)
        self.engine.register("runway", self._runway)
        self.engine.register("free_media", self._free_media)

    def _minimax(self, *, scene: Any) -> SceneResult:
        provider = MiniMaxProvider()
        output = Path("outputs") / f"{scene.scene_id}_minimax.mp4"
        path = provider.generate_and_download(scene.visual_prompt or scene.prompt or scene.scene_id, output)
        return SceneResult(
            output_path=str(path),
            media_mode="ai_video",
            provider="minimax",
        )

    def _runway(self, *, scene: Any) -> SceneResult:
        provider = RunwayProvider()
        prompt = scene.visual_prompt or scene.prompt or scene.scene_id
        # Runway's adapter currently performs image-to-video, so this operation
        # expects a scene-provided input image path when the adapter is used.
        image_path = getattr(scene, "image_path", None)
        if not image_path:
            raise RuntimeError("Runway fallback requires a scene image_path")
        output = Path("outputs") / f"{scene.scene_id}_runway.mp4"
        task_id = provider.generate_video(image_path, prompt)
        result = provider.wait_for_completion(task_id)
        provider.download_video(result, output)
        provider.validate_video(output)
        return SceneResult(output_path=str(output), media_mode="ai_video", provider="runway")

    def _free_media(self, *, scene: Any) -> SceneResult:
        query = scene.prompt or scene.scene_id
        output = Path("outputs") / f"{scene.scene_id}_stock.mp4"
        asset, path = self.media_search.search_and_download(
            query,
            output,
            target_duration=getattr(scene, "target_duration", None),
        )
        return SceneResult(
            output_path=path,
            asset_id=asset.asset_id,
            media_mode="free_media",
            decision_reason="Free stock media selected/downloaded.",
            provider="free_media",
        )
