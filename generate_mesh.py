"""
generate_mesh.py

Takes the dense point cloud from the previous pipeline run and:
  1. Runs Poisson surface reconstruction (Open3D)
  2. Exports mesh.ply + mesh.obj
  3. Converts mesh to JSON for the WebGL viewer
  4. Generates output/3d_model/index.html — a proper shaded 3D model viewer
"""

import sys
import os
import json
import time
import struct
import numpy as np
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT      = Path(__file__).resolve().parent
PLY_PATH  = ROOT / "output" / "test_run" / "dense_cloud.ply"
OUT_DIR   = ROOT / "output" / "test_run"
MODEL_DIR = ROOT / "output" / "3d_model"

MODEL_DIR.mkdir(parents=True, exist_ok=True)

print("=" * 60)
print("FlightPrint -- Generating 3D Mesh")
print("=" * 60)

# ── Load dense cloud PLY ──────────────────────────────────────────────────────
print(f"\n[1] Loading dense point cloud from {PLY_PATH} ...")

def load_ply(path):
    """Parse a simple ASCII PLY file with x y z r g b columns."""
    pts, cols = [], []
    with open(path) as f:
        in_header = True
        prop_order = []
        for line in f:
            line = line.strip()
            if in_header:
                if line.startswith("property"):
                    prop_order.append(line.split()[-1])
                if line == "end_header":
                    in_header = False
                continue
            vals = line.split()
            if len(vals) < 3:
                continue
            d = {p: float(v) for p, v in zip(prop_order, vals)}
            pts.append([d.get("x", 0), d.get("y", 0), d.get("z", 0)])
            cols.append([
                int(d.get("red", 128)),
                int(d.get("green", 128)),
                int(d.get("blue", 128)),
            ])
    return np.array(pts, dtype=np.float64), np.array(cols, dtype=np.uint8)

t0 = time.perf_counter()
points, colors = load_ply(PLY_PATH)
print(f"  OK  {len(points):,} points loaded  ({time.perf_counter()-t0:.1f}s)")

# ── Open3D Poisson meshing ────────────────────────────────────────────────────
print("\n[2] Running Poisson surface reconstruction ...")
try:
    import open3d as o3d
except ImportError:
    print("ERROR: open3d not installed. Run:  pip install open3d")
    sys.exit(1)

t0 = time.perf_counter()

pcd = o3d.geometry.PointCloud()
pcd.points = o3d.utility.Vector3dVector(points)
pcd.colors = o3d.utility.Vector3dVector(colors.astype(np.float64) / 255.0)

# Statistical outlier removal to clean the cloud first
print("  Removing outliers ...")
pcd, _ = pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
print(f"  After cleaning: {len(pcd.points):,} points")

# Voxel downsample for speed if still very large
if len(pcd.points) > 200000:
    print("  Downsampling for meshing ...")
    pcd = pcd.voxel_down_sample(voxel_size=0.05)
    print(f"  After downsample: {len(pcd.points):,} points")

# Estimate normals
print("  Estimating normals ...")
pcd.estimate_normals(
    search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.5, max_nn=30)
)
pcd.orient_normals_consistent_tangent_plane(30)

# Poisson
print("  Poisson reconstruction (depth=8) ...")
mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
    pcd, depth=8
)

# Remove low-density outlier faces
densities = np.asarray(densities)
thresh = np.quantile(densities, 0.05)
mesh.remove_vertices_by_mask(densities < thresh)

n_verts = len(mesh.vertices)
n_faces = len(mesh.triangles)
print(f"  Mesh: {n_verts:,} vertices, {n_faces:,} faces  ({time.perf_counter()-t0:.1f}s)")

# Simplify to a web-friendly size
TARGET_FACES = 80000
if n_faces > TARGET_FACES:
    print(f"  Simplifying to {TARGET_FACES:,} faces ...")
    mesh = mesh.simplify_quadric_decimation(TARGET_FACES)
    n_verts = len(mesh.vertices)
    n_faces = len(mesh.triangles)
    print(f"  After simplify: {n_verts:,} vertices, {n_faces:,} faces")

# Transfer vertex colors from point cloud
mesh.compute_vertex_normals()
print(f"  Final mesh: {n_verts:,} vertices, {n_faces:,} faces")

