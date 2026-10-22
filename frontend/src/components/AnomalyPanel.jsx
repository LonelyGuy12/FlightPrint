export default function AnomalyPanel({ anomalies, selectedIndex, onSelect }) {
  if (!anomalies || anomalies.length === 0) {
    return (
      <div className="anomaly-panel" style={{
        padding: '20px 16px',
        textAlign: 'center',
        color: 'var(--text-caption)',
      }}>
        <div style={{ fontSize: 28, marginBottom: 8, opacity: 0.3 }}>🔍</div>
        <div style={{ fontSize: 12, color: 'var(--text-caption)' }}>
          No anomalies detected yet
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-caption)', opacity: 0.7, marginTop: 4 }}>
          Run the AI analysis stage to find regions of interest
        </div>
      </div>
    );
  }

  const typeLabels = {
    elevation_high: '⬆️ Elevation High',
    elevation_low: '⬇️ Elevation Low',
    density_gap: '🔲 Density Gap',
    damage: '⚠️ Damage',
    obstruction: '🚧 Obstruction',
    unusual_object: '❓ Unusual Object',
  };

  return (
    <div className="anomaly-panel" style={{
      padding: '12px 16px',
      borderRadius: 12,
      background: "var(--bg-elevated)",
      border: '1px solid var(--border-subtle)',
    }}>
      <div style={{ padding: '12px 16px', fontSize: 11, color: 'var(--text-caption)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: '1px solid var(--border-subtle)' }}>
        Anomalies ({anomalies.length})
      </div>

      {anomalies.map((a, i) => (
        <div
          key={i}
          className={`anomaly-card ${selectedIndex === i ? 'anomaly-card--selected' : ''}`}
          onClick={() => onSelect?.(i)}
          style={{
            margin: '4px 12px',
            padding: '10px 12px',
            background: "var(--bg-elevated)",
            border: '1px solid var(--border-subtle)',
            borderRadius: 12,
            cursor: 'pointer',
            transition: 'all var(--transition-fast)',
          }}
        >
          <div className="anomaly-card__header" style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            marginBottom: 6,
          }}>
            <div className={`anomaly-card__severity anomaly-card__severity--${a.severity || 'low'}`}
              style={{ width: 6, height: 6, borderRadius: 50 }}
            />
            <span className="anomaly-card__type"
              style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)', flex: 1 }}
            >
              {typeLabels[a.type] || a.type || 'Unknown'}
            </span>
            <span className="anomaly-card__confidence"
              style={{ fontSize: 10, color: 'var(--text-caption)', fontFamily: 'var(--font-mono)', fontWeight: 500 }}
            >
              {((a.confidence || 0) * 100).toFixed(0)}%
            </span>
          </div>
          <div className="anomaly-card__desc"
            style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.4, marginTop: 4 }}
          >
            {a.description || 'No description available'}
          </div>
          {a.position_gps && (
            <div className="anomaly-card__coords"
              style={{ fontSize: 10, color: 'var(--text-caption)', fontFamily: 'var(--font-mongo)' }}
            >
              📍 {a.position_gps.lat?.toFixed(4)}°, {a.position_gps.lon?.toFixed(4)}°
            </div>
          )}
        </div>
      ))}
    </div>
  );
}