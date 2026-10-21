import { useState, useCallback, useEffect } from 'react';

/* ─── Mission Overview Screen ────────────────────────────────────────────
     Answers four questions:
     - What flight/reconstruction is being inspected?
     - What is the current processing state?
     - What has the pipeline produced?
     - Are there anomalies requiring attention?
  -------------------------------------------------------------------------- */

export default function OverviewScreen({
  jobId,
  pipelineStatus,
  stageStatuses,
  numPoints,
  numFrames,
  anomalies,
  selectedAnomaly,
  onSelectAnomaly,
  onStartPipeline,
  onUpload,
  onReset,
}) {
  // List recent jobs from the backend
  const [recentJobs, setRecentJobs] = useState([]);
  useEffect(() => {
    fetch('/api/upload/jobs')
      .then((res) => res.json())
      .then((data) => setRecentJobs(data.jobs || []))
      .catch(() => []);
  }, [jobId]);

  // Pipeline completion state
  const pipelineCompleted =
    pipelineStatus === 'completed' || pipelineStatus === 'partial';
  const pipelineFailed = pipelineStatus === 'failed';

  // Anomaly summary
  const anomalyCount = anomalies?.length || 0;
  const hasCriticalAnomalies = anomalies?.some((a) => a.severity === 'high') || false;

  return (
    <div className="overview-screen">
      {/* ─── Header / Hero Section ───────────────────────────────────────── */}
      <div className="overview-hero">
        <div className="hero-left">
          <h1 style={{ fontSize: 32, fontWeight: 700, marginBottom: 8 }}>
            Mission Overview
          </h1>
          <p style={{
            fontSize: 16, color: 'var(--text-caption)', marginBottom: 24,
            lineHeight: 1.6,
          }}>
            Select a job above or upload new drone footage to begin inspection.
          </p>
        </div>

        <div className="hero-right">
          {/* Pipeline status pill */}
          {jobId && (
            <div style={{
              marginTop: 24, padding: 16, background: var(--bg-elevated),
              border: '1px solid var(--border-subtle)', borderRadius: 12,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                <span className={`status-badge status-badge--${pipelineStatus}`}>
                  <span className="status-badge__dot" />{pipelineStatus.charAt(0).toUpperCase() + pipelineStatus.slice(1)}
                </span>
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-caption)' }}>
                Pipeline Status
              </div>
            </div>
          )}

          {/* Upload CTA when no job */}
          {!jobId && (
            <div style={{ marginTop: 24, padding: 24, border: '2px dashed var(--border-subtle)', borderRadius: 12, textAlign: 'center' }}>
              <div style={{ fontSize: 48, opacity: 0.3, marginBottom: 12 }}>📹</div>
              <h3 style={{ fontSize: 18, fontWeight: 600, marginBottom: 8 }}>Start a New Inspection</h3>
              <p style={{ color: 'var(--text-caption)', marginBottom: 16 }}>
                Upload drone video and optional GPS/IMU metadata to generate a 3D reconstruction.
              </p>
              <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
                <button
                  className="btn btn--primary btn--sm"
                  onClick={() => setTimeout(() => document.querySelector('input[type="file"]')?.click(), 0)}
                  style={{ display: 'none' }}
                  ref={null}
                >
                  ⬆️ Upload Files
                </button>
                <input
                  type="file"
                  accept=".mp4,.avi,.mov,.mkv,.json"
                  onChange={(e) => {
                    const files = e.target.files;
                    if (files.length > 0) {
                      // Simple handling - first video, then metadata
                      const videoFile = files[0];
                      // In a real implementation, we'd manage file state more carefully
                      // For now, just trigger upload with both files if available
                      if (videoFile.name.endsWith('.mp4') || videoFile.name.endsWith('.avi') || videoFile.name.endsWith('.mov') || videoFile.name.endsWith('.mkv')) {
                        // Would need to handle meta file selection too
                        alert(`Selected: ${videoFile.name}`);
                      }
                    }
                  }}
                  style={{ padding: '10px 20px', fontSize: 13 }}
                />
                <input
                  type="file"
                  accept=".json"
                  style={{ display: 'none' }}
                  ref={null}
                />
              </div>
            </div>
          )}

          {/* When job exists - show actions */}
          {jobId && (
            <div style={{ marginTop: 24, padding: 20, background: var(--bg-elevated), borderRadius: 12, border: '1px solid var(--border-subtle)' }}>
              <div style={{ display: 'flex', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
                {pipelineStatus !== 'running' && (
                  <button
                    className="btn btn--secondary btn--sm"
                    onClick={onStartPipeline}
                    style={{ flex: 1 }}
                  >
                    ▶ Start Pipeline
                  </button>
                )}
                <button
                  className="btn btn--secondary btn--sm"
                  onClick={onReset}
                  style={{ flex: 1 }}
                  title="Clear and start fresh"
                >
                  🔄 New Upload
                </button>
              </div>
              {pipelineStatus === 'running' && (
                <p style={{ fontSize: 12, color: 'var(--text-caption)', marginBottom: 0 }}>
                  Processing in background…
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ─── Recent Projects & Pipeline Summary ──────────────────────────── */}
      <div className="overview-content" style={{ marginTop: 32 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 24 }}>
          {/* Left: Recent Jobs */}
          <div>
            <div style={{ fontSize: 12, color: 'var(--text-caption)', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 12 }}>
              Recent Reconstructions
            </div>
            {recentJobs.length === 0 && pipelineStatus !== 'running' && (
              <div className="empty-state" style={{ padding: 32, textAlign: 'center' }}>
                <div style={{ fontSize: 48, opacity: 0.3, marginBottom: 12 }}>📁</div>
                <div style={{ fontSize: 15, fontWeight: 500 }}>No previous reconstructions</div>
                <p style={{ color: 'var(--text-caption)', marginTop: 8 }}>
                  Upload drone footage to create your first mission.
                </p>
              </div>
            )}
            {recentJobs.length > 0 && (
              <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                {recentJobs.slice(0, 5).map((job) => {
                  const status = job.status || 'unknown';
                  const created = job.created_at ? new Date(job.created_at * 1000).toLocaleDateString() : '—';
                  return (
                    <li
                      key={job.job_id}
                      style={{
                        padding: '8px 12px',
                        background: var(--bg-tertiary),
                        borderRadius: 8,
                        marginBottom: 6,
                        cursor: 'pointer',
                        transition: 'background var(--transition-fast)',
                        fontSize: 13,
                      }}
                      onMouseOver={(e) => e.currentTarget.style.background = 'var(--bg-surface)'}
                      onMouseOut={(e) => e.currentTarget.style.background = 'var(--bg-tertiary)'}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ color: 'var(--text-primary)' }}>{job.job_id}</span>
                        <span style={{ fontSize: 10, color: 'var(--text-caption)' }}>{created}</span>
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--text-caption)' }}>
                        {status}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {/* Right: Pipeline Stage Summary */}
          <div>
            <div style={{ fontSize: 12, color: 'var(--text-caption)', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 12 }}>
              Pipeline Stages
            </div>
            <div className="pipeline-stages" style={{
              display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 12,
            }}>
              {[
                { key: 'frame_extraction', name: 'Frame Extraction' },
                { key: 'camera_calibration', name: 'Camera Calibration' },
                { key: 'feature_detection', name: 'Feature Detection' },
                { key: 'pose_estimation', name: 'Pose Estimation' },
                { key: 'dense_reconstruction', name: 'Dense Reconstruction' },
                { key: 'meshing', name: 'Meshing' },
                { key: 'georeferencing', name: 'Georeferencing' },
                { key: 'dynamic_filtering', name: 'Filtering' },
                { key: 'ai_agent', name: 'AI Analysis' },
              ].map((stage) => {
                const st = stageStatuses[stage.key];
                const status = st?.status || 'pending';
                return (
                  <div
                    key={stage.key}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 6,
                      padding: '6px 10px',
                      borderRadius: 6,
                      background: status === 'running'
                        ? 'rgba(66, 217, 255, 0.18)'
                        : status === 'completed'
                          ? 'rgba(109, 213, 250, 0.12)'
                          : status === 'failed'
                            ? 'rgba(255, 93, 103, 0.12)'
                            : 'var(--border-subtle)',
                      },
                    }}
                  >
                    <span
                      style={{
                        width: 6, height: 6,
                        borderRadius: 50,
                        background: status === 'running'
                          ? '#42D9FF'
                          : status === 'completed'
                            ? '#6DD5FA'
                            : status === 'failed'
                              ? '#FF5D67'
                              : 'var(--border-subtle)',
                    />}
                    <span style={{ fontSize: 10, color: 'var(--text-caption)' }}>{stage.name}</span>
                  </div>
                );
              })}
            </div>

            {/* Completion state */}
            {pipelineCompleted && (
              <div style={{
                padding: 12, background: 'rgba(75, 200, 255, 0.1)', borderRadius: 8, marginTop: 12,
              }}>
                <div style={{ fontSize: 11, color: '#628BFF', marginBottom: 4 }}>✓ Pipeline Completed</div>
                <div style={{ fontSize: 11, color: 'var(--text-caption)' }}>
                  Reconstruction ready for anomaly inspection
                </div>
              </div>
            )}
            {pipelineFailed && (
              <div style={{
                padding: 12, background: 'rgba(255, 93, 103, 0.1)', borderRadius: 8, marginTop: 12,
              }}>
                <div style={{ fontSize: 11, color: var(--critical), marginBottom: 4 }}>✗ Pipeline Failed</div>
                <div style={{ fontSize: 11, color: 'var(--text-caption)' }}>
                  Review errors and retry or start a new upload
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ─── Anomaly Summary & Quick Actions ────────────────────────────── */}
        {anomalies.length > 0 || jobId && pipelineCompleted && (
          <div style={{ marginTop: 24, padding: 20, background: var(--bg-elevated), borderRadius: 12, border: '1px solid var(--border-subtle)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-caption)', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Anomaly Summary
                </div>
                <div style={{ fontSize: 14, fontWeight: 600, color: anomalyCount > 0 ? var(--accent-primary) : var(--text-caption) }}>
                  {anomalyCount} {anomalyCount === 1 ? 'finding' : 'findings'}
                </div>
              </div>
              {anomalyCount > 0 && (
                <button
                  className="btn btn--sm btn--secondary"
                  onClick={() => setSelectedAnomaly(0)}
                  style={{ padding: '4px 8px', fontSize: 11 }}
                  title="Go to first anomaly"
                >
                  View
                </button>
              )}
            </div>

            {anomalies.length > 0 && (
              <ul style={{ listStyle: 'none', padding: 0, margin: 0, maxHeight: '200px', overflowY: 'auto' }}>
                {anomalies.slice(0, 5).map((a, i) => {
                  const severity = a.severity || 'low';
                  const severityColor = { low: '#6DD5FA', medium: '#FFB547', high: '#FF5D67' }[severity] || '#6DD5FA';
                  return (
                    <li
                      key={i}
                      style={{
                        padding: '6px 10px',
                        marginBottom: 4,
                        background: selectedAnomaly === i ? 'rgba(66, 217, 255, 0.18)' : var(--bg-tertiary),
                        borderRadius: 6,
                        cursor: 'pointer',
                        transition: 'background var(--transition-fast)',
                        fontSize: 12,
                      }}
                      onMouseOver={(e) => e.currentTarget.style.background = 'rgba(66, 217, 255, 0.08)'}
                      onMouseOut={(e) => e.currentTarget.style.background = selectedAnomaly === i ? 'rgba(66, 217, 255, 0.18)' : var(--bg-tertiary)}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <div
                          style={{
                            width: 6, height: 6, borderRadius: 50,
                          background: severityColor }
                        />
                        <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{a.title || a.id || `Anomaly ${i + 1}`}</span>
                        <span style={{ fontSize: 10, color: 'var(--text-caption)' }}>{severity} severity</span>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}

            {anomalies.length === 0 && pipelineCompleted && (
              <p style={{ fontSize: 12, color: 'var(--text-caption)', marginTop: 8 }}>
                No anomalies detected. Run the AI analysis stage to identify regions of interest.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}