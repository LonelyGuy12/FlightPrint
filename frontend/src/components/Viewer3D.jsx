import { useRef, useMemo, useEffect, useCallback, Suspense } from 'react';
import { Canvas, useFrame, useThree, useLoader } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader';
import { parsePLY, computeBounds } from '../utils/plyParser';

/* ─── Point Cloud Object ─────────────────────────────────────────────── */
function PointCloud({ data, pointSize = 2.0 }) {
  const geometry = useMemo(() => {
    if (!data) return null;
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
        color={data?.colors ? undefined : '#818cf8'}
        transparent
        opacity={0.9}
        depthWrite={false}
      />
    </points>
  );
}

/* ─── 3D Mesh Object (Proper Map) ────────────────────────────────────── */
function SolidMap({ url }) {
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
    const material = new THREE.MeshStandardMaterial({
      vertexColors: hasColors,
      color: hasColors ? undefined : '#65a30d',
      roughness: 0.8,
      metalness: 0.05,
      side: THREE.DoubleSide,
    });
    return new THREE.Mesh(geom, material);
  }, [geometry]);

  if (!mesh) return null;
  return <primitive object={mesh} />;
}

/* ─── Camera Trajectory Line ─────────────────────────────────────────── */
function CameraPath({ trajectory, visible = true }) {
  const geometry = useMemo(() => {
    if (!trajectory?.trajectory) return null;
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
    <line geometry={geometry}>
      <lineBasicMaterial color="#6366f1" linewidth={2} transparent opacity={0.7} />
    </line>
  );
}

/* ─── Anomaly Markers ────────────────────────────────────────────────── */
function PulsingRing({ color }) {
  const ref = useRef();
  useFrame(({ clock }) => {
    if (ref.current) {
      const s = 1 + Math.sin(clock.elapsedTime * 3) * 0.3;
      ref.current.scale.set(s, s, s);
      ref.current.material.opacity = 0.5 - Math.sin(clock.elapsedTime * 3) * 0.2;
    }
  });
  return (
    <mesh ref={ref}>
      <ringGeometry args={[1.2, 1.6, 32]} />
      <meshBasicMaterial color={color} transparent opacity={0.3} side={THREE.DoubleSide} />
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
        const color = severityColors[a.severity] || '#818cf8';
        return (
          <group key={i} position={[pos[0], pos[1] || 0, pos[2] || 0]}>
            <mesh onClick={(e) => { e.stopPropagation(); onSelect?.(i); }} scale={isSelected ? 1.5 : 1}>
              <sphereGeometry args={[isSelected ? 0.8 : 0.5, 16, 16]} />
              <meshStandardMaterial color={color} emissive={color} emissiveIntensity={isSelected ? 0.8 : 0.3} transparent opacity={0.85} />
            </mesh>
            {isSelected && <PulsingRing color={color} />}
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
    const pts = points.map(p => new THREE.Vector3(p[0], p[1], p[2]));
    return new THREE.BufferGeometry().setFromPoints(pts);
  }, [points]);
  return (
    <group>
      <line geometry={geometry}>
        <lineBasicMaterial color="#fbbf24" linewidth={3} />
      </line>
      {points.map((p, i) => (
        <mesh key={i} position={p}>
          <sphereGeometry args={[0.15, 12, 12]} />
          <meshStandardMaterial color="#fbbf24" emissive="#fbbf24" emissiveIntensity={0.5} />
        </mesh>
      ))}
    </group>
  );
}

/* ─── Grid Floor ─────────────────────────────────────────────────────── */
function Grid({ size = 100 }) {
  return <gridHelper args={[size, Math.max(10, Math.round(size / 10)), '#1e293b', '#1e293b']} position={[0, -0.01, 0]} />;
}

/* ─── Scene Controller ───────────────────────────────────────────────── */
function SceneController({ bounds }) {
  const { camera, controls } = useThree();

  useEffect(() => {
    if (!bounds || bounds.size === 0) return;

    const cx = bounds.center[0];
    const cy = bounds.center[1];
    const cz = bounds.center[2];
    const d = bounds.size * 1.5;
    
    // Position camera dynamically based on bounds
    camera.position.set(
      cx + d * 0.5,
      cz + d * 0.7,
      -cy + d * 0.5
    );
    camera.near = Math.max(0.1, d * 0.001);
    camera.far = d * 20;
    camera.updateProjectionMatrix();

    if (controls) {
      controls.target.set(cx, cz, -cy);
      controls.update();
    }
  }, [bounds, camera, controls]);

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
  pointSize,
  measureMode,
  measurePoints,
  onMeasureClick,
  showTrajectory = true,
  showAnomalies = true,
}) {
  const bounds = useMemo(() => {
    if (pointCloudData?.positions) {
      return computeBounds(pointCloudData.positions);
    }
    return null;
  }, [pointCloudData]);

  const handleClick = useCallback((e) => {
    if (measureMode && e.point) {
      onMeasureClick?.([e.point.x, e.point.y, e.point.z]);
    }
  }, [measureMode, onMeasureClick]);

  if (!pointCloudData) {
    return (
      <div className="viewer__empty">
        <div className="viewer__empty-icon">🛩️</div>
        <div className="viewer__empty-text">No 3D data loaded</div>
        <div className="viewer__empty-hint">
          Upload a drone video and run the pipeline to see results here
        </div>
      </div>
    );
  }

  const targetArr = bounds 
    ? [bounds.center[0], bounds.center[2] || 0, -(bounds.center[1] || 0)]
    : [0, 0, 0];

  return (
    <Canvas
      className="viewer__canvas"
      camera={{ fov: 60, near: 0.1, far: 50000, position: [0, 100, 150] }}
      gl={{ antialias: true, alpha: false, powerPreference: 'high-performance' }}
      style={{ background: '#0a0e1a' }}
      onClick={handleClick}
    >
      <OrbitControls
        makeDefault
        enableDamping
        dampingFactor={0.08}
        rotateSpeed={0.6}
        panSpeed={0.8}
        zoomSpeed={1.2}
        minDistance={0.5}
        maxDistance={50000}
        target={targetArr}
      />

      <SceneController bounds={bounds} />

      {/* Lighting */}
      <ambientLight intensity={0.4} />
      <directionalLight position={[50, 80, 50]} intensity={0.6} />
      <directionalLight position={[-30, 60, -30]} intensity={0.3} color="#818cf8" />

      {/* Scene objects — ENU Z-up rotated to Three.js Y-up */}
      <group rotation={[-Math.PI / 2, 0, 0]}>
        {meshUrl ? (
          <Suspense fallback={null}>
            <SolidMap url={meshUrl} />
          </Suspense>
        ) : (
          <PointCloud data={pointCloudData} pointSize={pointSize} />
        )}
        <CameraPath trajectory={trajectory} visible={showTrajectory} />
        <AnomalyMarkers
          anomalies={anomalies}
          selectedIndex={selectedAnomaly}
          onSelect={onSelectAnomaly}
          visible={showAnomalies}
        />
        <MeasurementLine points={measurePoints} visible={measureMode} />
      </group>

      <Grid size={bounds ? bounds.size * 2 : 200} />

      {/* Depth fog */}
      <fog attach="fog" args={['#0a0e1a', bounds ? bounds.size * 3 : 200, bounds ? bounds.size * 8 : 800]} />
    </Canvas>
  );
}
