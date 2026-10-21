import { useState, useRef, useCallback, useEffect } from 'react';

const PIPELINE_STAGES = [
  { num: 1, name: 'Frame Extraction', key: 'frame_extraction' },
  { num: 2, name: 'Camera Calibration', key: 'camera_calibration' },
  { num: 3, name: 'Feature Detection', key: 'feature_detection' },
  { num: 4, name: 'Pose Estimation', key: 'pose_estimation' },
  { num: 5, name: 'Dense Reconstruction', key: 'dense_reconstruction' },
  { num: 6, name: 'Meshing', key: 'meshing' },
  { num: 7, name: 'Georeferencing', key: 'georeferencing' },
  { num: 8, name: 'Dynamic Filtering', key: 'dynamic_filtering' },
  { num: 9, name: 'AI Analysis', key: 'ai_agent' },
];

export default function Controls({
  onUpload,
  onStartPipeline,
  jobId,
  pipelineStatus,
  stageStatuses,
  uploadProgress,
  pointSize,
  onPointSizeChange,
  displayMode = 'mesh',
  onDisplayModeChange,
  showTrajectory,
  onToggleTrajectory,
  showAnomalies,
  onToggleAnomalies,
}) {
  const [videoFile, setVideoFile] = useState(null);
  const [metaFile, setMetaFile] = useState(null);
  const [activeTab, setActiveTab] = useState(jobId ? 'pipeline' : 'upload');
  const videoRef = useRef(null);
  const metaRef = useRef(null);

  useEffect(() => {
    if (jobId && (pipelineStatus === 'running' || pipelineStatus === 'completed' || pipelineStatus === 'partial')) {
      setActiveTab('pipeline');
    }
  }, [jobId, pipelineStatus]);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files);
    for (const f of files) {
      if (f.name.endsWith('.json')) setMetaFile(f);
      else if (/\.(mp4|avi|mov|mkv)$/i.test(f.name)) setVideoFile(f);
    }
  }, []);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
  }, []);

  const formatSize = (bytes) => {
    if (bytes > 1_000_000_000) return `${(bytes / 1_000_000_000).toFixed(1)} GB`;
    if (bytes > 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
    return `${(bytes / 1_000).toFixed(1)} KB`;
  };

  const getStageStatus = (key) => {
    if (!stageStatuses || !stageStatuses[key]) return 'pending';
    return stageStatuses[key].status || 'pending';
  };

  const getStageTime = (key) => {
    const st = stageStatuses?.[key];
    if (!st?.message) return '';
    const match = st.message.match(/([\d.]+)s/);
    return match ? `${match[1]}s` : '';
  };

  const canUpload = videoFile && !jobId;
  const canStart = jobId && pipelineStatus !== 'running';

  return (
    <div className="controls">
      {/* Tab switcher */}
      <div className="controls__tabs">
        <button
          className={`controls__tab ${activeTab === 'upload' ? 'controls__tab--active' : ''}`}
          onClick={() => setActiveTab('upload')}
        >
          Upload
        </button>
        <button
          className={`controls__tab ${activeTab === 'pipeline' ? 'controls__tab--active' : ''}`}
          onClick={() => setActiveTab('pipeline')}
        >
          Pipeline
        </button>
        <button
          className={`controls__tab ${activeTab === 'view' ? 'controls__tab--active' : ''}`}
          onClick={() => setActiveTab('view')}
        >
          View
        </button>
      </div>

      {/* Upload Tab */}
      {activeTab === 'upload' && (
        <div className="controls__upload">
          <div className="controls__section">
            <div className="controls__section-title">Input Files</div>
            <div
              className={`upload-zone ${videoFile ? 'upload-zone--active' : ''}`}
              onClick={() => videoRef.current?.click()}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
            >
              <div className="upload-zone__icon">📹</div>
              <div className="upload-zone__text">
                <strong>Drop drone video</strong> or click to browse
                <br />MP4, AVI, MOV • Up to 2GB
              </div>
              <input
                ref={videoRef}
                type="file"
                accept=".mp4,.avi,.mov,.mkv"
                style={{ display: 'none' }}
                onChange={(e) => setVideoFile(e.target.files[0])}
              />
            </div>

            {videoFile && (
              <div className="file-chip">
                <span className="file-chip__icon">🎬</span>
                <span className="file-chip__name">{videoFile.name}</span>
                <span className="file-chip__size">{formatSize(videoFile.size)}</span>
                <button className="file-chip__remove" onClick={() => setVideoFile(null)}>✕</button>
              </div>
            )}

            {metaFile && (
              <div className="file-chip">
                <span className="file-chip__icon">📄</span>
                <span className="file-chip__name">{metaFile.name}</span>
                <span className="file-chip__size">{formatSize(metaFile.size)}</span>
                <button className="file-chip__remove" onClick={() => setMetaFile(null)}>✕</button>
              </div>
            )}

            {videoFile && !metaFile && (
              <div style={{
                marginTop: 8, padding: '8px 10px',
                background: 'rgba(255,181,71,0.08)', border: '1px solid rgba(255,181,71,0.2)',
                borderRadius: 'var(--radius-sm)', fontSize: 11, color: 'var(--warning)',
              }}>
                👁️ No metadata — pipeline will run in <strong>vision-only mode</strong> (relative scale, no georeferencing)
              </div>
            )}

            {uploadProgress > 0 && uploadProgress < 100 && (
              <div style={{ marginBottom: 10 }}>
                <div style={{
                  height: 4, background: 'var(--border-default)', borderRadius: 2, overflow: 'hidden',
                }}>
                  <div style={{ width: `${uploadProgress}%`, height: '100%', background: 'var(--accent-primary)', borderRadius: 2, transition: 'width 0.3s ease' }} />
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4, fontFamily: 'var(--font-mono)' }}>
                  Uploading... {uploadProgress}%
                </div>
              </div>
            )}

            <div style={{ marginTop: 20 }}>
              <button
                className="btn btn--primary btn--full"
                disabled={!canUpload}
                onClick={() => onUpload?.(videoFile, metaFile)}
              >
                {uploadProgress > 0 && uploadProgress < 100 ? (
                  <><span className="spinner" /> Uploading...</>
                ) : (
                  <>⬆️ Upload Files</>
                )}
              </button>
            </div>

            {jobId && (
              <div style={{ marginTop: 20 }}>
                <button
                  className="btn btn--secondary btn--full"
                  style={{ marginTop: 8 }}
                  disabled={!canStart}
                  onClick={() => onStartPipeline?.()}
                >
                  {pipelineStatus === 'running' ? (
                    <><span className="spinner" /> Processing...</>
                  ) : (
                    <>▶ Start Pipeline</>
                  )}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Pipeline Tab */}
      {activeTab === 'pipeline' && (
        <div className="controls__pipeline">
          <div className="controls__section" style={{ flex: 1, overflow: 'auto' }}>
            <div className="controls__section-title">Pipeline Stages</div>
            <div className="pipeline-stages">
              {PIPELINE_STAGES.map((stage) => {
                const status = getStageStatus(stage.key);
                const time = getStageTime(stage.key);
                const isActive = status === 'running';

                return (
                  <div
                    key={stage.num}
                    className={`stage-item ${isActive ? 'stage-item--active' : ''}`}
                  >
                    <div className={`stage-item__indicator stage-item__indicator--${status}`} />
                    <span className="stage-item__name">
                      {stage.num}. {stage.name}
                    </span>
                    {time && <span className="stage-item__time">{time}</span>}
                    {status === 'running' && <span className="spinner" />}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* View Tab */}
      {activeTab === 'view' && (
        <div className="controls__view">
          <div className="controls__section">
            <div className="controls__section-title">3D Map View Layer</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 16 }}>
              <button
                className={`controls__layer-btn ${displayMode === 'mesh' ? 'controls__layer-btn--primary' : 'controls__layer-btn--secondary'}`}
                onClick={() => onDisplayModeChange?.('mesh')}
              >
                🏢 3D Map
              </button>
              <button
                className={`controls__layer-btn ${displayMode === 'cloud' ? 'controls__layer-btn--primary' : 'controls__layer-btn--secondary'}`}
                onClick={() => onDisplayModeChange?.('cloud')}
              >
                🌐 Point Cloud
              </button>
              <button
                className={`controls__layer-btn ${displayMode === 'wireframe' ? 'controls__layer-btn--primary' : 'controls__layer-btn--secondary'}`}
                onClick={() => onDisplayModeChange?.('wireframe')}
              >
                🔲 Wireframe
              </button>
              <button
                className={`controls__layer-btn ${displayMode === 'hybrid' ? 'controls__layer-btn--primary' : 'controls__layer-btn--secondary'}`}
                onClick={() => onDisplayModeChange?.('hybrid')}
              >
                ⚡ Hybrid
              </button>
            </div>

            <div className="controls__options">
              <div style={{ marginBottom: 12 }}>
                <label style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer',
                }}>
                  <input
                    type="checkbox"
                    checked={showTrajectory}
                    onChange={(e) => onToggleTrajectory?.(e.target.checked)}
                    style={{ accentColor: 'var(--accent-primary)' }}
                  />
                  Show Camera Path
                </label>

                <label style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer',
                }}>
                  <input
                    type="checkbox"
                    checked={showAnomalies}
                    onChange={(e) => onToggleAnomalies?.(e.target.checked)}
                    style={{ accentColor: 'var(--accent-primary)' }}
                  />
                  Show Anomaly Markers
                </label>
              </div>

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
            </div>
          </div>
        </div>
      )}
    </div>
  );
}