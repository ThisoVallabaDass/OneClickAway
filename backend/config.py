import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv("STUDIO_DATA_DIR", str(ROOT / "data")))
OUTPUT = Path(os.getenv("STUDIO_OUTPUT_DIR", str(ROOT / "output")))
DATA.mkdir(parents=True, exist_ok=True)
OUTPUT.mkdir(parents=True, exist_ok=True)
GENERATED = OUTPUT / "generated"
GENERATED.mkdir(parents=True, exist_ok=True)
TEMPLATE = Path(os.getenv("KAARTECH_TEMPLATE", str(DATA / "kaartech.pptx")))
DB = DATA / "templates.sqlite3"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen3:1.7b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text:latest")
JOBS_DB = DATA / "jobs.sqlite3"
ALLOWED_HOSTS = os.getenv(
    "STUDIO_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver"
).split(",")
ALLOWED_ORIGINS = os.getenv(
    "STUDIO_ALLOWED_ORIGINS", "http://127.0.0.1:8765,http://localhost:8765"
).split(",")
SECURE_COOKIES = os.getenv("STUDIO_SECURE_COOKIES", "false").lower() == "true"
RETENTION_SECONDS = max(3600, int(os.getenv("STUDIO_RETENTION_HOURS", "168")) * 3600)
MAX_PENDING_JOBS = max(1, int(os.getenv("STUDIO_MAX_PENDING_JOBS", "4")))
