# 🛩️ FlightPrint

**AI-powered 3D reconstruction from drone video** — reconstruct georeferenced, structured 3D models and detect anomalies from a single-pass drone flight.

---

## 🌟 Key Features

- **Single-Pass 3D Reconstruction**: Estimates camera intrinsics, poses, and dense point clouds from aerial drone video and GPS/IMU telemetry.
- **Dynamic 3D City Meshing**: Procedurally generates structured building geometry, textured rooftops, facades, and road networks aligned with flight telemetry without requiring pre-baked assets.
- **Georeferencing & Filtering**: WGS84 to UTM coordinate mapping, camera trajectory alignment, and dynamic outlier filtering.
- **AI-Powered Anomaly & Threat Detection**: Detects geometric anomalies fused with Amazon Bedrock (Amazon Nova Pro) visual reasoning and YOLOv8 object detection.
- **Interactive 3D Web Viewer**: High-performance Three.js/React-Three-Fiber frontend with orbit controls, point cloud vs. mesh toggles, trajectory overlays, and telemetry inspection.

---

## 🏗️ Architecture & Pipeline

```
Drone Video (MP4) + Telemetry (GPS / IMU JSON)
                    │
                    ▼
┌─────────────────────────────────────────────────────────┐
│ Stage 1: Frame Extraction (Adaptive sampling & dedup)   │
│ Stage 2: Camera Calibration (Intrinsics estimation)     │
│ Stage 3: Feature Detection (SIFT / ORB matching)        │
│ Stage 4: Pose Estimation (Essential matrix + GPS fusion)│
│ Stage 5: Dense Reconstruction (Optical-flow triangulation)
│ Stage 6: 3D Meshing (Procedural structured city mesh)   │
│ Stage 7: Georeferencing (WGS84 / UTM coordinate mapping)│
│ Stage 8: Filtering (Dynamic outlier & noise rejection)  │
│ Stage 9: AI Agent (Bedrock Nova Pro + YOLO detection)   │
│ Stage 10: Web Delivery (Interactive 3D viewer & report) │
└─────────────────────────────────────────────────────────┘
                    │
                    ▼
   FastAPI Backend (8000) ──► React / Three.js Frontend (5173)
```

| Stage | Description | Status |
|-------|-------------|--------|
| **1. Frame Extraction** | Adaptive sampling, keyframe selection, deduplication | ✅ Complete |
| **2. Camera Calibration** | Focal length, principal point, and distortion estimation | ✅ Complete |
| **3. Feature Detection** | SIFT/ORB feature extraction and cross-frame matching | ✅ Complete |
| **4. Pose Estimation** | Essential matrix estimation, RANSAC, GPS/IMU trajectory fusion | ✅ Complete |
| **5. Triangulation & Dense Cloud** | Optical flow triangulation + sparse cloud fusion | ✅ Complete |
| **6. 3D Meshing** | High-fidelity procedural building geometry, facades & terrain | ✅ Complete |
| **7. Georeferencing** | WGS84 to UTM coordinate transforms & GPS registration | ✅ Complete |
| **8. Filtering** | Statistical outlier removal and dynamic object filtering | ✅ Complete |
| **9. AI Agent & Vision** | Geometric anomaly detection + Amazon Bedrock + YOLOv8 | ✅ Complete |
| **10. Web Viewer** | Real-time interactive 3D WebGL viewer & inspection dashboard | ✅ Complete |

---

## 🚀 Quick Start: Running Backend & Web Server

### Prerequisites

- **Python 3.10+** (OpenCV 5.x or 4.8+)
- **Node.js 18+** & **npm**

---

### Step 1: Environment & Python Setup

Clone the repository and set up a Python virtual environment:

```bash
git clone https://github.com/LonelyGuy12/FlightPrint.git
cd FlightPrint

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

Verify your setup:
```bash
python -c "import cv2; print('OpenCV version:', cv2.__version__)"
python -m pytest tests/ -v
```

---

### Step 2: Start the Backend Server

The backend runs on **FastAPI** with **Uvicorn**:

```bash
# Make sure your virtual environment is active
source .venv/bin/activate

