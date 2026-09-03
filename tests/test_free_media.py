from pathlib import Path

from media.free_media import FreeMediaSearch, MediaAsset


def test_search_and_download_skips_invalid_asset_and_uses_next(monkeypatch, tmp_path):
    searcher = FreeMediaSearch()
    assets = [
        MediaAsset(
            source="pexels",
            asset_id="bad",
            title="Invalid video",
            page_url="https://example.test/bad",
            download_url="https://example.test/bad.mp4",
            width=1920,
            height=1080,
            duration_seconds=10,
        ),
        MediaAsset(
            source="pexels",
            asset_id="good",
            title="Valid video",
            page_url="https://example.test/good",
            download_url="https://example.test/good.mp4",
            width=1920,
            height=1080,
            duration_seconds=10,
        ),
    ]

    monkeypatch.setattr(searcher, "search", lambda query, per_source=5: assets)

    def fake_download(asset, destination):
        Path(destination).write_bytes(asset.asset_id.encode())
        return str(destination)

    def fake_validate(path):
        if Path(path).read_bytes() == b"bad":
            raise ValueError("invalid video file")
        return path

    monkeypatch.setattr(searcher, "download", fake_download)
    monkeypatch.setattr(searcher, "_validate_download", fake_validate)

    output = tmp_path / "scene.mp4"
    asset, path = searcher.search_and_download("mountains", output, target_duration=10)

    assert asset.asset_id == "good"
    assert path == str(output)
    assert output.read_bytes() == b"good"


def test_search_and_download_raises_when_every_download_is_invalid(monkeypatch, tmp_path):
    searcher = FreeMediaSearch()
    assets = [
        MediaAsset(
            source="wikimedia_commons",
            asset_id="bad-1",
            title="Invalid 1",
            page_url="https://example.test/1",
            download_url="https://example.test/1.mp4",
            width=1920,
            height=1080,
            duration_seconds=10,
        ),
        MediaAsset(
            source="wikimedia_commons",
            asset_id="bad-2",
            title="Invalid 2",
            page_url="https://example.test/2",
            download_url="https://example.test/2.mp4",
            width=1920,
            height=1080,
            duration_seconds=10,
        ),
    ]

    monkeypatch.setattr(searcher, "search", lambda query, per_source=5: assets)
    monkeypatch.setattr(
        searcher,
        "download",
        lambda asset, destination: Path(destination).write_bytes(b"invalid") or str(destination),
    )
    monkeypatch.setattr(searcher, "_validate_download", lambda path: (_ for _ in ()).throw(ValueError("invalid video file")))

    output = tmp_path / "scene.mp4"
    try:
        searcher.search_and_download("mountains", output, target_duration=10)
        assert False, "expected invalid-media failure"
    except IOError as exc:
        assert "Unable to download any valid free-media result" in str(exc)

    assert not output.exists()
