# FlightPrint Architecture Notes (M2 + M6)

Author: Chillsidealways (Lidiya). Covers the evidence method, the confidence
formula (v1 → v2), and the AWS picture. Verified against
`pipeline/evidence.py`, `pipeline/stage9_ai_agent.py`,
`pipeline/stage9_detection.py` and a real end-to-end run on 2026-10-11
(synthetic city video, 11 frames, 1130 points, 2/2 anomalies verified).

## 1. Pipeline at a glance

```
video + metadata.json ─▶ stages 1–4 (frames, calibration, SIFT/ORB, poses)
  ─▶ stage 5–8 (dense cloud, mesh, georef, filtering)
  ─▶ stage 9 (AI agent: geometry → evidence → detection → Bedrock)
  ─▶ anomaly_report.json (schema v2) + evidence/ crops ─▶ FastAPI ─▶ React 3D viewer
```

Modes: FULL (video+GPS+IMU, metric georeferenced), SCALE_ASSISTED
(video+GPS or altitude, approximate metric), VISION_ONLY (relative scale).
Mode auto-detected per run (`reconstruction_mode.json`).

## 2. Evidence method (how every finding is backed by frames)

Stage 4 gives a 4×4 world-to-camera pose per frame; Stage 2 gives intrinsics
K. A 3D anomaly position X projects into frame i as
`x_cam = R_i·X + t_i`, `[u,v,1]ᵀ ~ K·x_cam / z_cam`. A frame *supports* the
finding when `z_cam > 0` and the pixel lands inside the image (5% border
margin). Supporting frames rank by centrality (70%) + camera closeness (30%),
best first, capped at 8. The top 3 are saved as 256px JPEG crops with a red
ring (`evidence/<anom>_f<frame>.jpg`). Limitation (by design): occlusion is
not modelled — a supporting frame can show a wall in front of the point; the
crop makes that visible to the reviewer.

## 3. Confidence formula

Base (v1, `pipeline/evidence.py`), all factors in [0,1]:

```
views     = 1 − e^(−n_views/4)          # how many frames see it
diversity = min(1, angle_spread_deg/30) # viewpoint spread
points    = 1 − e^(−n_points/50)        # 3D support
confidence = 0.35·signal + 0.25·views + 0.20·diversity + 0.20·points
```

No supporting frame → capped at 0.30, `evidence_level: unverified`.
Levels: strong (≥3 views, diversity ≥0.5), moderate (≥2 views), weak,
unverified. Verified in the 2026-10-11 run: `density_gap` 0.655/moderate,
`elevation_high` 0.572/moderate.

v2 additions (additive only — all v1 fields keep working for the viewer):
- **Frame detection (Oct 7+10, `stage9_detection.py`)**: YOLOv8n ONNX via
  `cv2.dnn` (no torch), off by default, sampled frames (stride 2, ≤40).
  Anomaly pixels inside a detection bbox are recorded as
  `overlapping_detections`; a *relevant*-class overlap (person, car, truck,
  … — COCO subset) blends upward:
  `confidence = 0.85·confidence + 0.15·best_detection_conf` and adds the
  `detections` factor. Non-relevant overlaps are recorded but do not boost
  (observed live: 15 `kite`/`umbrella` detections on rooftops → overlaps
  logged, factor 0.0, no boost — correct). Absence of detections never lowers
  confidence. Validated with real YOLOv8n weights (12.8 MB, 0.2 s/frame CPU).
- **Bedrock visual check (Oct 4, off by default, top-10 cap)**: vision model
  classifies each anomaly's crops (`damage`/`obstruction`/`unusual_object`/
  `none` + description + confidence); blend
  `confidence = 0.75·prior + 0.25·visual_support` (support = model confidence,
  or `1 − confidence` for `none`); `damage`/`obstruction` ≥ 0.6 raises
  severity to high. Failure keeps the geometric result with
  `visual_assessment_error`. **No live Bedrock call has succeeded yet in any
  environment (no credentials) — prompt tuning is unvalidated.**

## 4. AWS picture (target; account/compute owned by M5 Felix)

```
drone upload ─▶ S3 s3://<bucket>/jobs/<job_id>/{input/,frames/,evidence/,
                                                     anomaly_report.json,scene.ply}
pipeline job ─▶ compute (open: ECS Fargate CPU vs EC2 GPU; decision after timing)
Stage 9      ─▶ Bedrock amazon.nova-pro-v1:0 in us-east-1 (BEDROCK_MODEL_ID/AWS_REGION)
API + viewer ─▶ AWS hosting (M5); billing alarm day one; Bedrock ≤10 anomalies/run
```

## 5. Verification status (2026-10-11)

Unit: 47 tests green (`test_evidence`, `test_frame_detection`,
`test_midair_adapter`, `test_modes`, `test_evidence_accuracy`). Real runs:
synthetic-city end-to-end (stages 1–4+9, real YOLO weights) ✅; real Mid-Air
trajectory ❌ (dataset not available); live Bedrock ❌ (no credentials).
`tools/evidence_accuracy.py` implements the Oct 16 ground-truth comparison;
its Mid-Air measurement is pending data (see `docs/BUG_LOG.md`).
