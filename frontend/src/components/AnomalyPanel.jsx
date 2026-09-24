export default function AnomalyPanel({ anomalies, selectedIndex, onSelect }) {
  if (!anomalies || anomalies.length === 0) {
    return (
      <div className="anomaly-panel" style={{ padding: '20px 16px', textAlign: 'center' }}>
        <div style={{ fontSize: 28, marginBottom: 8, opacity: 0.3 }}>🔍</div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          No anomalies detected yet
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', opacity: 0.7, marginTop: 4 }}>
          Run the AI analysis stage to find regions of interest
        </div>
      </div>
    );
  }

  const formatCoords = (gps) => {
    if (!gps) return null;
    return `${gps.lat?.toFixed(6)}°, ${gps.lon?.toFixed(6)}°`;
  };

  const typeLabels = {
    elevation_high: '⬆️ Elevation High',
    elevation_low: '⬇️ Elevation Low',
    density_gap: '🔲 Density Gap',
    damage: '⚠️ Damage',
    obstruction: '🚧 Obstruction',
    unusual_object: '❓ Unusual Object',
  };

  return (
    <div className="anomaly-panel">
      <div style={{
        padding: '12px 16px',
        fontSize: 11,
        color: 'var(--text-muted)',
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        borderBottom: '1px solid var(--border-subtle)',
      }}>
        Anomalies ({anomalies.length})
      </div>

      {anomalies.map((a, i) => (
        <div
          key={i}
          className={`anomaly-card ${selectedIndex === i ? 'anomaly-card--selected' : ''}`}
          onClick={() => onSelect?.(i)}
        >
          <div className="anomaly-card__header">
            <div className={`anomaly-card__severity anomaly-card__severity--${a.severity || 'low'}`} />
            <span className="anomaly-card__type">
              {typeLabels[a.type] || a.type || 'Unknown'}
            </span>
            <span className="anomaly-card__confidence">
              {((a.confidence || 0) * 100).toFixed(0)}%
            </span>
          </div>
          <div className="anomaly-card__desc">
            {a.description || 'No description available'}
          </div>
          {a.position_gps && (
            <div className="anomaly-card__coords">
              📍 {formatCoords(a.position_gps)}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
