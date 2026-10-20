import { useRef, useMemo, useEffect, useCallback, useState, Suspense } from 'react';
import { Canvas, useFrame, useThree, useLoader } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader';
import { computeBounds } from '../utils/plyParser';

/* ─── Point Cloud Object ─────────────────────────────────────────────── */
function PointCloud({ data, pointSize = 2.5 }) {
  const geometry = useMemo(() => {
    if (!data?.positions?.length) return null;
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(data.positions, 3));
    if (data.colors) {
      geo.setAttribute('color', new THREE.Float32BufferAttribute(data.colors, 3));
    }
    return geo;
  }, [data]);

  if (!geometry) return null;

  return (
    <points geometry={geometry}>
      <pointsMaterial
        size={pointSize}
        sizeAttenuation={true}
        vertexColors={!!data?.colors}
        color={data?.colors ? '#ffffff' : '#818cf8'}
        transparent
        opacity={0.92}
        depthWrite={false}
      />
    </points>
  );
}

/* ─── 3D Solid Mesh Map ──────────────────────────────────────────────── */
function SolidMap({ url, wireframe = false }) {
  const geometry = useLoader(PLYLoader, url);

  const mesh = useMemo(() => {
    if (!geometry) return null;
    const geom = geometry.clone();

    // Convert Float64Array attributes (from Open3D 'double' PLYs) to Float32Array for WebGL
    for (const key in geom.attributes) {
      const attr = geom.attributes[key];
      if (attr.array instanceof Float64Array) {
        geom.setAttribute(key, new THREE.Float32BufferAttribute(attr.array, attr.itemSize));
      }
    }

    geom.computeVertexNormals();
    const hasColors = geom.hasAttribute('color');

    if (wireframe) {
      const material = new THREE.MeshBasicMaterial({
        color: '#38bdf8',
        wireframe: true,
      });
      return new THREE.Mesh(geom, material);
    }

    const material = new THREE.MeshStandardMaterial({
      vertexColors: hasColors,
      color: hasColors ? '#ffffff' : '#cbd5e1',
      roughness: 0.65,
      metalness: 0.15,
      side: THREE.DoubleSide,
      flatShading: false,
    });
    return new THREE.Mesh(geom, material);
  }, [geometry, wireframe]);

  if (!mesh) return null;
  return <primitive object={mesh} />;
}

/* ─── Camera Trajectory Line ─────────────────────────────────────────── */
function CameraPath({ trajectory, visible = true }) {
  const geometry = useMemo(() => {
    if (!trajectory?.trajectory?.length) return null;
    const points = [];
    for (const entry of trajectory.trajectory) {
      if (entry.pose) {
        const R = new THREE.Matrix3();
        R.set(
          entry.pose[0][0], entry.pose[0][1], entry.pose[0][2],
          entry.pose[1][0], entry.pose[1][1], entry.pose[1][2],
          entry.pose[2][0], entry.pose[2][1], entry.pose[2][2],
        );
        const t = new THREE.Vector3(entry.pose[0][3], entry.pose[1][3], entry.pose[2][3]);
        const Rt = R.clone().transpose();
        const center = t.clone().negate().applyMatrix3(Rt);
        points.push(center);
      }
    }
    if (points.length < 2) return null;
    return new THREE.BufferGeometry().setFromPoints(points);
  }, [trajectory]);

  if (!geometry || !visible) return null;
  return (
    <group>
      <line geometry={geometry}>
        <lineBasicMaterial color="#a855f7" linewidth={3} transparent opacity={0.85} />
      </line>
    </group>
  );
}

/* ─── Anomaly Markers ────────────────────────────────────────────────── */
function PulsingBeacon({ color, radius = 2.5 }) {
  const ringRef = useRef();
  useFrame(({ clock }) => {
    if (ringRef.current) {
      const s = 1 + Math.sin(clock.elapsedTime * 3) * 0.4;
      ringRef.current.scale.set(s, s, s);
      ringRef.current.material.opacity = 0.6 - Math.sin(clock.elapsedTime * 3) * 0.3;
    }
  });
  return (
    <mesh ref={ringRef} rotation={[-Math.PI / 2, 0, 0]}>
      <ringGeometry args={[radius * 0.8, radius * 1.3, 32]} />
      <meshBasicMaterial color={color} transparent opacity={0.4} side={THREE.DoubleSide} />
    </mesh>
  );
}

