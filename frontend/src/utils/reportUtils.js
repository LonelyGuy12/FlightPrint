/* ─── Report Download Utilities ──────────────────────────────────────────
     Generates download links for inspection reports.
  -------------------------------------------------------------------------- */

import { API_BASE } from './api';

export async function downloadLink(jobId) {
  if (!jobId) throw new Error('Select a job before downloading its report.');

  // The results endpoint lists artifacts; it does not embed the report JSON.
  const response = await fetch(
    `${API_BASE}/api/viewer/files/${encodeURIComponent(jobId)}/anomaly_report.json`,
  );
  if (!response.ok) {
    throw new Error(`Report download failed (HTTP ${response.status}).`);
  }
  const report = await response.json();
  if (!report || typeof report !== 'object' || !Array.isArray(report.anomalies)) {
    throw new Error('The server did not return a valid anomaly report.');
  }
  return URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], {
    type: 'application/json',
  }));
}
