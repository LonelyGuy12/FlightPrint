# FlightPrint — Deck Outline (M6, ~8 slides, 5 min)

1. **Title** — FlightPrint: one drone pass → 3D model + provable findings.
   Team, roles, OpenCV 5 + AWS badges.
2. **Problem** — single-pass surveys produce footage nobody has time to review;
   damage hides in hours of video; existing tools don't cite their sources.
3. **Pipeline** — 9 stages diagram (upload → frames → poses → cloud → mesh →
   georef → AI → viewer). Modes: FULL / SCALE_ASSISTED / VISION_ONLY.
4. **Evidence-first AI (M2)** — project finding → frames → ranked crops;
   YOLO fusion; Bedrock visual check. Show a real crop + `confidence_factors`.
5. **Confidence, honestly** — formula on one slide; unverified capped at 0.30;
   "the system tells you when it can't prove it."
6. **Validation** — 47 tests; real run numbers (31 s, 2/2 verified, 15 YOLO
   detections); Mid-Air + Bedrock-live marked PENDING with dates, not faked.
7. **AWS** — S3 job layout, Bedrock Nova Pro us-east-1, compute decision,
   cost caps (top-10 Bedrock, billing alarm).
8. **Demo + reproduce** — live viewer (or recorded fallback), repo + TEST_PLAN
   links, "one pass in, provable findings out."

Speaker notes: keep to measured numbers only; brackets in `docs/write-up.md`
must be filled before presenting. Backup slide: occlusion limitation + crops
that expose it.