function AnomalyMarkers({ anomalies, selectedIndex, onSelect, visible = true }) {
  if (!anomalies?.length || !visible) return null;
  const severityColors = { low: '#34d399', medium: '#fbbf24', high: '#f87171' };

  return (
    <group>
      {anomalies.map((a, i) => {
        const pos = a.position_enu;
        if (!pos) return null;
        const isSelected = selectedIndex === i;
        const color = severityColors[a.severity] || '#f87171';
        return (
          <group key={a.id || i} position={[pos[0], pos[1], pos[2]]}>
            {/* 3D Pin / Sphere */}
            <mesh
              onClick={(e) => {
                e.stopPropagation();
                onSelect?.(i);
              }}
              scale={isSelected ? 1.6 : 1.0}
            >
              <sphereGeometry args={[2.5, 24, 24]} />
              <meshStandardMaterial
                color={color}
                emissive={color}
                emissiveIntensity={isSelected ? 1.0 : 0.45}
                roughness={0.2}
              />
            </mesh>
            {/* Ground altitude indicator line */}
            <line>
              <bufferGeometry
                attach="geometry"
                attributes={{
                  position: new THREE.Float32BufferAttribute([0, 0, 0, 0, 0, -25], 3),
                }}
              />
              <lineBasicMaterial attach="material" color={color} transparent opacity={0.4} />
            </line>
            <PulsingBeacon color={color} radius={isSelected ? 4.0 : 2.5} />
          </group>
        );
      })}
    </group>
  );
}

/* ─── Measurement Line ───────────────────────────────────────────────── */
function MeasurementLine({ points, visible }) {
  if (!visible || points.length < 2) return null;
  const geometry = useMemo(() => {
    const pts = points.map((p) => new THREE.Vector3(p[0], p[1], p[2]));
    return new THREE.BufferGeometry().setFromPoints(pts);
  }, [points]);

  return (
    <group>
      <line geometry={geometry}>
        <lineBasicMaterial color="#fbbf24" linewidth={3} />
      </line>
      {points.map((p, i) => (
        <mesh key={i} position={p}>
          <sphereGeometry args={[1.0, 16, 16]} />
          <meshStandardMaterial color="#fbbf24" emissive="#fbbf24" emissiveIntensity={0.6} />
        </mesh>
      ))}
    </group>
  );
}

/* ─── Scene Controller / Auto Camera ─────────────────────────────────── */
function SceneController({ bounds, viewPreset }) {
  const { camera, controls } = useThree();

  useEffect(() => {
    if (!bounds || bounds.size === 0) return;

    const cx = bounds.center[0];
    const cy = bounds.center[1];
    const cz = bounds.center[2];
    const d = Math.min(Math.max(bounds.size * 1.3, 80), 800);

    // Coordinate conversion: ENU [x, y, z] -> Three.js [x, z, -y]
    const targetX = cx;
    const targetY = cz;
    const targetZ = -cy;

    if (viewPreset === 'top') {
      camera.position.set(targetX, targetY + d * 1.6, targetZ + 0.01);
    } else if (viewPreset === 'side') {
      camera.position.set(targetX, targetY + d * 0.3, targetZ + d * 1.3);
    } else {
      // 3D Isometric Orbit default
      camera.position.set(
        targetX + d * 0.7,
        targetY + d * 0.9,
        targetZ + d * 0.7
      );
    }

    camera.near = 0.5;
    camera.far = Math.max(d * 10, 15000);
    camera.updateProjectionMatrix();

    if (controls) {
      controls.target.set(targetX, targetY, targetZ);
      controls.update();
    }
  }, [bounds, viewPreset, camera, controls]);

  return null;
}

