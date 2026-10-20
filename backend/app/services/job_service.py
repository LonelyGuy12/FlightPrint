"""Service for managing uploaded jobs and their in-memory/persisted records."""

import time
import uuid
import json
import shutil
from pathlib import Path
from typing import Any
from fastapi import UploadFile, HTTPException

from ..config import settings
from ..utils.file_utils import (
    validate_video_extension,
    validate_json_extension,
    save_upload_file,
    get_file_size_mb,
    ensure_dir,
)


class JobService:
    """Manages jobs storage, lookups, and file uploads."""

    def __init__(self):
        # In-memory job registry (would be Redis/DB in production)
        self.jobs: dict[str, dict[str, Any]] = {}

    def get_job(self, job_id: str) -> dict[str, Any]:
        """Fetch job info by job_id or discover from output directory."""
        if job_id in self.jobs:
            return self.jobs[job_id]

        # Auto-discover from output directory if server restarted
        out_dir = settings.output_dir / job_id
        if out_dir.exists() and out_dir.is_dir():
            job_record = {
                "job_id": job_id,
                "status": "completed",
                "output_dir": str(out_dir),
                "created_at": out_dir.stat().st_mtime,
            }
            self.jobs[job_id] = job_record
            return job_record

        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    def list_jobs(self) -> list[dict[str, Any]]:
        """List all active and discovered jobs."""
        # Discover existing output dirs
        if settings.output_dir.exists():
            for p in settings.output_dir.iterdir():
                if p.is_dir() and not p.name.startswith("."):
                    if p.name not in self.jobs:
                        self.jobs[p.name] = {
                            "job_id": p.name,
                            "status": "completed",
                            "output_dir": str(p),
                            "created_at": p.stat().st_mtime,
                        }
        return sorted(list(self.jobs.values()), key=lambda j: j.get("created_at", 0), reverse=True)

    def update_job_status(self, job_id: str, status: str, **kwargs: Any) -> dict[str, Any]:
        """Update fields on a job record."""
        job_info = self.get_job(job_id)
        job_info["status"] = status
        job_info.update(kwargs)
        return job_info

    async def create_job_from_upload(
        self,
        video: UploadFile,
        metadata: UploadFile | None = None,
    ) -> dict[str, Any]:
        """Validate, store uploaded video and metadata, and register job."""
        validate_video_extension(video.filename)

        if metadata is not None:
            validate_json_extension(metadata.filename)

        job_id = str(uuid.uuid4())[:8]
        job_dir = settings.upload_dir / job_id
        ensure_dir(job_dir)

        # Save video file
        video_filename = video.filename or "video.mp4"
        video_path = job_dir / video_filename
        await save_upload_file(video, video_path)

        # Save metadata (if provided)
        meta_path = None
        if metadata is not None:
            meta_path = job_dir / "metadata.json"
            meta_content = await metadata.read()
            try:
                json.loads(meta_content)  # Validate JSON content
            except json.JSONDecodeError:
                shutil.rmtree(job_dir, ignore_errors=True)
                raise HTTPException(status_code=400, detail="Metadata file contains invalid JSON")

            with open(meta_path, "wb") as f:
                f.write(meta_content)

        # Register job in store
        job_record = {
            "job_id": job_id,
            "status": "uploaded",
            "video_filename": video_filename,
            "video_path": str(video_path),
            "metadata_path": str(meta_path) if meta_path else None,
            "has_metadata": meta_path is not None,
            "created_at": time.time(),
            "output_dir": str(settings.output_dir / job_id),
        }
        self.jobs[job_id] = job_record

        return {
            "job_id": job_id,
            "message": f"Uploaded {video_filename} successfully"
                       + (" (no metadata — vision-only mode)" if meta_path is None else ""),
            "video_size_mb": get_file_size_mb(video_path),
            "has_metadata": meta_path is not None,
            "job_info": job_record,
        }


# Global singleton instance
job_service = JobService()
