import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from backend.models import DeckPlan
from backend.planner import plan_deck, chunks
from backend.template_engine import candidates, make_agenda
from backend.quality import clean_source, heading_case, lint_deck, agenda_titles
from backend.exporter import generate_deck
from backend.ooxml import NS, parse


class QualityUpgradeTests(unittest.TestCase):
    def plan(self, text, human=True, **options):
        return DeckPlan.model_validate(
            plan_deck(
                "KaarTech",
                text,
                use_ai=False,
                design={"human_touch": human, "section_dividers": False, **options},
                progress=lambda _: None,
            )
        )

    def test_related_pairs_are_not_a_comparison_in_either_mode(self):
        for human in (False, True):
            for items in (
                ["KaarTech: A consulting company.", "Core focus: SAP delivery."],
                [
                    "### KaarTech",
                    "A consulting company.",
                    "### Core focus",
                    "SAP delivery.",
                ],
            ):
                self.assertNotIn(
                    17,
                    candidates(
                        dict(title="Introduction", kind="content", items=items), human
                    ),
                )

    def test_real_contrasts_use_comparison_in_both_modes(self):
        for human in (False, True):
            for title, items in [
                (
                    "Before and after",
                    ["Before: Manual work.", "After: Automated work."],
                ),
                (
                    "Options",
                    ["Traditional: Fixed resources.", "Proposed: Flexible resources."],
                ),
                ("Azure vs AWS", ["Azure: First option.", "AWS: Second option."]),
            ]:
                self.assertEqual(
                    candidates(dict(title=title, kind="content", items=items), human)[
                        0
                    ],
                    17,
                )

    def test_agenda_contains_actual_topics_and_updates_after_edits(self):
        text = (Path(__file__).parent / "fixtures/kaartech-capabilities.md").read_text(
            encoding="utf-8"
        )
        p = self.plan(text)
        self.assertEqual(len(p.slides), 11)
        agenda = p.slides[1]
        self.assertEqual(agenda.template.number, 32)
        self.assertEqual(len(agenda.items), 8)
        self.assertNotIn("Core concepts", agenda.items)
        self.assertEqual(
            [t for g in agenda.agenda_topics for t in g],
            agenda_titles([s.model_dump() for s in p.slides]),
        )
        p.slides[4].title = "SAP integration capabilities"
        with tempfile.TemporaryDirectory() as tmp:
            generate_deck(p, Path(tmp) / "deck.pptx")
        self.assertIn("SAP integration capabilities", p.slides[1].items)

    def test_six_and_seven_topic_agendas_remove_entire_unused_rows(self):
        for count, unused in [
            (6, ("23", "24", "105", "106", "25", "26", "107", "108")),
            (7, ("25", "26", "107", "108")),
        ]:
            text = "\n".join(
                "## Topic " + str(i) + "\nDistinct fact " + str(i) + "."
                for i in range(count)
            )
            p = self.plan(text, complete_story=False)
            self.assertEqual(len(p.slides[1].items), count)
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "deck.pptx"
                generate_deck(p, path)
                with ZipFile(path) as z:
                    root = parse(z.read("ppt/slides/generated2.xml"))
                    # Added footer/brand shapes can reuse IDs; original unused
                    # rows must be gone, including their numeric and sample text.
                    visible = " ".join(root.xpath("//a:t/text()", namespaces=NS))
                    for value in range(count + 1, 9):
                        self.assertNotIn(
                            f"{value:02}",
                            visible.replace(f"02 / {len(p.slides):02}", ""),
                        )
                    self.assertNotIn("Agenda Title", visible)

    def test_footer_is_removed_before_architecture_detection(self):
        text = "## Conclusion\nA reviewed finding.\n🔗 Context Chain: KaarTech → SAP Consulting → Delivery"
        p = self.plan(text)
        self.assertFalse(any("Context Chain" in x for s in p.slides for x in s.items))
        self.assertIn("Context Chain", p.slides[0].source_text)
        self.assertFalse(any(s.diagram for s in p.slides))
        clean, _ = clean_source(
            "🔎 Security: Review access.\nSource: https://example.com\nUser → Service → Database"
        )
        self.assertIn("🔎 Security", clean)
        self.assertIn("Source:", clean)
        self.assertIn("User → Service → Database", clean)

    def test_edited_footer_is_blocked_at_export(self):
        p = self.plan(
            "## Introduction\nA company fact.\n## Conclusion\nA reviewed finding."
        )
        p.slides[-2].items.append("🔗 Context Chain: Topic → Answer")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deck.pptx"
            with self.assertRaisesRegex(ValueError, "authoring footer"):
                generate_deck(p, path)
            self.assertFalse(path.exists())

    def test_plain_outline_recovers_real_titles_instead_of_44_slides(self):
        text = (
            Path(__file__).parent / "fixtures/kaartech-plain-outline.txt"
        ).read_text(encoding="utf-8")
        parts = chunks(text, "KaarTech")
        self.assertEqual(len(parts), 8)
        self.assertEqual(parts[0]["title"], "Introduction to KaarTech")
        self.assertIn("### Enterprise SAP Partner", parts[0]["items"])
        self.assertFalse(any(s["title"] == "KaarTech" for s in parts))
        p = self.plan(text)
        self.assertLessEqual(len(p.slides), 12)
        self.assertFalse(any(s.title == "KaarTech" for s in p.slides[1:-1]))

    def test_heading_case_preserves_brands_and_technical_names(self):
        self.assertEqual(
            heading_case("SAP Ecosystem Expertise"), "SAP ecosystem expertise"
        )
        self.assertEqual(
            heading_case("KAARTECH Core Capabilities"), "KaarTech core capabilities"
        )
        self.assertEqual(
            heading_case("KTern.AI Transformation Platform"),
            "KTern.AI transformation platform",
        )
        self.assertEqual(heading_case("AZure APIs and NoSQL."), "Azure APIs and NoSQL")

    def test_long_agenda_topics_keep_coverage_in_readable_list_layout(self):
        body = [
            dict(
                title=f"Capability {i} across enterprise integration and operational management",
                kind="content",
                items=["A fact."],
            )
            for i in range(12)
        ]
        agenda = make_agenda(body, "modern")
        self.assertEqual(agenda["template"]["number"], 37)
        self.assertEqual(
            [t for group in agenda["agenda_topics"] for t in group],
            [s["title"] for s in body],
        )
        text = "\n".join("## " + s["title"] + "\nDistinct fact." for s in body)
        plan = self.plan(text, complete_story=False)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deck.pptx"
            generate_deck(plan, path)
            with ZipFile(path) as z:
                root = parse(z.read("ppt/slides/generated2.xml"))
                lines = root.findall(".//p:cxnSp", NS)
                self.assertEqual(len(lines), 7)
                for i, line in enumerate(lines):
                    # Dividers are below the two-line caption area, not at
                    # the old one-line baseline that struck through text.
                    self.assertGreater(
                        int(line.find("p:spPr/a:xfrm/a:off", NS).get("y")),
                        1100000 + i * 740000 + 650000,
                    )
