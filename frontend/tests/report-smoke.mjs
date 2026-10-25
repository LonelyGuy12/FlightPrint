// Local integration smoke test. Uses FastAPI + synthetic report fixtures, never AWS.
// Prerequisites: backend/requirements.txt, npm ci, and an installed Edge browser.
// Run: REPORT_TEST_PYTHON=<python executable> node tests/report-smoke.mjs
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { createServer } from 'vite';
import { chromium } from 'playwright-core';

const frontend = fileURLToPath(new URL('..', import.meta.url));
const backend = path.resolve(frontend, '../backend');
const temp = await mkdtemp(path.join(tmpdir(), 'flightprint-report-'));
const output = path.join(temp, 'output');
const job = 'report-smoke';
const anomalyReport = {
  schema_version: 2, total_anomalies: 1, verified_anomalies: 0,
  anomalies: [{ id: 'fixture-001', type: 'density_gap', severity: 'low',
    description: 'Synthetic integration-test finding', confidence: 0.3,
    evidence_level: 'unverified', supporting_frames: [] }],
};
await mkdir(path.join(output, job), { recursive: true });
await mkdir(path.join(output, 'empty-smoke'), { recursive: true });
await writeFile(path.join(output, job, 'anomaly_report.json'), JSON.stringify(anomalyReport));
await writeFile(path.join(output, job, 'pipeline_report.json'), JSON.stringify({
  video: 'synthetic-test-fixture.mp4', num_frames: 5, sparse_points: 0,
  reconstruction_mode: 'vision_only', scale_status: 'relative_unscaled',
}));
const apiBase = 'http://localhost:8000';
try {
  await fetch(`${apiBase}/health`);
  throw new Error('Port 8000 is already in use; stop the local backend before this isolated test.');
} catch (error) {
  if (!error.cause) throw error;
}
const processLog = [];
const child = spawn(process.env.REPORT_TEST_PYTHON || 'python', [
  '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000',
], {
  cwd: backend, env: { ...process.env, FLIGHTPRINT_OUTPUT_DIR: output,
    FLIGHTPRINT_UPLOAD_DIR: path.join(temp, 'uploads') },
  stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true,
});
child.stdout.on('data', b => processLog.push(b.toString()));
child.stderr.on('data', b => processLog.push(b.toString()));
let server;
let browser;
try {
  let ready = false;
  for (let i = 0; i < 80; i++) {
    try { if ((await fetch(`${apiBase}/health`)).ok) { ready = true; break; } } catch {}
    if (child.exitCode !== null) break;
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  assert.ok(ready, `Backend did not start:\n${processLog.join('')}`);
  server = await createServer({ root: frontend, server: { host: '127.0.0.1', port: 5173, strictPort: true } });
  await server.listen();
  browser = await chromium.launch({ channel: process.env.REPORT_TEST_BROWSER || 'msedge', headless: true });
  const page = await browser.newPage({ acceptDownloads: true });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const base = 'http://127.0.0.1:5173';

  await page.goto(base);
  await page.getByRole('heading', { name: 'Mission Overview' }).waitFor();
  await page.getByTitle('Anomaly Investigation', { exact: true }).click();
  await page.getByText('Select a finding to inspect its details and evidence.').waitFor();
  console.log('PASS: empty overview and anomaly screens render without a crash');

  await page.goto(base);
  const uploaded = page.waitForResponse(response => response.url().endsWith('/api/upload/') && response.request().method() === 'POST');
  await page.locator('input[type="file"]').first().setInputFiles({
    name: 'upload-fixture.mp4', mimeType: 'video/mp4', buffer: Buffer.from('Synthetic upload fixture; not used for reconstruction.'),
  });
  const uploadResponse = await uploaded;
  assert.equal(uploadResponse.status(), 200);
  assert.ok((await uploadResponse.json()).job_id);
  console.log('PASS: overview file selection reaches the real upload API (no reconstruction)');

  await page.goto(`${base}/?jobId=${job}`);
  await page.getByTitle('Evidence & Reports', { exact: true }).click();
  await page.getByRole('button', { name: /Download/ }).waitFor();
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: /Download/ }).click();
  const download = await downloadPromise;
  assert.equal(download.suggestedFilename(), `flightprint-report-${job}.json`);
  const downloaded = path.join(temp, download.suggestedFilename());
  await download.saveAs(downloaded);
  assert.deepEqual(JSON.parse(await readFile(downloaded, 'utf8')), anomalyReport);
  console.log('PASS: real FastAPI report download matches job JSON and filename');

  const reportUrl = `${apiBase}/api/viewer/files/${job}/anomaly_report.json`;
  await page.route(reportUrl, route => route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"Missing report"}' }));
  await page.getByRole('button', { name: /Download/ }).click();
  await page.getByRole('alert').filter({ hasText: 'HTTP 404' }).waitFor();
  assert.equal(await page.getByRole('button', { name: /Download/ }).isEnabled(), true);
  await page.unroute(reportUrl);
  console.log('PASS: HTTP failure is visible and download can be retried');

  await page.route(reportUrl, route => route.fulfill({ status: 200, contentType: 'application/json', body: '{"unexpected":true}' }));
  await page.getByRole('button', { name: /Download/ }).click();
  await page.getByRole('alert').filter({ hasText: 'valid anomaly report' }).waitFor();
  await page.unroute(reportUrl);
  console.log('PASS: malformed report payload is rejected');

  await page.getByTitle('Anomaly Investigation', { exact: true }).click();
  await page.getByText('Synthetic integration-test finding', { exact: true }).first().click();
  await page.getByRole('button', { name: 'Evidence Frames' }).click();
  await page.getByText('No supporting frame crops available').waitFor();
  console.log('PASS: anomaly selection and unverified evidence state');

  await page.goto(`${base}/?jobId=empty-smoke`);
  await page.getByTitle('Evidence & Reports', { exact: true }).click();
  await page.getByRole('heading', { name: 'No Report Available' }).waitFor();
  assert.equal(await page.getByRole('button', { name: /Download/ }).count(), 0);
  console.log('PASS: job without a report does not offer a bogus download');

  await page.route(`${apiBase}/api/viewer/scene/${job}`, route => route.fulfill({ status: 500, body: 'error' }));
  await page.goto(`${base}/?jobId=${job}`);
  await page.getByTitle('Evidence & Reports', { exact: true }).click();
  await page.getByRole('heading', { name: 'Report Unavailable' }).waitFor();
  console.log('PASS: report-loading failure is shown explicitly');
  assert.deepEqual(errors, [], `Uncaught browser errors: ${errors.join('; ')}`);
  console.log(`All report smoke checks passed. Download fixture: ${downloaded}`);
} finally {
  await browser?.close();
  await server?.close();
  child.kill();
}
