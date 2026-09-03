from pathlib import Path

import pytest

from providers.registry import ProviderRegistry


class FakeMiniMax:
    def __init__(self):
        self.calls = []

    def generate_and_download(self, prompt, output_path, duration=6, resolution="1080P"):
        self.calls.append((prompt, output_path, duration, resolution))
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"video")
        return {"output_path": output_path}


class FakeRunway:
    def __init__(self):
        self.calls = []

    def generate_video(self, prompt, ratio="1280:720", duration=5):
        self.calls.append((prompt, ratio, duration))
        return "task-1"

    def wait_for_completion(self, task_id):
        return "https://example.test/video.mp4"

    def download_video(self, url, output_path):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"video")

    def validate_video(self, output_path):
        return {"duration": 5}


def test_minimax_registry_uses_supported_durations(monkeypatch, tmp_path):
    fake = FakeMiniMax()
    monkeypatch.setattr("providers.registry.MiniMaxProvider", lambda: fake)
    registry = ProviderRegistry(media_search=object())

    scene = type("Scene", (), {"scene_id": "scene01", "visual_prompt": "cinematic shot", "prompt": "shot", "target_duration": 30})()
    result = registry._minimax(scene=scene)

    assert result.provider == "minimax"
    assert result.output_path.endswith("scene01_minimax.mp4")
    assert fake.calls[0][2] == 10
    assert Path(result.output_path).exists()


def test_runway_registry_clamps_duration_and_uses_landscape_ratio(monkeypatch, tmp_path):
    fake = FakeRunway()
    monkeypatch.setattr("providers.registry.RunwayProvider", lambda: fake)
    registry = ProviderRegistry(media_search=object())

    scene = type("Scene", (), {"scene_id": "scene02", "visual_prompt": "wide landscape", "prompt": "shot", "target_duration": 30})()
    result = registry._runway(scene=scene)

    assert result.provider == "runway"
    assert fake.calls[0][1] == "1280:720"
    assert fake.calls[0][2] == 10
    assert Path(result.output_path).exists()


def test_free_media_registry_returns_asset_metadata():
    class FakeMedia:
        def search_and_download(self, query, output_path, target_duration=None):
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(b"video")
            asset = type("Asset", (), {"asset_id": "asset-1", "metadata": lambda self: {"source": "pexels", "license_name": "Pexels License"}})()
            return asset, str(output_path)

    registry = ProviderRegistry(media_search=FakeMedia())
    scene = type("Scene", (), {"scene_id": "scene03", "prompt": "mountains", "target_duration": 30})()
    result = registry._free_media(scene=scene)

    assert result.provider == "free_media"
    assert result.asset_id == "asset-1"
    assert result.asset_metadata["license_name"] == "Pexels License"
