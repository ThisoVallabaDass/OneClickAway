"""Regression coverage for readable original layouts and authored slide order."""

import unittest

from backend.catalog import PROFILES
from backend.design import assignments
from backend.models import DesignOptions
from backend.template_engine import (
    candidates,
    fitted_layout_sizes,
    fits,
    organize,
    plan_templates,
    readable_layouts,
    select_layout,
)


class LayoutQualityTests(unittest.TestCase):
    def slide(self, title="SAP Basis responsibilities", items=None, **fields):
        return dict(
            title=title,
            kind="content",
            items=items
            or [
                "System Administration: Configure and maintain SAP technical environments",
                "User Administration: Manage users, roles, authorizations, and access",
                "Transport Management: Move development changes across system landscapes",
                "Monitoring: Track system health, performance, jobs, and technical errors",
            ],
            **fields,
        )

    def measurements(self, slide, enhanced=True):
        result = {}
        for number in candidates(slide, enhanced):
            try:
                result[number] = fitted_layout_sizes(slide, number, "modern")
            except ValueError:
                pass
        return result

    def test_real_sap_rows_yield_to_larger_readable_original_slots(self):
        # These are the four responsibilities in KaarTech-Presentation (14).
        # All four old row slots fit, but they top out at 18pt while layout104
        # holds the same complete wording at 24pt without altering its artwork.
        for enhanced in (False, True):
            with self.subTest(enhanced=enhanced):
                slide = self.slide()
                measured = self.measurements(slide, enhanced)
                peers, sizes = readable_layouts(measured)
                self.assertEqual(sizes[97], 18)
                self.assertEqual(sizes[104], 24)
                self.assertNotIn(97, peers)
                chosen = select_layout(measured, [], False)
                self.assertEqual(chosen, 104)
                values = assignments(PROFILES[chosen], slide["title"], slide["items"])
                self.assertEqual(
                    [values[k] for k in PROFILES[chosen]["body"]], slide["items"]
                )

    def test_long_caption_labels_count_towards_readability(self):
        measured = self.measurements(self.slide())
        peers, sizes = readable_layouts(measured)
        self.assertIn(119, measured)  # Mere fit used to hide the squeezed labels.
        self.assertEqual(sizes[119], 17)
        self.assertNotIn(119, peers)
        self.assertIn(104, peers)

    def test_short_labels_keep_the_original_panel_layout_available(self):
        slide = self.slide(
            items=[
                "Platform: Cloud services.",
                "Reach: Global footprint.",
                "Hybrid: Connected environments.",
                "Governance: Enterprise controls.",
            ]
        )
        measured = self.measurements(slide)
        peers, _ = readable_layouts(measured)
        self.assertIn(119, peers)
        self.assertEqual(select_layout(measured, [], True), 119)

    def test_old_nonadjacent_use_does_not_exhaust_suitable_layouts(self):
        slide = self.slide(
            items=["One: First.", "Two: Second.", "Three: Third.", "Four: Fourth."]
        )
        measured = self.measurements(slide)
        recent = [104, 13]
        self.assertEqual(select_layout(measured, recent, True), 119)
        self.assertEqual(
            select_layout(measured, [119, 97, 119, 13] + recent, True), 119
        )
        history = []
        for _ in range(12):
            history.append(select_layout(measured, history, True))
        self.assertEqual(history, [119, 104, 13] * 4)
        self.assertNotIn(97, history)

    def test_three_topics_can_reuse_a_readable_layout_after_a_short_interval(self):
        slide = self.slide(
            items=[
                "Jobs: Review logs.",
                "Spool: Resolve output errors.",
                "Clients: Maintain client settings.",
            ]
        )
        for enhanced in (False, True):
            measured = self.measurements(slide, enhanced)
            history = []
            for _ in range(9):
                history.append(select_layout(measured, history, True))
            self.assertEqual(history, [77, 13, 16] * 3)
            self.assertTrue(all(n not in (69, 87, 114) for n in history))

    def test_fallback_remains_available_when_no_layout_can_reach_twenty_points(self):
        # Do not force a split or discard text solely to meet the preference.
        measured = {
            97: {"2": 28, "10": 18, "11": 18, "12": 18, "13": 18},
            13: {"2": 28, "3": 19},
        }
        self.assertEqual(select_layout(measured, [13], True), 13)
        self.assertEqual(select_layout({97: measured[97]}, [97], True), 97)

    def test_semantic_relations_and_evidence_keep_their_required_layouts(self):
        for specialized in (14, 17, 19, 20, 69, 87):
            with self.subTest(layout=specialized):
                p = PROFILES[specialized]
                measured = {
                    specialized: {p["title"]: 24, **{k: 16 for k in p["body"]}},
                    13: {"2": 28, "3": 22},
                }
                self.assertEqual(
                    select_layout(measured, [specialized] * 4, True), specialized
                )
        self.assertEqual(
            candidates(self.slide(table=[["Name", "Value"], ["A", "1"]]), True), [14]
        )
        self.assertEqual(
            candidates(
                self.slide(diagram={"nodes": ["A", "B"], "edges": [(0, 1)]}), True
            ),
            [20],
        )
        self.assertEqual(
            candidates(self.slide(image={"id": "user-picture"}), True), [19]
        )

    def test_hierarchy_and_genuine_contrast_remain_distinct(self):
        neutral = self.slide(
            items=["### Operations", "Review jobs.", "### Access", "Review users."]
        )
        contrast = self.slide(
            title="Current versus proposed",
            items=[
                "### Current",
                "Manual checks.",
                "### Proposed",
                "Scheduled checks.",
            ],
        )
        self.assertEqual(candidates(neutral, True), [16, 13])
        self.assertEqual(candidates(contrast, True), [17, 16, 13])
        self.assertFalse(fits(self.slide(items=["One: First."] * 3), 119, "modern"))

    def test_explicit_order_survives_story_completion_and_agenda_creation(self):
        body = [
            self.slide(title=title, items=[item])
            for title, item in [
                ("Introduction", "Context for the supplied sequence."),
                ("Deployment", "Schedule the maintenance window."),
                ("Identity", "Review administrator access."),
                ("Architecture", "Document the system components."),
                ("Conclusion", "The operating team owns these activities."),
            ]
        ]
        expected = [s["title"] for s in body]
        arranged = organize(body, "SAP Basis", [], preserve_order=True)
        self.assertEqual([s["title"] for s in arranged], expected)
        design = DesignOptions(human_touch=True, section_dividers=False)
        slides = plan_templates(
            "SAP Basis", body, design, [], [], lambda _: None, preserve_order=True
        )
        self.assertEqual(
            [
                s["title"]
                for s in slides
                if s["kind"] not in ("cover", "agenda", "closing")
            ],
            expected,
        )
        agenda = next(s for s in slides if s["kind"] == "agenda")
        self.assertEqual(
            [title for group in agenda["agenda_topics"] for title in group], expected
        )
        # Unstructured callers retain the existing role-based ordering.
        self.assertNotEqual(
            [s["title"] for s in organize(body, "SAP Basis", [])], expected
        )


if __name__ == "__main__":
    unittest.main()