# ── Save PLY + OBJ ────────────────────────────────────────────────────────────
ply_path = OUT_DIR / "mesh.ply"
obj_path = OUT_DIR / "mesh.obj"
o3d.io.write_triangle_mesh(str(ply_path), mesh)
print(f"  Saved {ply_path}")
o3d.io.write_triangle_mesh(str(obj_path), mesh)
print(f"  Saved {obj_path}")

# ── Export mesh to compact JSON for WebGL viewer ──────────────────────────────
print("\n[3] Exporting mesh to JSON ...")
t0 = time.perf_counter()

verts  = np.asarray(mesh.vertices)
faces  = np.asarray(mesh.triangles)
norms  = np.asarray(mesh.vertex_normals)
vc     = np.asarray(mesh.vertex_colors) if mesh.has_vertex_colors() else None

# Center + normalize to [-1, 1] for easy viewing
center = verts.mean(axis=0)
verts  = verts - center
scale  = np.abs(verts).max()
if scale > 0:
    verts = verts / scale

# Build compact arrays
positions = verts.astype(np.float32).flatten().tolist()
normals   = norms.astype(np.float32).flatten().tolist() if len(norms) == len(verts) else []
indices   = faces.astype(np.int32).flatten().tolist()

if vc is not None and len(vc) == len(verts):
    vertex_colors = vc.astype(np.float32).flatten().tolist()
else:
    # Default gray
    vertex_colors = [0.55, 0.58, 0.62] * len(verts)

payload = {
    "positions":      positions,
    "normals":        normals,
    "vertex_colors":  vertex_colors,
    "indices":        indices,
    "n_vertices":     n_verts,
    "n_faces":        n_faces,
}

mesh_json = MODEL_DIR / "mesh_data.json"
with open(mesh_json, "w") as f:
    json.dump(payload, f)
print(f"  Saved {mesh_json}  ({time.perf_counter()-t0:.1f}s)")

# ── Build 3D model viewer ─────────────────────────────────────────────────────
print("\n[4] Building 3D model viewer ...")

HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>FlightPrint - 3D Model</title>
<meta name="description" content="Interactive textured 3D mesh from drone imagery - FlightPrint"/>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet"/>
<style>
*{margin:0;padding:0;box-sizing:border-box;}
:root{
  --bg:#07090f;--surface:#0d1421;--surface2:#121e31;
  --accent:#5090ff;--accent2:#8b5cf6;--green:#10b981;
  --amber:#f59e0b;--red:#f04747;--text:#dde4f0;--muted:#4b6080;
  --border:#172038;
}
body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--text);
     overflow:hidden;height:100vh;display:flex;flex-direction:column;}

