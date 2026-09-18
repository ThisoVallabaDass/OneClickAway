import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
from backend.models import DeckPlan, DesignOptions, DiagramSpec
from backend.planner import plan_deck, chunks, template_ref, choose_layout
from backend.design import fitted_size, FONT_PAIRS
from backend.exporter import generate_deck, group_tree
from backend.visuals import add_diagram
from backend.ooxml import NS, parse
from backend.images import image_bytes, fetch


class DesignTests(unittest.TestCase):
    def test_no_repeat_planning_and_exhaustion(self):
        content = "\n\n".join(
            f"# Topic {i}\nFirst finding.\nSecond finding.\nThird finding."
            for i in range(4)
        )
        with patch("backend.planner.search", return_value=[]):
            plan = plan_deck("Sample", content, use_ai=False, progress=lambda _: None)
        ids = [(s["template"]["id"], s["layout_variant"]) for s in plan["slides"]]
        self.assertTrue(all(s["layout_variant"] is None for s in plan["slides"]))
        from backend.catalog import PROFILES

        with self.assertRaisesRegex(ValueError, "No unused layout"):
            choose_layout(
                {"title": "Sample", "kind": "content", "items": ["Example"]},
                [],
                set(PROFILES),
                DesignOptions(),
            )

    def test_suitable_layout_reuse_exports(self):
        slide = {
            "title": "Test",
            "kind": "content",
            "items": ["Content"],
            "template": template_ref(13),
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test.pptx"
            generate_deck(DeckPlan(title="Test", slides=[slide, slide]), path)
            self.assertTrue(path.exists())

    def test_architecture_sequence_is_native_and_editable(self):
        section = chunks(
            "# Architecture pipeline\nInput -> Embeddings -> Retrieval -> Answer", "AI"
        )[0]
        self.assertEqual(
            section["diagram"]["nodes"], ["Input", "Embeddings", "Retrieval", "Answer"]
        )
        tree = group_tree()
        add_diagram(
            tree,
            DiagramSpec.model_validate(section["diagram"]),
            100,
            "horizontal",
            "modern",
        )
        self.assertEqual(len(tree.findall("p:cxnSp", NS)), 3)
        ids = {n.get("id") for n in tree.findall("p:sp/p:nvSpPr/p:cNvPr", NS)}
        self.assertTrue(
            all(
                n.get("id") in ids
                for n in tree.findall(".//a:stCxn", NS)
                + tree.findall(".//a:endCxn", NS)
            )
        )
        with self.assertRaisesRegex(ValueError, "invalid node"):
            add_diagram(
                group_tree(),
                DiagramSpec(nodes=["A", "B"], edges=[(0, 4)]),
                100,
                "horizontal",
                "modern",
            )

    def test_font_metrics_distinguish_wide_characters(self):
        bounds = [0, 0, 3000000, 800000]
        narrow = fitted_size(bounds, "i" * 50, 22, 10, "Segoe UI")
        wide = fitted_size(bounds, "W" * 50, 22, 10, "Segoe UI")
        self.assertGreater(narrow, wide)

    def test_typography_effects_and_contrast(self):
        for style, (heading, body) in FONT_PAIRS.items():
            for effects in ["none", "subtle"]:
                slides = [
                    {
                        "title": "Comparison",
                        "kind": "comparison",
                        "items": ["First: Verified value.", "Second: Approved value."],
                        "template": template_ref(126),
                    },
                    {
                        "title": "Thank you",
                        "kind": "closing",
                        "items": [],
                        "template": template_ref(170),
                    },
                ]
                with tempfile.TemporaryDirectory() as temp:
                    path = Path(temp) / "test.pptx"
                    generate_deck(
                        DeckPlan(
                            title="Test",
                            slides=slides,
                            design={"typography": style, "effects": effects},
                        ),
                        path,
                    )
                    with ZipFile(path) as z:
                        closing = parse(z.read("ppt/slides/generated2.xml"))
                        rpr = closing.xpath(
                            '//p:sp[p:nvSpPr/p:cNvPr[@descr="Generated presentation content"]]//a:rPr',
                            namespaces=NS,
                        )[0]
                        self.assertEqual(
                            rpr.find("a:solidFill/a:srgbClr", NS).get("val"), "FFFFFF"
                        )
                        self.assertEqual(
                            rpr.find("a:latin", NS).get("typeface"), heading
                        )
                        # DrawingML requires fill before font declarations; reversed order rendered black in Office.
                        self.assertLess(
                            list(rpr).index(rpr.find("a:solidFill", NS)),
                            list(rpr).index(rpr.find("a:latin", NS)),
                        )
                        self.assertEqual(
                            closing.find("p:transition", NS) is not None,
                            effects == "subtle",
                        )

    def test_images_fail_safely_and_preserve_notes(self):
        with (
            patch("backend.planner.search", return_value=[]),
            patch("backend.images.find_image", side_effect=OSError("offline")),
        ):
            plan = plan_deck(
                "AI",
                "# Overview\nSupplied information.",
                use_ai=False,
                design={"images": True, "agenda": False, "complete_story": False},
                progress=lambda _: None,
            )
        self.assertTrue(
            any("image search was unavailable" in w for w in plan["warnings"])
        )
        self.assertEqual(plan["slides"][1]["items"], ["Supplied information."])
        for invalid in ["../../secret", "xyz"]:
            with self.assertRaises(ValueError):
                image_bytes(invalid)
        with self.assertRaises(ValueError):
            fetch("http://127.0.0.1/private")


if __name__ == "__main__":
    unittest.main()
