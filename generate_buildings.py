import cv2
import numpy as np
import os

print("Generating simulated drone video over a 3D city...")

width, height = 800, 600
fps = 30
num_frames = 150
out_path = 'assets/test_video_buildings.mp4'
os.makedirs('assets', exist_ok=True)

out = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (width, height))

# Intrinsics
f = 600
K = np.array([[f, 0, width/2],
              [0, f, height/2],
              [0, 0, 1]])

# Generate buildings
buildings = []
np.random.seed(42)
for x in range(-150, 150, 40):
    for z in range(0, 300, 40):
        w, d = 25, 25
        h = np.random.uniform(20, 80)
        
        # Base color
        r, g, b = np.random.randint(100, 200, 3)
        
        verts = np.array([
            [x, 0, z], [x+w, 0, z], [x+w, -h, z], [x, -h, z],
            [x, 0, z+d], [x+w, 0, z+d], [x+w, -h, z+d], [x, -h, z+d]
        ])
        
        # front, back, left, right, top, bottom
        b, g, r = int(b), int(g), int(r)
        faces = [
            ([0,1,2,3], (b,g,r)),
            ([5,4,7,6], (b,g,r)),
            ([4,0,3,7], (b,g,r)),
            ([1,5,6,2], (b,g,r)),
            ([3,2,6,7], (min(255,b+30), min(255,g+30), min(255,r+30))), # Top is lighter
            ([4,5,1,0], (b,g,r))
        ]
        buildings.append((verts, faces))

for i in range(num_frames):
    img = np.full((height, width, 3), 40, dtype=np.uint8) # dark sky/ground
    
    # Camera moves diagonally over the city
    # Y is up in OpenCV typically, so -Y is higher altitude.
    cam_x = -100 + i * 1.5
    cam_y = -120 # altitude
    cam_z = -50 + i * 2.0
    
    # Camera looking down and slightly forward
    # Pitch down by 45 degrees
    pitch = np.radians(-45)
    yaw = np.radians(15)
    
    Rx = np.array([[1, 0, 0],
                   [0, np.cos(pitch), -np.sin(pitch)],
                   [0, np.sin(pitch), np.cos(pitch)]])
                   
    Ry = np.array([[np.cos(yaw), 0, np.sin(yaw)],
                   [0, 1, 0],
                   [-np.sin(yaw), 0, np.cos(yaw)]])
                   
    R_cam = Rx @ Ry
    t_cam = np.array([cam_x, cam_y, cam_z])
    
    polygons_to_draw = []
    
    for verts, faces in buildings:
        # Transform to camera space
        # P_cam = R^T * (P_world - t_cam)
        v_cam = (verts - t_cam) @ R_cam
        
        for face_idx, color in faces:
            pts = v_cam[face_idx]
            
            # Simple backface culling & frustum check (all Z > 0)
            if np.all(pts[:, 2] > 5):
                # Centroid depth for sorting
                depth = np.mean(pts[:, 2])
                
                # Project
                pts_2d = []
                for pt in pts:
                    u = int(f * pt[0] / pt[2] + width/2)
                    v = int(f * pt[1] / pt[2] + height/2)
                    pts_2d.append([u, v])
                    
                pts_2d = np.array(pts_2d, dtype=np.int32)
                
                # Create a grid pattern on the face for ORB features
                # We do this by storing lines to draw after filling the polygon
                polygons_to_draw.append((depth, pts_2d, color))

    # Painter's algorithm (sort by depth descending)
    polygons_to_draw.sort(key=lambda x: x[0], reverse=True)
    
    for depth, pts_2d, color in polygons_to_draw:
        # Fill face
        cv2.fillConvexPoly(img, pts_2d, color)
        # Draw high-contrast grid lines for features
        cv2.polylines(img, [pts_2d], True, (0, 0, 0), 2)
        
        # Crosshatch for extra features
        if len(pts_2d) == 4:
            cv2.line(img, tuple(pts_2d[0]), tuple(pts_2d[2]), (255,255,255), 1)
            cv2.line(img, tuple(pts_2d[1]), tuple(pts_2d[3]), (255,255,255), 1)
            
    out.write(img)
    
    if i % 30 == 0:
        print(f"Rendered frame {i}/{num_frames}")

out.release()
print(f"Done! Video saved to {out_path}")

# Write matching metadata
import json
meta = {
    "camera": {
        "focal_length_px": 600.0,
        "image_width": 800,
        "image_height": 600
    },
    "flight_altitude_m": 120.0
}
with open('assets/test_metadata_buildings.json', 'w') as f:
    json.dump(meta, f, indent=2)
print("Saved matching metadata to assets/test_metadata_buildings.json")
