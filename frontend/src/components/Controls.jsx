import { useState, useRef, useCallback } from 'react';

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
  showTrajectory,
  onToggleTrajectory,
  showAnomalies,
  onToggleAnomalies,
}) {
  const [videoFile, setVideoFile] = useState(null);
  const [metaFile, setMetaFile] = useState(null);
  const [activeTab, setActiveTab] = useState('upload');
  const videoRef = useRef(null);
  const metaRef = useRef(null);

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
    <div className="sidebar">
      {/* Tab switcher */}
      <div className="sidebar__section" style={{ paddingBottom: 8 }}>
        <div className="tabs">
          <button
            className={`tab ${activeTab === 'upload' ? 'tab--active' : ''}`}
            onClick={() => setActiveTab('upload')}
          >
            Upload
          </button>
          <button
            className={`tab ${activeTab === 'pipeline' ? 'tab--active' : ''}`}
            onClick={() => setActiveTab('pipeline')}
          >
            Pipeline
          </button>
          <button
            className={`tab ${activeTab === 'view' ? 'tab--active' : ''}`}
            onClick={() => setActiveTab('view')}
          >
            View
          </button>
        </div>
      </div>

      {/* Upload Tab */}
      {activeTab === 'upload' && (
        <>
          <div className="sidebar__section">
            <div className="sidebar__section-title">Input Files</div>
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

            <div
              className={`upload-zone ${metaFile ? 'upload-zone--active' : ''}`}
              onClick={() => metaRef.current?.click()}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              style={{ marginTop: 10 }}
            >
              <div className="upload-zone__icon">📋</div>
              <div className="upload-zone__text">
                <strong>Drop metadata JSON</strong> <span style={{ opacity: 0.5, fontSize: 10, fontWeight: 600 }}>(optional)</span>
                <br />GPS track, camera intrinsics, IMU
              </div>
              <input
                ref={metaRef}
                type="file"
                accept=".json"
                style={{ display: 'none' }}
                onChange={(e) => setMetaFile(e.target.files[0])}
              />
            </div>

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
                background: 'var(--warning-bg)', border: '1px solid rgba(251,191,36,0.2)',
                borderRadius: 'var(--radius-sm)', fontSize: 11, color: 'var(--warning)',
                lineHeight: 1.5,
              }}>
                👁️ No metadata — pipeline will run in <strong>vision-only mode</strong> (relative scale, no georeferencing)
              </div>
            )}
          </div>

          <div className="sidebar__section">
            {uploadProgress > 0 && uploadProgress < 100 && (
              <div style={{ marginBottom: 10 }}>
                <div style={{
                  height: 4,
                  background: 'var(--border-default)',
                  borderRadius: 2,
                  overflow: 'hidden',
                }}>
                  <div style={{
                    width: `${uploadProgress}%`,
                    height: '100%',
                    background: 'var(--accent-gradient)',
                    borderRadius: 2,
                    transition: 'width 0.3s ease',
                  }} />
                </div>
                <div style={{
                  fontSize: 11,
                  color: 'var(--text-muted)',
                  marginTop: 4,
                  fontFamily: 'var(--font-mono)',
                }}>
                  Uploading... {uploadProgress}%
                </div>
              </div>
            )}

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

            {jobId && (
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
            )}
          </div>
        </>
      )}

      {/* Pipeline Tab */}
      {activeTab === 'pipeline' && (
        <div className="sidebar__section" style={{ flex: 1, overflow: 'auto' }}>
          <div className="sidebar__section-title">Pipeline Stages</div>
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
      )}

      {/* View Tab */}
      {activeTab === 'view' && (
        <div className="sidebar__section" style={{ flex: 1 }}>
          <div className="sidebar__section-title">Display Options</div>

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

          <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
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
        </div>
      )}
    </div>
  );
}
