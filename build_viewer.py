"""build_viewer.py — writes the 3D map index.html into a given directory."""
from pathlib import Path


HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>FlightPrint - 3D Map</title>
<meta name="description" content="Interactive 3D reconstruction map from drone imagery - FlightPrint"/>
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

/* ==== Header ==== */
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

/* ==== Layout ==== */
.main{display:flex;flex:1;overflow:hidden;}

/* ==== Sidebar ==== */
.sidebar{
  width:246px;background:rgba(13,20,33,0.98);
  border-right:1px solid var(--border);
  display:flex;flex-direction:column;gap:10px;padding:12px;
  overflow-y:auto;flex-shrink:0;
}
.panel{background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:12px;}
.ptitle{font-size:9px;font-weight:700;color:var(--muted);
  text-transform:uppercase;letter-spacing:.1em;margin-bottom:10px;}

.tb{
  display:flex;align-items:center;gap:9px;font-size:12px;cursor:pointer;
  background:none;border:1px solid var(--border);border-radius:7px;
  padding:7px 11px;color:var(--text);transition:all .16s;width:100%;margin-bottom:7px;
}
.tb:last-child{margin-bottom:0;}
.tb:hover{border-color:rgba(80,144,255,.55);background:rgba(80,144,255,.06);}
.tb.active{background:rgba(80,144,255,.1);border-color:rgba(80,144,255,.4);color:#90bfff;}
.dot{width:7px;height:7px;border-radius:50%;flex-shrink:0;}

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

.li{display:flex;align-items:center;gap:8px;margin-bottom:7px;font-size:11.5px;color:var(--muted);}
.sw{width:11px;height:11px;border-radius:3px;flex-shrink:0;}

/* ==== Canvas ==== */
#wrap{flex:1;position:relative;overflow:hidden;}
canvas{display:block;width:100%;height:100%;}

/* ==== Overlays ==== */
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
  font-size:26px;font-weight:800;letter-spacing:-.02em;
  background:linear-gradient(90deg,#6db3ff,#b197fc);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:4px;
}
.lpct{font-size:20px;font-weight:700;color:var(--accent);}
.lmsg{font-size:12.5px;color:var(--muted);}

.info{
  position:absolute;top:14px;right:14px;
  background:rgba(7,9,15,.88);border:1px solid var(--border);
  backdrop-filter:blur(14px);border-radius:10px;padding:11px 14px;
  font-size:11.5px;line-height:2.0;
}
.ir{display:flex;justify-content:space-between;gap:20px;}
.ik{color:var(--muted);}
.iv{color:var(--text);font-weight:500;font-feature-settings:"tnum";}

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
    <span class="badge">3D Map</span>
  </div>
  <div class="hdr-stats">
    <div class="stat"><span class="sv" id="hpts">&#8212;</span><span class="sl">Points</span></div>
    <div class="stat"><span class="sv" id="hcams">&#8212;</span><span class="sl">Cameras</span></div>
    <div class="stat"><span class="sv" id="hmode">&#8212;</span><span class="sl">Mode</span></div>
  </div>
</header>

<div class="main">
  <div class="sidebar">

    <div class="panel">
      <div class="ptitle">Layers</div>
      <button class="tb active" id="btn-pts" onclick="toggleLayer('pts')">
        <div class="dot" style="background:#5090ff;"></div>Point Cloud
      </button>
      <button class="tb active" id="btn-traj" onclick="toggleLayer('traj')">
        <div class="dot" style="background:#f59e0b;"></div>Flight Path
      </button>
      <button class="tb active" id="btn-cams" onclick="toggleLayer('cams')">
        <div class="dot" style="background:#f04747;"></div>Camera Positions
      </button>
    </div>

    <div class="panel">
      <div class="ptitle">Rendering</div>
      <div class="cr"><span class="cl">Point size</span>
        <input type="range" min="1" max="8" step="0.5" value="2.5"
               oninput="ptSize=+this.value;render()"/>
      </div>
      <div class="cr"><span class="cl">Brightness</span>
        <input type="range" min="0.3" max="3" step="0.1" value="1.1"
               oninput="bright=+this.value;render()"/>
      </div>
      <div class="cr"><span class="cl">Opacity</span>
        <input type="range" min="0.1" max="1" step="0.05" value="0.85"
               oninput="alpha=+this.value;render()"/>
      </div>
    </div>

    <div class="panel">
      <div class="ptitle">Navigation</div>
      <div style="font-size:11.5px;color:var(--muted);line-height:2.2;">
        <div>&#128432; <b style="color:var(--text)">Drag</b> &mdash; Orbit</div>
        <div>&#128432; <b style="color:var(--text)">Right drag</b> &mdash; Pan</div>
        <div>&#128432; <b style="color:var(--text)">Scroll</b> &mdash; Zoom</div>
        <div>&#9000; <kbd>R</kbd> Reset view</div>
        <div>&#9000; <kbd>F</kbd> Fit scene</div>
      </div>
    </div>

    <div class="panel">
      <div class="ptitle">Legend</div>
      <div class="li"><div class="sw" style="background:#5090ff;"></div>Scene points</div>
      <div class="li"><div class="sw" style="background:#f59e0b;"></div>Flight path</div>
      <div class="li"><div class="sw" style="background:#f04747;border-radius:50%;"></div>Camera positions</div>
    </div>

  </div>

  <div id="wrap">
    <canvas id="c"></canvas>

    <div id="loading">
      <div class="bl">FlightPrint</div>
      <div class="spin"></div>
      <div class="lpct" id="lpct">0%</div>
      <div class="lmsg" id="lmsg">Loading scene data&hellip;</div>
    </div>

    <div class="info">
      <div class="ir"><span class="ik">FPS</span><span class="iv" id="fps">&#8212;</span></div>
      <div class="ir"><span class="ik">Azimuth</span><span class="iv" id="iaz">&#8212;</span></div>
      <div class="ir"><span class="ik">Elevation</span><span class="iv" id="iel">&#8212;</span></div>
      <div class="ir"><span class="ik">Distance</span><span class="iv" id="idist">&#8212;</span></div>
    </div>

    <div class="hud">
      <kbd>R</kbd> Reset &nbsp;&bull;&nbsp; <kbd>F</kbd> Fit scene &nbsp;&bull;&nbsp;
      Drag to orbit &nbsp;&bull;&nbsp; Scroll to zoom
    </div>
  </div>
</div>

<script>
'use strict';
let SCENE=null;

async function loadScene(){
  setLoad(5,'Fetching scene_data.json...');
  const r=await fetch('scene_data.json');
  setLoad(25,'Parsing JSON...');
  SCENE=await r.json();
  document.getElementById('hpts').textContent=SCENE.n_dense.toLocaleString();
  document.getElementById('hcams').textContent=SCENE.n_poses;
  document.getElementById('hmode').textContent=SCENE.mode.replace(/_/g,' ').replace(/\\b\\w/g,c=>c.toUpperCase());
  setLoad(55,'Building GPU buffers...');
  initGL();
  setLoad(95,'First render...');
  render();
  document.getElementById('loading').style.display='none';
  startFPS();
}

function setLoad(p,m){
  document.getElementById('lpct').textContent=p+'%';
  document.getElementById('lmsg').textContent=m;
}

// WebGL
let gl,canvas,pProg,lProg;
let pBuf,cBuf,lBuf,camBuf,camCBuf;
let nPts=0,nLines=0,nCams=0;
let showPts=true,showTraj=true,showCams=true;
let ptSize=2.5,bright=1.1,alpha=0.85;

const VS_PT=`#version 300 es
precision highp float;
in vec3 aP;in vec3 aC;
uniform mat4 uMVP;uniform float uSz;
out vec3 vC;
void main(){gl_Position=uMVP*vec4(aP,1.);gl_PointSize=uSz;vC=aC;}`;
const FS_PT=`#version 300 es
precision highp float;
in vec3 vC;uniform float uB,uA;out vec4 fc;
void main(){
  vec2 d=gl_PointCoord-.5;if(dot(d,d)>.25)discard;
  fc=vec4(clamp(vC*uB,0.,1.),uA);
}`;
const VS_LN=`#version 300 es
precision highp float;
in vec3 aP;uniform mat4 uMVP;uniform vec4 uCol;out vec4 vCol;
void main(){gl_Position=uMVP*vec4(aP,1.);vCol=uCol;}`;
const FS_LN=`#version 300 es
precision highp float;
in vec4 vCol;out vec4 fc;void main(){fc=vCol;}`;

function mkShader(t,s){const sh=gl.createShader(t);gl.shaderSource(sh,s);gl.compileShader(sh);return sh;}
function mkProg(vs,fs){
  const p=gl.createProgram();
  gl.attachShader(p,mkShader(gl.VERTEX_SHADER,vs));
  gl.attachShader(p,mkShader(gl.FRAGMENT_SHADER,fs));
  gl.linkProgram(p);return p;
}
function mkBuf(data,dyn){
  const b=gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER,b);
  gl.bufferData(gl.ARRAY_BUFFER,data,dyn?gl.DYNAMIC_DRAW:gl.STATIC_DRAW);
  return b;
}
function useAttr(prog,name,buf,size){
  gl.bindBuffer(gl.ARRAY_BUFFER,buf);
  const loc=gl.getAttribLocation(prog,name);
  gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc,size,gl.FLOAT,false,0,0);
}

