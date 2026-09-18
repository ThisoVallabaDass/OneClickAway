import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from backend.planner import plan_deck, chunks
from backend.models import DeckPlan
from backend.exporter import generate_deck
from backend.ooxml import NS, parse
from backend.design import label_parts


class RefinementTests(unittest.TestCase):
    def plan(self, content, **design):
        with patch("backend.planner.search", return_value=[]):
            return plan_deck(
                "GCP",
                content,
                use_ai=False,
                design={
                    "section_dividers": False,
                    "unique_layouts": False,
                    "agenda": False,
                    "complete_story": False,
                    **design,
                },
                progress=lambda _: None,
            )

    def test_default_story_and_one_optional_agenda(self):
        content = "## Compute\nOne fact.\n## Storage\nAnother fact."
        for human in (False, True):
            p = self.plan(content, human_touch=human, agenda=True, complete_story=True)
            self.assertEqual(len([s for s in p["slides"] if s["kind"] == "agenda"]), 1)
            self.assertEqual(p["slides"][2]["title"], "Introduction")
            self.assertFalse(any(s["title"] == "Key takeaways" for s in p["slides"]))
            self.assertTrue(
                any("author-written conclusion" in w for w in p["warnings"])
            )
            self.assertEqual(p["slides"][1]["template"]["number"], 35)
            self.assertEqual(len(self.plan(content, human_touch=human)["slides"]), 4)

    def test_glued_heading_is_recovered(self):
        p = chunks(
            "## Costs\nReview requirements.## Infrastructure\nRegions and zones.", "GCP"
        )
        self.assertEqual([s["title"] for s in p], ["Costs", "Infrastructure"])
        self.assertEqual(p[0]["items"], ["Review requirements."])

    def test_repetition_is_removed_but_distinct_facts_survive(self):
        p = self.plan(
            "## Compute\nA fact.\n## Compute\nA fact.\n## Compute\nAnother fact."
        )
        self.assertEqual(
            [s["items"] for s in p["slides"][1:-1]], [["A fact."], ["Another fact."]]
        )
        self.assertTrue(any("exact duplicate" in w for w in p["warnings"]))

    def test_catalogue_is_not_an_invented_pipeline(self):
        for human in (False, True):
            p = self.plan(
                "## Big Data Processing\n**BigQuery:** Query data.\n**Dataflow:** Transform streams.\n**Dataproc:** Run Spark.",
                human_touch=human,
            )
            self.assertFalse(p["slides"][1]["diagram"])
        self.assertEqual(p["slides"][1]["template"]["number"], 77)
        self.assertIsNone(p["slides"][1]["composition"])
        self.assertEqual(
            label_parts("**BigQuery:** Query **reviewed** data."),
            ("BigQuery", ":", "Query **reviewed** data."),
        )

    def test_related_database_groups_stay_on_one_slide(self):
        p = self.plan(
            "## Databases\n### Relational\nCloud SQL: Managed engines.\nSpanner: Distributed SQL.\n### Non-relational\nFirestore: Documents.\nBigtable: Wide columns.",
            human_touch=True,
        )
        self.assertEqual(len(p["slides"]), 3)
        self.assertEqual(p["slides"][1]["template"]["number"], 16)

    def test_numbered_stages_keep_their_explanations(self):
        p = self.plan(
            "## Migration\nStage 1 — Assess: Inventory applications.\nStage 2 — Prepare: Set up the foundation.\nStage 3 — Move: Transfer and validate.\nStage 4 — Optimize: Review usage.",
            human_touch=True,
        )
        self.assertEqual(p["slides"][1]["template"]["number"], 69)
        self.assertEqual(len(p["slides"]), 3)

    def test_export_keeps_artwork_without_sample_date_or_raw_markdown(self):
        p = self.plan(
            "## Compute\n**Compute Engine:** Run virtual machines.\n**Cloud Run:** Run containers.",
            human_touch=True,
        )
        p["slides"][1]["citations"] = ["https://cloud.google.com/products"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "result.pptx"
            generate_deck(DeckPlan.model_validate(p), path)
            with ZipFile(path) as z:
                for i in range(1, 4):
                    root = parse(z.read(f"ppt/slides/generated{i}.xml"))
                    text = " ".join(root.xpath("//a:t/text()", namespaces=NS))
                    self.assertNotIn("**", text)
                    self.assertNotIn("August 2024", text)
                cover = parse(z.read("ppt/slides/generated1.xml"))
                self.assertGreater(len(list(cover.find("p:cSld/p:spTree", NS))), 5)
                self.assertIn(
                    "https://cloud.google.com/products",
                    z.read("ppt/notesSlides/generated2.xml").decode(),
                )