/* Header */
header{
  display:flex;align-items:center;gap:14px;padding:10px 20px;
  background:rgba(13,20,33,0.96);border-bottom:1px solid var(--border);
  backdrop-filter:blur(20px);flex-shrink:0;z-index:10;
}
.logo{display:flex;align-items:center;gap:10px;}
.logo-icon{
  width:34px;height:34px;border-radius:9px;font-size:18px;
  background:linear-gradient(135deg,#3b7ef8,#7c3aed);
  display:flex;align-items:center;justify-content:center;
  box-shadow:0 0 18px rgba(59,126,248,.35);
}
.logo-text{
  font-size:17px;font-weight:700;letter-spacing:-.01em;
  background:linear-gradient(90deg,#6db3ff,#b197fc);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
}
.badge{
  font-size:9.5px;font-weight:700;letter-spacing:.08em;padding:3px 9px;
  border-radius:20px;text-transform:uppercase;
  background:rgba(80,144,255,.1);color:var(--accent);border:1px solid rgba(80,144,255,.25);
}
.hdr-stats{display:flex;gap:28px;margin-left:auto;}
.stat{display:flex;flex-direction:column;align-items:center;gap:1px;}
.sv{font-size:14px;font-weight:600;color:var(--accent);}
.sl{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;}

/* Layout */
.main{display:flex;flex:1;overflow:hidden;}

/* Sidebar */
.sidebar{
  width:246px;background:rgba(13,20,33,0.98);
  border-right:1px solid var(--border);
  display:flex;flex-direction:column;gap:10px;padding:12px;
  overflow-y:auto;flex-shrink:0;
}
.panel{background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:12px;}
.ptitle{font-size:9px;font-weight:700;color:var(--muted);
  text-transform:uppercase;letter-spacing:.1em;margin-bottom:10px;}

.rb-group{display:flex;flex-direction:column;gap:6px;}
.rb{
  display:flex;align-items:center;gap:9px;font-size:12px;cursor:pointer;
  background:none;border:1px solid var(--border);border-radius:7px;
  padding:7px 11px;color:var(--text);transition:all .16s;width:100%;
}
.rb:hover{border-color:rgba(80,144,255,.55);background:rgba(80,144,255,.06);}
.rb.active{background:rgba(80,144,255,.12);border-color:rgba(80,144,255,.45);color:#90bfff;}
.rb-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0;background:var(--accent);}

.cr{display:flex;align-items:center;justify-content:space-between;margin-bottom:9px;}
.cr:last-child{margin-bottom:0;}
.cl{font-size:11px;color:var(--muted);}
input[type=range]{
  -webkit-appearance:none;width:108px;height:3px;
  background:var(--border);border-radius:2px;outline:none;cursor:pointer;
}
input[type=range]::-webkit-slider-thumb{
  -webkit-appearance:none;width:13px;height:13px;border-radius:50%;
  background:var(--accent);cursor:pointer;box-shadow:0 0 6px rgba(80,144,255,.5);
}

.tb{
  display:flex;align-items:center;gap:9px;font-size:12px;cursor:pointer;
  background:none;border:1px solid var(--border);border-radius:7px;
  padding:7px 11px;color:var(--text);transition:all .16s;width:100%;margin-bottom:7px;
}
.tb:last-child{margin-bottom:0;}
.tb:hover{border-color:rgba(80,144,255,.55);}
.tb.active{background:rgba(80,144,255,.1);border-color:rgba(80,144,255,.4);color:#90bfff;}

/* Canvas */
#wrap{flex:1;position:relative;overflow:hidden;}
canvas{display:block;width:100%;height:100%;}

/* Loading */
#loading{
  position:absolute;inset:0;background:var(--bg);
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:16px;z-index:100;
}
.spin{
  width:52px;height:52px;border:3px solid rgba(80,144,255,.2);
  border-top-color:var(--accent);border-radius:50%;
  animation:sp 0.85s linear infinite;
}
@keyframes sp{to{transform:rotate(360deg);}}
.bl{
  font-size:26px;font-weight:800;
  background:linear-gradient(90deg,#6db3ff,#b197fc);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:4px;
}
.lpct{font-size:20px;font-weight:700;color:var(--accent);}
.lmsg{font-size:12.5px;color:var(--muted);}

/* Info */
.info{
  position:absolute;top:14px;right:14px;
  background:rgba(7,9,15,.88);border:1px solid var(--border);
  backdrop-filter:blur(14px);border-radius:10px;padding:11px 14px;
  font-size:11.5px;line-height:2.0;
}
.ir{display:flex;justify-content:space-between;gap:20px;}
.ik{color:var(--muted);}
.iv{color:var(--text);font-weight:500;}

/* HUD */
.hud{
  position:absolute;bottom:14px;left:50%;transform:translateX(-50%);
  display:flex;gap:8px;align-items:center;
  background:rgba(7,9,15,.82);border:1px solid var(--border);
  backdrop-filter:blur(12px);border-radius:12px;padding:7px 16px;
  font-size:11px;color:var(--muted);white-space:nowrap;
}
kbd{
  background:var(--surface2);border:1px solid var(--border);border-radius:4px;
  padding:1px 6px;color:var(--text);font-family:inherit;font-size:10px;
}
</style>
</head>
<body>
<header>
  <div class="logo">
    <div class="logo-icon">&#9992;</div>
    <span class="logo-text">FlightPrint</span>
    <span class="badge">3D Model</span>
  </div>
  <div class="hdr-stats">
    <div class="stat"><span class="sv" id="hverts">&#8212;</span><span class="sl">Vertices</span></div>
    <div class="stat"><span class="sv" id="hfaces">&#8212;</span><span class="sl">Faces</span></div>
    <div class="stat"><span class="sv" id="hfps">&#8212;</span><span class="sl">FPS</span></div>
  </div>
</header>

<div class="main">
  <div class="sidebar">

    <div class="panel">
      <div class="ptitle">Shading Mode</div>
      <div class="rb-group">
        <button class="rb active" id="rb-color" onclick="setShading('color')">
          <div class="rb-dot" style="background:#5090ff;"></div>Vertex Color
        </button>
        <button class="rb" id="rb-shaded" onclick="setShading('shaded')">
          <div class="rb-dot" style="background:#10b981;"></div>Phong Shaded
        </button>
        <button class="rb" id="rb-wire" onclick="setShading('wireframe')">
          <div class="rb-dot" style="background:#f59e0b;"></div>Wireframe
        </button>
        <button class="rb" id="rb-combined" onclick="setShading('combined')">
          <div class="rb-dot" style="background:#b197fc;"></div>Shaded + Wire
        </button>
      </div>
    </div>

    <div class="panel">
      <div class="ptitle">Lighting</div>
      <div class="cr"><span class="cl">Ambient</span>
        <input type="range" min="0" max="1" step="0.05" value="0.3"
               oninput="uAmbient=+this.value;render()"/>
      </div>
      <div class="cr"><span class="cl">Diffuse</span>
        <input type="range" min="0" max="2" step="0.1" value="1.0"
               oninput="uDiffuse=+this.value;render()"/>
      </div>
      <div class="cr"><span class="cl">Specular</span>
        <input type="range" min="0" max="2" step="0.1" value="0.4"
               oninput="uSpecular=+this.value;render()"/>
      </div>
      <div class="cr"><span class="cl">Shininess</span>
        <input type="range" min="1" max="128" step="1" value="32"
               oninput="uShininess=+this.value;render()"/>
      </div>
    </div>

    <div class="panel">
      <div class="ptitle">Navigation</div>
      <div style="font-size:11.5px;color:var(--muted);line-height:2.2;">
        <div>&#128432; <b style="color:var(--text)">Drag</b> &mdash; Orbit</div>
        <div>&#128432; <b style="color:var(--text)">Right drag</b> &mdash; Pan</div>
        <div>&#128432; <b style="color:var(--text)">Scroll</b> &mdash; Zoom</div>
        <div>&#9000; <kbd>R</kbd> Reset view</div>
        <div>&#9000; <kbd>F</kbd> Fit model</div>
        <div>&#9000; <kbd>L</kbd> Toggle light</div>
      </div>
    </div>

    <div class="panel">
      <div class="ptitle">Export</div>
      <a href="../test_run/mesh.obj" download style="
        display:flex;align-items:center;gap:8px;font-size:12px;
        background:rgba(80,144,255,.1);border:1px solid rgba(80,144,255,.3);
        border-radius:7px;padding:8px 12px;color:var(--accent);text-decoration:none;
        transition:all .16s;margin-bottom:7px;
      ">&#11015; Download OBJ</a>
      <a href="../test_run/mesh.ply" download style="
        display:flex;align-items:center;gap:8px;font-size:12px;
        background:rgba(139,92,246,.1);border:1px solid rgba(139,92,246,.3);
        border-radius:7px;padding:8px 12px;color:#b197fc;text-decoration:none;
        transition:all .16s;
      ">&#11015; Download PLY</a>
    </div>

  </div>

  <div id="wrap">
    <canvas id="c"></canvas>
    <div id="loading">
      <div class="bl">FlightPrint</div>
      <div class="spin"></div>
      <div class="lpct" id="lpct">0%</div>
      <div class="lmsg" id="lmsg">Loading mesh data&hellip;</div>
    </div>
    <div class="info">
      <div class="ir"><span class="ik">FPS</span><span class="iv" id="ifps">&#8212;</span></div>
      <div class="ir"><span class="ik">Azimuth</span><span class="iv" id="iaz">&#8212;</span></div>
      <div class="ir"><span class="ik">Elevation</span><span class="iv" id="iel">&#8212;</span></div>
      <div class="ir"><span class="ik">Shading</span><span class="iv" id="ishd">Color</span></div>
    </div>
    <div class="hud">
      <kbd>R</kbd> Reset &nbsp;&bull;&nbsp; <kbd>F</kbd> Fit &nbsp;&bull;&nbsp;
      <kbd>L</kbd> Light &nbsp;&bull;&nbsp; Drag to orbit &nbsp;&bull;&nbsp; Scroll to zoom
    </div>
  </div>
</div>

<script>
'use strict';
let MESH=null;

async function loadMesh(){
  setLoad(5,'Fetching mesh_data.json...');
  const r=await fetch('mesh_data.json');
  setLoad(30,'Parsing...');
  MESH=await r.json();
  document.getElementById('hverts').textContent=MESH.n_vertices.toLocaleString();
  document.getElementById('hfaces').textContent=MESH.n_faces.toLocaleString();
  setLoad(60,'Uploading to GPU...');
  initGL();
  setLoad(95,'Rendering...');
  render();
  document.getElementById('loading').style.display='none';
  startFPS();
}

function setLoad(p,m){
  document.getElementById('lpct').textContent=p+'%';
  document.getElementById('lmsg').textContent=m;
}

// WebGL state
let gl,canvas;
let meshProg,wireProg;
let vao,wVao;
let nIdx=0,nVerts=0;
let shadingMode='color';
let uAmbient=0.3,uDiffuse=1.0,uSpecular=0.4,uShininess=32;
let lightOrbit=true;

// Shaders ---------------------------------------------------------------
const MESH_VS=`#version 300 es
precision highp float;
in vec3 aPos;in vec3 aNorm;in vec3 aCol;
uniform mat4 uMV;uniform mat4 uP;uniform mat3 uNM;
out vec3 vPos;out vec3 vNorm;out vec3 vCol;
void main(){
  vec4 mv=uMV*vec4(aPos,1.);
  gl_Position=uP*mv;
  vPos=mv.xyz;
  vNorm=normalize(uNM*aNorm);
  vCol=aCol;
}`;
const MESH_FS=`#version 300 es
precision highp float;
in vec3 vPos;in vec3 vNorm;in vec3 vCol;
uniform int uMode; // 0=color,1=shaded,2=combined
uniform float uAmb,uDiff,uSpec,uShin;
uniform vec3 uLightPos;
out vec4 fc;
void main(){
  vec3 N=normalize(vNorm);
  vec3 L=normalize(uLightPos-vPos);
  vec3 V=normalize(-vPos);
  vec3 H=normalize(L+V);
  float diff=max(dot(N,L),0.)*uDiff;
  float spec=pow(max(dot(N,H),0.),uShin)*uSpec;
  if(uMode==0){
    // vertex color only
    fc=vec4(vCol,1.);
  } else if(uMode==1){
    // phong shaded (ignore vertex color, use neutral gray)
    vec3 base=vec3(0.72,0.75,0.80);
    vec3 c=base*(uAmb+diff)+vec3(spec);
    fc=vec4(clamp(c,0.,1.),1.);
  } else {
    // combined: vertex color + lighting
    vec3 c=vCol*(uAmb+diff)+vec3(spec);
    fc=vec4(clamp(c,0.,1.),1.);
  }
}`;
const WIRE_VS=`#version 300 es
precision highp float;
in vec3 aPos;uniform mat4 uMV;uniform mat4 uP;
void main(){gl_Position=uP*uMV*vec4(aPos,1.);}`;
const WIRE_FS=`#version 300 es
precision highp float;
uniform vec4 uCol;out vec4 fc;
void main(){fc=uCol;}`;

function mkSh(t,s){const sh=gl.createShader(t);gl.shaderSource(sh,s);gl.compileShader(sh);
  if(!gl.getShaderParameter(sh,gl.COMPILE_STATUS))console.error(gl.getShaderInfoLog(sh));return sh;}
function mkP(vs,fs){
  const p=gl.createProgram();
  gl.attachShader(p,mkSh(gl.VERTEX_SHADER,vs));
  gl.attachShader(p,mkSh(gl.FRAGMENT_SHADER,fs));
  gl.linkProgram(p);return p;
}

function initGL(){
  canvas=document.getElementById('c');
  gl=canvas.getContext('webgl2',{antialias:true,powerPreference:'high-performance'});
  meshProg=mkP(MESH_VS,MESH_FS);
  wireProg=mkP(WIRE_VS,WIRE_FS);
  gl.enable(gl.DEPTH_TEST);
  gl.enable(gl.CULL_FACE);
  gl.cullFace(gl.BACK);

  const pos=new Float32Array(MESH.positions);
  const nor=new Float32Array(MESH.normals.length?MESH.normals:MESH.positions.length/3*3|0);
  const col=new Float32Array(MESH.vertex_colors);
  const idx=new Uint32Array(MESH.indices);
  nIdx=idx.length;
  nVerts=pos.length/3;

  // Main VAO
  vao=gl.createVertexArray();gl.bindVertexArray(vao);
  function buf(data,loc,sz){
    const b=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,b);
    gl.bufferData(gl.ARRAY_BUFFER,data,gl.STATIC_DRAW);
    gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,sz,gl.FLOAT,false,0,0);
  }
  buf(pos,gl.getAttribLocation(meshProg,'aPos'),3);
  buf(nor.length===pos.length?nor:pos,gl.getAttribLocation(meshProg,'aNorm'),3);
  buf(col,gl.getAttribLocation(meshProg,'aCol'),3);
  const ib=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,ib);
  gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,idx,gl.STATIC_DRAW);
  gl.bindVertexArray(null);

  // Wire VAO (same positions + indices)
  wVao=gl.createVertexArray();gl.bindVertexArray(wVao);
  const wb=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,wb);
  gl.bufferData(gl.ARRAY_BUFFER,pos,gl.STATIC_DRAW);
  gl.enableVertexAttribArray(gl.getAttribLocation(wireProg,'aPos'));
  gl.vertexAttribPointer(gl.getAttribLocation(wireProg,'aPos'),3,gl.FLOAT,false,0,0);
  const wib=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,wib);
  gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,idx,gl.STATIC_DRAW);
  gl.bindVertexArray(null);

  resize();window.addEventListener('resize',()=>{resize();render();});
  addControls();
}