function initGL(){
  canvas=document.getElementById('c');
  gl=canvas.getContext('webgl2',{antialias:true,powerPreference:'high-performance'});
  pProg=mkProg(VS_PT,FS_PT);
  lProg=mkProg(VS_LN,FS_LN);
  gl.enable(gl.DEPTH_TEST);
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);

  const pc=SCENE.point_cloud;
  nPts=pc.points.length;
  if(nPts>0){
    pBuf=mkBuf(new Float32Array(pc.points.flat()));
    cBuf=mkBuf(new Float32Array(pc.colors.flat()));
  }
  const traj=SCENE.trajectory;
  nCams=traj.length;
  if(nCams>1){
    const lv=[];
    for(let i=0;i<traj.length-1;i++)lv.push(...traj[i].position,...traj[i+1].position);
    lBuf=mkBuf(new Float32Array(lv));
    nLines=(traj.length-1)*2;
  }
  if(nCams>0){
    camBuf=mkBuf(new Float32Array(traj.flatMap(t=>t.position)));
    camCBuf=mkBuf(new Float32Array(traj.flatMap(()=>[0.94,0.28,0.28])));
  }
  calcAABB();fitView();
  resize();
  window.addEventListener('resize',()=>{resize();render();});
  addControls();
}

// Camera
let AABB={cen:[0,0,0],r:1};
function calcAABB(){
  const pts=SCENE.point_cloud.points;
  const src=pts.length?pts:SCENE.trajectory.map(t=>t.position);
  if(!src.length)return;
  let mn=[1e9,1e9,1e9],mx=[-1e9,-1e9,-1e9];
  for(const p of src)for(let k=0;k<3;k++){if(p[k]<mn[k])mn[k]=p[k];if(p[k]>mx[k])mx[k]=p[k];}
  const cx=(mn[0]+mx[0])/2,cy=(mn[1]+mx[1])/2,cz=(mn[2]+mx[2])/2;
  AABB={cen:[cx,cy,cz],r:Math.max(Math.hypot(mx[0]-mn[0],mx[1]-mn[1],mx[2]-mn[2])/2,.01)};
}
let az=32,el=22,dist=3,tgt=[0,0,0];
function fitView(){tgt=[...AABB.cen];dist=AABB.r*4.0;az=32;el=22;}

