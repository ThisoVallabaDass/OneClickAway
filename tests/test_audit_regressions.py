import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from backend.config import TEMPLATE
from backend.models import DeckPlan
from backend.planner import plan_deck
from backend.exporter import generate_deck, validate_package
from backend.editorial import subject
from backend.ooxml import NS, parse


class AuditRegressions(unittest.TestCase):
    def plan(self, content, human=False):
        return DeckPlan.model_validate(
            plan_deck(
                "Azure",
                content,
                use_ai=False,
                design={"human_touch": human, "section_dividers": False},
                progress=lambda _: None,
            )
        )

    def test_actual_original_layouts_are_bound_and_unmodified(self):
        plan = self.plan(
            "## Introduction\nA: First.\nB: Second.\nC: Third.\nD: Fourth.\n## Migration\nStage 1 — Assess: Review.\nStage 2 — Plan: Choose.\nStage 3 — Move: Validate.\n## Conclusion\nA reviewed conclusion.",
            True,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deck.pptx"
            generate_deck(plan, path)
            names = []
            with ZipFile(path) as z, ZipFile(TEMPLATE) as original:
                for index, planned in enumerate(plan.slides, 1):
                    part = f"ppt/slideLayouts/slideLayout{planned.template.number}.xml"
                    rels = parse(z.read(f"ppt/slides/_rels/generated{index}.xml.rels"))
                    binding = [
                        r.get("Target")
                        for r in rels
                        if r.get("Type", "").endswith("/slideLayout")
                    ]
                    self.assertEqual(
                        binding,
                        [f"../slideLayouts/slideLayout{planned.template.number}.xml"],
                    )
                    name = parse(z.read(part)).find("p:cSld", NS).get("name")
                    self.assertEqual(name, planned.template.name)
                    names.append(name)
                    self.assertEqual(z.read(part), original.read(part))
                    root = parse(z.read(f"ppt/slides/generated{index}.xml"))
                    for body in root.findall(".//p:txBody", NS):
                        self.assertTrue(
                            "".join(body.xpath(".//a:t/text()", namespaces=NS)).strip()
                        )
                    self.assertTrue(
                        all(
                            n.isascii()
                            for n in root.xpath("//p:cNvPr/@name", namespaces=NS)
                        )
                    )
                    self.assertNotIn(
                        b"Source template slides:",
                        z.read(f"ppt/notesSlides/generated{index}.xml"),
                    )
            self.assertGreater(len(set(names)), 3)
            with self.assertRaisesRegex(ValueError, "not bound"):
                validate_package(path, len(plan.slides), [13] * len(plan.slides))

    def test_pointer_circle_fields_are_filled_and_unused_cover_title_is_dropped(self):
        p = self.plan(
            "## Introduction\nOne.\nTwo.\nThree.\nFour.\n## Conclusion\nReviewed findings."
        )
        # Exercise the row exporter explicitly; automatic planning now prefers
        # the original 24pt content blocks over these 18pt numbered rows.
        from backend.models import TemplateRef
        from backend.planner import template_ref

        p.slides[2].template = TemplateRef.model_validate(template_ref(97))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deck.pptx"
            generate_deck(p, path)
            with ZipFile(path) as z:
                root = parse(z.read("ppt/slides/generated3.xml"))
                for ident, number in zip(("4", "6", "7", "8"), ("1", "2", "3", "4")):
                    fields = root.xpath(
                        '//p:sp[p:nvSpPr/p:cNvPr[@id="' + ident + '"]]', namespaces=NS
                    )
                    self.assertEqual(
                        "".join(fields[0].xpath(".//a:t/text()", namespaces=NS)), number
                    )
                    self.assertEqual(
                        fields[0].find("p:txBody/a:bodyPr", NS).get("anchor"), "ctr"
                    )
                    self.assertEqual(
                        fields[0].find("p:txBody/a:p/a:pPr", NS).get("algn"), "ctr"
                    )
                self.assertFalse(
                    root.xpath(
                        '//p:sp[p:nvSpPr/p:cNvPr[@name="Text Placeholder 14"]]',
                        namespaces=NS,
                    )
                )
                cover = parse(z.read("ppt/slides/generated1.xml"))
                self.assertEqual(
                    len(
                        cover.xpath(
                            '//p:cNvPr[starts-with(@name,"Title")]', namespaces=NS
                        )
                    ),
                    1,
                )

    def test_duplicate_service_names_merge_without_dropping_details(self):
        p = self.plan(
            "## Cloud storage\nAzure Blob Storage manages archive tiers.\nAzure Files provides SMB shares.\n## Storage options\nBlob Storage supports analytics datasets.\nAzure Files offers NFS access.\nDisk Storage provides block storage."
        )
        storage = [s for s in p.slides if "Storage —" in s.title]
        self.assertEqual(len(storage), 1)
        self.assertEqual(len(storage[0].items), 3)
        text = " ".join(storage[0].items)
        for fact in (
            "archive tiers",
            "analytics datasets",
            "SMB shares",
            "NFS access",
            "block storage",
        ):
            self.assertIn(fact, text)

    def test_cloud_qualifiers_remain_distinct(self):
        p = self.plan(
            "## Azure compute\nAzure Functions runs event workloads.\n## AWS compute\nAWS Lambda runs serverless functions."
        )
        text = " ".join(x for s in p.slides for x in s.items)
        self.assertIn("Azure Functions", text)
        self.assertIn("AWS Lambda", text)

    def test_product_hosts_is_not_misread_as_a_verb(self):
        self.assertEqual(
            subject("Azure Dedicated Hosts provide physical isolation.")[1],
            "Azure Dedicated Hosts",
        )

    def test_audited_input_has_one_section_per_topic_and_new_conclusion(self):
        source = (Path(__file__).parent / "fixtures/azure-audited.md").read_text(
            encoding="utf-8"
        )
        for human in (False, True):
            p = self.plan(source, human)
            self.assertEqual(len(p.slides), 15)
            self.assertEqual(sum(s.kind == "agenda" for s in p.slides), 1)
            for family in (
                "Compute",
                "Storage",
                "Databases",
                "Networking",
                "Identity and governance",
            ):
                sections = [s for s in p.slides if s.title.startswith(family + " —")]
                self.assertEqual(len(sections), 1)
                subjects = [subject(x)[0] for x in sections[0].items if subject(x)[0]]
                self.assertEqual(len(subjects), len(set(subjects)))
            conclusion = p.slides[-2]
            self.assertEqual(conclusion.title, "Conclusion")
            self.assertEqual(len(conclusion.items), 3)
            previous = [x for s in p.slides[:-2] for x in s.items]
            self.assertFalse(any(x in previous for x in conclusion.items))
            self.assertFalse(
                any("Stage 1" in x or "(Assumption)" in x for x in conclusion.items)
            )
            self.assertIn("Editorial synthesis", conclusion.source_text)
            self.assertFalse(
                any("(Assumption)" in x for s in p.slides for x in s.items)
            )
            self.assertTrue(any("(Assumption)" in s.source_text for s in p.slides))
            for s in p.slides:
                if s.kind not in ("cover", "agenda", "closing"):
                    self.assertIn("selected original layout", s.selection_reason)
