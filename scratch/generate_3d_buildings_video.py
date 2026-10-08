import cv2
import numpy as np
import json
import math
from pathlib import Path
import random

def get_rotation_matrix(pitch, yaw, roll):
    # pitch (x), yaw (y), roll (z)
    Rx = np.array([
        [1, 0, 0],
        [0, math.cos(pitch), -math.sin(pitch)],
        [0, math.sin(pitch), math.cos(pitch)]
    ])
    Ry = np.array([
        [math.cos(yaw), 0, math.sin(yaw)],
        [0, 1, 0],
        [-math.sin(yaw), 0, math.cos(yaw)]
    ])
    Rz = np.array([
        [math.cos(roll), -math.sin(roll), 0],
        [math.sin(roll), math.cos(roll), 0],
        [0, 0, 1]
    ])
    return Rz @ Ry @ Rx

def project_points(pts_3d, K, R, t):
    # pts_3d: N x 3
    # R: 3 x 3, t: 3
    # K: 3 x 3
    pts_cam = (R @ pts_3d.T).T + t
    
    # Filter points behind camera
    valid = pts_cam[:, 2] > 0.1
    pts_cam_valid = pts_cam[valid]
    
    pts_2d_hom = (K @ pts_cam_valid.T).T
    pts_2d = pts_2d_hom[:, :2] / pts_2d_hom[:, 2:3]
    
    return pts_2d, valid, pts_cam[:, 2]

def generate_3d_buildings_video():
    assets_dir = Path("d:/hackathons/FlightPrint/assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
    video_path = assets_dir / "test_video_3d.mp4"
    metadata_path = assets_dir / "test_metadata_3d.json"

    width, height = 1280, 720
    fps = 30
    duration = 10
    num_frames = fps * duration

    # Camera intrinsics
    focal_length = 800.0
    K = np.array([
        [focal_length, 0, width / 2],
        [0, focal_length, height / 2],
        [0, 0, 1]
    ])

    # Generate scene
    # Buildings defined by (x, z, w, d, h)
    buildings = [
        (0, 0, 40, 40, 80),
        (-60, -50, 30, 30, 120),
        (50, -30, 25, 45, 60),
        (-30, 70, 35, 35, 90),
        (80, 60, 40, 30, 50)
    ]

    # Generate random 3D points on surfaces to act as features for SfM
    pts = []
    colors = []

    # Ground points
    for _ in range(30000):
        x = random.uniform(-150, 150)
        z = random.uniform(-150, 150)
        y = 0
        # Dark green/brown variations
        c = (random.randint(20, 60), random.randint(80, 140), random.randint(20, 60))
        pts.append([x, y, z])
        colors.append(c)

    # Building points
    for (bx, bz, bw, bd, bh) in buildings:
        # Top roof
        for _ in range(2000):
            x = random.uniform(bx - bw/2, bx + bw/2)
            z = random.uniform(bz - bd/2, bz + bd/2)
            y = -bh  # Y is down in OpenCV, so -bh is up
            c = (random.randint(150, 200), random.randint(150, 200), random.randint(150, 200))
            pts.append([x, y, z])
            colors.append(c)
        
        # Walls
        for _ in range(3000):
            wall = random.randint(0, 3)
            y = random.uniform(-bh, 0)
            if wall == 0: # Front
                x = random.uniform(bx - bw/2, bx + bw/2)
                z = bz - bd/2
                c = (120, 120, 120)
            elif wall == 1: # Back
                x = random.uniform(bx - bw/2, bx + bw/2)
                z = bz + bd/2
                c = (80, 80, 80)
            elif wall == 2: # Left
                x = bx - bw/2
                z = random.uniform(bz - bd/2, bz + bd/2)
                c = (100, 100, 100)
            else: # Right
                x = bx + bw/2
                z = random.uniform(bz - bd/2, bz + bd/2)
                c = (140, 140, 140)
            
            # Add some noise to wall color
            noise = random.randint(-20, 20)
            c = (max(0, min(255, c[0]+noise)), max(0, min(255, c[1]+noise)), max(0, min(255, c[2]+noise)))
            
            pts.append([x, y, z])
            colors.append(c)

    pts = np.array(pts, dtype=np.float32)
    colors = np.array(colors, dtype=np.uint8)

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(str(video_path), fourcc, fps, (width, height))

    gps_track = []
    imu_data = []
    base_lat, base_lon = 40.7128, -74.0060

    print("Generating 3D video frames...")
    for i in range(num_frames):
        t = i / float(num_frames - 1)
        
        # Camera path: circle around the buildings
        angle = t * math.pi * 1.5 - math.pi/4
        radius = 180.0
        
        cam_x = math.cos(angle) * radius
        cam_z = math.sin(angle) * radius
        cam_y = -120.0 - math.sin(t * math.pi) * 30.0 # Fly up and down a bit
        
        # Look at center
        # We need rotation matrix
        # forward vector
        fwd = np.array([-cam_x, -cam_y, -cam_z])
        fwd = fwd / np.linalg.norm(fwd)
        
        # right vector
        world_up = np.array([0, -1, 0]) # Y is down, so up is -Y
        right = np.cross(fwd, world_up)
        right = right / np.linalg.norm(right)
        
        # camera up vector
        up = np.cross(right, fwd)
        
        # Extrinsic matrix maps world to camera
        # R is transpose of camera axes
        R = np.vstack((right, up, fwd))
        t_vec = -R @ np.array([cam_x, cam_y, cam_z])
        
        pts_2d, valid, depths = project_points(pts, K, R, t_vec)
        
        # Render
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Sort points by depth (Painter's algorithm) to draw far points first
        valid_indices = np.where(valid)[0]
        valid_depths = depths[valid]
        valid_2d = pts_2d
        
        # Sort descending (far to near)
        sort_idx = np.argsort(-valid_depths)
        
        for idx in sort_idx:
            orig_idx = valid_indices[idx]
            px, py = int(valid_2d[idx, 0]), int(valid_2d[idx, 1])
            if 0 <= px < width and 0 <= py < height:
                # Draw a slightly larger point for closer objects
                d = valid_depths[idx]
                r = 2 if d < 150 else 1
                cv2.circle(frame, (px, py), r, tuple(int(x) for x in colors[orig_idx]), -1)

        out.write(frame)
        
        if i % (fps // 10) == 0:
            timestamp = i / fps
            lat = base_lat + (cam_z / 111000.0)
            lon = base_lon + (cam_x / (111000.0 * math.cos(math.radians(base_lat))))
            alt = -cam_y
            
            gps_track.append({
                "timestamp": timestamp,
                "lat": lat,
                "lon": lon,
                "alt": alt
            })
            
            # IMU yaw
            yaw_deg = math.degrees(math.atan2(fwd[0], fwd[2]))
            pitch_deg = math.degrees(math.asin(fwd[1]))
            
            imu_data.append({
                "timestamp": timestamp,
                "roll": 0.0,
                "pitch": pitch_deg,
                "yaw": yaw_deg
            })

    out.release()
    print("Video generation complete.")

    metadata = {
        "camera": {
            "focal_length_mm": 24.0,
            "sensor_width_mm": 36.0 * (width / focal_length), # approximate
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
    generate_3d_buildings_video()
