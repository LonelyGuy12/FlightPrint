# 🛩️ FlightPrint

**AI-powered 3D reconstruction from drone video** — reconstruct georeferenced, textured 3D models from a single-pass drone flight.

## Quick Start

```bash
# Install Python dependencies
pip install -r requirements.txt

# Sanity checks: OpenCV 5 (competition rule) + test suite
python -c "import cv2; print(cv2.__version__)"  # expect 5.x
python -m pytest tests/ -v

# Run the backend
cd backend
uvicorn app.main:app --reload --port 8000

# Run the frontend (separate terminal)
cd frontend
npm install && npm run dev
```

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `BEDROCK_MODEL_ID` | `amazon.nova-pro-v1:0` | Vision model for the Stage 9 visual check |
| `AWS_REGION` | `us-east-1` | AWS region for Bedrock (needs model access) |
| `FLIGHTPRINT_USE_BEDROCK` | off | Set to `1` to enable the Stage 9 visual check without a config file |
| `YOLO_MODEL_PATH` | _(empty)_ | Path to YOLOv5/YOLOv8 `.onnx` weights for Stage 9 frame detection |
| `FLIGHTPRINT_USE_DETECTION` | off | Set to `1` to enable Stage 9 frame detection without a config file |

The Stage 9 Bedrock visual check is **off by default** (no surprise AWS calls).
Enable it for one run with any of:

```bash
# CLI flag
python -m pipeline.cli --video <video.mp4> --metadata <metadata.json> --output <out> --bedrock

# Config JSON: {"stage9": {"use_bedrock": true}}
python -m pipeline.cli --video <video.mp4> --metadata <metadata.json> --output <out> --config bedrock.json

# API: POST /api/pipeline/run/{job_id} with {"config": {"stage9": {"use_bedrock": true}}}
```

At most the top 10 anomalies per run are sent to Bedrock (see
`max_bedrock_anomalies`). Each checked anomaly gets `visual_assessment`
(`label`, `description`, `confidence`, `model`) in `anomaly_report.json`;
failed checks keep the geometric result with a `visual_assessment_error` note.

Stage 9 frame object detection (YOLO via OpenCV DNN, any 80-class COCO
`.onnx` — weights not in the repo) is likewise **off by default**:

```bash
python -m pipeline.cli --video <video.mp4> --metadata <metadata.json> --output <out> --detect --yolo-model models/yolov8n.onnx
# Or config JSON: {"stage9": {"use_frame_detection": true, "yolo_model_path": "models/yolov8n.onnx"}}
```

Fused anomalies get `overlapping_detections` plus a `detections` confidence
factor; anomalies with no overlap are untouched.

## Testing & docs

- `docs/TEST_PLAN.md` — environment, Mid-Air data, Stage 1–9 and Bedrock
  procedures, expected outputs, pass/fail criteria.
- `docs/BUG_LOG.md` — observed issues only, with reproduction and status.
- `tools/README.md` — Mid-Air adapter usage plus test-data layout and where
  `anomaly_report.json` / `evidence/` outputs land.

## Pipeline

| Stage | Description | Status |
|-------|-------------|--------|
| 1. Frame Extraction | Adaptive sampling + deduplication | ✅ |
| 2. Camera Calibration | Intrinsics from metadata or estimation | ✅ |
| 3. Feature Detection | SIFT/ORB matching across frames | ✅ |
| 4. Pose Estimation | Essential matrix + GPS/IMU fusion | ✅ |
| 5. Triangulation | Sparse → dense point cloud | 🔄 |
| 6. Meshing | Poisson surface reconstruction | 🔄 |
| 7. Georeferencing | WGS84/UTM transform | 🔄 |
| 8. Filtering | Dynamic object removal | 🔄 |
| 9. AI Agent | Anomaly detection & scene understanding | 🔄 |
| 10. Delivery | Interactive web viewer | 🔄 |

## Architecture

```
Drone Video + GPS/IMU → Frame Extraction → Feature Matching → Pose Estimation
    → Triangulation → Meshing → Georeferencing → AI Analysis → Web Viewer
```

## Input Format

- **Video**: MP4 (1080p or 4K)
- **Metadata JSON**:
```json
{
  "gps_track": [
    {"timestamp": 0.0, "lat": 37.7749, "lon": -122.4194, "alt": 100.0}
  ],
  "camera": {
    "focal_length_mm": 24,
    "sensor_width_mm": 13.2,
    "image_width": 1920,
    "image_height": 1080
  },
  "imu": [
    {"timestamp": 0.0, "roll": 0.1, "pitch": -0.05, "yaw": 45.2}
  ]
}
```
