# Deployment

Run one FastAPI service with a same-origin frontend. No model API key is required
for the manual AI workflow. Configure environment variables in your shell or host
dashboard; `.env.example` is a reference and is not loaded automatically by Python.

| Variable | Default / purpose |
| --- | --- |
| `STUDIO_DATA_DIR` | `data/`: catalog, jobs database and uploads |
| `STUDIO_OUTPUT_DIR` | `output/`: service files go under `generated/` |
| `KAARTECH_TEMPLATE` | `<data>/kaartech.pptx`: original template |
| `STUDIO_ALLOWED_HOSTS` | `127.0.0.1,localhost,testserver`: comma-separated hostnames |
| `STUDIO_ALLOWED_ORIGINS` | Local port 8765 origins; exact comma-separated origins |
| `STUDIO_SECURE_COOKIES` | `false` locally; use `true` for public HTTPS |
| `STUDIO_RETENTION_HOURS` | `168`, minimum one hour |
| `STUDIO_MAX_PENDING_JOBS` | `4`, shared queue capacity |
| `OLLAMA_URL` | Optional Ollama endpoint, default loopback port 11434 |
| `CHAT_MODEL`, `EMBED_MODEL` | Optional installed Ollama model names |

Set your actual public hostname and HTTPS origin. Use HTTPS and configure proxy
upload limits/timeouts. Do not use wildcard origins. Persist both data and output.
Provision the private template separately from Git.

```bash
pip install -r requirements.txt
python scripts/setup.py --template /private/kaartech.pptx --lexical
uvicorn backend.app:app --host 0.0.0.0 --port 8765
```

Use your hosting platform's required port. `/api/live` is a lightweight liveness
probe; `/api/ready` reports 503 if the template is missing. `/api/health` includes
optional AI/catalog information for the UI.

## Docker

```bash
docker build -t oneclick-away .
docker volume create oneclick-away-data
docker run --rm -p 8765:8765 --env-file .env \
  -v oneclick-away-data:/var/lib/oneclick-away \
  -v /absolute/path/kaartech.pptx:/templates/kaartech.pptx:ro \
  -e KAARTECH_TEMPLATE=/templates/kaartech.pptx oneclick-away
```

Before first use, run the same image with the same volume/template mounts and
command `python scripts/setup.py --template /templates/kaartech.pptx --lexical`.
The image uses Linux fallback fonts. To match Windows typography, provision
appropriately licensed fonts through `PPT_FONT_DIR` and review generated slides.

## Operating boundaries

- SQLite coordination supports processes on one host and local persistent disk.
  Do not use a network filesystem or independent replicas. Multi-host deployment
  needs a shared queue/database and object storage.
- Generation is serialized to bound CPU/memory use. Interrupted work is marked
  failed, not retried automatically; the user can submit it again.
- Anonymous sessions isolate resources but do not verify identity. Use an
  identity-aware proxy if only approved users should access the application.
- Queue capacity and the 24-image browser-session limit are basic controls.
  Add IP/client rate limits at the public proxy for unrestricted deployments.
- Cleanup waits for idle periods. Monitor storage on continuously busy instances.
  Expired resource links stop authorizing access before physical cleanup.
- Back up the template and catalog. Runtime files are temporary, not a permanent
  user document archive. Existing historical output files are not auto-deleted.
