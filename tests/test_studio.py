import io
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
from PIL import Image
from fastapi.testclient import TestClient
from backend.app import app
from backend.models import DeckPlan
from backend.planner import chunks, plan_deck
from backend.exporter import generate_deck
from backend.ooxml import NS, parse
from backend.prompts import build_prompt
from backend.images import save_upload, image_bytes
from backend.human_design import text_layout

ROOT = Path(__file__).resolve().parents[1]


class StudioTests(unittest.TestCase):
    def plan(self, text, pictures=None, **design):
        with patch("backend.planner.search", return_value=[]):
            return plan_deck(
                "Cloud overview",
                text,
                use_ai=False,
                design={
                    "human_touch": True,
                    "section_dividers": False,
                    "agenda": False,
                    "complete_story": False,
                    **design,
                },
                pictures=pictures,
                progress=lambda _: None,
            )

    def test_plain_numbered_ai_slides_and_blank_lines(self):
        text = "Slide 1 — Cloud\n\nCloud services.\n\nMore detail.\n\n**Slide 2: Security**\n\n**Access**\n- Approved users.\n**Audit**\n- Record changes."
        parts = chunks(text, "Cloud")
        self.assertEqual([s["title"] for s in parts], ["Cloud", "Security"])
        self.assertEqual(parts[0]["items"], ["Cloud services.", "More detail."])
        self.assertIn("### Access", parts[1]["items"])
        self.assertFalse(any("Slide 1" in x for s in parts for x in s["items"]))

    def test_human_retains_nested_group(self):
        text = "## Team\nFirst fact.\nSecond fact.\n### Review\n- Parent point.\n  - Child one.\n  - Child two.\n### Next\n- Next point."
        p = self.plan(text)
        s = next(s for s in p["slides"] if "  Child one." in s["items"])
        self.assertIn("Parent point.", s["items"])
        self.assertIn("### Review", s["items"])

    def test_human_layouts_are_content_driven_and_preserve_words(self):
        text = "Slide 1 — Comparison\nBefore: A verified baseline.\nAfter: A proposed approach.\nSlide 2 — Pilot roadmap\nDiscovery: Choose a use case.\nReview: Evaluate the results.\nSlide 3 — Conclusion\nAll 125 records remain."
        p = self.plan(text)
        body = p["slides"][1:-1]
        self.assertEqual(body[0]["template"]["number"], 17)
        self.assertTrue(all(s["template"]["number"] in (13, 16) for s in body[1:]))
        self.assertTrue(all(s["composition"] is None for s in body))
        self.assertIn("125", " ".join(body[-1]["items"]))
        from backend.template_engine import fits

        self.assertTrue(all(fits(s, s["template"]["number"], "modern") for s in body))

    def test_uploaded_picture_is_embedded_and_not_cropped(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("backend.images.ASSETS", Path(tmp)),
        ):
            ref = save_upload(
                (ROOT / "static/kaar-logo.png").read_bytes(), "Company picture"
            )
            p = self.plan(
                "## Pilot\n- A short explanation.",
                pictures=[{"image": ref, "target": "Pilot"}],
            )
            path = Path(tmp) / "result.pptx"
            generate_deck(DeckPlan.model_validate(p), path)
            with ZipFile(path) as z:
                slide = parse(z.read("ppt/slides/generated2.xml"))
                self.assertEqual(slide.get("showMasterSp"), "0")
                self.assertGreaterEqual(len(slide.findall(".//p:pic", NS)), 1)
                self.assertFalse(slide.findall(".//a:srcRect", NS))
                self.assertTrue(
                    any(
                        ref["id"] in n
                        for n in z.namelist()
                        if n.startswith("ppt/media/")
                    )
                )
                text = " ".join(slide.xpath("//a:t/text()", namespaces=NS))
                self.assertIn("short explanation", text)
                self.assertNotIn("August 2024", text)

    def test_picture_target_failure_does_not_silently_omit_image(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("backend.images.ASSETS", Path(tmp)),
        ):
            ref = save_upload((ROOT / "static/kaar-logo.png").read_bytes(), "Picture")
            with self.assertRaisesRegex(ValueError, "matching slide heading"):
                self.plan(
                    "## Pilot\nA fact.",
                    pictures=[{"image": ref, "target": "Missing heading"}],
                )

    def test_invalid_upload_and_missing_topic(self):
        client = TestClient(app)
        self.assertEqual(
            client.post("/api/images/upload", content=b"not an image").status_code, 422
        )
        self.assertEqual(
            client.post(
                "/api/ai/prompt", json={"topic": "  ", "provider": "chatgpt"}
            ).status_code,
            422,
        )
        self.assertEqual(
            client.post(
                "/api/ai/prompt", json={"topic": "Cloud", "provider": "unknown"}
            ).status_code,
            422,
        )
        self.assertEqual(
            client.post(
                "/api/ai/prompt",
                json={"topic": "Cloud", "provider": "gemini", "slides": 99},
            ).status_code,
            422,
        )

    def test_prompt_contract(self):
        prompt = build_prompt("Cloud", 6, 3)
        self.assertIn("exactly 6 content slides", prompt)
        self.assertIn("2 to 3 short body lines", prompt)
        self.assertIn("<topic>\nCloud\n</topic>", prompt)

    def test_diagram_edited_in_review_rebuilds_native_connections(self):
        p = self.plan("## Data pipeline\nQuery -> Retrieval -> Answer")
        p["slides"][1]["diagram"] = None
        p["slides"][1]["items"] = ["Input", "Model", "Review"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "diagram.pptx"
            generate_deck(DeckPlan.model_validate(p), path)
            with ZipFile(path) as z:
                slide = parse(z.read("ppt/slides/generated2.xml"))
                self.assertEqual(len(slide.findall(".//p:cxnSp", NS)), 2)
                self.assertIn("Review", slide.xpath("//a:t/text()", namespaces=NS))

    def test_sequence_does_not_need_a_special_heading(self):
        p = self.plan(
            "## Application request flow\nUser -> CloudFront -> Load Balancer -> EC2 -> RDS"
        )
        self.assertEqual(p["slides"][1]["template"]["number"], 20)
        self.assertEqual(len(p["slides"][1]["diagram"]["nodes"]), 5)

    def test_human_table_pages_avoid_one_orphan_row(self):
        text = "## Services\n| Service | Purpose |\n|---|---|\n" + "\n".join(
            f"| Service {i} | Purpose {i} |" for i in range(8)
        )
        p = self.plan(text)
        tables = [s for s in p["slides"] if s["table"]]
        self.assertEqual([len(s["table"]) - 1 for s in tables], [4, 4])
        self.assertTrue(tables[1]["title"].endswith("(continued)"))

    def test_browser_automation_is_retired(self):
        client = TestClient(app)
        result = client.post(
            "/api/ai/generate", json={"topic": "Cloud", "provider": "claude"}
        )
        self.assertEqual(result.status_code, 410)
        self.assertIn("manually", result.json()["detail"])
        self.assertEqual(client.post("/api/ai/cancel", json={}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
