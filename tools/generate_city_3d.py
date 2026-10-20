"""Generate high-fidelity 3D city mesh and dense point cloud for FlightPrint.

Matches the procedural buildings and GPS coordinates in generate_buildings.py
with seed 42. Produces:
- assets/test_buildings_mesh.ply  (textured/colored 3D triangle mesh)
- assets/test_buildings_mesh.obj  (Wavefront OBJ)
- assets/test_buildings_cloud.ply (dense point cloud, ~80k colored points)
- assets/test_buildings_anomalies.json (realistic AI detected anomalies)
"""

import numpy as np
import os
import json
from pathlib import Path

def generate_city_3d():
    print("Generating 3D City Map Assets...")
    os.makedirs("assets", exist_ok=True)
    
    np.random.seed(42)
    
    # Coordinates mapping from generate_buildings.py:
    # cam_x = East, cam_z = North, cam_y = -Altitude
    # Origin at t=0:
    # cam_x(0) = -120.0
    # cam_z(0) = -30.0
    # alt(0) = 400.0 (BASE_ALT 250.0 + 150.0)
    # Ground is at BASE_ALT = 250.0 -> ENU Z = 250 - 400 = -150.0
    # ENU X = gx + 120.0
    # ENU Y = gz + 30.0
    # ENU Z = -150.0 + height
    
    ORIGIN_X = -120.0
    ORIGIN_Y = -30.0
    GROUND_Z = -150.0
    
    vertices = []
    normals = []
    colors = []
    triangles = []
    
    cloud_points = []
    cloud_colors = []
    
    def add_quad(p0, p1, p2, p3, n, c0, c1, c2, c3):
        """Add a quad (2 triangles) to the mesh."""
        idx = len(vertices)
        vertices.extend([p0, p1, p2, p3])
        normals.extend([n, n, n, n])
        colors.extend([c0, c1, c2, c3])
        triangles.append([idx, idx + 1, idx + 2])
        triangles.append([idx, idx + 2, idx + 3])
        
    def sample_quad(p0, p1, p2, p3, c, step=2.0):
        """Sample points densely across a quad for the point cloud."""
        p0, p1, p2, p3 = np.array(p0), np.array(p1), np.array(p2), np.array(p3)
        v_u = p1 - p0
        v_v = p3 - p0
        len_u = np.linalg.norm(v_u)
        len_v = np.linalg.norm(v_v)
        
        n_u = max(2, int(len_u / step))
        n_v = max(2, int(len_v / step))
        
        u_vals = np.linspace(0, 1, n_u)
        v_vals = np.linspace(0, 1, n_v)
        
        for u in u_vals:
            for v in v_vals:
                pt = p0 + u * v_u + v * v_v
                # Add tiny jitter so it looks like realistic point cloud scan
                jitter = np.random.normal(0, 0.05, 3)
                col_jitter = np.clip(np.array(c) + np.random.randint(-10, 10, 3), 0, 255)
                cloud_points.append(pt + jitter)
                cloud_colors.append(col_jitter)

    # ── 1. Ground Plane (Roads & Parks) ───────────────────────────────────────
    # City grid spans gx: -240 to 240, gz: -40 to 440
    # Map into ENU:
    min_x, max_x = -240.0 - ORIGIN_X, 240.0 - ORIGIN_X
    min_y, max_y = -40.0 - ORIGIN_Y, 440.0 - ORIGIN_Y
    
    # Subdivide ground into road grid & city blocks
    road_color = [48, 52, 58]       # Dark asphalt
    grass_color = [68, 115, 62]     # Lawn / park
    sidewalk_color = [180, 178, 172]# Concrete curb
    
    step_grid = 50.0
    for gx in range(-250, 250, 50):
        for gz in range(-50, 450, 50):
            ex0 = gx - ORIGIN_X
            ey0 = gz - ORIGIN_Y
            ex1 = ex0 + step_grid
            ey1 = ey0 + step_grid
            
            # Ground tile
            g0 = [ex0, ey0, GROUND_Z]
            g1 = [ex1, ey0, GROUND_Z]
            g2 = [ex1, ey1, GROUND_Z]
            g3 = [ex0, ey1, GROUND_Z]
            
            # Roads around border of block, park inside
            c = grass_color if np.random.rand() > 0.3 else road_color
            add_quad(g0, g1, g2, g3, [0, 0, 1], c, c, c, c)
            sample_quad(g0, g1, g2, g3, c, step=3.5)

    # ── 2. Procedural Buildings ───────────────────────────────────────────────
    building_records = []
    
    PALETTES = [
        # Facade base, Facade darker, Window color, Roof color
        ([190, 180, 165], [160, 150, 135], [55, 80, 115], [145, 140, 135]), # Sandstone
        ([175, 95, 75],   [145, 75, 55],   [45, 65, 90],  [130, 125, 120]), # Red brick
        ([135, 155, 175], [110, 130, 150], [60, 95, 135], [150, 150, 155]), # Blue steel & glass
        ([215, 215, 220], [185, 185, 190], [50, 75, 110], [160, 160, 160]), # Modern white concrete
        ([110, 115, 125], [85, 90, 100],   [70, 110, 150], [120, 120, 125]), # Slate charcoal
    ]
    
    b_id = 0
    for gx in range(-200, 200, 50):
        for gz in range(0, 400, 50):
            bw = np.random.randint(22, 36)
            bd = np.random.randint(22, 36)
            bh = float(np.random.uniform(25, 100))
            
            base_r = np.random.randint(120, 210)
            base_g = np.random.randint(110, 200)
            base_b = np.random.randint(100, 190)
            
            # Palette
            pal = PALETTES[b_id % len(PALETTES)]
            facade_col = pal[0]
            facade_dark = pal[1]
            win_col = pal[2]
            roof_col = pal[3]
            
            # Building footprint in ENU
            bx0 = gx - ORIGIN_X
            by0 = gz - ORIGIN_Y
            bx1 = bx0 + bw
            by1 = by0 + bd
            bz0 = GROUND_Z
            bz1 = GROUND_Z + bh
            
            building_records.append({
                "id": b_id,
                "gx": gx,
                "gz": gz,
                "enu_x": (bx0 + bx1) / 2,
                "enu_y": (by0 + by1) / 2,
                "height_m": round(bh, 1),
                "width_m": bw,
                "depth_m": bd,
                "roof_z": bz1,
            })
            b_id += 1
            
            # 8 corners
            v_bfl = [bx0, by0, bz0] # bottom front left
            v_bfr = [bx1, by0, bz0] # bottom front right
            v_tfr = [bx1, by0, bz1] # top front right
            v_tfl = [bx0, by0, bz1] # top front left
            
            v_bbl = [bx0, by1, bz0] # bottom back left
            v_bbr = [bx1, by1, bz0] # bottom back right
            v_tbr = [bx1, by1, bz1] # top back right
            v_tbl = [bx0, by1, bz1] # top back left
            
            # Front wall (Y = by0)
            add_quad(v_bfl, v_bfr, v_tfr, v_tfl, [0, -1, 0], facade_col, facade_col, facade_col, facade_col)
            sample_quad(v_bfl, v_bfr, v_tfr, v_tfl, facade_col, step=1.5)
            
            # Back wall (Y = by1)
            add_quad(v_bbr, v_bbl, v_tbl, v_tbr, [0, 1, 0], facade_dark, facade_dark, facade_dark, facade_dark)
            sample_quad(v_bbr, v_bbl, v_tbl, v_tbr, facade_dark, step=1.5)
            
            # Left wall (X = bx0)
            add_quad(v_bbl, v_bfl, v_tfl, v_tbl, [-1, 0, 0], facade_col, facade_col, facade_col, facade_col)
            sample_quad(v_bbl, v_bfl, v_tfl, v_tbl, facade_col, step=1.5)
            
            # Right wall (X = bx1)
            add_quad(v_bfr, v_bbr, v_tbr, v_tfr, [1, 0, 0], facade_dark, facade_dark, facade_dark, facade_dark)
            sample_quad(v_bfr, v_bbr, v_tbr, v_tfr, facade_dark, step=1.5)
            
            # Roof (Z = bz1)
            add_quad(v_tfl, v_tfr, v_tbr, v_tbl, [0, 0, 1], roof_col, roof_col, roof_col, roof_col)
            sample_quad(v_tfl, v_tfr, v_tbr, v_tbl, roof_col, step=1.2)
            
            # Rooftop AC unit / elevator box
            if bh > 35:
                ac_w, ac_d, ac_h = bw * 0.35, bd * 0.35, 4.0
                ac_x0 = bx0 + (bw - ac_w) / 2
                ac_y0 = by0 + (bd - ac_d) / 2
                ac_x1 = ac_x0 + ac_w
                ac_y1 = ac_y0 + ac_d
                ac_z0 = bz1
                ac_z1 = bz1 + ac_h
                ac_col = [95, 100, 105]
                
                # AC Top
                add_quad([ac_x0, ac_y0, ac_z1], [ac_x1, ac_y0, ac_z1],
                         [ac_x1, ac_y1, ac_z1], [ac_x0, ac_y1, ac_z1],
                         [0, 0, 1], ac_col, ac_col, ac_col, ac_col)
                # AC Sides
                add_quad([ac_x0, ac_y0, ac_z0], [ac_x1, ac_y0, ac_z0],
                         [ac_x1, ac_y0, ac_z1], [ac_x0, ac_y0, ac_z1],
                         [0, -1, 0], ac_col, ac_col, ac_col, ac_col)
                add_quad([ac_x1, ac_y0, ac_z0], [ac_x1, ac_y1, ac_z0],
                         [ac_x1, ac_y1, ac_z1], [ac_x1, ac_y0, ac_z1],
                         [1, 0, 0], ac_col, ac_col, ac_col, ac_col)
                add_quad([ac_x1, ac_y1, ac_z0], [ac_x0, ac_y1, ac_z0],
                         [ac_x0, ac_y1, ac_z1], [ac_x1, ac_y1, ac_z1],
                         [0, 1, 0], ac_col, ac_col, ac_col, ac_col)
                add_quad([ac_x0, ac_y1, ac_z0], [ac_x0, ac_y0, ac_z0],
                         [ac_x0, ac_y0, ac_z1], [ac_x0, ac_y1, ac_z1],
                         [-1, 0, 0], ac_col, ac_col, ac_col, ac_col)

    # ── 3. Write PLY Mesh ─────────────────────────────────────────────────────
    mesh_ply_path = Path("assets/test_buildings_mesh.ply")
    with open(mesh_ply_path, "w") as f:
        f.write("ply\n")
        f.write("format ascii 1.0\n")
        f.write(f"element vertex {len(vertices)}\n")
        f.write("property float x\n")
        f.write("property float y\n")
        f.write("property float z\n")
        f.write("property float nx\n")
        f.write("property float ny\n")
        f.write("property float nz\n")
        f.write("property uchar red\n")
        f.write("property uchar green\n")
        f.write("property uchar blue\n")
        f.write(f"element face {len(triangles)}\n")
        f.write("property list uchar int vertex_indices\n")
        f.write("end_header\n")
        for v, n, c in zip(vertices, normals, colors):
            f.write(f"{v[0]:.3f} {v[1]:.3f} {v[2]:.3f} {n[0]:.2f} {n[1]:.2f} {n[2]:.2f} {int(c[0])} {int(c[1])} {int(c[2])}\n")
        for t in triangles:
            f.write(f"3 {t[0]} {t[1]} {t[2]}\n")
            
    print(f"Saved 3D mesh: {mesh_ply_path} ({len(vertices)} vertices, {len(triangles)} faces)")

    # ── 4. Write OBJ Mesh ─────────────────────────────────────────────────────
    mesh_obj_path = Path("assets/test_buildings_mesh.obj")
    with open(mesh_obj_path, "w") as f:
        f.write("# FlightPrint 3D City Mesh\n")
        for v, c in zip(vertices, colors):
            f.write(f"v {v[0]:.3f} {v[1]:.3f} {v[2]:.3f} {c[0]/255:.3f} {c[1]/255:.3f} {c[2]/255:.3f}\n")
        for n in normals:
            f.write(f"vn {n[0]:.2f} {n[1]:.2f} {n[2]:.2f}\n")
        for t in triangles:
            # 1-indexed in OBJ
            f.write(f"f {t[0]+1}//{t[0]+1} {t[1]+1}//{t[1]+1} {t[2]+1}//{t[2]+1}\n")
    print(f"Saved OBJ mesh: {mesh_obj_path}")

    # ── 5. Write Dense Point Cloud PLY ────────────────────────────────────────
    cloud_ply_path = Path("assets/test_buildings_cloud.ply")
    cloud_points = np.array(cloud_points)
    cloud_colors = np.array(cloud_colors, dtype=np.uint8)
    
    with open(cloud_ply_path, "w") as f:
        f.write("ply\n")
        f.write("format ascii 1.0\n")
        f.write(f"element vertex {len(cloud_points)}\n")
        f.write("property float x\n")
        f.write("property float y\n")
        f.write("property float z\n")
        f.write("property uchar red\n")
        f.write("property uchar green\n")
        f.write("property uchar blue\n")
        f.write("end_header\n")
        for p, c in zip(cloud_points, cloud_colors):
            f.write(f"{p[0]:.3f} {p[1]:.3f} {p[2]:.3f} {c[0]} {c[1]} {c[2]}\n")
            
    print(f"Saved dense cloud: {cloud_ply_path} ({len(cloud_points)} points)")

    # ── 6. Realistic AI Anomalies ─────────────────────────────────────────────
    # Pick 4 notable buildings for detected anomalies
    b14 = building_records[14]
    b28 = building_records[28]
    b42 = building_records[42]
    b7 = building_records[7]
    
    BASE_LAT, BASE_LON = 28.6139, 77.2090
    def enu_to_gps(ex, ey, ez):
        gx = ex + ORIGIN_X
        gz = ey + ORIGIN_Y
        lat = BASE_LAT + gz / 111320.0
        lon = BASE_LON + gx / (111320.0 * np.cos(np.radians(BASE_LAT)))
        alt = 250.0 + (ez - GROUND_Z)
        return round(lat, 8), round(lon, 8), round(alt, 1)

    lat1, lon1, alt1 = enu_to_gps(b14["enu_x"], b14["enu_y"], b14["roof_z"])
    lat2, lon2, alt2 = enu_to_gps(b28["enu_x"], b28["enu_y"], b28["roof_z"] - 15)
    lat3, lon3, alt3 = enu_to_gps(b42["enu_x"], b42["enu_y"], b42["roof_z"])
    lat4, lon4, alt4 = enu_to_gps(b7["enu_x"], b7["enu_y"], b7["roof_z"])

    anomalies = [
        {
            "id": "ANOM-001",
            "type": "thermal_fault",
            "title": "Rooftop HVAC Overheating",
            "description": "High temperature differential (+18°C) detected on cooling tower unit. Potential compressor failure.",
            "severity": "high",
            "position_enu": [round(b14["enu_x"], 1), round(b14["enu_y"], 1), round(b14["roof_z"], 1)],
            "gps": {"lat": lat1, "lon": lon1, "alt": alt1},
            "building_id": 14,
            "building_height_m": b14["height_m"],
            "evidence_frames": [45, 46, 47],
        },
        {
            "id": "ANOM-002",
            "type": "structural_crack",
            "title": "Facade Concrete Spalling",
            "description": "Vertical shear crack (length 3.4m, width 12mm) detected between floors 4 and 5.",
            "severity": "medium",
            "position_enu": [round(b28["enu_x"], 1), round(b28["enu_y"], 1), round(b28["roof_z"] - 15, 1)],
            "gps": {"lat": lat2, "lon": lon2, "alt": alt2},
            "building_id": 28,
            "building_height_m": b28["height_m"],
            "evidence_frames": [112, 113, 115],
        },
        {
            "id": "ANOM-003",
            "type": "unauthorized_modification",
            "title": "Unpermitted Rooftop Installation",
            "description": "Unregistered 24-panel PV array installed without municipal permit records.",
            "severity": "low",
            "position_enu": [round(b42["enu_x"], 1), round(b42["enu_y"], 1), round(b42["roof_z"], 1)],
            "gps": {"lat": lat3, "lon": lon3, "alt": alt3},
            "building_id": 42,
            "building_height_m": b42["height_m"],
            "evidence_frames": [188, 190],
        },
        {
            "id": "ANOM-004",
            "type": "parapet_hazard",
            "title": "Roof Parapet Wall Displacement",
            "description": "Outward masonry shift of 42mm along northern roof edge. Immediate falling debris risk.",
            "severity": "high",
            "position_enu": [round(b7["enu_x"], 1), round(b7["enu_y"], 1), round(b7["roof_z"], 1)],
            "gps": {"lat": lat4, "lon": lon4, "alt": alt4},
            "building_id": 7,
            "building_height_m": b7["height_m"],
            "evidence_frames": [25, 26, 28],
        },
    ]

    anom_path = Path("assets/test_buildings_anomalies.json")
    with open(anom_path, "w") as f:
        json.dump({"anomalies": anomalies, "scene": "City Quad Alpha", "total_buildings": len(building_records)}, f, indent=2)
    print(f"Saved anomalies: {anom_path}")

if __name__ == "__main__":
    generate_city_3d()
