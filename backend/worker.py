"""Background execution of serializable, durable jobs."""

import logging
import threading
import time
import uuid

from .config import GENERATED as OUTPUT
from .images import ASSETS
from .models import DeckPlan

logger = logging.getLogger(__name__)


def execute(job, progress):
    if job["kind"] == "plan":
        from .planner import plan_deck

        result = plan_deck(**job["payload"], progress=progress)
        images = [
            ("image", s["image"]["id"]) for s in result["slides"] if s.get("image")
        ]
        return result, images
    if job["kind"] == "generate":
        from .exporter import generate_deck

        plan = DeckPlan.model_validate(job["payload"])
        ident = uuid.uuid4().hex
        path = OUTPUT / (ident + ".pptx")
        try:
            result = generate_deck(plan, path, progress=progress)
            (OUTPUT / (ident + ".json")).write_text(
                plan.model_dump_json(indent=2), encoding="utf-8"
            )
        except Exception:
            path.unlink(missing_ok=True)
            (OUTPUT / (ident + ".json")).unlink(missing_ok=True)
            raise
        return {
            "download": "/api/download/" + ident,
            "outline": plan.model_dump(),
            **result,
        }, [("deck", ident)]
    raise ValueError("Unknown job type")


class Worker:
    def __init__(self, store, handler=execute):
        self.store = store
        self.handler = handler
        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=self.run, name="presentation-worker", daemon=True
        )

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=5)

    def run(self):
        next_cleanup = 0
        while not self.stop_event.is_set():
            try:
                if time.monotonic() >= next_cleanup:
                    self.store.cleanup(OUTPUT, ASSETS)
                    next_cleanup = time.monotonic() + 300
                job = self.store.claim()
                if job:
                    self.process(job)
                    continue
            except Exception:
                logger.exception(
                    "Worker loop failed", extra={"event": "worker_loop_failed"}
                )
            self.stop_event.wait(0.5)

    def process(self, job):
        done = threading.Event()

        def renew():
            while not done.wait(max(0.1, self.store.lease_seconds / 3)):
                try:
                    if not self.store.heartbeat(job["id"], job["lease"]):
                        return
                except Exception:
                    logger.exception("Heartbeat failed", extra={"job_id": job["id"]})

        pulse = threading.Thread(target=renew, daemon=True)
        pulse.start()
        try:
            result, resources = self.handler(
                job,
                lambda details: self.store.progress(job["id"], job["lease"], details),
            )
            if not self.store.finish(job, result=result, resources=resources):
                # A stale worker cannot publish files after losing its lease.
                for kind, ident in resources:
                    if kind == "deck":
                        for suffix in (".pptx", ".json"):
                            (OUTPUT / (ident + suffix)).unlink(missing_ok=True)
            logger.info(
                "Job completed", extra={"job_id": job["id"], "event": "job_completed"}
            )
        except Exception as exc:
            logger.exception(
                "Job failed", extra={"job_id": job["id"], "event": "job_failed"}
            )
            message = (
                str(exc)
                if isinstance(exc, ValueError)
                else "Generation failed. Please try again or contact the operator with job ID "
                + job["id"]
                + "."
            )
            self.store.finish(job, error=message)
        finally:
            done.set()
            pulse.join(timeout=1)
