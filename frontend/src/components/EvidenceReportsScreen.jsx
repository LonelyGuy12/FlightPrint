import { useState, useCallback, useEffect, useRef } from 'react';
import { downloadLink } from '../utils/reportUtils';
import { getSceneData } from '../utils/api';

/* ─── Evidence & Reports Screen ───────────────────────────────────────────
     Professional inspection-report experience using actual anomaly report and
     reconstruction metadata produced by the backend.
  -------------------------------------------------------------------------- */

export default function EvidenceReportsScreen({
  jobId,
  pipelineStatus,
  stageStatuses,
  anomalies,
  selectedAnomaly,
  onSelectAnomaly,
  onStartPipeline,
  reconstructionMode,
  scaleStatus,
  modeLabel,
}) {
  const [report, setReport] = useState(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [reportError, setReportError] = useState('');
  const [downloadError, setDownloadError] = useState('');
  const downloadInProgress = useRef(false);

  // Load report data from backend
  useEffect(() => {
    let cancelled = false;
    setReport(null);
    setReportError('');
    setDownloadError('');
    setReportLoading(false);
    if (!jobId) return;
    const loadReport = async () => {
      setReportLoading(true);
      try {
        const scene = await getSceneData(jobId);
        if (!cancelled && scene.report) {
          setReport({ ...scene.report, assets: scene.assets || {} });
        }
      } catch (err) {
        if (!cancelled) setReportError('Unable to load this job’s report. Check the backend connection.');
      } finally {
        if (!cancelled) setReportLoading(false);
      }
    };
    loadReport();
    return () => { cancelled = true; };
  }, [jobId, pipelineStatus]);

  // Generate download link for report
  const generateDownload = useCallback(async () => {
    if (!report || !jobId || downloadInProgress.current) return;
    downloadInProgress.current = true;
    setExporting(true);
    setDownloadError('');
    try {
      const url = await downloadLink(jobId);
      const a = document.createElement('a');
      a.href = url;
      a.download = `flightprint-report-${jobId}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      // Let the browser start consuming the blob before releasing it.
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      setDownloadError(err.message || 'Unable to download this job’s report.');
    } finally {
      downloadInProgress.current = false;
      setExporting(false);
    }
  }, [jobId, report]);

  // No report available
  if (!report && pipelineStatus !== 'running') {
    return (
      <div className="evidence-reports-screen">
        <div style={{
          padding: '60px 40px', textAlign: 'center',
        }}>
          <div style={{ fontSize: 48, opacity: 0.3, marginBottom: 16 }}>📄</div>
          <h2 style={{ fontSize: 20, fontWeight: 600, marginBottom: 8 }}>
            {reportLoading ? 'Loading Report' : reportError ? 'Report Unavailable' : 'No Report Available'}
          </h2>
          <p style={{ marginBottom: 24, fontSize: 14 }}>
            {reportLoading ? 'Loading this job’s report…' : reportError || 'Run the pipeline to generate an inspection report.'}
          </p>
          <button
            className="btn btn--primary"
            onClick={onStartPipeline}
            disabled={!jobId || reportLoading || !!reportError}
            style={{ marginBottom: 12 }}
          >
            ▶ Start Pipeline
          </button>
          <p style={{ fontSize: 12, color: 'var(--text-caption)' }}>
            Or upload new drone footage to begin.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="evidence-reports-screen">
      {/* ─── Header ──────────────────────────────────────────────────────── */}
      <div className="reports-header">
        <div className="header-content">
          <h1 style={{ fontSize: 22, fontWeight: 600, marginBottom: 4 }}>
            Inspection Report
          </h1>
          <p style={{ fontSize: 13, color: 'var(--text-caption)', marginBottom: 0 }}>
            Flight {jobId || ''} — {reconstructionMode || 'Vision-Only Mode'}
          </p>
        </div>

        <div className="header-actions">
          <div style={{ marginBottom: 8, fontSize: 11, color: 'var(--text-caption)' }}>
            Pipeline Status: {pipelineStatus === 'completed' ? '✓ Completed' : pipelineStatus === 'failed' ? '✗ Failed' : '◱ Processing'}
          </div>
          <button
            className="btn btn--sm btn--secondary"
            onClick={generateDownload}
            disabled={!report || reportLoading || exporting}
            title="Download Report"
            style={{ padding: '6px 12px', fontSize: 11 }}
          >
            ↓ Download
          </button>
          {exporting && (
            <span style={{ fontSize: 11, color: 'var(--accent-primary)' }}>Generating…</span>
          )}
          {downloadError && <p role="alert">{downloadError}</p>}
        </div>
      </div>

      {/* ─── Report Content ─────────────────────────────────────────────── */}
      <div className="reports-content">
        {reportLoading && (
          <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-caption)' }}>
            <div style={{ fontSize: 24, marginBottom: 16 }}>⏳</div>
            <div>Generating inspection report…</div>
            <div style={{ fontSize: 12, marginTop: 12 }}>This may take a moment while we compile the pipeline data.</div>
          </div>
        )}

        {/* Mission & Reconstruction Metadata ───────────────────────────── */}
        {report && report.video && (
          <div className="report-metadata" style={{
            padding: 20, background: 'var(--bg-elevated)', borderRadius: 12, marginBottom: 24, border: '1px solid var(--border-subtle)'
          }}>
            <div style={{ fontSize: 11, color: 'var(--text-caption)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 12 }}>
              Mission & Reconstruction Metadata
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-caption)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>Job ID</div>
                <div style={{ fontSize: 13, color: 'var(--text-primary)' }}>{jobId}</div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-caption)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>Reconstruction Mode</div>
                <div style={{ fontSize: 13, color: 'var(--accent-primary)' }}>{reconstructionMode || '—'}</div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-caption)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>Scale Status</div>
                <div style={{ fontSize: 13, color: scaleStatus === 'metric_georeferenced' ? '#6DD5FA' : scaleStatus === 'metric_approximate' ? '#FFB547' : 'var(--text-caption)' }}>{scaleStatus || '—'}</div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-caption)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>Frames Processed</div>
                <div style={{ fontSize: 13, color: 'var(--text-primary)' }}>{report.num_frames || 0}</div>
              </div>
            </div>
          </div>
        )}

        {/* 3D Reconstruction Preview ─────────────────────────────────────── */}
        {report && report.assets && Object.keys(report.assets).length > 0 && (
          <div className="report-preview" style={{
            padding: 20, background: 'var(--bg-elevated)', borderRadius: 12, marginBottom: 24, border: '1px solid var(--border-subtle)'
          }}>
            <div style={{ fontSize: 11, color: 'var(--text-caption)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 12 }}>
              3D Reconstruction Preview
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 12 }}>
              {report.assets['sparse_cloud.ply'] && (
                <div>
                  <div style={{ fontSize: 10, color: 'var(--text-caption)', marginBottom: 4 }}>Sparse Cloud</div>
                  <div style={{ fontSize: 12, color: 'var(--text-primary)' }}>Available</div>
                </div>
              )}
              {report.assets['mesh.ply'] && (
                <div>
                  <div style={{ fontSize: 10, color: 'var(--text-caption)', marginBottom: 4 }}>Mesh</div>
                  <div style={{ fontSize: 12, color: 'var(--text-primary)' }}>Available</div>
                </div>
              )}
              {report.assets['dense_cloud.ply'] && (
                <div>
                  <div style={{ fontSize: 10, color: 'var(--text-caption)', marginBottom: 4 }}>Dense Cloud</div>
                  <div style={{ fontSize: 12, color: 'var(--text-primary)' }}>Available</div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Finding Categories & Severity Distribution ─────────────────────── */}
        {anomalies && anomalies.length > 0 && (
          <div className="report-findings" style={{
            padding: 20, background: 'var(--bg-elevated)', borderRadius: 12, marginBottom: 24, border: '1px solid var(--border-subtle)'
          }}>
            <div style={{ fontSize: 11, color: 'var(--text-caption)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 12 }}>
              Finding Categories & Severity
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
              {['low', 'medium', 'high'].map((severity) => {
                const count = anomalies.filter(a => a.severity === severity).length;
                const color = { low: '#6DD5FA', medium: '#FFB547', high: '#FF5D67' }[severity] || '#6DD5FA';
                return (
                  <span key={severity} style={{
                    display: 'flex', alignItems: 'center', gap: 4,
                    padding: '6px 12px',
                    borderRadius: 6,
                    background: 'rgba(' + (color === '#6DD5FA' ? 109 : color === '#FFB547' ? 255 : 255) + ', ' + (color === '#6DD5FA' ? 213 : color === '#FFB547' ? 181 : 103) + ', ' + (color === '#6DD5FA' ? 255 : color === '#FFB547' ? 71 : 67) + ', 0.1)',
                    color: color,
                    fontSize: 11,
                  }}>
                    <span style={{ width: 6, height: 6, borderRadius: 50, background: color }} />
                    {count} {count === 1 ? severity : severity.charAt(0).toUpperCase() + severity.slice(1)}
                  </span>
                );
              })}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              Total anomalies: {anomalies.length}
            </div>
          </div>
        )}

        {/* Individual Findings with Supporting Explanations ────────────────── */}
        {anomalies && anomalies.length > 0 && (
          <div className="report-individual-findings" style={{
            padding: 20, background: 'var(--bg-elevated)', borderRadius: 12, marginBottom: 24, border: '1px solid var(--border-subtle)'
          }}>
            <div style={{ fontSize: 11, color: 'var(--text-caption)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 12 }}>
              Individual Findings
            </div>
            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {anomalies.slice(0, 10).map((a, i) => {
                const severity = a.severity || 'low';
                const severityColor = { low: '#6DD5FA', medium: '#FFB547', high: '#FF5D67' }[severity] || '#6DD5FA';
                const confidence = ((a.confidence || 0) * 100).toFixed(0);
                const source = a.source || 'geometry';

                return (
                  <li
                    key={i}
                    style={{
                      padding: '10px 12px',
                      marginBottom: 8,
                      background: 'var(--bg-tertiary)',
                      borderRadius: 8,
                      borderLeft: `3px solid ${severityColor}`,
                      cursor: 'pointer',
                      transition: 'background var(--transition-fast)',
                    }}
                    onMouseOver={(e) => e.currentTarget.style.background = 'var(--bg-surface)'}
                    onMouseOut={(e) => e.currentTarget.style.background = 'var(--bg-tertiary)'}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: 6 }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 2 }}>
                          {a.title || a.id || `Anomaly ${i + 1}`}
                        </div>
                        <div style={{ fontSize: 10, color: 'var(--text-caption)' }}>
                          {severity} · {confidence}% · {source}
                        </div>
                      </div>
                      <div style={{ fontSize: 10, color: 'var(--text-caption)' }}>
                        {a.id || '—'}
                      </div>
                    </div>

                    {/* Coordinates / GPS */}
                    {a.position_gps && (
                      <div style={{ fontSize: 10, color: 'var(--text-caption)', marginTop: 4 }}>
                        📍 {a.position_gps.lat.toFixed(4)}°, {a.position_gps.lon.toFixed(4)}°
                      </div>
                    )}

                    {a.position_enu && !a.position_gps && (
                      <div style={{ fontSize: 10, color: 'var(--text-caption)', marginTop: 4 }}>
                        📐 {a.position_enu.map(c => c.toFixed(2)).join(', ')}
                      </div>
                    )}

                    {/* Visual assessment */}
                    {a.visual_assessment && a.visual_assessment.label !== 'none' && (
                      <div style={{ fontSize: 10, color: 'var(--critical)', marginTop: 4, fontStyle: 'italic' }}>
                        AI: {a.visual_assessment.label}
                      </div>
                    )}

                    {a.visual_assessment && a.visual_assessment.label === 'none' && (
                      <div style={{ fontSize: 10, color: '#628BFF', marginTop: 4, fontStyle: 'italic' }}>
                        AI: No visual features detected
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
            {anomalies.length > 10 && (
              <div style={{ fontSize: 11, color: 'var(--text-caption)', marginTop: 8, textAlign: 'center' }}>
                … and {anomalies.length - 10} more findings
              </div>
            )}
          </div>
        )}

        {/* Pipeline Completion Summary ────────────────────────────────────── */}
        {pipelineStatus === 'completed' && (
          <div className="report-summary" style={{
            padding: 20, background: 'var(--bg-elevated)', borderRadius: 12, marginBottom: 24, border: '1px solid var(--border-subtle)'
          }}>
            <div style={{ fontSize: 11, color: 'var(--text-caption)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 12 }}>
              Pipeline Completion Summary
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-primary)', fontWeight: 500 }}>Stages Completed</div>
                <div style={{ fontSize: 14, color: 'var(--text-secondary)' }}>{Object.keys(stageStatuses || {}).length ? `${Math.round(Object.values(stageStatuses).filter(s => s.status === 'completed').length / Object.keys(stageStatuses).length * 100)}%` : '—'}</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-primary)', fontWeight: 500 }}>Processing Mode</div>
                <div style={{ fontSize: 14, color: 'var(--text-secondary)' }}>{reconstructionMode || 'vision_only'}</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-primary)', fontWeight: 500 }}>Data Availability</div>
                <div style={{ fontSize: 14, color: 'var(--text-secondary)' }}>
                  {report?.assets?.['mesh.ply'] ? 'Mesh available' : report?.assets?.['sparse_cloud.ply'] || report?.assets?.['dense_cloud.ply'] ? 'Point cloud available' : 'No 3D asset available'}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Limitations & Review Status ─────────────────────────────────────── */}
        {pipelineStatus === 'completed' && (
          <div className="report-limitations" style={{
            padding: 20, background: 'var(--bg-tertiary)', borderRadius: 12, marginBottom: 24, border: '1px solid var(--border-subtle)'
          }}>
            <div style={{ fontSize: 11, color: 'var(--text-caption)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 12 }}>
              Limitations & Review Status
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              <div style={{ marginBottom: 8 }}>
                <strong>Finding Review:</strong> Findings are based on the analysis enabled for this job. Evidence-based confidence is a heuristic score, not proof of damage. An optional visual assessment is only available when it is present in the job’s results.
              </div>
              <div style={{ marginBottom: 8 }}>
                <strong>Georeferencing:</strong> Absolute GPS coordinates are only available when GPS/IMU metadata was provided during upload. In vision-only mode, all positions are relative to the reconstruction frame.
              </div>
              <div>
                <strong>Detection Scope:</strong> Anomaly detection is limited to geometric elevation outliers and density gaps from the point cloud. Frame-level object detection requires separate model weights and is opt-in.
              </div>
              <div>
                <strong>Human Review Required:</strong> All findings, confidence scores, and visual assessments must be reviewed and validated by a qualified operator before any engineering conclusions are drawn.
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
