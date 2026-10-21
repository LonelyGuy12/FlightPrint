/* ─── Report Download Utilities ──────────────────────────────────────────
     Generates download links for inspection reports.
  -------------------------------------------------------------------------- */

export function downloadLink(jobId, report) {
  // Try to get the pipeline report from the backend
  try {
    const url = `/api/pipeline/results/${jobId}`;
    fetch(url)
      .then((res) => res.json())
      .then((data) => {
        if (data.anomaly_report) {
          // Could create a blob and trigger download
          // For now, return a data URL if report data is available
          if (data.anomaly_report && typeof data.anomaly_report === 'object') {
            const blob = new Blob([JSON.stringify(data.anomaly_report, null, 2)], {
              type: 'application/json',
            });
            return URL.createObjectURL(blob);
          }
        }
        return null;
      })
      .catch(() => null);
  } catch (e) {
    console.error('Report download failed:', e);
    return null;
  }
  return null;
}