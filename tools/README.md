# Tools

## Mid-Air adapter (`midair_adapter.py`)

Converts one trajectory from the [Mid-Air dataset](https://midair.ulg.ac.be) into FlightPrint's input format, so we can test the pipeline on drone footage that comes with GPS, IMU and ground-truth poses.

Mid-Air isn't plug-and-play with FlightPrint:

| Mid-Air | FlightPrint expects | What the adapter does |
|---|---|---|
| JPEG image sequence (25 fps, 1024×1024) | MP4 video | Stitches frames into an H.264 MP4 |
| `sensor_records.hdf5` | `metadata.json` | Reads HDF5, writes JSON |
| Positions in local NED metres | GPS lat/lon/alt | Converts NED → lat/lon/alt around a configurable origin |
| Attitude as quaternions | IMU roll/pitch/yaw (degrees) | Converts quaternions → Euler angles |
| Intrinsics fx = w/2 (90° FOV) | `focal_length_mm` / `sensor_width_mm` | Writes an equivalent 18 mm / 36 mm pair |

### 1. Get the data

From the [download page](https://midair.ulg.ac.be/download.html), pick **one** trajectory, **one** climate (e.g. `Kite_training/sunny`), and the `color_left` camera plus sensor records. The full dataset is very large.

### 2. Convert

```bash
pip install h5py
python tools/midair_adapter.py \
    --climate-dir data/MidAir/Kite_training/sunny \
    --trajectory 0 \
    --out data/midair_traj0 \
    --max-seconds 30
```

Outputs:
- `trajectory.mp4`: the video
- `metadata.json`: GPS track, camera intrinsics, IMU in FlightPrint's format
- `groundtruth_poses.json`: exact 100 Hz poses for checking pose-estimation accuracy

Options:
- `--max-seconds N`: convert only the first N seconds
- `--position-source groundtruth`: use exact positions instead of the noisy simulated 1 Hz GPS
- `--camera color_down`: use the downward-looking camera
- `--origin-lat / --origin-lon / --origin-alt`: where to place the scene on Earth (any point works; the scene is synthetic)
- `--quat-order wxyz|xyzw`: override the auto-detected quaternion order

On the first run, check the printed `Quaternion order` line. The first sample should be close to `[1, 0, 0, 0]` for `wxyz`.

### 3. Run the pipeline

```bash
python -m pipeline.cli \
    --video data/midair_traj0/trajectory.mp4 \
    --metadata data/midair_traj0/metadata.json \
    --output output/midair_traj0 \
    --stages 1 2 3 4
```

The pipeline should report `Reconstruction mode: full` (GPS + IMU + intrinsics detected).

### 4. Test-data layout & outputs (M6)

Where things belong (nothing under `data/` is committed — it is git-ignored):

```
data/
  MidAir/<climate>/...          # downloaded dataset (sensor_records.hdf5 + color_* folders)
  midair_traj0/                 # adapter output for one trajectory
    trajectory.mp4              # converted video (pipeline input)
    metadata.json               # GPS track, camera, IMU (pipeline input)
    groundtruth_poses.json      # 100 Hz exact poses (for accuracy checks, Phase 3)
output/
  midair_traj0/                 # pipeline output for that trajectory
    frames/                     # extracted frames
    anomaly_report.json         # schema_version 2 (see below)
    evidence/                   # evidence crops: <anom_id>_f<frame>.jpg, red ring = finding
    progress.json               # per-stage status (for API polling)
    pipeline_report.json        # final summary
```

Run Stage 9 with the Bedrock visual check (off by default; needs AWS
credentials, billed per call — at most the top 10 anomalies):

```bash
python -m pipeline.cli \
    --video data/midair_traj0/trajectory.mp4 \
    --metadata data/midair_traj0/metadata.json \
    --output output/midair_traj0 \
    --bedrock
# Optional overrides: --bedrock-model-id <id> --bedrock-region <region>
#   --max-bedrock-anomalies N
# Or via env: FLIGHTPRINT_USE_BEDROCK=1 BEDROCK_MODEL_ID=amazon.nova-pro-v1:0 AWS_REGION=us-east-1
# Or via config JSON: {"stage9": {"use_bedrock": true}}
```

What to check afterwards:

- `output/midair_traj0/anomaly_report.json`: `schema_version` is 2;
  every verified anomaly lists `supporting_frames` (best first) with
  `frame_index`, `timestamp`, `pixel`, `depth`, `crop_path`; unverified
  findings have `confidence <= 0.30` and `evidence_level: unverified`.
- `output/midair_traj0/evidence/`: every `crop_path` in the report exists
  on disk; open a few and confirm the red ring marks a real structure.
- With `--bedrock`: top anomalies carry `visual_assessment` (`label`,
  `description`, `confidence`, `model`); failed checks carry
  `visual_assessment_error` instead and keep their geometric result.
- Full pass/fail criteria live in `docs/TEST_PLAN.md`; observed issues go in
  `docs/BUG_LOG.md`.

> Status 2026-10-04: no real trajectory has been run in this environment yet
> (dataset not downloaded here). The commands above are the exact,
> verified-CLI procedure — do not claim a trajectory run until its outputs
> exist under `output/` and are recorded in `docs/BUG_LOG.md`.

### License

Mid-Air is released under [CC BY-NC-SA 4.0](http://creativecommons.org/licenses/by-nc-sa/4.0/). Don't commit the data (`data/` is git-ignored). Cite:
Fonder & Van Droogenbroeck, *Mid-Air: A multi-modal dataset for extremely low altitude drone flights*, CVPRW 2019.