// Math
function m4(){return new Float32Array(16);}
function id(m){m.fill(0);m[0]=m[5]=m[10]=m[15]=1;return m;}
function persp(m,f,a,n,fr){id(m);const t=1/Math.tan(f/2);m[0]=t/a;m[5]=t;m[10]=(fr+n)/(n-fr);m[11]=-1;m[14]=2*fr*n/(n-fr);m[15]=0;return m;}
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
function getMVP(){
  const aR=az*Math.PI/180,eR=el*Math.PI/180;
  const ex=tgt[0]+dist*Math.cos(eR)*Math.sin(aR),ey=tgt[1]+dist*Math.sin(eR),ez=tgt[2]+dist*Math.cos(eR)*Math.cos(aR);
  const V=m4();lkat(V,ex,ey,ez,...tgt);
  const P=m4();persp(P,Math.PI/3,canvas.width/canvas.height,.0001,100000);
  return mul4(P,V);
}
function resize(){canvas.width=canvas.clientWidth*devicePixelRatio;canvas.height=canvas.clientHeight*devicePixelRatio;gl.viewport(0,0,canvas.width,canvas.height);}

function render(){
  gl.clearColor(.028,.035,.059,1);
  gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
  const mvp=getMVP();

  if(showPts&&nPts>0&&pBuf){
    gl.useProgram(pProg);
    gl.uniformMatrix4fv(gl.getUniformLocation(pProg,'uMVP'),false,mvp);
    gl.uniform1f(gl.getUniformLocation(pProg,'uSz'),ptSize*devicePixelRatio);
    gl.uniform1f(gl.getUniformLocation(pProg,'uB'),bright);
    gl.uniform1f(gl.getUniformLocation(pProg,'uA'),alpha);
    useAttr(pProg,'aP',pBuf,3);useAttr(pProg,'aC',cBuf,3);
    gl.drawArrays(gl.POINTS,0,nPts);
  }
  if(showTraj&&nLines>0&&lBuf){
    gl.useProgram(lProg);
    gl.uniformMatrix4fv(gl.getUniformLocation(lProg,'uMVP'),false,mvp);
    gl.uniform4fv(gl.getUniformLocation(lProg,'uCol'),[.953,.624,.067,.92]);
    useAttr(lProg,'aP',lBuf,3);
    gl.lineWidth(2);gl.drawArrays(gl.LINES,0,nLines);
  }
  if(showCams&&nCams>0&&camBuf){
    gl.useProgram(pProg);
    gl.uniformMatrix4fv(gl.getUniformLocation(pProg,'uMVP'),false,mvp);
    gl.uniform1f(gl.getUniformLocation(pProg,'uSz'),8*devicePixelRatio);
    gl.uniform1f(gl.getUniformLocation(pProg,'uB'),1.8);
    gl.uniform1f(gl.getUniformLocation(pProg,'uA'),1.0);
    useAttr(pProg,'aP',camBuf,3);useAttr(pProg,'aC',camCBuf,3);
    gl.drawArrays(gl.POINTS,0,nCams);
  }
  document.getElementById('iaz').textContent=(((az%360)+360)%360).toFixed(1)+String.fromCharCode(176);
  document.getElementById('iel').textContent=el.toFixed(1)+String.fromCharCode(176);
  document.getElementById('idist').textContent=dist.toFixed(3);
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
      const s=dist*.0018;
      tgt[0]-=dx*rx*s;tgt[2]-=dx*rz*s;tgt[0]-=dy*ux*s;tgt[1]-=dy*uy*s;tgt[2]-=dy*uz*s;
    }else{az+=dx*.4;el=Math.max(-89,Math.min(89,el-dy*.3));}
    render();
  });
  canvas.addEventListener('wheel',e=>{e.preventDefault();dist*=e.deltaY>0?1.12:.9;dist=Math.max(.00001,dist);render();},{passive:false});
  window.addEventListener('keydown',e=>{
    if(e.key==='r'||e.key==='R'){az=32;el=22;render();}
    if(e.key==='f'||e.key==='F'){fitView();render();}
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

function toggleLayer(l){
  if(l==='pts'){showPts=!showPts;document.getElementById('btn-pts').classList.toggle('active',showPts);}
  if(l==='traj'){showTraj=!showTraj;document.getElementById('btn-traj').classList.toggle('active',showTraj);}
  if(l==='cams'){showCams=!showCams;document.getElementById('btn-cams').classList.toggle('active',showCams);}
  render();
}

let ff=0,fl=performance.now();
function startFPS(){
  (function loop(){ff++;const n=performance.now();if(n-fl>1000){document.getElementById('fps').textContent=ff;ff=0;fl=n;}requestAnimationFrame(loop);})();
}

loadScene();
</script>
</body>
</html>
"""


def build_viewer(viewer_dir):
    """Write the 3D map index.html to viewer_dir."""
    p = __import__('pathlib').Path(viewer_dir)
    p.mkdir(parents=True, exist_ok=True)
    out = p / "index.html"
    out.write_text(HTML, encoding="utf-8")
    print(f"  OK  Viewer -> {out}")
    return out


if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else "output/3d_map"
    build_viewer(d)
