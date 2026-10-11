# FlightPrint Demo Script (M6 — Eshal role, covered by Lidiya)

Status 2026-10-11: script + storyboard ready. Recording is BLOCKED until a
real Mid-Air trajectory run exists (dataset unavailable here); the beats below
are validated against the synthetic-city run
(`output/synth_buildings`, stages 1–4+9, 2/2 anomalies verified). Timings are
for a ~4-minute video. Do NOT record claims about Mid-Air results that have
not been measured.

## 0. Setup (before recording)

- Backend running (`uvicorn app.main:app`), frontend on live API (Phase 3).
- One converted Mid-Air trajectory ready: `data/midair_traj0/{trajectory.mp4,
  metadata.json, groundtruth_poses.json}` [PENDING DATA].
- Bedrock access confirmed in us-east-1, or demo with `--detect` only and say
  the Bedrock check runs the same way (honest fallback).
- Screen recorder + clear `output/demo` folder.

## 1. Hook (0:00–0:30)

"One drone pass. No ground crew, no second flight. FlightPrint turns it into a
georeferenced 3D model — and every finding it reports links back to the exact
video frames that show it."

## 2. Upload + job (0:30–1:15)

- Show `POST /api/upload/`: drag `trajectory.mp4` + `metadata.json`, job created.
- Point out vision-only fallback note when metadata is missing (do not demo it;
  one path per recording).

## 3. Pipeline run (1:15–2:15, timelapse allowed)

- `POST /api/pipeline/run/{job_id}` with
  `{"config": {"stage9": {"use_frame_detection": true}}}` (+ `use_bedrock`
  only if credentials verified pre-recording).
- Poll `GET /api/pipeline/status/{job_id}`: narrate stages 1–4 (frames,
  calibration, SIFT, poses) → 5–8 → 9. Quote real numbers from the run
  (synthetic reference: 11 frames, 10 poses, 1130 points, 31 s).

## 4. The money shot: evidence-backed anomalies (2:15–3:15)

- Open `anomaly_report.json`: `schema_version: 2`, `verified_anomalies`.
- Click an anomaly in the viewer → evidence crops (`evidence/*.jpg`, red ring)
  → "click jumps to the frame" (Hamza's panel).
- Show `overlapping_detections` (YOLO boxes) and `confidence_factors`
  breakdown; state the formula once:
  `0.35·signal + 0.25·views + 0.20·diversity + 0.20·points`, unverified capped
  at 0.30, detection blend `0.85/0.15`, Bedrock blend `0.75/0.25`.
- Show one unverified finding and say plainly: "capped at 0.30 — the system
  tells you when it can't prove what it found."

## 5. 3D model + close (3:15–4:00)

- Orbit the mesh/point cloud; toggle trajectory + anomaly markers.
- Close: "One pass in, model plus provable findings out. OpenCV 5, AWS
  Bedrock, everything reproducible from `tools/README.md`."
- On-screen: repo link, `docs/TEST_PLAN.md`, competition tags.

## Storyboard (shots)

1. Terminal: upload curl + job JSON. 2. Status polling timelapse. 3. Viewer
   orbit. 4. Anomaly click → crops → source frame. 5. Report JSON scroll
   (confidence_factors highlighted). 6. Closing card.

## Do-not-claim list

- No Mid-Air accuracy numbers until `tools/evidence_accuracy.py` runs on real
  converted data. - No live Bedrock footage unless the pre-recording check
  passes (else narrate the `--bedrock` path over the detection run).
