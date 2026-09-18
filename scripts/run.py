import sys
import webbrowser
import threading
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import uvicorn
    from backend.config import TEMPLATE
except ImportError:
    raise SystemExit(
        "Install the free dependencies first: python -m pip install -r requirements.txt"
    )

URL = "http://127.0.0.1:8765"
if not TEMPLATE.exists():
    raise SystemExit(
        'Template missing. Run: python scripts/setup.py --template "path/to/company.pptx"'
    )
try:
    with urllib.request.urlopen(URL + "/api/health", timeout=2) as response:
        if response.status == 200:
            webbrowser.open(URL)
            raise SystemExit(0)
except OSError:
    pass


def open_when_ready():
    import time

    for _ in range(30):
        try:
            with urllib.request.urlopen(URL + "/api/health", timeout=2) as response:
                if response.status == 200:
                    webbrowser.open(URL)
                    return
        except OSError:
            time.sleep(0.5)


threading.Thread(target=open_when_ready, daemon=True).start()
uvicorn.run("backend.app:app", host="127.0.0.1", port=8765)
