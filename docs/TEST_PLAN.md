# FlightPrint Test Plan (M6 — Testing)

Owner: Chillsidealways (Lidiya). Status: living document; results are recorded only
from actual runs, never invented.

## 1. Environment / setup

```bash
pip install -r requirements.txt
python -c "import cv2; print(cv2.__version__)"   # expect 5.x
python -m pytest tests/ -v
```

Pass criteria: `tests/test_evidence.py`, `tests/test_midair_adapter.py` and
`tests/test_modes.py` all pass on the machine under test. OpenCV major version
must be 5 (competition rule).

## 2. Mid-Air test data

See `tools/README.md` ("Test-data layout & outputs" section) for where the
dataset belongs and how to convert one trajectory. Do NOT commit data (`data/`
is git-ignored). The adapter's conversion helpers are covered by
`tests/test_midair_adapter.py` (no dataset needed). Conversion of a real
trajectory is a manual step; record date, climate, trajectory id and output
hashes in the bug/test log when done.

## 3. Stage 1–9 testing

| Stages | How | Expected outputs (under the job output dir) |
|---|---|---|
| 1–4 | `python -m pipeline.cli --video <mp4> --metadata <json> --output <out> --stages 1 2 3 4` | frames/, camera params, matches, poses; log reports `Reconstruction mode: full` on Mid-Air input |
| 5–8 | Same CLI, `--stages 5 6 7 8` | dense cloud, mesh, georeferenced outputs, filtered cloud |
| 9 (geometry only) | `--stages 9` (Bedrock off by default) | `anomaly_report.json` (`schema_version: 2`), `evidence/` crops |
| 9 (with Bedrock) | Add `--bedrock` (see §4) | Same as above plus `visual_assessment` on up to 10 top anomalies |

Unit coverage for Stage 9 geometry/evidence/confidence lives in
`tests/test_evidence.py` (synthetic scene, no dataset or AWS needed).

## 4. Bedrock testing

Bedrock is OFF by default (`use_bedrock: False`) so nobody is billed by accident.
Three equivalent ways to enable it for one run (explicit config wins over env):

```bash
# a) CLI flag (plus optional model/region/cap overrides)
python -m pipeline.cli --video <mp4> --metadata <json> --output <out> --bedrock

# b) Config JSON
# {"stage9": {"use_bedrock": true}}
python -m pipeline.cli --video <mp4> --metadata <json> --output <out> --config bedrock.json

# c) Environment (plus model/region)
FLIGHTPRINT_USE_BEDROCK=1 BEDROCK_MODEL_ID=amazon.nova-pro-v1:0 AWS_REGION=us-east-1 \
  python -m pipeline.cli --video <mp4> --metadata <json> --output <out> --stages 9
```

Model/region defaults: `BEDROCK_MODEL_ID=amazon.nova-pro-v1:0`, `AWS_REGION=us-east-1`.
Cost cap: only the top-`max_bedrock_anomalies` (default 10) anomalies are checked;
the run logs `Bedrock visual check on top-N anomalies (model=...)`.

Unit coverage (mock client, clearly labelled): `test_bedrock_*` in
`tests/test_evidence.py` covers JSON-only replies, JSON-in-prose, malformed
responses, missing fields, invalid labels, invalid confidence, missing crop
files, env/explicit precedence, and the confidence blend. These do NOT count as
a real Bedrock test.

A REAL Bedrock test requires AWS credentials + model access and at least one
real evidence crop. Until it is performed, Oct 4 stays PARTIAL. Record model,
region, input crop, output location, response validity and any prompt changes
in `docs/BUG_LOG.md` when it happens.

## 5. Expected outputs (per job output dir)

- `anomaly_report.json` — `schema_version: 2`, `total_anomalies`,
  `verified_anomalies`, per-anomaly `id`, `signal_strength`, `supporting_frames`
  (`frame_index`, `timestamp`, `pixel`, `depth`, `crop_path`),
  `view_angle_spread_deg`, `confidence`, `confidence_factors`
  (`signal`, `views`, `diversity`, `points`, plus `visual` after a Bedrock
  check), `evidence_level`, and `visual_assessment` (`label`, `description`,
  `confidence`, `model`) when the visual check succeeded.
- `evidence/` — JPEG crops with a red ring at the finding (`<anom>_f<frame>.jpg`).
- `progress.json`, `pipeline_report.json`, stage artefacts (frames, clouds, mesh).

## 6. Pass / fail criteria

- Geometry: `verified_anomalies / total_anomalies` reported; every verified
  anomaly has ≥1 existing `crop_path`; every unverified anomaly has
  `confidence ≤ 0.30` and `evidence_level: unverified`.
- Confidence blend (after a successful visual check): equals
  `0.75 * prior + 0.25 * visual_support` (±0.001), where visual support is the
  model confidence for labels other than `none`, else `1 - confidence`.
- Bedrock failure safety: a failed check records `visual_assessment_error` on
  that anomaly only; the geometric result and its confidence are preserved and
  the pipeline still completes.
- No OpenAI/GPT-4o code paths in Stage 9 (grep must show only Bedrock/boto3).

## 7. Evidence validation

For each verified anomaly: open the saved crop, confirm the ring marks a real
structure (not sky/edge artefact), and confirm the reported `frame_index` /
`pixel` projects inside that frame. Occlusion is a known limitation (see
`docs/BUG_LOG.md`): a supporting frame may show a wall in front of the point;
the crop makes this visible by design.

## 8. API / frontend integration checks (deferred)

Upload → run → status → results → viewer scene with evidence frames. Not part
of Oct 4 scope; tracked for Phase 3 integration. Known gap: the anomaly panel
does not render evidence thumbnails yet (see `docs/BUG_LOG.md`).
