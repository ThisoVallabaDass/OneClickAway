import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from backend.planner import plan_deck
from backend.models import DeckPlan
from backend.exporter import generate_deck
from backend.ooxml import NS, parse


class CompanyTemplateTests(unittest.TestCase):
    def plan(self, text, **design):
        return DeckPlan.model_validate(
            plan_deck(
                "AZure",
                text,
                use_ai=False,
                design=dict(human_touch=True, section_dividers=False, **design),
                progress=lambda _: None,
            )
        )

    def test_story_is_complete_without_duplicate_navigation(self):
        p = self.plan(
            "## Agenda\nTopics.\n## Introduction\nContext.\n## Types\nA: First.\nB: Second.\n## Conclusion\nTakeaway.\n## Thank you\nThanks."
        )
        self.assertEqual(p.title, "Azure")
        self.assertEqual(
            [s.kind for s in p.slides],
            ["cover", "agenda", "content", "content", "content", "closing"],
        )
        self.assertEqual(p.slides[2].title, "Introduction")
        self.assertEqual(p.slides[-2].title, "Conclusion")
        self.assertFalse(any(s.composition or s.layout_variant for s in p.slides))

    def test_decorative_corners_do_not_receive_text(self):
        p = self.plan(
            "## Introduction\nPlatform: Cloud services.\nReach: Global footprint.\nHybrid: Connected environments.\nGovernance: Enterprise controls.",
            agenda=False,
            complete_story=False,
        )
        self.assertEqual(p.slides[1].template.number, 119)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deck.pptx"
            generate_deck(p, path)
            with ZipFile(path) as z:
                root = parse(z.read("ppt/slides/generated2.xml"))
                corners = root.xpath(
                    '//p:sp[p:spPr/a:prstGeom[@prst="corner"]]', namespaces=NS
                )
                self.assertEqual(len(corners), 4)
                self.assertTrue(
                    all(
                        not "".join(s.xpath(".//a:t/text()", namespaces=NS)).strip()
                        for s in corners
                    )
                )
                panels = root.xpath(
                    '//p:sp[p:nvSpPr/p:cNvPr[@name="Template panel content"]]',
                    namespaces=NS,
                )
                self.assertEqual(len(panels), 4)
                bars = root.xpath(
                    '//p:sp[p:nvSpPr/p:cNvPr[@id="10"]]/p:spPr', namespaces=NS
                )
                self.assertEqual(bars[0].find("a:prstGeom", NS).get("prst"), "rect")
                self.assertIsNotNone(bars[0].find("a:solidFill", NS))

    def test_edited_four_panel_slide_is_refitted_without_empty_slot(self):
        p = self.plan(
            "## Types\nA: First.\nB: Second.\nC: Third.\nD: Fourth.",
            agenda=False,
            complete_story=False,
        )
        p.slides[1].items.pop()
        with tempfile.TemporaryDirectory() as tmp:
            result = generate_deck(p, Path(tmp) / "deck.pptx")
            self.assertEqual(result["adjusted_slides"], 1)
            self.assertEqual(p.slides[1].template.number, 77)
            self.assertEqual(len(p.slides[1].items), 3)

    def test_short_agenda_has_no_unused_number_artwork(self):
        p = self.plan("## Introduction\nContext.\n## Conclusion\nTakeaway.")
        self.assertEqual(p.slides[1].items, ["Introduction", "Conclusion"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deck.pptx"
            generate_deck(p, path)
            with ZipFile(path) as z:
                root = parse(z.read("ppt/slides/generated2.xml"))
                ids = root.xpath("//p:cNvPr/@id", namespaces=NS)
                self.assertNotIn("36", ids)
                self.assertNotIn("40", ids)
                self.assertNotIn("44", ids)
                self.assertIn("28", ids)
                self.assertIn("32", ids)

    def test_catalogue_does_not_become_a_cycle_or_pipeline(self):
        p = self.plan(
            "## Service architecture\nOne: Stores objects.\nTwo: Runs containers.\nThree: Hosts databases.\nFour: Manages users.",
            agenda=False,
            complete_story=False,
        )
        s = p.slides[1]
        self.assertIn(s.template.number, [119, 104, 97, 13])
        self.assertIsNone(s.diagram)

    def test_real_numbered_process_keeps_company_timeline(self):
        p = self.plan(
            "## Migration\nStage 1 — Assess: Review workloads.\nStage 2 — Plan: Choose targets.\nStage 3 — Move: Validate migration.\nStage 4 — Improve: Optimize cost.",
            agenda=False,
            complete_story=False,
        )
        self.assertEqual(p.slides[1].template.number, 69)
        self.assertIsNone(p.slides[1].diagram)

    def test_uncertainty_is_withheld_and_preserved_in_notes(self):
        p = self.plan(
            "## Hybrid\nConnectivity is required (Assumption).",
            agenda=False,
            complete_story=False,
        )
        self.assertFalse(any("(Assumption)" in x for s in p.slides for x in s.items))
        self.assertIn("Connectivity is required (Assumption).", p.slides[0].source_text)
        self.assertTrue(any("Unverified" in x for x in p.warnings))

    def test_sparse_input_requests_a_conclusion_instead_of_sampling(self):
        p = self.plan(
            "## Measures\n| Item | Value |\n|---|---|\n| A | 10 |\n| B | 20 |"
        )
        self.assertEqual(p.slides[-2].title, "Measures")
        self.assertTrue(any("author-written conclusion" in w for w in p.warnings))
        self.assertFalse(any("improved" in x.lower() for x in p.slides[-2].items))

    def test_lifecycle_order_is_clockwise_and_sample_label_is_cleared(self):
        p = self.plan(
            "## Delivery lifecycle\nDiscover: Understand.\nDesign: Develop.\nDeliver: Implement.\nReview: Learn.",
            agenda=False,
            complete_story=False,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deck.pptx"
            generate_deck(p, path)
            with ZipFile(path) as z:
                root = parse(z.read("ppt/slides/generated2.xml"))
                text = lambda ident: root.xpath(
                    '//p:sp[p:nvSpPr/p:cNvPr[@id="' + ident + '"]]//a:t/text()',
                    namespaces=NS,
                )
                self.assertEqual(text("47"), ["Deliver"])
                self.assertEqual(text("55"), ["Review"])
                self.assertFalse("".join(text("84")).strip())
