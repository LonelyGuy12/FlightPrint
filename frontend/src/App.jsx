import { useState, useCallback, useEffect, useRef } from 'react';
import Viewer3D from './components/Viewer3D';
import Controls from './components/Controls';
import AnomalyPanel from './components/AnomalyPanel';
import MeasureTool from './components/MeasureTool';
import { parsePLY } from './utils/plyParser';
import {
  uploadFiles,
  startPipeline,
  getPipelineStatus,
  getSceneData,
  fetchFile,
  applyScale,
  API_BASE,
} from './utils/api';

export default function App() {
  // ─── State ──────────────────────────────────────────────────────────
  const [jobId, setJobId] = useState(null);
  const [pipelineStatus, setPipelineStatus] = useState('idle');
  const [stageStatuses, setStageStatuses] = useState({});
  const [uploadProgress, setUploadProgress] = useState(0);

  // 3D Data
  const [pointCloudData, setPointCloudData] = useState(null);
  const [meshUrl, setMeshUrl] = useState(null);
  const [trajectory, setTrajectory] = useState(null);
  const [anomalies, setAnomalies] = useState([]);
  const [selectedAnomaly, setSelectedAnomaly] = useState(null);

  // View options
  const [pointSize, setPointSize] = useState(2.0);
  const [showTrajectory, setShowTrajectory] = useState(true);
  const [showAnomalies, setShowAnomalies] = useState(true);

  // Measurement
  const [measureMode, setMeasureMode] = useState(false);
  const [measurePoints, setMeasurePoints] = useState([]);
  const [distance, setDistance] = useState(null);

  // Stats
  const [numPoints, setNumPoints] = useState(0);
  const [numFrames, setNumFrames] = useState(0);

  // Reconstruction mode
  const [reconstructionMode, setReconstructionMode] = useState(null);
  const [scaleStatus, setScaleStatus] = useState(null);
  const [modeLabel, setModeLabel] = useState(null);

  const pollRef = useRef(null);

  // ─── Upload ─────────────────────────────────────────────────────────
  const handleUpload = useCallback(async (videoFile, metaFile) => {
    try {
      setUploadProgress(1);
      const result = await uploadFiles(videoFile, metaFile, setUploadProgress);
      setJobId(result.job_id);
      setUploadProgress(100);
      setTimeout(() => setUploadProgress(0), 1500);
    } catch (err) {
      console.error('Upload failed:', err);
      setUploadProgress(0);
      alert(`Upload failed: ${err.response?.data?.detail || err.message}`);
    }
  }, []);

  // ─── Start Pipeline ─────────────────────────────────────────────────
  const handleStartPipeline = useCallback(async () => {
    if (!jobId) return;
    try {
      await startPipeline(jobId);
      setPipelineStatus('running');
      // Start polling
      startPolling();
    } catch (err) {
      console.error('Pipeline start failed:', err);
      alert(`Pipeline start failed: ${err.response?.data?.detail || err.message}`);
    }
  }, [jobId]);

  // ─── Poll Status ───────────────────────────────────────────────────
  const startPolling = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);

    pollRef.current = setInterval(async () => {
      try {
        const status = await getPipelineStatus(jobId);
        setPipelineStatus(status.pipeline_status || status.status);
        setStageStatuses(status.stages || {});

        // If completed or failed, stop polling and load results
        if (['completed', 'partial', 'failed'].includes(status.pipeline_status || status.status)) {
          clearInterval(pollRef.current);
          pollRef.current = null;

          if (status.pipeline_status !== 'failed') {
            loadResults();
          }
        }
      } catch {
        // Keep polling on transient errors
      }
    }, 2000);
  }, [jobId]);

  // ─── Load Results ──────────────────────────────────────────────────
  const loadResults = useCallback(async () => {
    if (!jobId) return;

    try {
      // Load scene data
      const scene = await getSceneData(jobId);

      // Load reconstruction mode
      if (scene.reconstruction_mode) {
        setReconstructionMode(scene.reconstruction_mode);
        setScaleStatus(scene.scale_status);
        setModeLabel(scene.mode_label);
      }

      // Load trajectory
      if (scene.trajectory) {
        setTrajectory(scene.trajectory);
      }

      // Load anomalies
      if (scene.anomalies?.length) {
        setAnomalies(scene.anomalies);
      }

      // Load point cloud — prefer filtered > dense > sparse
      const cloudFiles = ['filtered_cloud.ply', 'dense_cloud.ply', 'sparse_cloud.ply'];
      for (const cloudFile of cloudFiles) {
        if (scene.assets?.[cloudFile]) {
          try {
            const plyText = await fetchFile(jobId, cloudFile);
            const parsed = parsePLY(plyText);
            setPointCloudData(parsed);
            setNumPoints(parsed.vertexCount);
            break;
          } catch {
            continue;
          }
        }
      }

      // Load mesh URL if available (PLY for vertex colors)
      if (scene.assets?.['mesh.ply']) {
        const apiUrl = scene.assets['mesh.ply'].url;
        setMeshUrl(API_BASE + apiUrl);
      } else {
        setMeshUrl(null);
      }

      // Stats from report
      if (scene.report) {
        setNumFrames(scene.report.num_frames || 0);
        if (!numPoints && scene.report.sparse_points) {
          setNumPoints(scene.report.sparse_points);
        }
      }
    } catch (err) {
      console.error('Failed to load results:', err);
    }
  }, [jobId]);

  // ─── Measurement ──────────────────────────────────────────────────
  const handleMeasureClick = useCallback((point) => {
    if (!measureMode) return;

    setMeasurePoints((prev) => {
      if (prev.length >= 2) {
        // Start new measurement
        return [point];
      }

      const next = [...prev, point];

      if (next.length === 2) {
        const dx = next[1][0] - next[0][0];
        const dy = next[1][1] - next[0][1];
        const dz = next[1][2] - next[0][2];
        setDistance(Math.sqrt(dx * dx + dy * dy + dz * dz));
      } else {
        setDistance(null);
      }

      return next;
    });
  }, [measureMode]);

  const toggleMeasure = useCallback(() => {
    setMeasureMode((prev) => {
      if (prev) {
        setMeasurePoints([]);
        setDistance(null);
      }
      return !prev;
    });
  }, []);

  const handleApplyScale = useCallback(async (realMeters, measuredUnits) => {
    if (!jobId || measuredUnits === 0) return;
    const scaleFactor = realMeters / measuredUnits;
    try {
      await applyScale(jobId, scaleFactor);
      window.location.reload();
    } catch (e) {
      console.error("Failed to apply scale", e);
      alert("Failed to apply scale factor.");
    }
  }, [jobId]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // ─── Render ───────────────────────────────────────────────────────
  const isMetric = scaleStatus && scaleStatus !== 'relative_unscaled';
  const distanceUnit = isMetric ? 'm' : 'units';

  const statusLabel = pipelineStatus === 'idle' && !jobId ? 'idle'
    : pipelineStatus === 'running' ? 'running'
    : pipelineStatus === 'completed' ? 'completed'
    : pipelineStatus === 'partial' ? 'completed'
    : pipelineStatus === 'failed' ? 'failed'
    : jobId ? 'completed' : 'idle';

  const modeBannerClass = reconstructionMode === 'full' ? 'mode-banner--full'
    : reconstructionMode === 'scale_assisted' ? 'mode-banner--assisted'
    : reconstructionMode === 'vision_only' ? 'mode-banner--vision'
    : null;

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <div className="header__brand">
          <div className="header__logo">✈️</div>
          <div>
            <div className="header__title">FlightPrint</div>
            <div className="header__subtitle">3D Drone Reconstruction</div>
          </div>
        </div>
        <div className="header__status">
          {jobId && (
            <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              Job: {jobId}
            </span>
          )}
          <div className={`status-badge status-badge--${statusLabel}`}>
            <span className="status-badge__dot" />
            {statusLabel.charAt(0).toUpperCase() + statusLabel.slice(1)}
          </div>
        </div>
      </header>

      {/* Main */}
      <div className="main">
        {/* Left Sidebar — Controls */}
        <Controls
          onUpload={handleUpload}
          onStartPipeline={handleStartPipeline}
          jobId={jobId}
          pipelineStatus={pipelineStatus}
          stageStatuses={stageStatuses}
          uploadProgress={uploadProgress}
          pointSize={pointSize}
          onPointSizeChange={setPointSize}
          showTrajectory={showTrajectory}
          onToggleTrajectory={setShowTrajectory}
          showAnomalies={showAnomalies}
          onToggleAnomalies={setShowAnomalies}
        />

        {/* 3D Viewer */}
        <div className="viewer">
          {modeBannerClass && (
            <div className={`mode-banner ${modeBannerClass}`}>
              <span className="mode-banner__icon">
                {reconstructionMode === 'full' ? '🌍' : reconstructionMode === 'scale_assisted' ? '📐' : '👁️'}
              </span>
              <span className="mode-banner__text">{modeLabel}</span>
            </div>
          )}
          <Viewer3D
            pointCloudData={pointCloudData}
            meshUrl={meshUrl}
            trajectory={trajectory}
            anomalies={anomalies}
            selectedAnomaly={selectedAnomaly}
            onSelectAnomaly={setSelectedAnomaly}
            pointSize={pointSize}
            measureMode={measureMode}
            measurePoints={measurePoints}
            onMeasureClick={handleMeasureClick}
            showTrajectory={showTrajectory}
            showAnomalies={showAnomalies}
          />
          <MeasureTool
            measureMode={measureMode}
            onToggle={toggleMeasure}
            measurePoints={measurePoints}
            distance={distance}
            isMetric={isMetric}
            onApplyScale={handleApplyScale}
          />
        </div>

        {/* Right Sidebar — Anomalies */}
        {anomalies.length > 0 && (
          <div className="sidebar" style={{ width: 280, borderRight: 'none', borderLeft: '1px solid var(--border-subtle)' }}>
            <AnomalyPanel
              anomalies={anomalies}
              selectedIndex={selectedAnomaly}
              onSelect={setSelectedAnomaly}
            />
          </div>
        )}
      </div>

      {/* Stats Bar */}
      <div className="stats-bar">
        <div className="stat-item">
          📐 Points: <span className="stat-item__value">{numPoints.toLocaleString()}</span>
        </div>
        <div className="stat-item">
          🖼️ Frames: <span className="stat-item__value">{numFrames}</span>
        </div>
        <div className="stat-item">
          🔍 Anomalies: <span className="stat-item__value">{anomalies.length}</span>
        </div>
        {distance !== null && (
          <div className="stat-item">
            📏 Distance: <span className="stat-item__value">
              {distance.toFixed(2)}{distanceUnit}
              {!isMetric && ' (relative)'}
            </span>
          </div>
        )}
        {reconstructionMode && (
          <div className="stat-item" style={{ marginLeft: 'auto' }}>
            🔧 Mode: <span className="stat-item__value">{reconstructionMode}</span>
          </div>
        )}
      </div>
    </div>
  );
}
