# Local frontend/report validation

These checks use a local FastAPI server and explicitly synthetic JSON fixtures.
They do not run reconstruction, call Bedrock, or create AWS resources.

## Setup (Windows PowerShell, from the repository root)

```powershell
python -m venv .venv-report-test
.\.venv-report-test\Scripts\python.exe -m pip install -r backend/requirements.txt
cd frontend
npm ci
npm run build
npm run lint
$env:REPORT_TEST_PYTHON = (Resolve-Path ..\.venv-report-test\Scripts\python.exe).Path
npm run test:report
```

The browser test launches installed Microsoft Edge headlessly. Set
`REPORT_TEST_BROWSER=chrome` to use installed Chrome instead. It needs local
ports 8000 and 5173 free. It starts/stops its own servers and uses a temporary
output/upload directory; existing jobs are not used or modified.

For Linux/macOS, point `REPORT_TEST_PYTHON` to a Python environment containing
the backend dependencies and choose an installed supported browser channel.

## Checks

- Production frontend build succeeds.
- Lint reports no errors (existing warnings are not treated as a pass for code quality).
- Empty overview/anomaly screens render without uncaught browser errors.
- Selecting a small synthetic upload fixture reaches the real upload API.
  The fixture is not a decodable video and is never passed to reconstruction.
- The real viewer-file endpoint downloads the anomaly JSON for the selected
  fixture job; parsed content and suggested filename match exactly.
- Injected HTTP 404 and invalid-report responses show a visible download error;
  the button becomes usable again for retry.
- Selecting an unverified anomaly shows its no-supporting-frames state.
- A job without a pipeline report does not offer a bogus download.
- An injected scene HTTP 500 displays a report-loading error.

The test prints the temporary downloaded JSON path on success. The fixture
download is evidence of frontend/API integration, not reconstruction accuracy.

## Observed fixes

Build failures included unquoted CSS variables, invalid padding, missing JSX
braces/closing tags, and an invalid image `src` attribute. Report download
previously returned `null` synchronously and expected an embedded report from
an endpoint that actually lists artifact URLs. The corrected implementation
awaits the job's `anomaly_report.json`, checks HTTP/payload validity, and reports
failures in the UI. Report loading uses the same API base as the other screens.

Related smoke-test blockers fixed: undefined anomaly-selection setter,
null-anomaly access, a conditional measurement hook, and point-size setters
being called during render. Optional visual-assessment copy no longer claims
that Bedrock ran for every job.

## Limitations

No live drone reconstruction, AWS deployment, COOL benchmark, or model
inference is validated here. The production build still warns about bundle
size, and lint still reports warnings in existing UI code.

## Local result — 2026-10-25

- Node 22.19.0, Windows, installed Microsoft Edge, Vite 8.3.1 from the lockfile.
- `npm run build`: PASS (large-bundle warning remains).
- `npm run lint`: exit 0, no errors, 51 warnings remain.
- `npm run test:report`: all 8 checks PASS; no uncaught browser errors.
- `git diff --check`: PASS.
- `npm audit`: 3 high-severity findings in the existing dependency graph
  (`follow-redirects`, `source-map-js`, `vite`). These were also present after
  the initial `npm ci`; this frontend patch does not resolve them.

The download comparison used the actual FastAPI file endpoint. HTTP failure
and malformed-payload cases were injected by Playwright and are explicitly
test scenarios, not live service failures.
