"""Pydantic models for FlightPrint API."""

from pydantic import BaseModel
from typing import Optional


class PipelineRequest(BaseModel):
    """Request to start a pipeline run."""
    job_id: str | None = None
    stages: list[int] | None = None  # None = run all stages
    config: dict | None = None


class ScaleRequest(BaseModel):
    """Request to apply manual scale factor."""
    scale_factor: float


class PipelineProgress(BaseModel):
    """Pipeline progress update."""
    job_id: str
    pipeline_status: str
    current_stage: str | None = None
    stages: dict = {}
    error: str | None = None


class AnomalyItem(BaseModel):
    """A detected anomaly in the scene."""
    type: str
    description: str
    position_enu: list[float] | None = None
    position_gps: dict | None = None
    confidence: float = 0.5
    severity: str = "low"
    num_points: int | None = None


class AnomalyReport(BaseModel):
    """Full anomaly report from the AI agent."""
    total_anomalies: int
    anomalies: list[AnomalyItem]


class JobInfo(BaseModel):
    """Information about a pipeline job."""
    job_id: str
    status: str
    video_filename: str
    created_at: float
    completed_at: float | None = None
    num_frames: int | None = None
    num_points: int | None = None
    has_mesh: bool = False
    has_anomalies: bool = False
