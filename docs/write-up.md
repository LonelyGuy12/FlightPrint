# FlightPrint — Submission Write-up (draft, M6)

> Draft 2026-10-11 by Lidiya (M2+M6). Figures in brackets are placeholders
> pending real Mid-Air runs — do not submit with brackets unfilled.

## What it is

FlightPrint turns one drone pass into a georeferenced 3D model, finds damage
and anomalies, and backs every finding with the video frames that show it.
Stack: OpenCV 5 ( hard requirement ✅ — running 5.0.0), FastAPI backend, React
3D viewer, AWS (S3 storage layout, Bedrock scene analysis).

## How it works (9 stages)

1–4: adaptive frame extraction → intrinsics from metadata/estimation →
SIFT/ORB matching → pose estimation with GPS/IMU fusion (FULL, SCALE_ASSISTED
or VISION_ONLY auto-detected). 5–8: dense cloud → Poisson mesh →
WGS84/UTM georeferencing → dynamic-object filtering. 9 (M2): geometric
detectors (elevation outliers, density gaps) → evidence linking (project each
finding into posed frames, rank, save ring-marked crops) → YOLOv8n frame
detection via OpenCV DNN fused by bbox overlap → optional Bedrock visual check
 top-10 cap) → `anomaly_report.json` (schema v2).

## Evidence & confidence (the core claim)

Every anomaly carries `supporting_frames` (best first), `view_angle_spread_deg`,
`confidence` + `confidence_factors`, `evidence_level`, and `visual_assessment`
after the Bedrock check. Formula:
`0.35·signal + 0.25·views + 0.20·diversity + 0.20·points`; unverified capped at
0.30; detection blend 0.85/0.15 (relevant COCO classes only); Bedrock blend
0.75/0.25. See `docs/ARCHITECTURE.md`.

## Validation

- 47 unit tests green (evidence, frame detection, adapter, modes, accuracy tool).
- Real end-to-end run (synthetic city video, 10.5 MB): stages 1–4+9 in 31 s,
  11 frames, 10 poses, 1130 points, 2/2 anomalies with frame evidence, 15 real
  YOLOv8n detections (0.2 s/frame CPU), 6/6 crops on disk.
- [PENDING] 3 Mid-Air trajectories via `tools/midair_adapter.py`; evidence
  accuracy vs `groundtruth_poses.json` via `tools/evidence_accuracy.py`
  (tool ready + tested, measurement needs data).
- [PENDING] One live Bedrock run (needs credentials in us-east-1); prompt
  tuning unvalidated until then.

## AWS usage

Target layout `s3://<bucket>/jobs/<job_id>/{input/,frames/,evidence/,
anomaly_report.json,scene.ply}`; Bedrock `amazon.nova-pro-v1:0` (us-east-1,
overridable); compute choice (ECS Fargate vs EC2 GPU) with M5 after timing;
billing alarm day one. Note: repo-local runs to date used local disk, not S3
(M3/M5 integration, Phase 3).

## Reproduce

`pip install -r requirements.txt` → `python tools/midair_adapter.py …` →
`python -m pipeline.cli --video … --metadata … --output … [--bedrock]
[--detect --yolo-model …]`. Full criteria: `docs/TEST_PLAN.md`.
