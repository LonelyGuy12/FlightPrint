import { useState, useCallback, useEffect, useRef } from 'react';
import Viewer3D from './Viewer3D';
import AnomalyPanel from './AnomalyPanel';

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
  const [focusedAnomaly, setFocusedAnomaly] = useState(null);
  const [viewMode, setViewMode] = useState('3d'); // '3d' | 'evidence' | 'details'

  // Handle anomaly selection
  const handleAnomalySelect = useCallback((index) => {
    setSelectedAnomaly(index);
    setFocusedAnomaly(anomalies[index]);
    setViewMode('details');

    // Highlight in 3D viewer - the Viewer3D component handles this via onSelectAnomaly
    // and the selected anomaly is already passed down
  }, [anomalies]);

  // Navigate between findings
  const nextFinding = useCallback(() => {
    if (!focusedAnomaly || anomalies.length === 0) return;
    const currentIndex = anomalies.indexOf(focusedAnomaly);
    const nextIndex = (currentIndex + 1) % anomalies.length;
    setSelectedAnomaly(nextIndex);
    setFocusedAnomaly(anomalies[nextIndex]);
  }, [anomalies, focusedAnomaly]);

  const prevFinding = useCallback(() => {
    if (!focusedAnomaly || anomalies.length === 0) return;
    const currentIndex = anomalies.indexOf(focusedAnomaly);
    const prevIndex = (currentIndex - 1 + anomalies.length) % anomalies.length;
    setSelectedAnomaly(prevIndex);
    setFocusedAnomaly(anomalies[prevIndex]);
  }, [anomalies, focusedAnomaly]);

  return (
    <div className="anomaly-investigation-screen">
      {/* ─── Header ──────────────────────────────────────────────────────── */}
      <div className="investigation-header">
        <div className="header-left">
          <h1 style={{ fontSize: 20, fontWeight: 600, marginBottom: 4 }}>
            Anomaly Investigation
          </h1>
          <p style={{ fontSize: 13, color: 'var(--text-caption)', marginBottom: 0 }}>
            Detected Regions of Interest
          </p>
        </div>

        <div className="header-right">
          <span className={`status-badge status-badge--${pipelineStatus}`}>
            {pipelineStatus.charAt(0).toUpperCase() + pipelineStatus.slice(1)}
          </span>
          <button
            className="btn btn--sm btn--secondary"
            onClick={handleAnomalySelect}
            title="Deselect anomaly"
            style={{ padding: '4px 8px', fontSize: 11, marginLeft: 8 }}
          >
            ✕
          </button>
        </div>
      </div>

      {/* ─── Main Content Area ──────────────────────────────────────────── */}
      <div className="investigation-main">
        {viewMode === '3d' && anomalies.length > 0 ? (
          {/* ─── 3D View with Anomaly Focus ───────────────────────────────── */}
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
        ) : viewMode === 'evidence' && focusedAnomaly ? (
          {/* ─── Evidence Detail View ─────────────────────────────────────── */}
          <div className="investigation-evidence-view">
            <div style={{ padding: 20, background: var(--bg-elevated), borderRadius: 12, marginBottom: 20 }}>
              <div style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 12 }}>
                <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 6 }}>
                  Evidence for {focusedAnomaly.title || focusedAnomaly.id}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-caption)' }}>
                  <div>Category: {focusedAnomaly.type || 'Unknown'}</div>
                  <div>Severity: {focusedAnomaly.severity || 'low'}</div>
                  <div>Confidence: {((focusedAnomaly.confidence || 0) * 100).toFixed(0)}%</div>
                  {focusedAnomaly.visual_assessment && (
                    <div>
                      <div style={{ fontSize: 10, color: 'var(--text-caption)', marginBottom: 4 }}>
                        Visual Assessment:
                      </div>
                      <div style={{
                        fontSize: 11, color: 'var(--text-primary)',
                        display: 'flex', gap: 8, alignItems: 'center',
                      }}>
                        {focusedAnomaly.visual_assessment.label !== 'none' && (
                          <span style={{ color: var(--critical), fontWeight: 500 }}>
                            {focusedAnomaly.visual_assessment.label}
                          </span>
                        )}
                        {focusedAnomaly.visual_assessment.confidence && (
                          <span style={{ fontSize: 10, color: 'var(--text-caption)' }}>
                            (confidence {((focusedAnomaly.visual_assessment.confidence || 0) * 100).toFixed(0)}%)
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
                </div>
              </div>

              {/* Evidence thumbnails / crops */}
              {focusedAnomaly.supporting_frames && focusedAnomaly.supporting_frames.length > 0 ? (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 8, marginTop: 12 }}>
                  {focusedAnomaly.supporting_frames.slice(0, 6).map((f, i) => {
                    const cropPath = f.crop_path;
                    return (
                      <div
                        key={i}
                        style={{
                          padding: 8,
                          background: var(--bg-tertiary),
                          borderRadius: 6,
                          textAlign: 'center',
                          border: '1px solid var(--border-subtle)',
                        }}
                      >
                        {cropPath && Path.exists ? (
                          <img
                            src: {cropPath}
                            style={{ width: 120, height: 80, objectFit: 'cover', borderRadius: 4 }}
                          />
                        ) : (
                          <div
                            style={{
                              width: 120, height: 80,
                              background: var(--bg-secondary),
                              borderRadius: 4,
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                              color: 'var(--text-caption)', fontSize: 10,
                            }}
                          >
                            ⚠️
                          </div>
                        )}
                        <div style={{ fontSize: 10, color: 'var(--text-caption)', marginTop: 4 }}>
                          Frame {f.frame_index}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div style={{ padding: 12, textAlign: 'center', color: 'var(--text-caption)' }}>
                  <div style={{ fontSize: 16, opacity: 0.5, marginBottom: 8 }}>📷</div>
                  <p>No supporting frame crops available</p>
                </div>
              )}
            </div>
          </div>
        ) : (
          {/* ─── Anomaly Details Panel ─────────────────────────────────────── */}
          <div className="anomaly-details-panel">
            <div style={{ padding: 20, background: var(--bg-elevated), borderRadius: 12, marginBottom: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: 12 }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
                    {focusedAnomaly ? (focusedAnomaly.title || focusedAnomaly.id || 'Anomaly') : 'No anomaly selected'}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-caption)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
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

              {/* Finding metadata */}
              {focusedAnomaly && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, marginTop: 12, fontSize: 12 }}>
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--text-caption)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>Type</div>
                    <div style={{ color: 'var(--text-primary)' }}>{focusedAnomaly.type || 'Unknown'}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--text-caption)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>Severity</div>
                    <div>
                      <div
                        style={{
                          width: 8, height: 8, borderRadius: 50,
                          background: { low: '#6DD5FA', medium: '#FFB547', high: '#FF5D67' }[focusedAnomaly.severity] || '#6DD5FA',
                        }}
                      /></div>
                      <span style={{ color: 'var(--text-primary)' }}>{focusedAnomaly.severity || 'low'}</span>
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--text-caption)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>Confidence</div>
                    <div>
                      <span style={{ color: 'var(--accent-primary)' }}>{((focusedAnomaly.confidence || 0) * 100).toFixed(0)}%</span>
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--text-caption)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>Source</div>
                    <div style={{ color: 'var(--text-primary)' }}>{focusedAnomaly.source || 'geometry'}</div>
                  </div>
                </div>
              )}

              {/* Description */}
              {focusedAnomaly && focusedAnomaly.description && (
                <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border-subtle) }}>
                  <div style={{ fontSize: 10, color: 'var(--text-caption)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
                    Assessment Description
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                    {focusedAnomaly.description}
                  </div>
                </div>
              )}

              {/* Coordinates */}
              {focusedAnomaly.position_enu && (
                <div style={{ marginTop: 12, padding: 10, background: var(--bg-tertiary), borderRadius: 6, fontSize: 11 }}>
                  <div style={{ fontSize: 10, color: 'var(--text-caption)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }>3D Location (ENU)</div>
                  <div style={{ color: 'var(--text-primary)' }}>
                    {focusedAnomaly.position_enu.map((c, i) => `${['x', 'y', 'z'][i]}: ${c.toFixed(2)}`).join('<br />')}
                  </div>
                </div>
              )}

              {/* GPS when available */}
              {focusedAnomaly.position_gps && (
                <div style={{ marginTop: 12, padding: 10, background: var(--bg-tertiary), borderRadius: 6, fontSize: 11 }}>
                  <div style={{ fontSize: 10, color: 'var(--text-caption)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }>Geolocation</div>
                  <div style={{ color: 'var(--text-primary)' }}>
                    {`${focusedAnomaly.position_gps.lat.toFixed(4)}°, ${focusedAnomaly.position_gps.lon.toFixed(4)}°`}
                  </div>
                </div>
              )}

              {/* Detection method */}
              {focusedAnomaly.visual_assessment && focusedAnomaly.visual_assessment.label !== 'none' && (
                <div style={{ marginTop: 12, padding: 8, background: 'rgba(255, 93, 103, 0.08)', borderRadius: 6, fontSize: 11 }}>
                  <div style={{ fontSize: 10, color: 'var(--text-caption)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
                    AI Visual Assessment
                  </div>
                  <div style={{ color: 'var(--text-primary)', fontStyle: 'italic' }}>
                    Model detected: {focusedAnomaly.visual_assessment.label}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-caption)' }}>
                    Model checked {focusedAnomaly.visual_assessment.crops_checked || 0} evidence crops
                  </div>
                </div>
              )}

              {/* Important disclaimer */}
              {!focusedAnomaly.visual_assessment || focusedAnomaly.visual_assessment.label === 'none' && (
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

            {/* Navigate between findings */}
            {anomalies.length > 1 && (
              <div style={{ padding: 16, background: var(--bg-secondary), borderTop: '1px solid var(--border-subtle) ' }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', justifyContent: 'center' }}>
                  <button
                    className="btn btn--sm btn--secondary"
                    onClick={prevFinding}
                    style={{ flex: 1, padding: '4px 8px', fontSize: 11 }}
                    title="Previous anomaly"
                  >
                    ←
                  </button>
                  <span style={{ flex: 1, fontSize: 11, color: 'var(--text-caption)' }}>
                    {selectedAnomaly + 1} of {anomalies.length}
                  </span>
                  <button
                    className="btn btn--sm btn--secondary"
                    onClick={nextFinding}
                    style={{ flex: 1, padding: '4px 8px', fontSize: 11 }}
                    title="Next anomaly"
                  >
                    →
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}