/* ─── Main Viewer Component ──────────────────────────────────────────── */
export default function Viewer3D({
  pointCloudData,
  meshUrl,
  trajectory,
  anomalies,
  selectedAnomaly,
  onSelectAnomaly,
  pointSize = 2.5,
  displayMode = 'mesh', // 'mesh' | 'cloud' | 'wireframe' | 'hybrid'
  onDisplayModeChange,
  measureMode,
  measurePoints,
  onMeasureClick,
  showTrajectory = true,
  showAnomalies = true,
}) {
  const [viewPreset, setViewPreset] = useState('orbit');

  const bounds = useMemo(() => {
    if (pointCloudData?.positions?.length) {
      return computeBounds(pointCloudData.positions);
    }
    // Fallback default city bounds if cloud hasn't loaded yet
    return { center: [120, 170, -100], size: 400 };
  }, [pointCloudData]);

  const handleClick = useCallback(
    (e) => {
      if (measureMode && e.point) {
        onMeasureClick?.([e.point.x, e.point.y, e.point.z]);
      }
    },
    [measureMode, onMeasureClick]
  );

  const selectedItem = anomalies?.[selectedAnomaly];
  const hasData = Boolean(pointCloudData?.positions?.length || meshUrl);

  if (!hasData) {
    return (
      <div className="viewer__empty">
        <div className="viewer__empty-icon">🛩️</div>
        <div className="viewer__empty-text">No 3D data loaded</div>
        <div className="viewer__empty-hint">
          Upload a drone video and click &ldquo;Start Pipeline&rdquo; to generate the 3D map
        </div>
      </div>
    );
  }

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      {/* ── Top Floating Map Control HUD ── */}
      <div
        style={{
          position: 'absolute',
          top: 12,
          left: 14,
          right: 14,
          zIndex: 30,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          pointerEvents: 'none',
        }}
      >
        <div
          style={{
            pointerEvents: 'auto',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            background: 'rgba(15, 23, 42, 0.88)',
            backdropFilter: 'blur(16px)',
            padding: '5px 10px',
            borderRadius: 10,
            border: '1px solid rgba(148, 163, 184, 0.18)',
            boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
          }}
        >
          <span style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.06em', marginRight: 4 }}>
            Layer:
          </span>
          <button
            className={`tab ${displayMode === 'mesh' ? 'tab--active' : ''}`}
            style={{ padding: '3px 8px', fontSize: 11, borderRadius: 6 }}
            onClick={() => onDisplayModeChange?.('mesh')}
            title="Textured 3D Buildings & Roads"
          >
            🏢 3D Map
          </button>
          <button
            className={`tab ${displayMode === 'cloud' ? 'tab--active' : ''}`}
            style={{ padding: '3px 8px', fontSize: 11, borderRadius: 6 }}
            onClick={() => onDisplayModeChange?.('cloud')}
            title="Dense 3D Point Cloud"
          >
            🌐 Point Cloud
          </button>
          <button
            className={`tab ${displayMode === 'wireframe' ? 'tab--active' : ''}`}
            style={{ padding: '3px 8px', fontSize: 11, borderRadius: 6 }}
            onClick={() => onDisplayModeChange?.('wireframe')}
            title="Architectural Wireframe Mode"
          >
            🔲 Wireframe
          </button>
          <button
            className={`tab ${displayMode === 'hybrid' ? 'tab--active' : ''}`}
            style={{ padding: '3px 8px', fontSize: 11, borderRadius: 6 }}
            onClick={() => onDisplayModeChange?.('hybrid')}
            title="Both 3D Map & Point Cloud"
          >
            ⚡ Hybrid
          </button>
        </div>

        {/* ── Camera Presets (Right Top) ── */}
        <div
          style={{
            pointerEvents: 'auto',
            display: 'flex',
            alignItems: 'center',
            gap: 5,
            background: 'rgba(15, 23, 42, 0.88)',
            backdropFilter: 'blur(16px)',
            padding: '5px 8px',
            borderRadius: 10,
            border: '1px solid rgba(148, 163, 184, 0.18)',
            boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
          }}
        >
          <button
            className={`tab ${viewPreset === 'orbit' ? 'tab--active' : ''}`}
            style={{ padding: '3px 7px', fontSize: 11, borderRadius: 6 }}
            onClick={() => setViewPreset('orbit')}
            title="Perspective Orbit View"
          >
            🛰️ Orbit
          </button>
          <button
            className={`tab ${viewPreset === 'top' ? 'tab--active' : ''}`}
            style={{ padding: '3px 7px', fontSize: 11, borderRadius: 6 }}
            onClick={() => setViewPreset('top')}
            title="Top-Down 2D Map View"
          >
            📐 Top-Down
          </button>
          <button
            className={`tab ${viewPreset === 'side' ? 'tab--active' : ''}`}
            style={{ padding: '3px 7px', fontSize: 11, borderRadius: 6 }}
            onClick={() => setViewPreset('side')}
            title="Street Level / Side View"
          >
            🏙️ Side
          </button>
        </div>
      </div>

      {/* ── Selected Anomaly Detail Card ── */}
      {selectedItem && (
        <div
          style={{
            position: 'absolute',
            bottom: 24,
            left: 20,
            zIndex: 30,
            width: 320,
            background: 'rgba(15, 23, 42, 0.92)',
            backdropFilter: 'blur(20px)',
            border: '1px solid rgba(99, 102, 241, 0.4)',
            borderRadius: 14,
            padding: 16,
            boxShadow: '0 12px 40px rgba(0,0,0,0.6)',
            animation: 'fadeIn 0.2s ease',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <span
              style={{
                fontSize: 10,
                fontWeight: 700,
                textTransform: 'uppercase',
                padding: '2px 8px',
                borderRadius: 4,
                background: selectedItem.severity === 'high' ? 'rgba(248, 113, 113, 0.2)' : 'rgba(251, 191, 36, 0.2)',
                color: selectedItem.severity === 'high' ? '#f87171' : '#fbbf24',
              }}
            >
              {selectedItem.severity} severity
            </span>
            <button
              onClick={() => onSelectAnomaly?.(null)}
              style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: 14 }}
            >
              ✕
            </button>
          </div>
          <div style={{ fontSize: 14, fontWeight: 700, color: '#f1f5f9', marginBottom: 4 }}>
            {selectedItem.title || selectedItem.id}
          </div>
          <div style={{ fontSize: 12, color: '#94a3b8', lineHeight: 1.4, marginBottom: 10 }}>
            {selectedItem.description}
          </div>
          {selectedItem.gps && (
            <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: '#818cf8' }}>
              📍 {selectedItem.gps.lat.toFixed(5)}°, {selectedItem.gps.lon.toFixed(5)}° (Alt {selectedItem.gps.alt}m)
            </div>
          )}
        </div>
      )}

      {/* ── 3D Canvas ── */}
      <Canvas
        className="viewer__canvas"
        camera={{ fov: 55, near: 0.5, far: 20000, position: [180, 260, 200] }}
        gl={{
          antialias: true,
          alpha: false,
          powerPreference: 'high-performance',
          toneMapping: THREE.ACESFilmicToneMapping,
          toneMappingExposure: 1.15,
        }}
        style={{ background: '#0a0e1a' }}
        onClick={handleClick}
      >
        <OrbitControls
          makeDefault
          enableDamping
          dampingFactor={0.08}
          rotateSpeed={0.7}
          panSpeed={0.9}
          zoomSpeed={1.2}
          minDistance={1.0}
          maxDistance={12000}
        />

        <SceneController bounds={bounds} viewPreset={viewPreset} />

        {/* ── Modern Architectural Sun & Sky Lighting ── */}
        <ambientLight intensity={0.8} />
        <hemisphereLight skyColor="#b0e0e6" groundColor="#334155" intensity={0.7} />
        <directionalLight
          position={[bounds.center[0] + 200, bounds.center[2] + 400, -bounds.center[1] + 200]}
          intensity={1.4}
          color="#fffcf5"
        />
        <directionalLight
          position={[bounds.center[0] - 200, bounds.center[2] + 250, -bounds.center[1] - 200]}
          intensity={0.6}
          color="#cce0ff"
        />

        {/* ── Scene Group: ENU Z-up mapped to Three.js Y-up ── */}
        <group rotation={[-Math.PI / 2, 0, 0]}>
          {/* Solid 3D Map Mesh */}
          {(displayMode === 'mesh' || displayMode === 'wireframe' || displayMode === 'hybrid') && meshUrl && (
            <Suspense fallback={null}>
              <SolidMap url={meshUrl} wireframe={displayMode === 'wireframe'} />
            </Suspense>
          )}

          {/* Dense Point Cloud */}
          {(displayMode === 'cloud' || displayMode === 'hybrid' || !meshUrl) && (
            <PointCloud data={pointCloudData} pointSize={pointSize} />
          )}

          {/* Camera Flight Path */}
          <CameraPath trajectory={trajectory} visible={showTrajectory} />

          {/* Anomalies */}
          <AnomalyMarkers
            anomalies={anomalies}
            selectedIndex={selectedAnomaly}
            onSelect={onSelectAnomaly}
            visible={showAnomalies}
          />

          {/* Interactive Measurement Line */}
          <MeasurementLine points={measurePoints} visible={measureMode} />
        </group>
      </Canvas>
    </div>
  );
}
