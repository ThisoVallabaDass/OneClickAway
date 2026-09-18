import re
import threading
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.job_store import JobStore
from backend.worker import Worker
import hashlib
from backend.planner import sections, plan_deck
from backend.models import DeckPlan
from backend.exporter import generate_deck
from backend.ooxml import NS, parse
from backend.richtext import plain_text
from backend.variants import variant_spec

SOURCE = Path(__file__).parent / "fixtures/aws-java-300.txt"


def rendered_text(archive, part):
    """Slide text with runs joined inside each paragraph, as a reader sees it."""
    root = parse(archive.read(part))
    return " ".join(
        "".join(p.xpath(".//a:t/text()", namespaces=NS))
        for p in root.findall(".//a:p", NS)
    )


class LongContentTests(unittest.TestCase):
    def test_all_300_statements_survive_long_deck(self):
        content = SOURCE.read_text(encoding="utf8")
        # One '###' document title plus fifteen '**Part n**' headings: the title ranks above
        # the parts, so the parts become the slide-title level and no divider is invented.
        self.assertEqual(len(sections(content, "AWS")), 15)
        self.assertTrue(all(s["role"] == "slide" for s in sections(content, "AWS")))
        events = []
        with patch("backend.planner.search", return_value=[]):
            raw = plan_deck(
                "AWS + Java Backend",
                content,
                use_ai=False,
                design={"agenda": False, "complete_story": False},
                progress=events.append,
            )
        self.assertEqual(len(raw["slides"]), 62)
        slides = [
            s for s in raw["slides"] if s["kind"] not in ("agenda", "cover", "closing")
        ]
        supplied = [
            re.sub(r"^\d+\.\s+", "", line)
            for line in content.splitlines()
            if re.match(r"^\d+\. ", line)
        ]
        self.assertEqual(len(supplied), 300)
        self.assertEqual(
            " ".join(supplied).split(),
            " ".join(item for s in slides for item in s["items"]).split(),
        )
        identities = [(s["template"]["id"], s["layout_variant"]) for s in raw["slides"]]
        self.assertTrue(all(s["layout_variant"] is None for s in raw["slides"]))
        self.assertTrue(any("reused" in w for w in raw["warnings"]))
        self.assertFalse(
            any(s["diagram"] for s in slides),
            "Architecture facts must not become an invented sequential pipeline",
        )
        plan = DeckPlan.model_validate(raw)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "aws.pptx"
            generate_deck(plan, path, progress=events.append)
            with ZipFile(path) as z:
                text = " ".join(
                    rendered_text(z, f"ppt/slides/generated{i + 1}.xml")
                    for i, s in enumerate(raw["slides"])
                    if s["kind"] not in ("agenda", "cover", "closing")
                )
                text = " ".join(text.split())
                # Markdown delimiters are formatting, so compare the wording they carry.
                for statement in supplied:
                    self.assertIn(" ".join(plain_text(statement).split()), text)
        for stage in ("layout", "export"):
            updates = [e for e in events if isinstance(e, dict) and e["stage"] == stage]
            self.assertTrue(updates)
            self.assertTrue(
                all(
                    e["current"] and e["total"] == len(raw["slides"]) and e["title"]
                    for e in updates
                )
            )
        self.assertTrue(
            any(isinstance(e, dict) and e["stage"] == "validation" for e in events)
        )

    def test_job_reports_current_work_and_completes(self):
        gate = threading.Event()
        ready = threading.Event()

        def work(job, progress):
            progress(
                dict(
                    message="Measuring text",
                    stage="layout",
                    current=8,
                    total=65,
                    title="IAM & Security",
                )
            )
            ready.set()
            gate.wait(5)
            return {"ok": True}, []

        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp) / "jobs.sqlite3")
            app = create_app(store, start_worker=False)
            with TestClient(app) as client:
                client.get("/")
                owner = hashlib.sha256(
                    client.cookies["studio_session"].encode()
                ).hexdigest()
                ident = store.enqueue(owner, "plan", {})
                worker = Worker(store, work)
                worker.start()
                try:
                    self.assertTrue(ready.wait(3))
                    response = client.get("/api/jobs/" + ident).json()
                    self.assertEqual(response["status"], "running")
                    self.assertEqual(response["current"], 8)
                    self.assertEqual(response["title"], "IAM & Security")
                    self.assertGreaterEqual(response["elapsed_seconds"], 0)
                    self.assertIn("seconds_since_update", response)
                finally:
                    gate.set()
                    worker.stop()
                self.assertEqual(store.get(ident, owner)["status"], "done")

    def test_variants_measure_all_font_pairs(self):
        items = ["Security: Keep credentials outside application source code."] * 6
        for style in ("modern", "corporate", "editorial"):
            for code in (
                "v000",
                "v001",
                "v002",
                "v003",
                "v004",
                "v005",
                "v024",
                "v048",
            ):
                spec = variant_spec(code, "AWS and Java", items, style)
                self.assertTrue(all(size >= 16 for size in spec["sizes"]))


if __name__ == "__main__":
    unittest.main()