# Navigate to backend directory and start Uvicorn
cd backend
uvicorn app.main:app --reload --port 8000
```

- **Backend API URL**: `http://localhost:8000`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`
- **Health Check / Jobs**: `http://localhost:8000/api/pipeline/jobs`

---

### Step 3: Start the Frontend Web Server

In a **separate terminal window**, launch the Vite-powered React web application:

```bash
cd FlightPrint/frontend

# Install frontend dependencies (first time only)
npm install

# Start Vite development server
npm run dev
```

- **Web Application URL**: `http://localhost:5173`
- The viewer connects directly to the backend at `http://localhost:8000`.

---

## 💻 Running the Reconstruction Pipeline

### Option A: Using the Web UI (Recommended)
1. Open `http://localhost:5173` in your browser.
2. Upload your drone video (`.mp4`) and flight telemetry (`metadata.json`).
3. Click **Start Pipeline**.
4. Monitor live stage-by-stage progress and explore the rendered 3D scene in the interactive viewer once complete.

### Option B: Using the CLI
You can also run the full pipeline directly from the command line:

```bash
source .venv/bin/activate

# Basic run
python -m pipeline.cli \
  --video data/sample_flight.mp4 \
  --metadata data/flight_metadata.json \
  --output backend/output/demo_run

# With Amazon Bedrock AI anomaly assessment enabled:
python -m pipeline.cli \
  --video data/sample_flight.mp4 \
  --metadata data/flight_metadata.json \
  --output backend/output/demo_run \
  --bedrock
```

---

## ⚙️ Configuration & AI Models

| Environment Variable | Default | Description |
|---|---|---|
| `BEDROCK_MODEL_ID` | `amazon.nova-pro-v1:0` | Amazon Bedrock vision model ID for Stage 9 anomaly assessment |
| `AWS_REGION` | `us-east-1` | AWS Region for Amazon Bedrock service |
| `FLIGHTPRINT_USE_BEDROCK` | `0` (off) | Set to `1` to enable Bedrock multimodal checks by default |
| `YOLO_MODEL_PATH` | _(empty)_ | File path to YOLOv5/YOLOv8 `.onnx` model weights |
| `FLIGHTPRINT_USE_DETECTION` | `0` (off) | Set to `1` to enable YOLOv8 frame detection by default |

### Stage 9: Amazon Bedrock Vision Check
Stage 9 inspects the reconstructed scene for anomalies. When enabled with `--bedrock` (or `FLIGHTPRINT_USE_BEDROCK=1`), detected anomaly crops are sent to Amazon Bedrock Nova Pro for semantic identification:
- Produces `visual_assessment` tags (`label`, `description`, `confidence`).
- Stored directly in `output/<job_id>/anomaly_report.json`.

### Stage 9: YOLO Frame Detection
Stage 9 can run real-time COCO-80 object detection via OpenCV DNN:
```bash
python -m pipeline.cli --video flight.mp4 --metadata meta.json --output out/ --detect --yolo-model models/yolov8n.onnx
```

---

## 📁 Input Metadata Format

FlightPrint uses synchronization between video frames and GPS/IMU telemetry:

```json
{
  "camera": {
    "focal_length_mm": 24.0,
    "sensor_width_mm": 13.2,
    "image_width": 1920,
    "image_height": 1080
  },
  "gps_track": [
    {"timestamp": 0.0, "lat": 37.7749, "lon": -122.4194, "alt": 100.0},
    {"timestamp": 1.0, "lat": 37.7751, "lon": -122.4192, "alt": 100.5}
  ],
  "imu": [
    {"timestamp": 0.0, "roll": 0.1, "pitch": -0.05, "yaw": 45.2},
    {"timestamp": 1.0, "roll": 0.12, "pitch": -0.04, "yaw": 45.8}
  ]
}
```

---

## 🧪 Testing & Verification

Run the automated test suite across all pipeline stages:

```bash
source .venv/bin/activate
pytest tests/ -v
```

Additional documentation:
- `docs/TEST_PLAN.md` — Test procedures, environment setup, Mid-Air benchmark evaluation.
- `docs/BUG_LOG.md` — Observed issues and tracked resolutions.
- `tools/README.md` — Mid-Air dataset adapter and synthetic test tools.
