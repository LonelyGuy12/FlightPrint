import cv2
import numpy as np
import json
from pathlib import Path
import math

def generate_buildings_video():
    assets_dir = Path("d:/hackathons/FlightPrint/assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
    video_path = assets_dir / "test_video_buildings.mp4"
    metadata_path = assets_dir / "test_metadata_buildings.json"
    image_path = r"C:\Users\phoen\.gemini\antigravity-ide\brain\8a7378eb-f936-46a4-bd7e-d0f1213cf360\top_down_buildings_1791032542134.jpg"

    print(f"Loading AI image from: {image_path}")
    base_img = cv2.imread(image_path)
    if base_img is None:
        raise ValueError("Could not load the generated image.")

    # Upscale the image so we have plenty of room to pan
    map_size = 4000
    ground = cv2.resize(base_img, (map_size, map_size), interpolation=cv2.INTER_CUBIC)

    # Video parameters
    width, height = 1280, 720
    fps = 30
    duration = 15 # seconds
    num_frames = fps * duration

    # Drone flight path - pan over the buildings
    start_x, start_y = width // 2 + 100, map_size - (height // 2) - 100
    end_x, end_y = map_size - (width // 2) - 100, height // 2 + 100

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(str(video_path), fourcc, fps, (width, height))

    gps_track = []
    imu_data = []

    base_lat, base_lon = 40.7128, -74.0060

    print("Generating video frames...")
    for i in range(num_frames):
        t = i / float(num_frames - 1)
        
        # Smooth interpolation (ease in / ease out)
        smooth_t = t * t * (3 - 2 * t)
        
        cx = int(start_x + (end_x - start_x) * smooth_t)
        cy = int(start_y + (end_y - start_y) * smooth_t)
        
        drift_x = int(math.sin(t * math.pi * 4) * 20)
        drift_y = int(math.cos(t * math.pi * 3) * 15)
        
        cx += drift_x
        cy += drift_y
        
        half_w, half_h = width // 2, height // 2
        
        y1, y2 = cy - half_h, cy + half_h
        x1, x2 = cx - half_w, cx + half_w
        
        frame = ground[y1:y2, x1:x2]
        if frame.shape[:2] != (height, width):
             frame = cv2.resize(frame, (width, height))
        
        out.write(frame)

        # Generate GPS and IMU at 10Hz
        if i % (fps // 10) == 0:
            timestamp = i / fps
            
            dx_px = cx - start_x
            dy_px = cy - start_y
            
            dx_m = dx_px * 0.05
            dy_m = dy_px * 0.05
            
            lat = base_lat + (dy_m / 111000.0)
            lon = base_lon + (dx_m / (111000.0 * math.cos(math.radians(base_lat))))
            
            alt = 80.0 + math.sin(t * math.pi * 2) * 5.0 # Higher altitude for buildings
            
            gps_track.append({
                "timestamp": timestamp,
                "lat": lat,
                "lon": lon,
                "alt": alt
            })
            
            imu_data.append({
                "timestamp": timestamp,
                "roll": float(math.sin(t * math.pi * 6) * 1.5),
                "pitch": float(math.cos(t * math.pi * 4) * 1.5),
                "yaw": -45.0
            })

    out.release()
    print("Video generation complete.")

    metadata = {
        "camera": {
            "focal_length_mm": 24.0,
            "sensor_width_mm": 13.2,
            "image_width": width,
            "image_height": height
        },
        "gps_track": gps_track,
        "imu": imu_data
    }

    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"Generated {video_path}")
    print(f"Generated {metadata_path}")

if __name__ == "__main__":
    generate_buildings_video()
