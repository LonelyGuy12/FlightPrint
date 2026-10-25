import { useState, useCallback, useEffect, useRef } from 'react';
import Viewer3D from './Viewer3D';
import Controls from './Controls';
import AnomalyPanel from './AnomalyPanel';
import MeasureTool from './MeasureTool';

/* ─── Reconstruction Workspace — Hero Experience ────────────────────────
     The 3D reconstruction occupies 65-75% of the usable workspace on desktop.
     Interactive viewport with full controls.
  -------------------------------------------------------------------------- */

export default function ReconstructionScreen({
  jobId,
  pipelineStatus,
  stageStatuses,
  pointCloudData,
  meshUrl,
  trajectory,
  anomalies,
  selectedAnomaly,
  onSelectAnomaly,
  onStartPipeline,
  onDisplayModeChange,
  onPointSizeChange,
  pointSize = 2.5,
  measureMode = false,
  measurePoints = [],
  toggleMeasure,
  applyScale,
  numPoints,
  numFrames,
  reconstructionMode,
  displayMode,
  showTrajectory,
  showAnomalies,
  onMeasureClick,
}) {
  // Toolbar ref for viewport toolbar
  const toolbarRef = useRef(null);

  return (
    <div className="reconstruction-screen">
      {/* ─── Header with viewport toolbar ───────────────────────────────── */}
      <div className="viewport-toolbar-wrapper">
        <div className="viewport-toolbar">
          <button
            className="toolbar-btn toolbar-btn--active"
            title="Mesh Mode"
          >
            🏢
          </button>
          <button
            className="toolbar-btn"
            title="Point Cloud Mode"
          >
            🌐
          </button>
          <button
            className="toolbar-btn"
            title="Wireframe Mode"
          >
            🔲
          </button>
          <button
            className="toolbar-btn"
            title="Hybrid Mode"
          >
            ⚡
          </button>
          <div className="slider-group">
            <span className="slider-group__label">Point Size</span>
            <input
              type="range"
              min="0.5"
              max="8"
              step="0.5"
              value={pointSize}
              onChange={(e) => onPointSizeChange?.(parseFloat(e.target.value))}
            />
            <span className="slider-group__value">{pointSize}</span>
          </div>
          <button
            className="toolbar-btn"
            title="Camera Trajectory"
          >
            {showTrajectory ? 'Hide Path' : 'Show Path'}
          </button>
          <button
            className="toolbar-btn"
            title="Anomaly Markers"
          >
            {showAnomalies ? 'Hide Markers' : 'Show Markers'}
          </button>
          <button
            className="toolbar-btn toolbar-btn--destructive"
            title="Apply Scale"
          >
            📏
          </button>
        </div>
      </div>

      {/* ─── Main Area: Viewer (65-75% width) + Panels ──────────────────── */}
      <div className="reconstruction-main">
        {/* ─── 3D Viewer Pane - Primary ─── */}
        <div className="viewer-pane">
          <Viewer3D
            pointCloudData={pointCloudData}
            meshUrl={meshUrl}
            trajectory={trajectory}
            anomalies={anomalies}
            selectedAnomaly={selectedAnomaly}
            onSelectAnomaly={onSelectAnomaly}
            pointSize={pointSize}
            displayMode={displayMode}
            onDisplayModeChange={onDisplayModeChange}
            measureMode={measureMode}
            measurePoints={measurePoints}
            onMeasureClick={onMeasureClick}
            showTrajectory={showTrajectory}
            showAnomalies={showAnomalies}
          />
        </div>

        {/* ─── Right Panel: Findings & Metadata ─── */}
        <div className="findings-panel">
          {/* Anomaly Panel */}
          {anomalies.length > 0 || selectedAnomaly ? (
            <AnomalyPanel
              anomalies={anomalies}
              selectedIndex={selectedAnomaly}
              onSelect={onSelectAnomaly}
            />
          ) : (
            <div
              style={{
                padding: '20px',
                textAlign: 'center',
                color: 'var(--text-caption)',
                fontSize: 14,
              }}
            >
              <div style={{ fontSize: 28, opacity: 0.3, marginBottom: 8 }}>🔍</div>
              <div>Select an anomaly to inspect</div>
            </div>
          )}

          {/* Pipeline Status Overlay */}
          {jobId && (
            <div
              style={{
                marginTop: 20,
                padding: 12,
                background: 'var(--bg-elevated)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 8,
              }}
            >
              <div style={{ fontSize: 11, color: 'var(--text-caption)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
                Pipeline Stage Status
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {[
                  'frame_extraction', 'camera_calibration', 'feature_detection',
                  'pose_estimation', 'dense_reconstruction', 'meshing',
                  'georeferencing', 'dynamic_filtering', 'ai_agent',
                ].map((key) => {
                  const st = stageStatuses[key];
                  const status = st?.status || 'pending';
                  return (
                    <div
                      key={key}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 4,
                        padding: '3px 6px',
                        borderRadius: 4,
                        fontSize: 10,
                        color: status === 'running' ? '#42D9FF' : status === 'completed' ? '#6DD5FA' : status === 'failed' ? '#FF5D67' : 'var(--text-caption)',
                      }}
                    >
                      <span
                        style={{
                          width: 4, height: 4,
                          borderRadius: 50,
                          background: status === 'running' ? '#42D9FF' : status === 'completed' ? '#6DD5FA' : status === 'failed' ? '#FF5D67' : 'var(--border-subtle)',
                        }}
                      />
                      <span>{status === 'running' ? '▶' : status === 'completed' ? '✓' : status === 'failed' ? '✗' : '•'} {key.replace(/_/g, ' ')}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ─── Bottom Stats / Measure Bar ──────────────────────────────────── */}
      <div className="reconstruction-stats">
        <div className="stat-item">
          📐 Points: <span className="stat-item__value">{numPoints.toLocaleString()}</span>
        </div>
        <div className="stat-item">
          🖼️ Frames: <span className="stat-item__value">{numFrames}</span>
        </div>
        <div className="stat-item">
          🔍 Anomalies: <span className="stat-item__value">{anomalies.length}</span>
        </div>
        {reconstructionMode && (
          <div className="stat-item" style={{ marginLeft: 'auto' }}>
            🔧 Mode: <span className="stat-item__value">{reconstructionMode}</span>
          </div>
        )}
      </div>
    </div>
  );
}
