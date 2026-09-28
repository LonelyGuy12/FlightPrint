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

### License

Mid-Air is released under [CC BY-NC-SA 4.0](http://creativecommons.org/licenses/by-nc-sa/4.0/). Don't commit the data (`data/` is git-ignored). Cite:
Fonder & Van Droogenbroeck, *Mid-Air: A multi-modal dataset for extremely low altitude drone flights*, CVPRW 2019.
