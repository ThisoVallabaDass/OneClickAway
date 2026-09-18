import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
from fastapi.testclient import TestClient
from backend.app import app
from backend.catalog import stats, search, get_layout
from backend.planner import chunks, plan_deck, template_ref
from backend.models import DeckPlan
from backend.exporter import generate_deck, validate_package
from backend.ooxml import parse, NS


class GeneratorTests(unittest.TestCase):
    def test_entire_template_indexed(self):
        s = stats()
        self.assertEqual(s["slides"], 187)
        self.assertEqual(s["layouts"], 183)
        self.assertEqual(s["documents"], 370)

    def test_all_original_numbers(self):
        from backend.catalog import connect

        with connect() as con:
            ids = {r[0] for r in con.execute("SELECT id FROM documents")}
        self.assertTrue(all(f"KTC-S{i:03}" in ids for i in range(1, 188)))

    def test_long_content_preserves_words_and_numbers(self):
        text = " ".join(f"Item{i} saves {i}.25 hours." for i in range(85))
        result = chunks("# Results\n" + text, "Results")
        rebuilt = " ".join(item for s in result for item in s["items"])
        self.assertEqual(rebuilt.split(), text.split())
        self.assertGreater(len(result), 3)

    def test_heading_classification(self):
        result = chunks(
            "# Pilot roadmap\nDiscovery: Choose scope.\nPilot: Evaluate.\nReview: Decide.",
            "AI",
        )
        self.assertEqual(result[0]["kind"], "timeline")

    def test_table_continuation_preserves_all_rows(self):
        text = "# Metrics\n| Name | Value |\n|---|---|\n" + "\n".join(
            f"| Metric {i} | {i}% |" for i in range(15)
        )
        result = chunks(text, "Metrics")
        self.assertEqual(len(result), 3)
        rows = [r for s in result for r in s["table"][1:]]
        self.assertEqual(len(rows), 15)
        self.assertEqual(rows[-1], ["Metric 14", "14%"])

    def test_classification_failure_keeps_content(self):
        with (
            patch("backend.local_ai.status", return_value={"chat_ready": False}),
            patch("backend.planner.search", return_value=[]),
        ):
            plan = plan_deck(
                "Pilot", "# Facts\nBudget is 125 rupees.", progress=lambda _: None
            )
        self.assertTrue(plan["warnings"])
        self.assertTrue(any("125" in x for s in plan["slides"] for x in s["items"]))

    def test_content_required_without_drafting(self):
        client = TestClient(app)
        self.assertEqual(
            client.post("/api/plan", json={"prompt": "AI", "content": ""}).status_code,
            422,
        )

    def test_cross_origin_rejected(self):
        client = TestClient(app)
        r = client.post(
            "/api/plan",
            headers={"origin": "https://example.com"},
            json={"prompt": "AI", "content": "test"},
        )
        self.assertEqual(r.status_code, 403)

    def test_download_path_validation(self):
        self.assertEqual(
            TestClient(app).get("/api/download/not-a-uuid").status_code, 404
        )

    def test_semantic_retrieval(self):
        result = search(
            "implementation roadmap milestones timeline", kind="layout", limit=3
        )
        self.assertTrue(any(r["category"] == "timeline" for r in result))

    def test_editable_native_export_and_no_template_sample_copy(self):
        with patch("backend.planner.search", return_value=[]):
            plan = DeckPlan.model_validate(
                plan_deck(
                    "Data test",
                    "# Metrics\n| Measure | Value |\n|---|---|\n| Hours | 12 |\n| Quality | 95% |",
                    use_ai=False,
                    progress=lambda _: None,
                )
            )
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test.pptx"
            generate_deck(plan, path)
            validate_package(path, len(plan.slides))
            with ZipFile(path) as z:
                all_text = []
                tables = 0
                for n in z.namelist():
                    if n.startswith("ppt/slides/generated") and n.endswith(".xml"):
                        root = parse(z.read(n))
                        all_text += root.xpath("//a:t/text()", namespaces=NS)
                        tables += len(root.findall(".//a:tbl", NS))
                        for graphic in root.findall(".//a:graphicData", NS):
                            if graphic.find("a:tbl", NS) is not None:
                                self.assertEqual(
                                    graphic.get("uri"),
                                    "http://schemas.openxmlformats.org/drawingml/2006/table",
                                )
                text = " ".join(all_text)
                self.assertIn("95%", text)
                self.assertIn("12", text)
                self.assertEqual(tables, 1)
                self.assertNotIn("Click to edit", text)
                self.assertNotIn("Green marketing", text)
                self.assertTrue(
                    any(n.startswith("ppt/notesSlides/generated") for n in z.namelist())
                )
                self.assertLess(path.stat().st_size, 10_000_000)

    def test_unsupported_layout_rejected(self):
        from backend.models import SlidePlan

        slides = [
            SlidePlan(
                title="Test", kind="content", items=["test"], template=template_ref(60)
            )
        ] * 2
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "not been configured"):
                generate_deck(
                    DeckPlan(
                        title="Test", slides=slides, design={"unique_layouts": False}
                    ),
                    Path(temp) / "test.pptx",
                )


if __name__ == "__main__":
    unittest.main()
