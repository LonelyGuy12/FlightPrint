import { useState, useCallback } from 'react';

export default function MeasureToolbar({ measureMode, onToggle, measurePoints, distance, isMetric = true, onApplyScale }) {
  const [realDistance, setRealDistance] = useState('');
  const [isApplying, setIsApplying] = useState(false);

  const unit = isMetric ? 'm' : 'units';
  const qualifier = isMetric ? '' : ' (relative)';

  const handleApply = async () => {
    if (!realDistance || isNaN(realDistance) || !distance) return;
    setIsApplying(true);
    await onApplyScale(parseFloat(realDistance), distance);
    setIsApplying(false);
    setRealDistance('');
  };

  return (
    <>
      {/* Toolbar buttons */}
      <div className="viewer-toolbar">
        <button
          className={`toolbar-btn ${measureMode ? 'toolbar-btn--active' : ''}`}
          onClick={onToggle}
          title="Measure distance"
        >
          📏
        </button>
      </div>

      {/* Distance overlay */}
      {measureMode && (
        <div className="measure-overlay">
          <div>
            <div className="measure-overlay__label">
              Distance{!isMetric ? ' (relative scale)' : ''}
            </div>
            <div className="measure-overlay__value">
              {distance !== null ? distance.toFixed(2) : '—'}
              <span className="measure-overlay__unit"> {unit}</span>
            </div>
            {!isMetric && distance !== null && (
              <div style={{ marginTop: 8 }}>
                <div style={{ fontSize: 10, color: 'var(--warning)', marginBottom: 6 }}>
                  ⚠ Values are not real-world measurements
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <input
                    type="number"
                    placeholder="Real distance (m)"
                    value={realDistance}
                    onChange={e => setRealDistance(e.target.value)}
                    style={{
                      width: 110, padding: '4px 6px', fontSize: 11,
                      background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-default)',
                      color: '#fff', borderRadius: 4, outline: 'none'
                    }}
                  />
                  <button 
                    onClick={handleApply}
                    disabled={isApplying || !realDistance}
                    style={{
                      padding: '4px 8px', fontSize: 11, background: 'var(--accent-primary)',
                      border: 'none', color: '#fff', borderRadius: 4, cursor: 'pointer',
                      opacity: (isApplying || !realDistance) ? 0.5 : 1
                    }}
                  >
                    {isApplying ? 'Applying...' : 'Set Scale'}
                  </button>
                </div>
              </div>
            )}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', maxWidth: 160 }}>
            {measurePoints.length === 0
              ? 'Click a point to start measuring'
              : measurePoints.length === 1
                ? 'Click another point to measure distance'
                : 'Click to start a new measurement'}
          </div>
        </div>
      )}
    </>
  );
}
