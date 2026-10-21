import { useState, useCallback, useEffect, useRef } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader';
import { computeBounds } from './utils/plyParser';
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
  const [pointSize, setPointSize] = useState(2.5);
  const [displayMode, setDisplayMode] = useState('mesh'); // 'mesh' | 'cloud' | 'wireframe' | 'hybrid'
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

  // UI state
  const [activeView, setActiveView] = useState('overview'); // 'overview' | 'reconstruction' | 'anomaly' | 'reports'
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

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

      // Load mesh URL if available (PLY for vertex colors) — set this immediately!
      if (scene.assets?.['mesh.ply']) {
        const apiUrl = scene.assets['mesh.ply'].url;
        setMeshUrl(API_BASE + apiUrl);
        setDisplayMode('mesh');
      } else {
        setMeshUrl(null);
        setDisplayMode('cloud');
      }

      // Stats from report
      if (scene.report) {
        setNumFrames(scene.report.num_frames || 0);
        if (scene.report.dense_points) {
          setNumPoints(scene.report.dense_points);
        } else if (scene.report.sparse_points) {
          setNumPoints(scene.report.sparse_points);
        }
      }

      // Load point cloud asynchronously — prioritize clean/sparse clouds for instant interactive rendering
      const targetCloudFile = scene.assets?.['sparse_cloud.ply']
        ? 'sparse_cloud.ply'
        : scene.assets?.['filtered_cloud.ply']
        ? 'filtered_cloud.ply'
        : scene.assets?.['dense_cloud.ply']
        ? 'dense_cloud.ply'
        : null;

      if (targetCloudFile) {
        fetchFile(jobId, targetCloudFile)
          .then((plyText) => {
            const parsed = parsePLY(plyText);
            if (parsed && parsed.vertexCount > 0) {
              setPointCloudData(parsed);
              setNumPoints(parsed.vertexCount);
            }
          })
          .catch((err) => {
            console.warn('Point cloud load failed, mesh will be shown:', err);
          });
      }
    } catch (err) {
      console.error('Failed to load results:', err);
    }
  }, [jobId]);

  // ─── Initialize Active Job on Mount ───────────────────────────────
  useEffect(() => {
    // Only load if explicitly requested via ?jobId= in URL
    const urlParams = new URLSearchParams(window.location.search);
    const urlJobId = urlParams.get('jobId') || urlParams.get('job_id') || urlParams.get('project');
    if (urlJobId) {
      setJobId(urlJobId);
    } else {
      // Clear any stored job on fresh visit
      localStorage.removeItem('flightprint_active_job');
    }
  }, []);

  // When jobId is set and pipeline is not running, load results!
  useEffect(() => {
    if (jobId && pipelineStatus !== 'running') {
      loadResults();
    }
  }, [jobId, pipelineStatus, loadResults]);

  // ─── Reset to New Upload ──────────────────────────────────────────
  const handleReset = useCallback(() => {
    setJobId(null);
    setPipelineStatus('idle');
    setStageStatuses({});
    setPointCloudData(null);
    setMeshUrl(null);
    setTrajectory(null);
    setAnomalies([]);
    setSelectedAnomaly(null);
    setNumPoints(0);
    setNumFrames(0);
    setReconstructionMode(null);
    setScaleStatus(null);
    setModeLabel(null);
    setActiveView('overview');
    localStorage.removeItem('flightprint_active_job');
    window.history.replaceState({}, '', window.location.pathname);
  }, []);

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

  // Top bar right-side status
  const rightStatus = jobId ? (
    <div className="header__right">
      <div className="status-bar">
        <span style={{ fontSize: 11, color: 'var(--text-caption)', fontFamily: 'var(--font-mono)' }}>
          Job: {jobId}
        </span>
        <StatusBadge status={pipelineStatus} />
        <button
          className="btn btn--sm btn--secondary"
          onClick={handleReset}
          title="Clear current model and start a new upload"
        >
          🔄 New Upload
        </button>
      </div>
    </div>
  ) : (
    <div className="header__right">
      <button
        className="btn btn--sm btn--primary"
        onClick={() => setActiveView('overview')}
        style={{ padding: '6px 12px', fontSize: 12 }}
        title="Mission Overview"
      >
        Overview
      </button>
    </div>
  );

  return (
    <div className="app">
      {/* ─── Top Status Bar ───────────────────────────────────────────── */}
      <header className="header">
        {/* Left: Brand & Navigation */}
        <div className="header__left">
          <div className="header__brand">
            <div className="header__logo">FP</div>
            <div>
              <div className="header__title">FlightPrint</div>
              <div className="header__subtitle">3D Drone Reconstruction</div>
            </div>
          </div>
          <div className="header__nav">
            <div className="header__nav-item">Navigation</div>
          </div>
        </div>

        {/* Center: Mode Banner */}
        {modeBannerClass && (
          <div className={`mode-banner ${modeBannerClass}`}>
            <span className="mode-banner__icon">
              {reconstructionMode === 'full' ? '🌍' : reconstructionMode === 'scale_assisted' ? '📐' : '👁️'}
            </span>
            <span className="mode-banner__text">{modeLabel}</span>
          </div>
        )}

        {/* Right: Status & Controls */}
        {rightStatus}
      </header>

      {/* ─── Main Content Area ────────────────────────────────────────── */}
      <main className="main">
        <div className="content">

          {/* ─── Left Navigation Rail ───────────────────────────────────── */}
          <aside className="sidebar">
            <div className="sidebar__brand">FP</div>

            <nav className="sidebar__nav">
              <button
                className={`sidebar__nav-btn ${activeView === 'overview' ? 'sidebar__nav-btn--active' : ''}`}
                onClick={() => setActiveView('overview')}
                title="Mission Overview"
              >
                <span className="sidebar__nav-title">📊</span>
              </button>

              <button
                className={`sidebar__nav-btn ${activeView === 'reconstruction' ? 'sidebar__nav-btn--active' : ''}`}
                onClick={() => setActiveView('reconstruction')}
                title="Reconstruction Workspace"
              >
                <span className="sidebar__nav-title">🛰️</span>
              </button>

              <button
                className={`sidebar__nav-btn ${activeView === 'anomaly' ? 'sidebar__nav-btn--active' : ''}`}
                onClick={() => setActiveView('anomaly')}
                title="Anomaly Investigation"
              >
                <span className="sidebar__nav-title">🔍</span>
              </button>

              <button
                className={`sidebar__nav-btn ${activeView === 'reports' ? 'sidebar__nav-btn--active' : ''}`}
                onClick={() => setActiveView('reports')}
                title="Evidence & Reports"
              >
                <span className="sidebar__nav-title">📄</span>
              </button>
            </nav>
          </aside>

          {/* ─── Content Area ───────────────────────────────────────────── */}
          <div className="viewport-wrapper">
            {/* ─── Pipeline Stage Monitor (showing when job exists) ─────────── */}
            {jobId && (
              <div className="pipeline-overview">
                {Object.keys(stageStatuses).length > 0 && (
                  <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
                    {[
                      'frame_extraction', 'camera_calibration', 'feature_detection',
                      'pose_estimation', 'dense_reconstruction', 'meshing',
                      'georeferencing', 'dynamic_filtering', 'ai_agent'
                    ].map((key, i) => {
                      const st = stageStatuses[key];
                      const status = st?.status || 'pending';
                      const stageNames = {
                        'frame_extraction': '1. Frames',
                        'camera_calibration': '2. Calib',
                        'feature_detection': '3. Features',
                        'pose_estimation': '4. Poses',
                        'dense_reconstruction': '5. Dense',
                        'meshing': '6. Mesh',
                        'georeferencing': '7. Geo',
                        'dynamic_filtering': '8. Filter',
                        'ai_agent': '9. AI',
                      };
                      return (
                        <div
                          key={key}
                          className={`pipeline-stage ${status === 'running' ? 'pipeline-stage--running' : status === 'completed' ? 'pipeline-stage--completed' : status === 'failed' ? 'pipeline-stage--failed' : 'pipeline-stage--pending'}`}
                        >
                          {stageNames[key]}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {/* ─── Screen Content Based on Active View ─────────────────────── */}
            {activeView === 'overview' && (
              <OverviewScreen
                jobId={jobId}
                pipelineStatus={pipelineStatus}
                stageStatuses={stageStatuses}
                numPoints={numPoints}
                numFrames={numFrames}
                anomalies={anomalies}
                selectedAnomaly={selectedAnomaly}
                onSelectAnomaly={setSelectedAnomaly}
                onStartPipeline={handleStartPipeline}
                onUpload={handleUpload}
                onReset={handleReset}
              />
            )}

            {activeView === 'reconstruction' && (
              <ReconstructionScreen
                jobId={jobId}
                pipelineStatus={pipelineStatus}
                stageStatuses={stageStatuses}
                pointCloudData={pointCloudData}
                meshUrl={meshUrl}
                trajectory={trajectory}
                anomalies={anomalies}
                selectedAnomaly={selectedAnomaly}
                onSelectAnomaly={setSelectedAnomaly}
                onStartPipeline={handleStartPipeline}
                onDisplayModeChange={setDisplayMode}
                onPointSizeChange={setPointSize}
                onToggleTrajectory={setShowTrajectory}
                onToggleAnomalies={setShowAnomalies}
                onMeasureClick={handleMeasureClick}
                toggleMeasure={toggleMeasure}
                applyScale={handleApplyScale}
                numPoints={numPoints}
                numFrames={numFrames}
                reconstructionMode={reconstructionMode}
                displayMode={displayMode}
                showTrajectory={showTrajectory}
                showAnomalies={showAnomalies}
              />
            )}

            {activeView === 'anomaly' && (
              <AnomalyInvestigationScreen
                jobId={jobId}
                pipelineStatus={pipelineStatus}
                stageStatuses={stageStatuses}
                anomalies={anomalies}
                selectedAnomaly={selectedAnomaly}
                onSelectAnomaly={setSelectedAnomaly}
                onStartPipeline={handleStartPipeline}
                onDisplayModeChange={setDisplayMode}
                onPointSizeChange={setPointSize}
              />
            )}

            {activeView === 'reports' && (
              <EvidenceReportsScreen
                jobId={jobId}
                pipelineStatus={pipelineStatus}
                stageStatuses={stageStatuses}
                anomalies={anomalies}
                selectedAnomaly={selectedAnomaly}
                onSelectAnomaly={setSelectedAnomaly}
                onStartPipeline={handleStartPipeline}
                reconstructionMode={reconstructionMode}
                scaleStatus={scaleStatus}
                modeLabel={modeLabel}
              />
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

/* ─── Status Badge Component ──────────────────────────────────────────── */
function StatusBadge({ status }) {
  return (
    <span className={`status-badge status-badge--${status}`}>
      <span className="status-badge__dot" />
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}