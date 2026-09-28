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


class SupportingFrame(BaseModel):
    """A video frame in which an anomaly is visible."""
    frame_index: int
    timestamp: float | None = None
    frame_path: str | None = None
    pixel: list[float]
    depth: float | None = None
    centrality: float | None = None
    score: float | None = None
    crop_path: str | None = None


class VisualAssessment(BaseModel):
    """What a Bedrock vision model saw in the evidence crops."""
    label: str  # damage | obstruction | unusual_object | none
    description: str = ""
    confidence: float
    model: str | None = None
    crops_checked: int = 0


class AnomalyItem(BaseModel):
    """A detected anomaly in the scene."""
    type: str
    description: str
    position_enu: list[float] | None = None
    position_gps: dict | None = None
    confidence: float = 0.5
    severity: str = "low"
    num_points: int | None = None
    # Evidence (anomaly report schema v2)
    id: str | None = None
    source: str | None = None
    signal_strength: float | None = None
    supporting_frames: list[SupportingFrame] = []
    view_angle_spread_deg: float | None = None
    evidence_level: str | None = None  # strong | moderate | weak | unverified
    confidence_factors: dict[str, float] = {}
    visual_assessment: VisualAssessment | None = None


class AnomalyReport(BaseModel):
    """Full anomaly report from the AI agent."""
    schema_version: int = 1
    total_anomalies: int
    verified_anomalies: int | None = None
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
