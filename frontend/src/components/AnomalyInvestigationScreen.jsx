import { useState, useCallback } from 'react';
import Viewer3D from './Viewer3D';
import AnomalyPanel from './AnomalyPanel';
import { API_BASE } from '../utils/api';

/* ─── Anomaly Investigation Screen ───────────────────────────────────────
     Focused workspace for examining detected anomalies.
     Each finding shows available information and links to evidence.
  -------------------------------------------------------------------------- */

export default function AnomalyInvestigationScreen({
  jobId,
  pipelineStatus,
  stageStatuses,
  anomalies,
  selectedAnomaly,
  onSelectAnomaly,
  onStartPipeline,
  onDisplayModeChange,
  onPointSizeChange,
}) {
  const focusedAnomaly = anomalies[selectedAnomaly] || null;
  const [viewMode, setViewMode] = useState('3d'); // '3d' | 'evidence' | 'details'

  // Handle anomaly selection
  const handleAnomalySelect = useCallback((index) => {
    onSelectAnomaly?.(index);
    setViewMode('details');

    // Highlight in 3D viewer - the Viewer3D component handles this via onSelectAnomaly
    // and the selected anomaly is already passed down
  }, [onSelectAnomaly]);

  // Navigate between findings
  const nextFinding = useCallback(() => {
    if (!focusedAnomaly || anomalies.length === 0) return;
    const currentIndex = anomalies.indexOf(focusedAnomaly);
    const nextIndex = (currentIndex + 1) % anomalies.length;
    onSelectAnomaly?.(nextIndex);
  }, [anomalies, focusedAnomaly, onSelectAnomaly]);

  const prevFinding = useCallback(() => {
    if (!focusedAnomaly || anomalies.length === 0) return;
    const currentIndex = anomalies.indexOf(focusedAnomaly);
    const prevIndex = (currentIndex - 1 + anomalies.length) % anomalies.length;
    onSelectAnomaly?.(prevIndex);
  }, [anomalies, focusedAnomaly, onSelectAnomaly]);

  // Determine which view to render based on viewMode
  let investigationView;
  if (viewMode === '3d' && anomalies.length > 0) {
    investigationView = (
      <div className="investigation-3d-view">
        <Viewer3D
          pointCloudData={null} // Will be loaded on demand
          meshUrl={null}
          trajectory={null}
          anomalies={anomalies}
          selectedAnomaly={selectedAnomaly}
          onSelectAnomaly={handleAnomalySelect}
          pointSize={2.5}
          displayMode="mesh"
          onDisplayModeChange={() => {}}
          measureMode={false}
          measurePoints={[]}
          onMeasureClick={() => {}}
          showTrajectory={false}
          showAnomalies={true}
        />
      </div>
    );
  } else if (viewMode === 'evidence' && focusedAnomaly) {
    investigationView = (
      <div className="investigation-evidence-view">
        <div style={{ padding: 20, background: '#1A2636', borderRadius: 12, marginBottom: 20 }}>
          <div style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 6 }}>
              Evidence for {focusedAnomaly.title || focusedAnomaly.id}
            </div>
            <div style={{ fontSize: 11, color: '#4A5F79' }}>
              <div>Category: {focusedAnomaly.type || 'Unknown'}</div>
              <div>Severity: {focusedAnomaly.severity || 'low'}</div>
              <div>Confidence: {((focusedAnomaly.confidence || 0) * 100).toFixed(0)}%</div>
              {focusedAnomaly.visual_assessment && (
                <div>
                  <div style={{ fontSize: 10, color: '#4A5F79', marginBottom: 4 }}>
                    Visual Assessment:
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-primary)', display: 'flex', gap: 8, alignItems: 'center' }}>
                    {focusedAnomaly.visual_assessment.label !== 'none' && (
                      <span style={{ color: 'var(--critical)', fontWeight: 500 }}>
                        {focusedAnomaly.visual_assessment.label}
                      </span>
                    )}
                    {focusedAnomaly.visual_assessment.confidence && (
                      <span style={{ fontSize: 10, color: '#4A5F79' }}>
                        (confidence {((focusedAnomaly.confidence || 0) * 100).toFixed(0)}%)
                      </span>
                    )}
                  </div>
                </div>
              )}
              {focusedAnomaly.description && (
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 6, lineHeight: 1.4 }}>
                  {focusedAnomaly.description}
                </div>
              )}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 8, marginTop: 12 }}>
                {focusedAnomaly.supporting_frames && focusedAnomaly.supporting_frames.length > 0 ? (
                  focusedAnomaly.supporting_frames.slice(0, 6).map((f, i) => {
                    const cropPath = f.crop_path;
                    return (
                      <div
                        key={i}
                        style={{
                          padding: 8,
                          background: 'var(--bg-tertiary)',
                          borderRadius: 6,
                          textAlign: 'center',
                          border: '1px solid var(--border-subtle)',
                        }}
                      >
                        {cropPath ? (
                          <img
                            src={`${API_BASE}/api/viewer/files/${encodeURIComponent(jobId)}/${cropPath.split('/').map(encodeURIComponent).join('/')}`}
                            alt={`Evidence crop from frame ${f.frame_index}`}
                            style={{ width: 120, height: 80, objectFit: 'cover', borderRadius: 4 }}
                          />
                        ) : (
                          <div
                            style={{
                              width: 120, height: 80,
                              background: 'var(--bg-secondary)',
                              borderRadius: 4,
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                              color: '#4A5F79', fontSize: 10,
                            }}
                          >
                            ⚠️
                          </div>
                        )}
                        <div style={{ fontSize: 10, color: '#4A5F79', marginTop: 4 }}>
                          Frame {f.frame_index}
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div style={{ padding: 12, textAlign: 'center', color: '#4A5F79' }}>
                    <div style={{ fontSize: 16, opacity: 0.5, marginBottom: 8 }}>📷</div>
                    <p>No supporting frame crops available</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
        );
  } else if (focusedAnomaly) {
    investigationView = (
      <div className="anomaly-details-panel">
        <div style={{ padding: 20, background: '#1A2636', borderRadius: 12, marginBottom: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: 12 }}>
            <div>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
                {focusedAnomaly ? (focusedAnomaly.title || focusedAnomaly.id || 'Anomaly') : 'No anomaly selected'}
              </div>
              <div style={{ fontSize: 11, color: '#4A5F79', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Anomaly {selectedAnomaly + 1} of {anomalies.length}
              </div>
            </div>
            <button
              className="btn btn--sm btn--secondary"
              onClick={prevFinding}
              style={{ padding: '4px 6px', fontSize: 10, minWidth: 60 }}
              title="Previous finding"
            >
              ← Prev
            </button>
            <button
              className="btn btn--sm btn--secondary"
              onClick={nextFinding}
              style={{ padding: '4px 6px', fontSize: 10, minWidth: 60 }}
              title="Next finding"
            >
              Next →
            </button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, marginTop: 12, fontSize: 12 }}>
            <div>
              <div style={{ fontSize: 10, color: '#4A5F79', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>Type</div>
              <div style={{ color: 'var(--text-primary)' }}>{focusedAnomaly.type || 'Unknown'}</div>
            </div>
            <div>
              <div style={{ fontSize: 10, color: '#4A5F79', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>Severity</div>
              <div>
                <div
                  style={{
                    width: 8, height: 8, borderRadius: 50,
                    background: { low: '#6DD5FA', medium: '#FFB547', high: '#FF5D67' }[focusedAnomaly.severity] || '#6DD5FA',
                  }}
                />
                <span style={{ color: 'var(--text-primary)' }}>{focusedAnomaly.severity || 'low'}</span>
              </div>
            </div>
            <div>
              <div style={{ fontSize: 10, color: '#4A5F79', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>Confidence</div>
              <div>
                <span style={{ color: 'var(--accent-primary)' }}>{((focusedAnomaly.confidence || 0) * 100).toFixed(0)}%</span>
              </div>
            </div>
            <div>
              <div style={{ fontSize: 10, color: '#4A5F79', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>Source</div>
              <div style={{ color: 'var(--text-primary)' }}>{focusedAnomaly.source || 'geometry'}</div>
            </div>
          </div>
        </div>

        <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border-subtle)' }}>
          <div style={{ fontSize: 10, color: '#4A5F79', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
            Assessment Description
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            {focusedAnomaly.description}
          </div>
        </div>

        {focusedAnomaly.position_enu && (
          <div style={{ marginTop: 12, padding: 10, background: 'var(--bg-tertiary)', borderRadius: 6, fontSize: 11 }}>
            <div style={{ fontSize: 10, color: '#4A5F79', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>3D Location (ENU)</div>
            <div style={{ color: 'var(--text-primary)' }}>
              {focusedAnomaly.position_enu.map((c, i) => `${['x', 'y', 'z'][i]}: ${c.toFixed(2)}`).join('<br />')}
            </div>
          </div>
        )}

        {focusedAnomaly.position_gps && (
          <div style={{ marginTop: 12, padding: 10, background: 'var(--bg-tertiary)', borderRadius: 6, fontSize: 11 }}>
            <div style={{ fontSize: 10, color: '#4A5F79', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>Geolocation</div>
            <div style={{ color: 'var(--text-primary)' }}>
              {`${focusedAnomaly.position_gps.lat.toFixed(4)}°, ${focusedAnomaly.position_gps.lon.toFixed(4)}°`}
            </div>
          </div>
        )}

        {focusedAnomaly.visual_assessment && focusedAnomaly.visual_assessment.label !== 'none' && (
          <div style={{ marginTop: 12, padding: 8, background: 'rgba(255, 93, 103, 0.08)', borderRadius: 6, fontSize: 11 }}>
            <div style={{ fontSize: 10, color: '#4A5F79', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
              AI Visual Assessment
            </div>
            <div style={{ color: 'var(--text-primary)', fontStyle: 'italic' }}>
              Model detected: {focusedAnomaly.visual_assessment.label}
            </div>
            <div style={{ fontSize: 10, color: '#4A5F79' }}>
              Model checked {focusedAnomaly.visual_assessment.crops_checked || 0} evidence crops
            </div>
          </div>
        )}

        {(!focusedAnomaly.visual_assessment || focusedAnomaly.visual_assessment.label === 'none') && (
          <div style={{ marginTop: 12, padding: 8, background: 'rgba(66, 217, 255, 0.08)', borderRadius: 6, fontSize: 10, color: '#628BFF' }}>
            <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
              ⚠ Important Note
            </div>
            <div style={{ fontSize: 11, lineHeight: 1.5 }}>
              An AI-generated assessment does not establish a confirmed structural defect. All findings
              require human verification before drawing engineering conclusions.
            </div>
          </div>
        )}
      </div>
    );
  } else {
    investigationView = <p>Select a finding to inspect its details and evidence.</p>;
  }

  return (
    <div className="anomaly-investigation-screen">
      {/* ─── Header ──────────────────────────────────────────────────────── */}
      <div className="investigation-header">
        <div className="header-left">
          <h1 style={{ fontSize: 20, fontWeight: 600, marginBottom: 4 }}>
            Anomaly Investigation
          </h1>
          <p style={{ fontSize: 13, color: '#4A5F79', marginBottom: 0 }}>
            Detected Regions of Interest
          </p>
        </div>

        <div className="header-right">
          <span className={`status-badge status-badge--${pipelineStatus}`}>
            {pipelineStatus.charAt(0).toUpperCase() + pipelineStatus.slice(1)}
          </span>
          <button
            className="btn btn--sm btn--secondary"
            onClick={() => onSelectAnomaly?.(null)}
            title="Deselect anomaly"
            style={{ padding: '4px 8px', fontSize: 11, marginLeft: 8 }}
          >
            ✕
          </button>
        </div>
      </div>

      {/* ─── Main Content Area ──────────────────────────────────────────── */}
      <div className="investigation-main">
        <AnomalyPanel anomalies={anomalies} selectedIndex={selectedAnomaly} onSelect={handleAnomalySelect} />
        {focusedAnomaly && (
          <div>
            <button className="btn btn--secondary" onClick={() => setViewMode('details')}>Finding Details</button>
            <button className="btn btn--secondary" onClick={() => setViewMode('evidence')}>Evidence Frames</button>
          </div>
        )}
        {investigationView}
      </div>
    </div>
  );
}
