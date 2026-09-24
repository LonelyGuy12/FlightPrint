import axios from 'axios';

const API_BASE = 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 300000, // 5 min for large uploads
});

/**
 * Upload video + optional metadata files.
 * If metadataFile is null, pipeline will run in vision-only mode.
 */
export async function uploadFiles(videoFile, metadataFile, onProgress) {
  const form = new FormData();
  form.append('video', videoFile);
  if (metadataFile) {
    form.append('metadata', metadataFile);
  }

  const res = await api.post('/api/upload/', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (onProgress && e.total) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    },
  });
  return res.data;
}

/**
 * Start the pipeline for a job.
 */
export async function startPipeline(jobId, stages = null, config = null) {
  const res = await api.post(`/api/pipeline/run/${jobId}`, { stages, config });
  return res.data;
}

/**
 * Poll pipeline status.
 */
export async function getPipelineStatus(jobId) {
  const res = await api.get(`/api/pipeline/status/${jobId}`);
  return res.data;
}

/**
 * Get pipeline results (available outputs).
 */
export async function getPipelineResults(jobId) {
  const res = await api.get(`/api/pipeline/results/${jobId}`);
  return res.data;
}

/**
 * Get full scene data for the 3D viewer.
 */
export async function getSceneData(jobId) {
  const res = await api.get(`/api/viewer/scene/${jobId}`);
  return res.data;
}

/**
 * Apply a manual scale factor.
 */
export async function applyScale(jobId, scaleFactor) {
  const res = await api.post(`/api/pipeline/scale/${jobId}`, { scale_factor: scaleFactor });
  return res.data;
}

/**
 * Fetch a raw file (e.g. PLY point cloud).
 */
export async function fetchFile(jobId, filename) {
  const res = await api.get(`/api/viewer/files/${jobId}/${filename}`, {
    responseType: 'text',
  });
  return res.data;
}

/**
 * Fetch file as blob (for binary files).
 */
export async function fetchFileBlob(jobId, filename) {
  const res = await api.get(`/api/viewer/files/${jobId}/${filename}`, {
    responseType: 'blob',
  });
  return res.data;
}

export { API_BASE };
export default api;
