import { useRef, useMemo, useState, useEffect, useCallback } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera } from '@react-three/drei';
import * as THREE from 'three';
import { parsePLY, computeBounds } from '../utils/plyParser';

/* ─── Point Cloud Object ─────────────────────────────────────────────── */
function PointCloud({ data, pointSize = 2.0, visible = true }) {
  const ref = useRef();

  const geometry = useMemo(() => {
    if (!data) return null;
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(data.positions, 3));
    if (data.colors) {
      geo.setAttribute('color', new THREE.Float32BufferAttribute(data.colors, 3));
    }
    return geo;
  }, [data]);

  if (!geometry || !visible) return null;

  return (
    <points ref={ref} geometry={geometry}>
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

/* ─── Camera Trajectory Line ─────────────────────────────────────────── */
function CameraPath({ trajectory, visible = true }) {
  const geometry = useMemo(() => {
    if (!trajectory?.trajectory) return null;

    const points = [];
    for (const entry of trajectory.trajectory) {
      if (entry.pose) {
        // Camera center = -R^T * t
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
function AnomalyMarkers({ anomalies, selectedIndex, onSelect, visible = true }) {
  if (!anomalies?.length || !visible) return null;

  const severityColors = {
    low: '#34d399',
    medium: '#fbbf24',
    high: '#f87171',
  };

  return (
    <group>
      {anomalies.map((a, i) => {
        const pos = a.position_enu;
        if (!pos) return null;

        const isSelected = selectedIndex === i;
        const color = severityColors[a.severity] || '#818cf8';

        return (
          <group key={i} position={[pos[0], pos[2] || 0, -(pos[1] || 0)]}>
            {/* Marker sphere */}
            <mesh
              onClick={(e) => { e.stopPropagation(); onSelect?.(i); }}
              scale={isSelected ? 1.5 : 1}
            >
              <sphereGeometry args={[isSelected ? 0.8 : 0.5, 16, 16]} />
              <meshStandardMaterial
                color={color}
                emissive={color}
                emissiveIntensity={isSelected ? 0.8 : 0.3}
                transparent
                opacity={0.85}
              />
            </mesh>
            {/* Pulsing ring for selected */}
            {isSelected && (
              <PulsingRing color={color} />
            )}
          </group>
        );
      })}
    </group>
  );
}

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
    <mesh ref={ref} rotation={[-Math.PI / 2, 0, 0]}>
      <ringGeometry args={[1.2, 1.6, 32]} />
      <meshBasicMaterial color={color} transparent opacity={0.3} side={THREE.DoubleSide} />
    </mesh>
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
  return (
    <gridHelper
      args={[size, size / 2, '#1e293b', '#1e293b']}
      position={[0, -0.01, 0]}
    />
  );
}

/* ─── Scene Setup ────────────────────────────────────────────────────── */
function SceneSetup({ bounds }) {
  const { camera } = useThree();

  useEffect(() => {
    if (bounds && bounds.size > 0) {
      const d = bounds.size * 1.5;
      camera.position.set(
        bounds.center[0] + d * 0.6,
        bounds.center[2] + d * 0.8,
        -(bounds.center[1]) + d * 0.6,
      );
      camera.lookAt(bounds.center[0], bounds.center[2] || 0, -(bounds.center[1] || 0));
      camera.near = 0.1;
      camera.far = bounds.size * 10;
      camera.updateProjectionMatrix();
    }
  }, [bounds, camera]);

  return null;
}

/* ─── Main Viewer Component ──────────────────────────────────────────── */
export default function Viewer3D({
  pointCloudData,
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

  return (
    <Canvas
      className="viewer__canvas"
      gl={{ antialias: true, alpha: false, powerPreference: 'high-performance' }}
      style={{ background: '#0a0e1a' }}
      onClick={handleClick}
    >
      <PerspectiveCamera makeDefault fov={60} near={0.1} far={10000} />
      <SceneSetup bounds={bounds} />

      {/* Lighting */}
      <ambientLight intensity={0.4} />
      <directionalLight position={[50, 80, 50]} intensity={0.6} />
      <directionalLight position={[-30, 60, -30]} intensity={0.3} color="#818cf8" />

      {/* Scene objects */}
      <PointCloud data={pointCloudData} pointSize={pointSize} />
      <CameraPath trajectory={trajectory} visible={showTrajectory} />
      <AnomalyMarkers
        anomalies={anomalies}
        selectedIndex={selectedAnomaly}
        onSelect={onSelectAnomaly}
        visible={showAnomalies}
      />
      <MeasurementLine points={measurePoints} visible={measureMode} />
      <Grid size={bounds ? bounds.size * 2 : 100} />

      {/* Controls */}
      <OrbitControls
        makeDefault
        enableDamping
        dampingFactor={0.08}
        rotateSpeed={0.5}
        panSpeed={0.8}
        zoomSpeed={1.2}
        target={bounds ? [bounds.center[0], bounds.center[2] || 0, -(bounds.center[1] || 0)] : [0, 0, 0]}
      />

      {/* Fog for depth */}
      <fog attach="fog" args={['#0a0e1a', bounds ? bounds.size * 2 : 100, bounds ? bounds.size * 5 : 500]} />
    </Canvas>
  );
}
