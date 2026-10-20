"""Generate a synthetic drone flyover video of a textured 3D city.

The buildings have rich procedural textures (brick patterns, windows, 
roof details) so that the SfM pipeline has enough visual features for
stereo matching and dense reconstruction.
"""

import cv2
import numpy as np
import os
import json

print("Generating textured drone flyover video...")

WIDTH, HEIGHT = 1280, 960
FPS = 30
NUM_FRAMES = 300  # 10 seconds
OUT_VIDEO = "assets/test_video_buildings.mp4"
OUT_META = "assets/test_metadata_buildings.json"
os.makedirs("assets", exist_ok=True)

FOCAL = 800
K = np.array([[FOCAL, 0, WIDTH / 2],
              [0, FOCAL, HEIGHT / 2],
              [0, 0, 1]], dtype=np.float64)

# ── Procedural texture generation ─────────────────────────────────────────────

def make_brick_texture(w, h, base_color):
    """Create a brick-wall texture patch."""
    tex = np.full((h, w, 3), base_color, dtype=np.uint8)
    # Add noise
    noise = np.random.randint(-20, 20, (h, w, 3), dtype=np.int16)
    tex = np.clip(tex.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    # Brick rows
    brick_h, brick_w = max(6, h // 8), max(12, w // 4)
    mortar = [60, 60, 55]
    for row in range(0, h, brick_h):
        cv2.line(tex, (0, row), (w, row), mortar, 1)
        offset = (brick_w // 2) if (row // brick_h) % 2 else 0
        for col in range(offset, w, brick_w):
            cv2.line(tex, (col, row), (col, min(row + brick_h, h)), mortar, 1)
    return tex


def make_window_texture(w, h, base_color):
    """Create a wall with windows."""
    tex = np.full((h, w, 3), base_color, dtype=np.uint8)
    noise = np.random.randint(-15, 15, (h, w, 3), dtype=np.int16)
    tex = np.clip(tex.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    win_w, win_h = max(8, w // 5), max(10, h // 6)
    gap_x, gap_y = max(4, w // 8), max(5, h // 8)
    
    for y in range(gap_y, h - win_h, win_h + gap_y):
        for x in range(gap_x, w - win_w, win_w + gap_x):
            # Window glass - dark blue/gray
            glass = [np.random.randint(80, 120), np.random.randint(70, 90), np.random.randint(40, 60)]
            cv2.rectangle(tex, (x, y), (x + win_w, y + win_h), glass, -1)
            # Window frame
            cv2.rectangle(tex, (x, y), (x + win_w, y + win_h), [200, 200, 200], 1)
            # Window cross
            cx, cy = x + win_w // 2, y + win_h // 2
            cv2.line(tex, (cx, y), (cx, y + win_h), [180, 180, 180], 1)
            cv2.line(tex, (x, cy), (x + win_w, cy), [180, 180, 180], 1)
    return tex


def make_roof_texture(w, h, base_color):
    """Create a rooftop texture with AC units, edges etc."""
    tex = np.full((h, w, 3), base_color, dtype=np.uint8)
    noise = np.random.randint(-25, 25, (h, w, 3), dtype=np.int16)
    tex = np.clip(tex.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    # Border/parapet
    cv2.rectangle(tex, (0, 0), (w - 1, h - 1), [140, 140, 130], 2)
    cv2.rectangle(tex, (3, 3), (w - 4, h - 4), [160, 155, 145], 1)
    
    # AC units / vents
    for _ in range(np.random.randint(1, 4)):
        bx = np.random.randint(w // 6, 5 * w // 6)
        by = np.random.randint(h // 6, 5 * h // 6)
        bw, bh = np.random.randint(8, 16), np.random.randint(6, 12)
        cv2.rectangle(tex, (bx, by), (bx + bw, by + bh), [100, 100, 100], -1)
        cv2.rectangle(tex, (bx, by), (bx + bw, by + bh), [70, 70, 70], 1)
        # Vent lines
        for vl in range(by + 2, by + bh - 1, 2):
            cv2.line(tex, (bx + 1, vl), (bx + bw - 1, vl), [80, 80, 80], 1)
    
    return tex


def make_ground_texture(w, h):
    """Create a textured ground plane."""
    tex = np.full((h, w, 3), [75, 80, 70], dtype=np.uint8)
    noise = np.random.randint(-30, 30, (h, w, 3), dtype=np.int16)
    tex = np.clip(tex.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    # Road grid
    road_color = [50, 50, 50]
    road_w = 6
    for x in range(0, w, 80):
        cv2.rectangle(tex, (x - road_w, 0), (x + road_w, h), road_color, -1)
        # Lane markings
        for y in range(0, h, 20):
            cv2.line(tex, (x, y), (x, y + 10), [200, 200, 180], 1)
    for y in range(0, h, 80):
        cv2.rectangle(tex, (0, y - road_w), (w, y + road_w), road_color, -1)
        for x in range(0, w, 20):
            cv2.line(tex, (x, y), (x + 10, y), [200, 200, 180], 1)
    
    return tex


# ── 3D Rendering ──────────────────────────────────────────────────────────────

TEX_SIZE = 128  # texture resolution per face

np.random.seed(42)

# Generate buildings with pre-baked textures
buildings = []
WALL_STYLES = [make_brick_texture, make_window_texture]

for gx in range(-200, 200, 50):
    for gz in range(0, 400, 50):
        bw, bd = np.random.randint(20, 35), np.random.randint(20, 35)
        bh = np.random.uniform(25, 100)
        
        base_r = np.random.randint(120, 210)
        base_g = np.random.randint(110, 200)
        base_b = np.random.randint(100, 190)
        base = [base_b, base_g, base_r]
        
        verts = np.array([
            [gx,      0,   gz],       # 0 - front-bottom-left
            [gx + bw, 0,   gz],       # 1 - front-bottom-right
            [gx + bw, -bh, gz],       # 2 - front-top-right
            [gx,      -bh, gz],       # 3 - front-top-left
            [gx,      0,   gz + bd],  # 4 - back-bottom-left
            [gx + bw, 0,   gz + bd],  # 5 - back-bottom-right
            [gx + bw, -bh, gz + bd],  # 6 - back-top-right
            [gx,      -bh, gz + bd],  # 7 - back-top-left
        ], dtype=np.float64)
        
        style = np.random.choice(WALL_STYLES)
        darker = [max(0, c - 25) for c in base]
        lighter = [min(255, c + 35) for c in base]
        
        # Pre-render textures for each face
        face_textures = {
            "front":  style(TEX_SIZE, TEX_SIZE, base),
            "back":   style(TEX_SIZE, TEX_SIZE, darker),
            "left":   style(TEX_SIZE, TEX_SIZE, base),
            "right":  style(TEX_SIZE, TEX_SIZE, darker),
            "top":    make_roof_texture(TEX_SIZE, TEX_SIZE, lighter),
        }
        
        faces = [
            ([0, 1, 2, 3], "front"),
            ([5, 4, 7, 6], "back"),
            ([4, 0, 3, 7], "left"),
            ([1, 5, 6, 2], "right"),
            ([3, 2, 6, 7], "top"),
        ]
        
        buildings.append((verts, faces, face_textures))

# Ground plane
GROUND_SIZE = 600
GROUND_TEX = make_ground_texture(512, 512)
ground_verts = np.array([
    [-GROUND_SIZE / 2, 0, -50],
    [ GROUND_SIZE / 2, 0, -50],
    [ GROUND_SIZE / 2, 0, GROUND_SIZE],
    [-GROUND_SIZE / 2, 0, GROUND_SIZE],
], dtype=np.float64)


def project_quad(pts_3d, R_cam, t_cam):
    """Transform 3D points to camera space and project to 2D."""
    pts_cam = (pts_3d - t_cam) @ R_cam  # Nx3
    if np.any(pts_cam[:, 2] <= 1):
        return None, None
    depth = np.mean(pts_cam[:, 2])
    pts_2d = np.zeros((len(pts_cam), 2), dtype=np.int32)
    pts_2d[:, 0] = (FOCAL * pts_cam[:, 0] / pts_cam[:, 2] + WIDTH / 2).astype(int)
    pts_2d[:, 1] = (FOCAL * pts_cam[:, 1] / pts_cam[:, 2] + HEIGHT / 2).astype(int)
    return pts_2d, depth


def draw_textured_quad(img, pts_2d, texture):
    """Warp a texture onto a projected quadrilateral."""
    th, tw = texture.shape[:2]
    src_pts = np.array([[0, 0], [tw, 0], [tw, th], [0, th]], dtype=np.float32)
    dst_pts = pts_2d.astype(np.float32)
    
    # Need exactly 4 points
    if len(dst_pts) != 4:
        return
    
    # Check if quad is large enough to be visible
    area = cv2.contourArea(dst_pts)
    if area < 10:
        return
    
    # Compute perspective transform and warp
    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    warped = cv2.warpPerspective(texture, M, (img.shape[1], img.shape[0]))
    
    # Create mask for the quad
    mask = np.zeros(img.shape[:2], dtype=np.uint8)
    cv2.fillConvexPoly(mask, dst_pts.astype(np.int32), 255)
    
    # Blend
    mask_3ch = mask[:, :, np.newaxis] > 0
    img[mask_3ch.squeeze()] = warped[mask_3ch.squeeze()]


# ── Camera trajectory (smooth orbit over city) ────────────────────────────────

out = cv2.VideoWriter(OUT_VIDEO, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (WIDTH, HEIGHT))

# GPS track for metadata
gps_track = []
imu_data = []
BASE_LAT, BASE_LON, BASE_ALT = 28.6139, 77.2090, 250.0  # Delhi coordinates

for i in range(NUM_FRAMES):
    t = i / NUM_FRAMES
    
    # Smooth S-curve path over the city
    cam_x = -120 + 240 * t + 30 * np.sin(2 * np.pi * t)
    cam_z = -30 + 350 * t
    cam_y = -150 - 10 * np.sin(np.pi * t)  # slight altitude variation
    
    # Camera looks down at ~50 degrees, slowly panning
    pitch = np.radians(-50 - 5 * np.sin(2 * np.pi * t))
    yaw = np.radians(10 + 15 * np.sin(np.pi * t))
    
    Rx = np.array([[1, 0, 0],
                   [0, np.cos(pitch), -np.sin(pitch)],
                   [0, np.sin(pitch),  np.cos(pitch)]])
    Ry = np.array([[ np.cos(yaw), 0, np.sin(yaw)],
                   [0, 1, 0],
                   [-np.sin(yaw), 0, np.cos(yaw)]])
    R_cam = Rx @ Ry
    t_cam = np.array([cam_x, cam_y, cam_z])
    
    # Dark blue sky gradient
    img = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    for row in range(HEIGHT):
        frac = row / HEIGHT
        img[row, :] = [int(60 - 40 * frac), int(40 - 20 * frac), int(30 - 10 * frac)]
    
    # Collect all renderable quads with depth
    render_list = []
    
    # Ground plane
    pts_2d, depth = project_quad(ground_verts, R_cam, t_cam)
    if pts_2d is not None:
        render_list.append((depth + 1000, pts_2d, GROUND_TEX))  # push ground behind buildings
    
    # Building faces
    for verts, faces, textures in buildings:
        for face_idx, tex_name in faces:
            pts = verts[face_idx]
            pts_2d, depth = project_quad(pts, R_cam, t_cam)
            if pts_2d is not None:
                render_list.append((depth, pts_2d, textures[tex_name]))
    
    # Painter's algorithm
    render_list.sort(key=lambda x: x[0], reverse=True)
    
    for _, pts_2d, tex in render_list:
        draw_textured_quad(img, pts_2d, tex)
    
    out.write(img)
    
    # Generate GPS + IMU metadata
    ts = i / FPS
    # Convert camera position to approximate GPS (meters -> degrees)
    lat = BASE_LAT + cam_z / 111320.0
    lon = BASE_LON + cam_x / (111320.0 * np.cos(np.radians(BASE_LAT)))
    alt = BASE_ALT + abs(cam_y)
    
    gps_track.append({
        "timestamp": ts,
        "lat": round(lat, 8),
        "lon": round(lon, 8),
        "alt": round(alt, 2)
    })
    
    imu_data.append({
        "timestamp": ts,
        "roll": round(float(np.degrees(0)), 2),
        "pitch": round(float(np.degrees(pitch)), 2),
        "yaw": round(float(np.degrees(yaw)), 2)
    })
    
    if i % 50 == 0:
        print(f"  Frame {i}/{NUM_FRAMES}")

out.release()
print(f"Video saved: {OUT_VIDEO}")

# ── Metadata ──────────────────────────────────────────────────────────────────

meta = {
    "camera": {
        "focal_length_px": FOCAL,
        "image_width": WIDTH,
        "image_height": HEIGHT
    },
    "flight_altitude_m": 150.0,
    "gps_track": gps_track,
    "imu": imu_data
}

with open(OUT_META, "w") as f:
    json.dump(meta, f, indent=2)
print(f"Metadata saved: {OUT_META}")
print("Done!")
