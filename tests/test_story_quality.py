import unittest

from backend.models import DeckPlan
from backend.planner import plan_deck
from backend.quality import heading_case


class StoryQualityTests(unittest.TestCase):
    def plan(self, content):
        return DeckPlan.model_validate(
            plan_deck(
                "SAP Basis",
                content,
                use_ai=False,
                design={"human_touch": True, "section_dividers": False},
                progress=lambda _: None,
            )
        )

    def test_authored_story_keeps_the_sequence_of_its_middle_slides(self):
        for heading in ("## {title}", "Slide {n} — {title}"):
            titles = [
                "Introduction",
                "Security controls",
                "System architecture",
                "Delivery roadmap",
                "Daily operations",
                "Conclusion",
            ]
            content = "\n\n".join(
                heading.format(n=i, title=title)
                + "\n- Distinct supplied detail "
                + str(i)
                + "."
                for i, title in enumerate(titles, 1)
            )
            plan = self.plan(content)
            self.assertEqual([s.title for s in plan.slides[2:-1]], titles)
            self.assertEqual(plan.slides[1].items, titles)

    def test_prompt_uncertainty_labels_stay_in_notes(self):
        plan = self.plan(
            "## Introduction\n- SAP Basis supports system administration.\n"
            "- To verify: The team operates 80 systems.\n"
            "- **Assumption:** Production uses this topology.\n"
            "## Conclusion\n- Confirm access before releasing changes."
        )
        visible = "\n".join(x for s in plan.slides for x in s.items)
        notes = "\n".join(s.source_text for s in plan.slides)
        self.assertNotIn("80 systems", visible)
        self.assertNotIn("this topology", visible)
        self.assertIn("80 systems", notes)
        self.assertIn("this topology", notes)
        self.assertIn("supports system administration", visible)

    def test_ordinary_verification_and_examples_remain_visible(self):
        plan = self.plan(
            "## Introduction\n- Verification: Check the import results.\n"
            "- Illustrative example: A failed job needs investigation.\n"
            "## Conclusion\n- Review failed imports before proceeding."
        )
        visible = "\n".join(x for s in plan.slides for x in s.items)
        self.assertIn("Verification:", visible)
        self.assertIn("Illustrative example:", visible)

    def test_sap_product_names_survive_sentence_case(self):
        self.assertEqual(
            heading_case("SAP BASIS RESPONSIBILITIES"), "SAP Basis responsibilities"
        )
        self.assertEqual(heading_case("SAP GUI and SAP Fiori"), "SAP GUI and SAP Fiori")


if __name__ == "__main__":
    unittest.main()
