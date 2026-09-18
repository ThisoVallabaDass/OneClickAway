# OneClick-Away

Create editable PowerPoint presentations from reviewed content using the KaarTech
layout collection. Includes a browser editor, fitted text, tables, diagrams,
pictures, and a manual ChatGPT/Claude/Gemini prompt workflow. Optional Ollama
classification preserves your supplied body text.

## Quick start

Requires Python 3.12. Node is only used for development checks.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/setup.py --template "C:\path\to\kaartech.pptx" --lexical
python scripts/run.py
```

Open http://127.0.0.1:8765. Windows users can also use `start.bat`.
The original template is required separately and is not included in Git. The
renderer is configured for that specific collection; arbitrary PPTX files are
not interchangeable. PowerPoint is not required for generation.

## Structure

| Location | Responsibility |
| --- | --- |
| `backend/app.py`, `routes.py` | Application lifecycle and HTTP endpoints |
| `backend/job_store.py`, `worker.py` | Durable jobs, ownership, recovery and expiry |
| `backend/middleware.py` | Streaming request limits and browser sessions |
| `backend/planner.py`, `template_engine.py` | Content planning and layout selection |
| `backend/presentation/` | Drawing, slide rendering and package validation |
| `backend/exporter.py` | Export orchestration and stable Python entry point |
| `static/app.js`, `static/js/` | Editor, API, AI workflow, previews and storyboard |
| `tests/`, `scripts/`, `docs/` | Regression tests, setup tools and documentation |

## Reliability

- Queued jobs and results survive restarts in SQLite. Atomic claims serialize
  generation across processes sharing the same local disk.
- Running jobs renew a lease. Lost workers are detected after 90 seconds and
  reported as interrupted; queued jobs resume automatically.
- HttpOnly browser cookies isolate jobs, images and downloads. This is anonymous
  ownership, not account login. Clearing cookies loses access to old resources.
- Request limits apply before parsing, including uploads without Content-Length.
- New runtime files expire after seven days. Cleanup runs every five minutes
  while idle and preserves images needed by pending jobs.
- Source templates and historical outputs outside runtime directories are retained.
  Old images must be uploaded again to establish session ownership.
- Unexpected failures produce operator logs with job IDs and tracebacks instead
  of exposing server paths in browser errors.

## Verification

```powershell
python -m pip install -r requirements-dev.txt
python -m ruff check backend
python -m ruff format --check backend scripts tests
python -m unittest discover -s tests
npm ci
npm run check
```

Full generation tests require the template and catalog. CI runs the independent
service tests with `python -m unittest discover -s tests -p test_service.py`.
For browser checks, start the app and run `python tests/ui_smoke.py` with Chrome
installed. Set `STUDIO_TEST_URL` to use a separate local test server.

See [Deployment](docs/DEPLOYMENT.md), [Architecture](ARCHITECTURE.md),
[Contributing](docs/CONTRIBUTING.md), and [User guide](docs/USER_GUIDE.md).

Templates, databases, uploads, outputs, `.env`, and build artifacts are excluded
from Git. Company branding remains in the frontend; publish only with the
appropriate rights. No software license has been selected for this repository.
