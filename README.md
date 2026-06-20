# Scrooge

"한정된 AI 크레딧으로 더 많은 일을."

Scrooge is a local-first AI efficiency layer for internal developer workflows. It optimizes prompts, compresses noisy context, estimates token and cost impact, and records auditable usage metadata without changing the user's core AI workflow.

## MVP Capabilities

- FastAPI backend with local proxy, prompt optimization, token metering, pricing registry, SQLite usage collection, and dashboard summaries.
- Tauri + React frontend skeleton for a Windows tray-style desktop app, optimizer preview, token meter, and efficiency dashboard.
- Trust-first preview flow: original prompt, optimized prompt, reduction estimate, applied rules, and pricing version are visible before approval.
- Local-first audit storage: prompt bodies are not stored by default; hashes, token counts, task type, rule IDs, pricing version, and approval state are stored.
- Low-setup desktop flow: focus an AI input and press `Ctrl+Alt+S` to select, optimize, paste back, and record hotkey telemetry.
- Reliability metrics: Scrooge separates short prompt preservation, long-context savings, measured token coverage, hotkey success, and re-ask rate.

## Repository Layout

```text
backend/        FastAPI service, optimizer, compressor, pricing, storage, tests
frontend/       Tauri + React + TypeScript desktop UI
docs/           Architecture and trust model notes
```

## Backend Development

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn scrooge.main:app --reload --port 8750
```

## Frontend Development

```powershell
cd frontend
npm install
npm run dev
```

For desktop packaging:

```powershell
cd frontend
npm run tauri:dev
```

## Windows Install Smoke

Scrooge packages the FastAPI backend as a Tauri sidecar. Build the backend
sidecar before running a Tauri installer build:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_backend_sidecar.ps1 -TargetTriple aarch64-pc-windows-msvc
cd frontend
npm run tauri:build
```

On Windows ARM64, native Tauri packaging also requires Rust and the Visual
Studio C++ ARM64 build tools. The backend sidecar can be smoke-tested without a
Python runtime by running the generated `frontend/src-tauri/binaries` executable
and checking `GET http://127.0.0.1:8750/health`.

Run the reliability gate against a running backend:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify_install_smoke.ps1 -ApiBase http://127.0.0.1:8750
```

Run the broader API smoke or soak matrix:

```powershell
cd backend
.\.venv\Scripts\python.exe tools\run_smoke_matrix.py --api http://127.0.0.1:8750 --mode smoke
.\.venv\Scripts\python.exe tools\run_smoke_matrix.py --api http://127.0.0.1:8750 --mode soak --duration-sec 14400 --interval-sec 30
```

## API Sketch

- `POST /api/optimize`: analyze and optimize a prompt for preview.
- `POST /api/approvals/{request_id}/approve`: mark an optimized request as approved.
- `POST /proxy/{provider}/{path:path}`: capture proxy metadata and optionally forward to an upstream provider.
- `GET /api/dashboard/summary`: return usage and savings summary.
- `GET /api/dashboard/category-summary`: return task-type savings and token error summary.
- `GET /api/runtime/status`: return backend/database runtime status for installed-app checks.
- `GET /api/pricing`: return active pricing registry.

## Trust Model

Scrooge separates estimated, sent, and measured usage. Cost savings are shown as estimates unless upstream usage data is available. Pricing data is versioned and references official provider pricing pages so internal users can audit how cost projections were calculated. Short prompts are allowed to produce zero savings when preserving meaning is safer; long logs, diffs, traces, and command output are evaluated against stricter savings targets.

## Git Milestones

The intended implementation milestones are:

1. `chore: initialize scrooge repository`
2. `feat: add local proxy and request capture baseline`
3. `feat: add prompt optimizer preview flow`
4. `feat: add token meter and pricing registry`
5. `feat: add sqlite usage storage and dashboard`
6. `test: add optimizer quality and cost reliability checks`
