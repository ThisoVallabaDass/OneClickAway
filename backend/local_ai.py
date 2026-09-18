import json
import urllib.request
import urllib.error
from .config import OLLAMA_URL, CHAT_MODEL, EMBED_MODEL


def request(endpoint, payload=None, timeout=180):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        OLLAMA_URL + endpoint, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def status():
    try:
        models = [x["name"] for x in request("/api/tags", timeout=3).get("models", [])]
        return {
            "available": True,
            "models": models,
            "chat_model": CHAT_MODEL,
            "embedding_model": EMBED_MODEL,
            "chat_ready": CHAT_MODEL in models,
            "embedding_ready": EMBED_MODEL in models,
        }
    except (OSError, ValueError):
        return {
            "available": False,
            "models": [],
            "chat_model": CHAT_MODEL,
            "embedding_model": EMBED_MODEL,
            "chat_ready": False,
            "embedding_ready": False,
        }


def embed(texts):
    return request(
        "/api/embed", {"model": EMBED_MODEL, "input": texts, "truncate": True}
    )["embeddings"]


def chat(system, payload):
    result = request(
        "/api/chat",
        {
            "model": CHAT_MODEL,
            "stream": False,
            "think": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 3000},
        },
        timeout=240,
    )
    return json.loads(result["message"]["content"])
