"""Durable queue and resource ownership, shared by processes on one host.

SQLite transactions serialize claims; a renewable lease detects interrupted work.
Queued work survives restarts. Interrupted running work fails visibly rather than
silently repeating exports. Use a shared broker for deployment across hosts.
"""

import json
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class QueueFull(ValueError):
    pass


class JobStore:
    def __init__(self, path: Path, retention=604800, capacity=4, lease_seconds=90):
        self.path = path
        self.retention = retention
        self.capacity = capacity
        self.lease_seconds = lease_seconds
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, kind TEXT NOT NULL,
                    payload TEXT NOT NULL, status TEXT NOT NULL, state TEXT NOT NULL,
                    created REAL NOT NULL, updated REAL NOT NULL, finished REAL,
                    lease TEXT, heartbeat REAL
                );
                CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status, created);
                CREATE TABLE IF NOT EXISTS resources (
                    kind TEXT NOT NULL, id TEXT NOT NULL, owner TEXT NOT NULL,
                    expires REAL NOT NULL, PRIMARY KEY(kind, id, owner)
                );
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def enqueue(self, owner, kind, payload, image_ids=()):
        now = time.time()
        ident = uuid.uuid4().hex
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._recover(db, now)
            count = db.execute(
                "SELECT count(*) FROM jobs WHERE status IN ('queued','running')"
            ).fetchone()[0]
            if count >= self.capacity:
                raise QueueFull(
                    "The generator is busy. Try again after a job finishes."
                )
            for image_id in image_ids:
                if not self._owns(db, "image", image_id, owner, now):
                    raise PermissionError(
                        "An image expired or belongs to another browser session. Upload it again."
                    )
                db.execute(
                    "UPDATE resources SET expires=? WHERE kind=? AND id=? AND owner=?",
                    (now + self.retention, "image", image_id, owner),
                )
            state = {
                "message": "Waiting for the generator…",
                "stage": "queued",
                "current": None,
                "total": None,
                "title": None,
            }
            db.execute(
                "INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ident,
                    owner,
                    kind,
                    json.dumps(payload),
                    "queued",
                    json.dumps(state),
                    now,
                    now,
                    None,
                    None,
                    None,
                ),
            )
        return ident

    def _recover(self, db, now):
        state = json.dumps(
            {
                "message": "The worker stopped before completion. Please submit again.",
                "stage": "interrupted",
            }
        )
        db.execute(
            "UPDATE jobs SET status='error',state=?,finished=?,updated=? WHERE status='running' AND heartbeat<?",
            (state, now, now, now - self.lease_seconds),
        )

    def claim(self):
        now = time.time()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._recover(db, now)
            # One active export across all local server processes, not one per process.
            if db.execute("SELECT 1 FROM jobs WHERE status='running'").fetchone():
                return None
            row = db.execute(
                "SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            lease = uuid.uuid4().hex
            db.execute(
                "UPDATE jobs SET status='running',lease=?,heartbeat=?,updated=? WHERE id=?",
                (lease, now, now, row["id"]),
            )
            return {**dict(row), "payload": json.loads(row["payload"]), "lease": lease}

    def heartbeat(self, ident, lease):
        with self.connection() as db:
            return (
                db.execute(
                    "UPDATE jobs SET heartbeat=? WHERE id=? AND lease=? AND status='running'",
                    (time.time(), ident, lease),
                ).rowcount
                == 1
            )

    def progress(self, ident, lease, details):
        state = (
            details
            if isinstance(details, dict)
            else {"message": details, "stage": "preparing"}
        )
        with self.connection() as db:
            changed = db.execute(
                "UPDATE jobs SET state=?,updated=? WHERE id=? AND lease=? AND status='running'",
                (json.dumps(state), time.time(), ident, lease),
            ).rowcount
        if not changed:
            raise RuntimeError("Job lease expired")

    def finish(self, job, result=None, error=None, resources=()):
        now = time.time()
        state = {"message": error or "Complete.", "stage": "error" if error else "done"}
        if error is None:
            state["result"] = result
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute(
                "UPDATE jobs SET status=?,state=?,finished=?,updated=?,payload='{}' WHERE id=? AND lease=? AND status='running'",
                (
                    "error" if error else "done",
                    json.dumps(state),
                    now,
                    now,
                    job["id"],
                    job["lease"],
                ),
            ).rowcount
            if changed and error is None:
                for kind, ident in resources:
                    self._grant(db, kind, ident, job["owner"], now)
            return bool(changed)

    def get(self, ident, owner):
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM jobs WHERE id=? AND owner=?", (ident, owner)
            ).fetchone()
        if row is None:
            return None
        return {
            **json.loads(row["state"]),
            "status": row["status"],
            "created_at": row["created"],
            "updated_at": row["updated"],
            "elapsed_seconds": round(
                (row["finished"] or time.time()) - row["created"], 1
            ),
            "seconds_since_update": round(time.time() - row["updated"], 1),
        }

    def _grant(self, db, kind, ident, owner, now):
        db.execute(
            "INSERT OR REPLACE INTO resources VALUES (?,?,?,?)",
            (kind, ident, owner, now + self.retention),
        )

    def grant(self, kind, ident, owner):
        with self.connection() as db:
            self._grant(db, kind, ident, owner, time.time())

    def save_image(self, owner, save):
        """Publish uploads under the expiry lock, avoiding deletion races."""
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute(
                "SELECT count(*) FROM resources WHERE kind='image' AND owner=? AND expires>?",
                (owner, time.time()),
            ).fetchone()[0]
            if count >= 24:
                raise QueueFull(
                    "This browser has reached its 24-image storage limit. Try again after older images expire."
                )
            record = save()
            self._grant(db, "image", record["id"], owner, time.time())
            return record

    @staticmethod
    def _owns(db, kind, ident, owner, now):
        return (
            db.execute(
                "SELECT 1 FROM resources WHERE kind=? AND id=? AND owner=? AND expires>?",
                (kind, ident, owner, now),
            ).fetchone()
            is not None
        )

    def owns(self, kind, ident, owner):
        with self.connection() as db:
            return self._owns(db, kind, ident, owner, time.time())

    def cleanup(self, output, assets):
        """Expire owned artifacts only; preserve source templates and legacy files.

        Skip resource deletion while work is pending, since its payload may refer
        to an image. The same write lock prevents enqueue/grant races.
        """
        now = time.time()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._recover(db, now)
            db.execute("DELETE FROM jobs WHERE finished<?", (now - self.retention,))
            if db.execute(
                "SELECT 1 FROM jobs WHERE status IN ('queued','running')"
            ).fetchone():
                return
            expired = db.execute(
                "SELECT DISTINCT kind,id FROM resources WHERE expires<=?", (now,)
            ).fetchall()
            for kind, ident in expired:
                if db.execute(
                    "SELECT 1 FROM resources WHERE kind=? AND id=? AND expires>?",
                    (kind, ident, now),
                ).fetchone():
                    continue
                paths = (
                    [output / (ident + suffix) for suffix in (".pptx", ".json")]
                    if kind == "deck"
                    else [
                        assets / (ident + suffix)
                        for suffix in (".img", ".metadata.json")
                    ]
                )
                for path in paths:
                    path.unlink(missing_ok=True)
            db.execute("DELETE FROM resources WHERE expires<=?", (now,))
            # Reap orphaned runtime files left by a crash before publication.
            for folder, kind, pattern in (
                (output, "deck", r"([a-f0-9]{32})\.(?:pptx|json|tmp)"),
                (assets, "image", r"([a-f0-9]{64})\.(?:img|metadata\.json|json)"),
            ):
                for path in folder.iterdir():
                    match = re.fullmatch(pattern, path.name)
                    if (
                        not match
                        or path.is_symlink()
                        or not path.is_file()
                        or path.stat().st_mtime > now - self.retention
                    ):
                        continue
                    if not db.execute(
                        "SELECT 1 FROM resources WHERE kind=? AND id=?",
                        (kind, match[1]),
                    ).fetchone():
                        path.unlink(missing_ok=True)
