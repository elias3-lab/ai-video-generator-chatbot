"""Free stock-media search adapters with source/license metadata."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote
import re

import requests

from utils.video_processor import VideoProcessor


@dataclass(frozen=True)
class MediaAsset:
    source: str
    asset_id: str
    title: str
    page_url: str
    download_url: str
    thumbnail_url: Optional[str] = None
    creator: Optional[str] = None
    license_name: Optional[str] = None
    license_url: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None

    def metadata(self) -> dict[str, Any]:
        return asdict(self)


class FreeMediaSearch:
    """Search and download free stock video with source/license metadata."""

    def __init__(self, *, pexels_api_key: str = "", pixabay_api_key: str = "", timeout: int = 20) -> None:
        self.pexels_api_key = pexels_api_key
        self.pixabay_api_key = pixabay_api_key
        self.timeout = timeout

    @staticmethod
    def _clean_query(query: str, max_length: int = 90) -> str:
        """Turn a long cinematic prompt into a compact stock-footage search query."""
        text = re.sub(r"https?://\S+", " ", query or "")
        text = re.sub(r"[^\w\s,-]", " ", text, flags=re.UNICODE)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_length].strip()

    def search(self, query: str, *, per_source: int = 5) -> list[MediaAsset]:
        results: list[MediaAsset] = []
        compact_query = self._clean_query(query)
        for source in (self._pexels, self._pixabay, self._wikimedia):
            try:
                if source is self._pexels and not self.pexels_api_key:
                    continue
                if source is self._pixabay and not self.pixabay_api_key:
                    continue
                results.extend(source(compact_query, per_source))
            except requests.RequestException:
                # One unavailable stock provider must not block the others.
                continue
            except Exception:
                continue
        return results

    @staticmethod
    def select_best(assets: list[MediaAsset], *, target_duration: Optional[float] = None, prefer_landscape: bool = True) -> MediaAsset:
        if not assets:
            raise ValueError("No free-media assets found")
        source_rank = {"pexels": 3, "pixabay": 2, "wikimedia_commons": 1}

        def score(asset: MediaAsset) -> tuple[float, int, int]:
            duration_score = 0.0
            if target_duration is not None and asset.duration_seconds is not None:
                duration_score = -abs(asset.duration_seconds - target_duration)
            landscape_score = 1 if (asset.width or 0) >= (asset.height or 0) else 0
            return duration_score, landscape_score if prefer_landscape else 0, source_rank.get(asset.source, 0)

        return max(assets, key=score)

    def download(self, asset: MediaAsset, output_path: str | Path) -> str:
        if not asset.download_url:
            raise ValueError(f"Asset {asset.asset_id} has no download URL")
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(asset.download_url, stream=True, timeout=self.timeout)
        response.raise_for_status()
        with destination.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
        if not destination.exists() or destination.stat().st_size == 0:
            raise IOError(f"Downloaded media is empty: {destination}")
        return str(destination)

    def _validate_download(self, path: str) -> str:
        VideoProcessor.validate_video_file(path)
        return path

    def search_and_download(self, query: str, output_path: str | Path, *, target_duration: Optional[float] = None, per_source: int = 5) -> tuple[MediaAsset, str]:
        assets = self.search(query, per_source=per_source)
        if not assets:
            raise IOError("No free-media results found")
        ordered = sorted(
            assets,
            key=lambda item: (
                abs(item.duration_seconds - target_duration)
                if target_duration is not None and item.duration_seconds is not None
                else float("inf"),
                -(item.width or 0),
            ),
        )
        last_error: Optional[Exception] = None
        for asset in ordered:
            try:
                path = self.download(asset, output_path)
                return asset, self._validate_download(path)
            except Exception as exc:
                last_error = exc
                try:
                    Path(output_path).unlink(missing_ok=True)
                except OSError:
                    pass
        raise IOError(f"Unable to download any valid free-media result: {last_error}")

    def _pexels(self, query: str, limit: int) -> list[MediaAsset]:
        response = requests.get("https://api.pexels.com/v1/videos/search", headers={"Authorization": self.pexels_api_key}, params={"query": query, "orientation": "landscape", "per_page": limit}, timeout=self.timeout)
        response.raise_for_status()
        assets: list[MediaAsset] = []
        for video in response.json().get("videos", []):
            files = video.get("video_files", [])
            if not files:
                continue
            file = max(files, key=lambda item: (item.get("width", 0), item.get("height", 0)))
            assets.append(MediaAsset(source="pexels", asset_id=str(video.get("id")), title=f"Pexels video {video.get('id')}", page_url=video.get("url", ""), download_url=file.get("link", ""), thumbnail_url=video.get("image"), creator=video.get("user", {}).get("name"), license_name="Pexels License", license_url="https://www.pexels.com/license/", width=file.get("width"), height=file.get("height"), duration_seconds=video.get("duration")))
        return assets

    def _pixabay(self, query: str, limit: int) -> list[MediaAsset]:
        response = requests.get("https://pixabay.com/api/videos/", params={"key": self.pixabay_api_key, "q": query, "safesearch": "true", "order": "popular", "per_page": limit}, timeout=self.timeout)
        response.raise_for_status()
        assets: list[MediaAsset] = []
        for video in response.json().get("hits", []):
            variants = video.get("videos", {})
            file = variants.get("large") or variants.get("medium") or variants.get("small") or {}
            assets.append(MediaAsset(source="pixabay", asset_id=str(video.get("id")), title=f"Pixabay video {video.get('id')}", page_url=video.get("pageURL", ""), download_url=file.get("url", ""), thumbnail_url=file.get("thumbnail"), creator=video.get("user"), license_name="Pixabay Content License", license_url="https://pixabay.com/service/license-summary/", width=file.get("width"), height=file.get("height")))
        return assets

    def _wikimedia(self, query: str, limit: int) -> list[MediaAsset]:
        response = requests.get("https://commons.wikimedia.org/w/api.php", params={"action": "query", "format": "json", "generator": "search", "gsrsearch": f"{query} filetype:video", "gsrnamespace": 6, "gsrlimit": limit, "prop": "imageinfo", "iiprop": "url|mime|size|extmetadata"}, timeout=self.timeout)
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", {})
        assets: list[MediaAsset] = []
        for page in pages.values():
            info = (page.get("imageinfo") or [{}])[0]
            if not info.get("mime", "").startswith("video/"):
                continue
            meta = info.get("extmetadata", {})
            title = page.get("title", "")
            assets.append(MediaAsset(source="wikimedia_commons", asset_id=str(page.get("pageid")), title=title, page_url="https://commons.wikimedia.org/wiki/" + quote(title.replace(" ", "_")), download_url=info.get("url", ""), creator=(meta.get("Artist") or {}).get("value"), license_name=(meta.get("LicenseShortName") or {}).get("value"), license_url="https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia", width=info.get("width"), height=info.get("height")))
        return assets
