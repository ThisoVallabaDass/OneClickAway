"""Public-service boundaries, durable queue recovery and retention regressions."""

import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.job_store import JobStore, QueueFull
from backend.middleware import RequestLimit
from backend.worker import Worker


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = JobStore(self.root / "jobs.sqlite3")
        self.output = self.root / "generated"
        self.assets = self.root / "uploads"
        self.output.mkdir()
        self.assets.mkdir()

    def client(self):
        client = TestClient(create_app(self.store, start_worker=False))
        client.get("/")
        return client

    def owner(self, client):
        return hashlib.sha256(client.cookies["studio_session"].encode()).hexdigest()

    def test_queue_survives_restart_and_result_is_shared(self):
        ident = self.store.enqueue("owner", "plan", {"topic": "Hello"})
        restarted = JobStore(self.store.path)
        job = restarted.claim()
        self.assertEqual(job["payload"]["topic"], "Hello")
        restarted.finish(job, result={"ok": True})
        self.assertEqual(self.store.get(ident, "owner")["result"], {"ok": True})

    def test_processes_cannot_claim_same_job(self):
        self.store.enqueue("owner", "plan", {})
        code = "import sys,json;from pathlib import Path;from backend.job_store import JobStore;print(json.dumps(JobStore(Path(sys.argv[1])).claim()))"
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", code, str(self.store.path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(2)
        ]
        results = []
        for proc in procs:
            out, err = proc.communicate(timeout=15)
            self.assertEqual(proc.returncode, 0, err)
            results.append(json.loads(out))
        self.assertEqual(sum(r is not None for r in results), 1)

    def test_stale_worker_fails_and_cannot_publish(self):
        ident = self.store.enqueue("owner", "plan", {})
        job = self.store.claim()
        with self.store.connection() as db:
            db.execute("UPDATE jobs SET heartbeat=0 WHERE id=?", (ident,))
        self.assertIsNone(JobStore(self.store.path).claim())
        self.assertEqual(self.store.get(ident, "owner")["status"], "error")
        self.assertFalse(
            self.store.finish(job, result={}, resources=[("deck", "a" * 32)])
        )
        self.assertFalse(self.store.owns("deck", "a" * 32, "owner"))

    def test_capacity_is_shared(self):
        for _ in range(4):
            self.store.enqueue("owner", "plan", {})
        with self.assertRaises(QueueFull):
            JobStore(self.store.path).enqueue("another", "plan", {})

    def test_another_session_cannot_poll_download_or_reuse_image(self):
        alice, bob = self.client(), self.client()
        owner = self.owner(alice)
        ident = self.store.enqueue(owner, "plan", {})
        self.assertEqual(alice.get("/api/jobs/" + ident).status_code, 200)
        self.assertEqual(bob.get("/api/jobs/" + ident).status_code, 404)
        image_id = "a" * 64
        self.store.grant("image", image_id, owner)
        with self.assertRaises(PermissionError):
            self.store.enqueue(self.owner(bob), "generate", {}, [image_id])
        self.assertEqual(bob.get("/api/images/" + image_id).status_code, 404)
        deck_id = "b" * 32
        self.store.grant("deck", deck_id, owner)
        (self.output / (deck_id + ".pptx")).write_bytes(b"example")
        with patch("backend.routes.OUTPUT", self.output):
            self.assertEqual(alice.get("/api/download/" + deck_id).status_code, 200)
            self.assertEqual(bob.get("/api/download/" + deck_id).status_code, 404)

    def test_browser_cookie_and_cross_origin(self):
        client = self.client()
        response = TestClient(create_app(self.store, False)).get("/")
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("SameSite=Strict", response.headers["set-cookie"])
        r = client.post(
            "/api/ai/prompt",
            json={"provider": "chatgpt", "topic": "Hello"},
            headers={"origin": "https://untrusted.example"},
        )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(
            client.get("/api/jobs/missing").headers["cache-control"], "no-store"
        )

    def test_stream_limit_stops_reading_before_route(self):
        calls = []
        chunks = iter(
            [
                {"type": "http.request", "body": b"a" * 600000, "more_body": True},
                {"type": "http.request", "body": b"b" * 600000, "more_body": True},
            ]
        )

        async def receive():
            calls.append("read")
            return next(chunks)  # Fails if middleware tries to drain more data.

        async def endpoint(*args):
            self.fail("Oversized body reached the application")

        sent = []

        async def send(message):
            sent.append(message)

        asyncio.run(
            RequestLimit(endpoint)(
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/api/generate",
                    "headers": [],
                },
                receive,
                send,
            )
        )
        self.assertEqual(sent[0]["status"], 413)
        self.assertEqual(len(calls), 2)

    def test_declared_oversize_rejected_without_reading(self):
        async def never(*args):
            self.fail("Request was read or dispatched")

        sent = []

        async def send(message):
            sent.append(message)

        asyncio.run(
            RequestLimit(never)(
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/api/plan",
                    "headers": [(b"content-length", b"1000001")],
                },
                never,
                send,
            )
        )
        self.assertEqual(sent[0]["status"], 413)

    def test_cleanup_preserves_shared_images_and_pending_work(self):
        ident = "c" * 64
        path = self.assets / (ident + ".img")
        path.write_bytes(b"image")
        self.store.grant("image", ident, "alice")
        self.store.grant("image", ident, "bob")
        with self.store.connection() as db:
            db.execute("UPDATE resources SET expires=0 WHERE owner='alice'")
        self.store.cleanup(self.output, self.assets)
        self.assertTrue(path.exists())
        pending = self.store.enqueue("bob", "plan", {}, [ident])
        with self.store.connection() as db:
            db.execute("UPDATE resources SET expires=0")
        self.store.cleanup(self.output, self.assets)
        self.assertTrue(path.exists())
        job = self.store.claim()
        self.assertEqual(job["id"], pending)
        self.store.finish(job, result={})
        self.store.cleanup(self.output, self.assets)
        self.assertFalse(path.exists())

    def test_cleanup_reaps_crash_orphans_not_reference_files(self):
        orphan = self.output / ("d" * 32 + ".tmp")
        reference = self.output / "reference.pptx"
        for path in (orphan, reference):
            path.write_bytes(b"x")
            os.utime(path, (0, 0))
        self.store.cleanup(self.output, self.assets)
        self.assertFalse(orphan.exists())
        self.assertTrue(reference.exists())

    def test_unexpected_error_logs_traceback_without_exposing_path(self):
        ident = self.store.enqueue("owner", "generate", {})

        def fail(job, progress):
            raise OSError("/private/server/path failed")

        with self.assertLogs("backend.worker", level="ERROR") as logs:
            Worker(self.store, fail).process(self.store.claim())
        self.assertIn("Traceback", "\n".join(logs.output))
        result = self.store.get(ident, "owner")
        self.assertEqual(result["status"], "error")
        self.assertNotIn("/private/", result["message"])
        self.assertIn(ident, result["message"])


if __name__ == "__main__":
    unittest.main()
