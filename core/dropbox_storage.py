"""Dropbox-backed artifact store for Render's ephemeral filesystem."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import requests


class DropboxStorage:
    def __init__(self) -> None:
        self.token = os.getenv("DROPBOX_ACCESS_TOKEN", "").strip()
        self.base_path = "/" + os.getenv("DROPBOX_BASE_PATH", "CASTELOU/video-generator").strip("/")

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def _path(self, remote_path: str) -> str:
        return f"{self.base_path}/{remote_path.strip('/')}"

    @staticmethod
    def _is_final_path(remote_path: str) -> bool:
        parts = [p for p in remote_path.strip("/").split("/") if p]
        return "final" in parts

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def ensure_folder(self, remote_folder: str) -> None:
        if not self.enabled or self._is_final_path(remote_folder):
            return
        parts = [p for p in remote_folder.strip("/").split("/") if p]
        current = ""
        for part in parts:
            current = f"{current}/{part}"
            response = requests.post(
                "https://api.dropboxapi.com/2/files/create_folder_v2",
                headers={**self._headers(), "Content-Type": "application/json"},
                json={"path": self._path(current), "autorename": False},
                timeout=30,
            )
            if response.status_code not in (200, 409):
                response.raise_for_status()

    def upload_bytes(self, data: bytes, remote_path: str) -> str:
        if not self.enabled or self._is_final_path(remote_path):
            return ""
        self.ensure_folder(str(Path(remote_path).parent).replace("\\", "/"))
        response = requests.post(
            "https://content.dropboxapi.com/2/files/upload",
            headers={
                **self._headers(),
                "Content-Type": "application/octet-stream",
                "Dropbox-API-Arg": json.dumps({"path": self._path(remote_path), "mode": "overwrite", "autorename": False, "mute": True}),
            },
            data=data,
            timeout=300,
        )
        response.raise_for_status()
        return self._path(remote_path)

    def upload_file(self, local_path: str | Path, remote_path: str) -> str:
        source = Path(local_path)
        if not source.exists() or not source.is_file():
            return ""
        return self.upload_bytes(source.read_bytes(), remote_path)

    def download_bytes(self, remote_path: str) -> Optional[bytes]:
        if not self.enabled or self._is_final_path(remote_path):
            return None
        response = requests.post(
            "https://content.dropboxapi.com/2/files/download",
            headers={**self._headers(), "Dropbox-API-Arg": json.dumps({"path": self._path(remote_path)})},
            timeout=300,
        )
        if response.status_code == 409:
            return None
        response.raise_for_status()
        return response.content

    def download_file(self, remote_path: str, local_path: str | Path) -> bool:
        data = self.download_bytes(remote_path)
        if data is None:
            return False
        destination = Path(local_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return True

    def list_files(self, remote_folder: str) -> list[str]:
        if not self.enabled or self._is_final_path(remote_folder):
            return []
        response = requests.post(
            "https://api.dropboxapi.com/2/files/list_folder",
            headers={**self._headers(), "Content-Type": "application/json"},
            json={"path": self._path(remote_folder), "recursive": False},
            timeout=30,
        )
        if response.status_code == 409:
            return []
        response.raise_for_status()
        data = response.json()
        paths = [e.get("path_display", "") for e in data.get("entries", []) if e.get(".tag") == "file"]
        while data.get("has_more"):
            response = requests.post(
                "https://api.dropboxapi.com/2/files/list_folder/continue",
                headers={**self._headers(), "Content-Type": "application/json"},
                json={"cursor": data["cursor"]},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            paths.extend(e.get("path_display", "") for e in data.get("entries", []) if e.get(".tag") == "file")
        prefix = self.base_path.rstrip("/") + "/"
        return [p[len(prefix):] if p.startswith(prefix) else p.lstrip("/") for p in paths]


storage = DropboxStorage()
