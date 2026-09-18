"""Heading hierarchy, inline formatting and template differentiation."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
from backend.catalog import PROFILES
from backend.design import SECTION_ORDER, fitted_size
from backend.exporter import generate_deck
from backend.models import DeckPlan
from backend.ooxml import NS, parse
from backend.planner import chunks, compatible, plan_deck, sections, template_ref
from backend.richtext import heading_roles, inline_runs, parse_item, plain_text

SECTIONED = "\n".join(
    [
        "# Platform review",
        "## Current state",
        "The platform serves internal teams.",
        "### Reliability",
        "Two incidents were recorded last quarter.",
        "### Cost",
        "Spend grew with usage.",
        "# Next steps",
        "## Proposals",
        "Consolidate the two ingestion paths.",
    ]
)
FLAT = "# Overview\nFirst point.\nSecond point.\n\n# Detail\nThird point."


def slide_by_kind(plan, kind):
    return [s for s in plan["slides"] if s["kind"] == kind]


def build(slides, **design):
    plan = DeckPlan(title="Formatting", slides=slides, design=design)
    temp = tempfile.TemporaryDirectory()
    path = Path(temp.name) / "deck.pptx"
    generate_deck(plan, path)
    return temp, path


def body_shape(archive, part, shape_id="3"):
    root = parse(archive.read(part))
    for shape in root.findall(".//p:sp", NS):
        node = shape.find("p:nvSpPr/p:cNvPr", NS)
        if node is not None and node.get("id") == shape_id:
            return shape
    raise AssertionError("shape " + shape_id + " is missing from " + part)


class HierarchyTests(unittest.TestCase):
    def test_heading_markers_are_ranked_per_document(self):
        self.assertEqual(
            heading_roles(SECTIONED), {1: "section", 2: "slide", 3: "subheading"}
        )
        # A single top-level heading is a document title, not a divider.
        self.assertEqual(
            heading_roles("# Title\n## A\nx\n## B\ny"), {1: "document", 2: "slide"}
        )
        self.assertEqual(heading_roles(FLAT), {1: "slide"})
        # Bold-only and "Label:" lines rank below any ATX heading.
        self.assertEqual(
            heading_roles("## Topic\ntext\n**Aside**\nmore\n## Two\nx"),
            {2: "slide", 7: "subheading"},
        )

    def test_top_level_headings_become_divider_slides(self):
        parts = sections(SECTIONED, "Review")
        self.assertEqual(
            [p["role"] for p in parts], ["section", "slide", "section", "slide"]
        )
        self.assertEqual(
            [p["title"] for p in parts if p["role"] == "section"],
            ["Platform review", "Next steps"],
        )
        self.assertEqual(parts[1]["section"], "Platform review")

    def test_deeper_headings_stay_with_their_content(self):
        body = chunks(SECTIONED, "Review")
        slide = [c for c in body if c["kind"] != "section"][0]
        self.assertEqual(
            slide["items"][:2],
            ["The platform serves internal teams.", "### Reliability"],
        )

    def test_flat_document_keeps_one_heading_level(self):
        self.assertEqual(
            [p["role"] for p in sections(FLAT, "Overview")], ["slide", "slide"]
        )

    def test_horizontal_rule_forces_a_slide_break(self):
        parts = sections("# Topic\nFirst.\n---\nSecond.", "Topic")
        self.assertEqual([p["body"] for p in parts], ["First.", "Second."])

    def test_indentation_becomes_nesting(self):
        parts = sections(
            "# Topic\n- Parent point\n  - Child point\n    - Grandchild point", "Topic"
        )
        self.assertEqual(
            parts[0]["body"].splitlines(),
            ["Parent point", "  Child point", "    Grandchild point"],
        )
        self.assertEqual(
            [parse_item(line)["level"] for line in parts[0]["body"].splitlines()],
            [0, 1, 2],
        )

    def test_divider_slides_rotate_and_feed_the_agenda(self):
        with patch("backend.planner.search", return_value=[]):
            plan = plan_deck(
                "Platform",
                SECTIONED,
                use_ai=False,
                design={"agenda": True, "complete_story": False},
                progress=lambda _: None,
            )
        dividers = slide_by_kind(plan, "section")
        self.assertEqual(
            [s["title"] for s in dividers], ["Platform review", "Next steps"]
        )
        self.assertEqual([s["template"]["number"] for s in dividers], SECTION_ORDER[:2])
        for divider in dividers:
            self.assertEqual(PROFILES[divider["template"]["number"]]["mode"], "section")
        # The agenda lists the top-level headings, not every slide title.
        agenda = slide_by_kind(plan, "agenda")[0]
        self.assertEqual(agenda["items"], ["Platform review", "Next steps"])
        self.assertEqual(
            slide_by_kind(plan, "content")[0]["section"], "Platform review"
        )

    def test_dividers_can_be_turned_off(self):
        with patch("backend.planner.search", return_value=[]):
            plan = plan_deck(
                "Platform",
                SECTIONED,
                use_ai=False,
                design={
                    "section_dividers": False,
                    "agenda": True,
                    "complete_story": False,
                },
                progress=lambda _: None,
            )
        self.assertEqual(slide_by_kind(plan, "section"), [])
        self.assertEqual(
            slide_by_kind(plan, "agenda")[0]["items"], ["Platform review", "Next steps"]
        )

    def test_divider_captions_fit_a_long_heading(self):
        long_heading = "Consolidated platform reliability and cost review for the coming planning cycle"
        with patch("backend.planner.search", return_value=[]):
            plan = plan_deck(
                "Platform",
                f"# {long_heading}\n## Detail\nA supplied point.\n"
                f"# Second division\n## More\nAnother supplied point.",
                use_ai=False,
                progress=lambda _: None,
            )
        temp, path = build(
            [
                DeckPlan.model_validate(plan).slides[i]
                for i in range(len(plan["slides"]))
            ]
        )
        with ZipFile(path) as z:
            index = [
                i for i, s in enumerate(plan["slides"], 1) if s["kind"] == "section"
            ][0]
            shape = body_shape(
                z,
                f"ppt/slides/generated{index}.xml",
                PROFILES[plan["slides"][index - 1]["template"]["number"]]["title"],
            )
            self.assertEqual(
                "".join(shape.xpath(".//a:t/text()", namespaces=NS)), long_heading
            )
            # The divider keeps the template's own caption colour rather than a guessed one.
            rpr = shape.xpath(".//a:rPr", namespaces=NS)[0]
            self.assertIsNone(rpr.find("a:solidFill/a:srgbClr", NS))
        temp.cleanup()

    def test_structured_content_avoids_one_item_per_slot_layouts(self):
        plain = {
            "title": "Controls",
            "kind": "pointers",
            "items": ["First: value", "Second: value", "Third: value", "Fourth: value"],
        }
        structured = {**plain, "items": ["### Group", "First: value", "  Nested value"]}
        self.assertTrue(compatible(plain, 97, "modern"))
        self.assertFalse(compatible(structured, 97, "modern"))


class InlineFormattingTests(unittest.TestCase):
    def test_delimiters_carry_formatting_and_never_survive_as_text(self):
        runs = inline_runs("Plain **bold** *italic* ++under++ ~~gone~~ `code` end")
        self.assertEqual(
            "".join(r["text"] for r in runs), "Plain bold italic under gone code end"
        )
        styled = {r["text"]: r for r in runs}
        self.assertTrue(styled["bold"]["bold"])
        self.assertTrue(styled["italic"]["italic"])
        self.assertTrue(styled["under"]["underline"])
        self.assertTrue(styled["gone"]["strike"])
        self.assertTrue(styled["code"]["code"])

    def test_underline_accepts_both_spellings(self):
        for value in ["++Reviewed++", "<u>Reviewed</u>"]:
            self.assertTrue(inline_runs(value)[0]["underline"], value)

    def test_nested_emphasis_combines(self):
        runs = inline_runs("**bold and *also italic* here**")
        self.assertTrue(all(r["bold"] for r in runs))
        self.assertEqual([r["text"] for r in runs if r["italic"]], ["also italic"])
        # Unbalanced markers stay literal instead of dropping words.
        self.assertEqual(
            plain_text("**bold and *also italic***"), "bold and *also italic*"
        )

    def test_arithmetic_and_identifiers_stay_literal(self):
        for value in ["5 * 3 * 2 items", "use snake_case_name here", "a_b and c_d"]:
            self.assertEqual(plain_text(value), value)

    def test_escapes_produce_literal_markers(self):
        self.assertEqual(plain_text(r"literal \*stars\* kept"), "literal *stars* kept")

    def test_links_become_underlined_runs(self):
        run = inline_runs("see [the policy](https://example.com/policy) now")[1]
        self.assertEqual(
            (run["text"], run["link"], run["underline"]),
            ("the policy", "https://example.com/policy", True),
        )

    def test_block_roles_are_decoded_from_the_item_prefix(self):
        self.assertEqual(parse_item("### Approach")["role"], "subheading")
        self.assertEqual(parse_item("> Quoted line")["role"], "quote")
        self.assertEqual(parse_item("  Nested line")["level"], 1)
        # Non-structural text keeps its characters; only inline markup is interpreted.
        self.assertEqual(
            parse_item("### Approach", structural=False)["plain"], "### Approach"
        )

    def test_capacity_accounts_for_subheadings_and_nesting(self):
        bounds = [0, 0, 4000000, 900000]
        flat = ["Point one wording here", "Point two wording here"]
        nested = ["### Heading", "  Point one wording here", "  Point two wording here"]
        self.assertLessEqual(
            fitted_size(bounds, nested, 22, 8, "Segoe UI", True, structural=True),
            fitted_size(bounds, flat, 22, 8, "Segoe UI", True, structural=True),
        )
        # Delimiters must not consume space.
        self.assertEqual(
            fitted_size(
                bounds,
                ["**Point one wording here**"],
                22,
                8,
                "Segoe UI",
                True,
                structural=True,
            ),
            fitted_size(
                bounds,
                ["Point one wording here"],
                22,
                8,
                "Segoe UI",
                True,
                structural=True,
            ),
        )


class ExportFormattingTests(unittest.TestCase):
    def deck(self, items):
        slides = [
            {
                "title": "Findings",
                "kind": "content",
                "items": items,
                "template": template_ref(13),
            },
            {
                "title": "Thank you",
                "kind": "closing",
                "items": [],
                "template": template_ref(170),
            },
        ]
        return build(slides)

    def test_subheading_renders_bold_underlined_and_unbulleted(self):
        temp, path = self.deck(
            ["### Reliability", "Two incidents were recorded.", "  A nested detail."]
        )
        with ZipFile(path) as z:
            shape = body_shape(z, "ppt/slides/generated1.xml")
            paragraphs = shape.findall("p:txBody/a:p", NS)
            heading, bullet, nested = paragraphs
            self.assertEqual(
                "".join(heading.xpath(".//a:t/text()", namespaces=NS)), "Reliability"
            )
            self.assertIsNotNone(heading.find("a:pPr/a:buNone", NS))
            rpr = heading.find("a:r/a:rPr", NS)
            self.assertEqual((rpr.get("b"), rpr.get("u")), ("1", "sng"))
            # A subheading reads one step above the bullets beneath it.
            self.assertGreater(
                int(rpr.get("sz")), int(bullet.find("a:r/a:rPr", NS).get("sz"))
            )
            self.assertEqual(bullet.find("a:pPr/a:buChar", NS).get("char"), "\u2022")
            self.assertEqual(nested.find("a:pPr/a:buChar", NS).get("char"), "\u2013")
            self.assertGreater(
                int(nested.find("a:pPr", NS).get("marL")),
                int(bullet.find("a:pPr", NS).get("marL")),
            )
        temp.cleanup()

    def test_inline_formatting_reaches_the_slide(self):
        temp, path = self.deck(
            ["A ++reviewed++ and ~~withdrawn~~ **finding** with `code`."]
        )
        with ZipFile(path) as z:
            shape = body_shape(z, "ppt/slides/generated1.xml")
            runs = {
                "".join(r.xpath("a:t/text()", namespaces=NS)): r.find("a:rPr", NS)
                for r in shape.findall("p:txBody/a:p/a:r", NS)
            }
            self.assertEqual(runs["reviewed"].get("u"), "sng")
            self.assertEqual(runs["withdrawn"].get("strike"), "sngStrike")
            self.assertEqual(runs["finding"].get("b"), "1")
            self.assertEqual(
                runs["code"].find("a:latin", NS).get("typeface"), "Consolas"
            )
            text = "".join(
                "".join(r.xpath("a:t/text()", namespaces=NS))
                for r in shape.findall("p:txBody/a:p/a:r", NS)
            )
            self.assertEqual(text, "A reviewed and withdrawn finding with code.")
        temp.cleanup()

    def test_quote_renders_italic_without_a_bullet(self):
        temp, path = self.deck(
            ["> Reviewed by the platform team.", "A following point."]
        )
        with ZipFile(path) as z:
            quote = body_shape(z, "ppt/slides/generated1.xml").findall(
                "p:txBody/a:p", NS
            )[0]
            self.assertEqual(
                "".join(quote.xpath(".//a:t/text()", namespaces=NS)),
                "Reviewed by the platform team.",
            )
            self.assertIsNotNone(quote.find("a:pPr/a:buNone", NS))
            self.assertEqual(quote.find("a:r/a:rPr", NS).get("i"), "1")
        temp.cleanup()

    def test_supplied_link_becomes_a_real_external_relationship(self):
        temp, path = self.deck(["Read [the policy](https://example.com/policy) first."])
        with ZipFile(path) as z:
            shape = body_shape(z, "ppt/slides/generated1.xml")
            link = shape.find(".//a:hlinkClick", NS)
            self.assertIsNotNone(link)
            rid = link.get("{" + NS["r"] + "}id")
            targets = {
                r.get("Id"): (r.get("Target"), r.get("TargetMode"))
                for r in parse(z.read("ppt/slides/_rels/generated1.xml.rels"))
            }
            self.assertEqual(targets[rid], ("https://example.com/policy", "External"))
        temp.cleanup()

    def test_notes_reproduce_the_supplied_markdown_verbatim(self):
        source = "A **bold** finding with `code`."
        slides = [
            {
                "title": "Findings",
                "kind": "content",
                "items": [source],
                "source_text": source,
                "section": "Platform review",
                "template": template_ref(13),
            },
            {
                "title": "Thank you",
                "kind": "closing",
                "items": [],
                "template": template_ref(170),
            },
        ]
        temp, path = build(slides)
        with ZipFile(path) as z:
            notes = "".join(
                parse(z.read("ppt/notesSlides/generated1.xml")).xpath(
                    "//a:t/text()", namespaces=NS
                )
            )
            self.assertIn(source, notes)
            self.assertIn("Section: Platform review.", notes)
        temp.cleanup()

    def test_structural_slides_may_reuse_their_layout_under_no_repeat(self):
        slides = [
            {
                "title": "One",
                "kind": "section",
                "items": [],
                "template": template_ref(SECTION_ORDER[0]),
            },
            {
                "title": "Two",
                "kind": "section",
                "items": [],
                "template": template_ref(SECTION_ORDER[0]),
            },
        ]
        temp, path = build(slides, unique_layouts=True)
        self.assertTrue(path.exists())
        temp.cleanup()


if __name__ == "__main__":
    unittest.main()


class PackageWeightTests(unittest.TestCase):
    def test_section_dividers_do_not_inflate_the_package(self):
        content = "\n".join(
            f"# Division {i}\n## Topic {i}\nA supplied point for topic {i}."
            for i in range(5)
        )
        with patch("backend.planner.search", return_value=[]):
            plan = plan_deck("Weight", content, use_ai=False, progress=lambda _: None)
        self.assertEqual(len(slide_by_kind(plan, "section")), 5)
        temp, path = build(DeckPlan.model_validate(plan).slides)
        # Every divider design in the rotation is free of heavy decorative bitmaps.
        self.assertLess(
            path.stat().st_size, 6_000_000, "a divider design pulled in large media"
        )
        temp.cleanup()
