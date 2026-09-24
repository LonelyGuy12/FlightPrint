# 🛩️ FlightPrint

**AI-powered 3D reconstruction from drone video** — reconstruct georeferenced, textured 3D models from a single-pass drone flight.

## Quick Start

```bash
# Install Python dependencies
pip install -r requirements.txt

# Run the backend
cd backend
uvicorn app.main:app --reload --port 8000

# Run the frontend (separate terminal)
cd frontend
npm install && npm run dev
```

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
