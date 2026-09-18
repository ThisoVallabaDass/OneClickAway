from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from zipfile import ZipFile
from backend.planner import plan_deck
from backend.models import DeckPlan
from backend.exporter import generate_deck
from backend.tables import table_layout, paginate_table
from backend.ooxml import NS, parse
from backend.prompts import build_prompt

FIXTURE = Path(__file__).parent / "fixtures/azure-table.md"


class CapacityTests(unittest.TestCase):
    def test_screenshot_table_plans_and_exports_in_every_font(self):
        for human in (False, True):
            for style in ("modern", "corporate", "editorial"):
                with patch("backend.planner.search", return_value=[]):
                    raw = plan_deck(
                        "Azure",
                        FIXTURE.read_text(),
                        use_ai=False,
                        design=dict(
                            human_touch=human,
                            typography=style,
                            unique_layouts=False,
                            section_dividers=False,
                        ),
                        progress=lambda _: None,
                    )
                tables = [s for s in raw["slides"] if s["table"]]
                rows = [row for s in tables for row in s["table"][1:]]
                self.assertEqual(len(rows), 4)
                self.assertEqual(
                    rows[-1][-1], "Apache Spark environment integrated with Azure"
                )
                with TemporaryDirectory() as tmp:
                    path = Path(tmp) / "test.pptx"
                    generate_deck(DeckPlan.model_validate(raw), path)
                    with ZipFile(path) as z:
                        for i, s in enumerate(raw["slides"], 1):
                            if not s["table"]:
                                continue
                            xml = parse(z.read(f"ppt/slides/generated{i}.xml"))
                            heights = [
                                int(x.get("h")) for x in xml.findall(".//a:tr", NS)
                            ]
                            expected = table_layout(s["table"], style, human)
                            self.assertEqual(heights, expected["heights"])
                            self.assertLessEqual(sum(heights), 4500000)

    def test_dense_tables_split_without_losing_rows_or_cells(self):
        rows = [["Service", "Purpose", "Audience", "Feature"]] + [
            [
                f"Row {i}",
                "Enterprise data warehousing and advanced analytics",
                "Data engineers, analysts, and application developers",
                "Collaborative processing and integration with enterprise data",
            ]
            for i in range(12)
        ]
        pages = paginate_table(rows, human=True)
        self.assertGreater(len(pages), 2)
        self.assertEqual([r for p in pages for r in p[1:]], rows[1:])
        for page in pages:
            self.assertGreaterEqual(table_layout(page, human=True)["size"], 18)

    def test_prompt_defines_visual_budget_and_exact_slide_count(self):
        text = build_prompt("Azure", 8, 4)
        for requirement in (
            "exactly 8 content slides",
            "60 characters",
            "80 characters",
            "60 body words",
            "3 columns",
            "4 data rows",
            "30 characters",
            "2–4 nodes",
            "not AI token limits",
        ):
            self.assertIn(requirement, text)