// Camera
let az=30,el=25,dist=2.5,tgt=[0,0,0];
function resetView(){az=30;el=25;dist=2.5;tgt=[0,0,0];}

// Math
const m4=()=>new Float32Array(16);
function id(m){m.fill(0);m[0]=m[5]=m[10]=m[15]=1;return m;}
function persp(m,f,a,n,fr){
  id(m);const t=1/Math.tan(f/2);
  m[0]=t/a;m[5]=t;m[10]=(fr+n)/(n-fr);m[11]=-1;m[14]=2*fr*n/(n-fr);m[15]=0;return m;
}
function lkat(m,ex,ey,ez,cx,cy,cz){
  const nrm=(...v)=>{const a=v.length===1?v[0]:v,n=Math.hypot(...a)||1;return Array.isArray(a)?a.map(x=>x/n):[a[0]/n,a[1]/n,a[2]/n];};
  const crs=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
  const dot=(a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
  const fz=nrm(ex-cx,ey-cy,ez-cz),rx=nrm(...crs([0,1,0],fz)),ry=crs(fz,rx);
  m[0]=rx[0];m[4]=rx[1];m[8]=rx[2];m[12]=-dot(rx,[ex,ey,ez]);
  m[1]=ry[0];m[5]=ry[1];m[9]=ry[2];m[13]=-dot(ry,[ex,ey,ez]);
  m[2]=fz[0];m[6]=fz[1];m[10]=fz[2];m[14]=-dot(fz,[ex,ey,ez]);
  m[3]=0;m[7]=0;m[11]=0;m[15]=1;return m;
}
function mul4(a,b){const r=m4();for(let i=0;i<4;i++)for(let j=0;j<4;j++){let s=0;for(let k=0;k<4;k++)s+=a[i+k*4]*b[k+j*4];r[i+j*4]=s;}return r;}
function inv3(m4){
  const m=m4;
  const a=m[0],b=m[4],c=m[8],d=m[1],e=m[5],f=m[9],g=m[2],h=m[6],i=m[10];
  const det=a*(e*i-f*h)-b*(d*i-f*g)+c*(d*h-e*g);
  const inv=1/det;
  return new Float32Array([
    (e*i-f*h)*inv,(c*h-b*i)*inv,(b*f-c*e)*inv,
    (f*g-d*i)*inv,(a*i-c*g)*inv,(c*d-a*f)*inv,
    (d*h-e*g)*inv,(b*g-a*h)*inv,(a*e-b*d)*inv,
  ]);
}
function getMatrices(){
  const aR=az*Math.PI/180,eR=el*Math.PI/180;
  const ex=tgt[0]+dist*Math.cos(eR)*Math.sin(aR);
  const ey=tgt[1]+dist*Math.sin(eR);
  const ez=tgt[2]+dist*Math.cos(eR)*Math.cos(aR);
  const MV=m4();lkat(MV,ex,ey,ez,...tgt);
  const P=m4();persp(P,Math.PI/3,canvas.width/canvas.height,.0001,1000);
  const NM=inv3(MV);
  // Orbiting light position in camera space
  const lt=lightOrbit?[2*Math.cos(az*0.7*Math.PI/180),2,2]:[-2,3,2];
  return{MV,P,NM,lightPos:lt,eye:[ex,ey,ez]};
}

function resize(){
  canvas.width=canvas.clientWidth*devicePixelRatio;
  canvas.height=canvas.clientHeight*devicePixelRatio;
  gl.viewport(0,0,canvas.width,canvas.height);
}

function render(){
  gl.clearColor(.028,.035,.059,1);
  gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
  const{MV,P,NM,lightPos}=getMatrices();

  if(shadingMode==='wireframe'){
    // Wireframe only
    gl.useProgram(wireProg);
    gl.uniformMatrix4fv(gl.getUniformLocation(wireProg,'uMV'),false,MV);
    gl.uniformMatrix4fv(gl.getUniformLocation(wireProg,'uP'),false,P);
    gl.uniform4fv(gl.getUniformLocation(wireProg,'uCol'),[0.3,0.6,1.0,0.85]);
    gl.bindVertexArray(wVao);
    // Draw as lines — need line indices (pairs from triangles)
    // Use TRIANGLES but with polygon offset to see edges
    gl.enable(gl.POLYGON_OFFSET_FILL);
    gl.polygonOffset(1,1);
    gl.drawElements(gl.TRIANGLES,nIdx,gl.UNSIGNED_INT,0);
    gl.disable(gl.POLYGON_OFFSET_FILL);
    gl.bindVertexArray(null);
    return;
  }

  // Draw solid mesh
  gl.useProgram(meshProg);
  gl.uniformMatrix4fv(gl.getUniformLocation(meshProg,'uMV'),false,MV);
  gl.uniformMatrix4fv(gl.getUniformLocation(meshProg,'uP'),false,P);
  gl.uniformMatrix3fv(gl.getUniformLocation(meshProg,'uNM'),false,NM);
  gl.uniform3fv(gl.getUniformLocation(meshProg,'uLightPos'),lightPos);
  gl.uniform1f(gl.getUniformLocation(meshProg,'uAmb'),uAmbient);
  gl.uniform1f(gl.getUniformLocation(meshProg,'uDiff'),uDiffuse);
  gl.uniform1f(gl.getUniformLocation(meshProg,'uSpec'),uSpecular);
  gl.uniform1f(gl.getUniformLocation(meshProg,'uShin'),uShininess);
  const modeMap={'color':0,'shaded':1,'combined':2};
  gl.uniform1i(gl.getUniformLocation(meshProg,'uMode'),modeMap[shadingMode]??2);

  gl.enable(gl.POLYGON_OFFSET_FILL);
  gl.polygonOffset(1,1);
  gl.bindVertexArray(vao);
  gl.drawElements(gl.TRIANGLES,nIdx,gl.UNSIGNED_INT,0);
  gl.bindVertexArray(null);
  gl.disable(gl.POLYGON_OFFSET_FILL);

  // If combined mode, overlay wireframe
  if(shadingMode==='combined'){
    gl.useProgram(wireProg);
    gl.uniformMatrix4fv(gl.getUniformLocation(wireProg,'uMV'),false,MV);
    gl.uniformMatrix4fv(gl.getUniformLocation(wireProg,'uP'),false,P);
    gl.uniform4fv(gl.getUniformLocation(wireProg,'uCol'),[0.4,0.65,1.0,0.15]);
    gl.bindVertexArray(wVao);
    gl.drawElements(gl.TRIANGLES,nIdx,gl.UNSIGNED_INT,0);
    gl.bindVertexArray(null);
  }

  document.getElementById('iaz').textContent=(((az%360)+360)%360).toFixed(1)+String.fromCharCode(176);
  document.getElementById('iel').textContent=el.toFixed(1)+String.fromCharCode(176);
}

function setShading(mode){
  shadingMode=mode;
  ['color','shaded','wireframe','combined'].forEach(m=>{
    document.getElementById('rb-'+m).classList.toggle('active',m===mode);
  });
  document.getElementById('ishd').textContent=mode.charAt(0).toUpperCase()+mode.slice(1);
  if(mode==='wireframe'){gl.disable(gl.CULL_FACE);}else{gl.enable(gl.CULL_FACE);}
  render();
}

function addControls(){
  let drag=false,rDrag=false,lx=0,ly=0;
  canvas.addEventListener('mousedown',e=>{drag=true;rDrag=e.button===2;lx=e.clientX;ly=e.clientY;});
  canvas.addEventListener('contextmenu',e=>e.preventDefault());
  window.addEventListener('mouseup',()=>{drag=false;});
  window.addEventListener('mousemove',e=>{
    if(!drag)return;
    const dx=e.clientX-lx,dy=e.clientY-ly;lx=e.clientX;ly=e.clientY;
    if(rDrag){
      const aR=az*Math.PI/180,eR=el*Math.PI/180;
      const rx=Math.cos(aR),rz=-Math.sin(aR);
      const ux=-Math.sin(eR)*Math.sin(aR),uy=Math.cos(eR),uz=-Math.sin(eR)*Math.cos(aR);
      const s=dist*.002;
      tgt[0]-=dx*rx*s;tgt[2]-=dx*rz*s;tgt[0]-=dy*ux*s;tgt[1]-=dy*uy*s;tgt[2]-=dy*uz*s;
    }else{az+=dx*.4;el=Math.max(-89,Math.min(89,el-dy*.3));}
    render();
  });
  canvas.addEventListener('wheel',e=>{e.preventDefault();dist*=e.deltaY>0?1.1:.9;dist=Math.max(.001,dist);render();},{passive:false});
  window.addEventListener('keydown',e=>{
    if(e.key==='r'||e.key==='R'){resetView();render();}
    if(e.key==='f'||e.key==='F'){resetView();render();}
    if(e.key==='l'||e.key==='L'){lightOrbit=!lightOrbit;render();}
  });
  let lt=null,ld=null;
  canvas.addEventListener('touchstart',e=>{
    if(e.touches.length===1)lt={x:e.touches[0].clientX,y:e.touches[0].clientY};
    if(e.touches.length===2)ld=Math.hypot(e.touches[0].clientX-e.touches[1].clientX,e.touches[0].clientY-e.touches[1].clientY);
  },{passive:true});
  canvas.addEventListener('touchmove',e=>{
    if(e.touches.length===1&&lt){const dx=e.touches[0].clientX-lt.x,dy=e.touches[0].clientY-lt.y;lt={x:e.touches[0].clientX,y:e.touches[0].clientY};az+=dx*.4;el=Math.max(-89,Math.min(89,el-dy*.3));render();}
    if(e.touches.length===2&&ld){const d=Math.hypot(e.touches[0].clientX-e.touches[1].clientX,e.touches[0].clientY-e.touches[1].clientY);dist*=ld/d;ld=d;render();}
  },{passive:true});
}

let ff=0,fl=performance.now();
function startFPS(){
  (function loop(){ff++;const n=performance.now();if(n-fl>1000){const fps=ff;document.getElementById('hfps').textContent=fps;document.getElementById('ifps').textContent=fps;ff=0;fl=n;}requestAnimationFrame(loop);})();
}

loadMesh();
</script>
</body>
</html>
"""

viewer_path = MODEL_DIR / "index.html"
with open(viewer_path, "w", encoding="utf-8") as f:
    f.write(HTML)

print(f"  Saved {viewer_path}")
print("\n" + "=" * 60)
print("DONE!")
print(f"  Mesh vertices: {n_verts:,}")
print(f"  Mesh faces:    {n_faces:,}")
print(f"  OBJ:           {obj_path}")
print(f"  PLY:           {ply_path}")
print(f"  Viewer:        {viewer_path}")
print("=" * 60)
print(f"\nServe with:  python -m http.server 8766 --directory output/3d_model")
print(f"Then open:   http://localhost:8766/")
