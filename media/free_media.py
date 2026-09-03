"""Free stock-media search adapters with source/license metadata."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional
from urllib.parse import quote_plus

import requests


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
    """Search Pexels, Pixabay and Wikimedia Commons without exposing keys."""

    def __init__(
        self,
        *,
        pexels_api_key: str = "",
        pixabay_api_key: str = "",
        timeout: int = 20,
    ) -> None:
        self.pexels_api_key = pexels_api_key
        self.pixabay_api_key = pixabay_api_key
        self.timeout = timeout

    def search(self, query: str, *, per_source: int = 5) -> list[MediaAsset]:
        results: list[MediaAsset] = []
        if self.pexels_api_key:
            results.extend(self._pexels(query, per_source))
        if self.pixabay_api_key:
            results.extend(self._pixabay(query, per_source))
        results.extend(self._wikimedia(query, per_source))
        return results

    def _pexels(self, query: str, limit: int) -> list[MediaAsset]:
        response = requests.get(
            "https://api.pexels.com/v1/videos/search",
            headers={"Authorization": self.pexels_api_key},
            params={"query": query, "orientation": "landscape", "per_page": limit},
            timeout=self.timeout,
        )
        response.raise_for_status()
        assets: list[MediaAsset] = []
        for video in response.json().get("videos", []):
            files = video.get("video_files", [])
            if not files:
                continue
            file = max(files, key=lambda item: (item.get("width", 0), item.get("height", 0)))
            assets.append(
                MediaAsset(
                    source="pexels",
                    asset_id=str(video.get("id")),
                    title=f"Pexels video {video.get('id')}",
                    page_url=video.get("url", ""),
                    download_url=file.get("link", ""),
                    thumbnail_url=video.get("image"),
                    creator=video.get("user", {}).get("name"),
                    license_name="Pexels License",
                    license_url="https://www.pexels.com/license/",
                    width=file.get("width"),
                    height=file.get("height"),
                    duration_seconds=video.get("duration"),
                )
            )
        return assets

    def _pixabay(self, query: str, limit: int) -> list[MediaAsset]:
        response = requests.get(
            "https://pixabay.com/api/videos/",
            params={
                "key": self.pixabay_api_key,
                "q": query,
                "safesearch": "true",
                "order": "popular",
                "per_page": limit,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        assets: list[MediaAsset] = []
        for video in response.json().get("hits", []):
            variants = video.get("videos", {})
            file = variants.get("large") or variants.get("medium") or variants.get("small") or {}
            assets.append(
                MediaAsset(
                    source="pixabay",
                    asset_id=str(video.get("id")),
                    title=f"Pixabay video {video.get('id')}",
                    page_url=video.get("pageURL", ""),
                    download_url=file.get("url", ""),
                    thumbnail_url=file.get("thumbnail"),
                    creator=video.get("user"),
                    license_name="Pixabay Content License",
                    license_url="https://pixabay.com/service/license-summary/",
                    width=file.get("width"),
                    height=file.get("height"),
                )
            )
        return assets

    def _wikimedia(self, query: str, limit: int) -> list[MediaAsset]:
        response = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "format": "json",
                "generator": "search",
                "gsrsearch": f"{query} filetype:video",
                "gsrnamespace": 6,
                "gsrlimit": limit,
                "prop": "imageinfo",
                "iiprop": "url|mime|size|extmetadata",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", {})
        assets: list[MediaAsset] = []
        for page in pages.values():
            info = (page.get("imageinfo") or [{}])[0]
            mime = info.get("mime", "")
            if not mime.startswith("video/"):
                continue
            meta = info.get("extmetadata", {})
            license_name = (meta.get("LicenseShortName") or {}).get("value")
            creator = (meta.get("Artist") or {}).get("value")
            assets.append(
                MediaAsset(
                    source="wikimedia_commons",
                    asset_id=str(page.get("pageid")),
                    title=page.get("title", ""),
                    page_url="https://commons.wikimedia.org/wiki/" + quote_plus(page.get("title", "").replace(" ", "_")),
                    download_url=info.get("url", ""),
                    creator=creator,
                    license_name=license_name,
                    license_url="https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia",
                    width=info.get("width"),
                    height=info.get("height"),
                )
            )
        return assets
