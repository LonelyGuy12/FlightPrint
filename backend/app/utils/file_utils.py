"""Reusable file and filesystem utilities for backend services."""

import json
from pathlib import Path
from typing import Any
from fastapi import UploadFile, HTTPException

VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".mkv")

MIME_TYPES = {
    ".ply": "application/octet-stream",
    ".obj": "text/plain",
    ".json": "application/json",
    ".geojson": "application/geo+json",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".npy": "application/octet-stream",
}


def validate_video_extension(filename: str | None) -> None:
    """Validate that filename has a supported video extension."""
    if not filename or not filename.lower().endswith(VIDEO_EXTENSIONS):
        raise HTTPException(status_code=400, detail="Video must be MP4, AVI, MOV, or MKV")


def validate_json_extension(filename: str | None) -> None:
    """Validate that filename has a JSON extension."""
    if not filename or not filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="Metadata must be a JSON file")


async def save_upload_file(upload_file: UploadFile, destination: Path, chunk_size: int = 8192) -> int:
    """Stream an UploadFile to disk and return total bytes written."""
    total_bytes = 0
    with open(destination, "wb") as f:
        while chunk := await upload_file.read(chunk_size):
            f.write(chunk)
            total_bytes += len(chunk)
    return total_bytes


def read_json_file(file_path: Path, default: Any = None) -> Any:
    """Safely read and parse a JSON file if it exists."""
    if not file_path.exists():
        return default
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def get_file_size_kb(file_path: Path, precision: int = 1) -> float:
    """Return file size in kilobytes."""
    return round(file_path.stat().st_size / 1024, precision)


def get_file_size_mb(file_path: Path, precision: int = 1) -> float:
    """Return file size in megabytes."""
    return round(file_path.stat().st_size / 1_000_000, precision)


def ensure_dir(path: Path) -> Path:
    """Ensure directory exists and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_safe_subpath(base_dir: Path, subpath: str) -> Path:
    """Ensure the resolved subpath does not escape base_dir."""
    target_path = base_dir / subpath
    try:
        target_path.resolve().relative_to(base_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")
    return target_path
