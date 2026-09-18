"""Generate the company capabilities example through the normal application engine."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.planner import plan_deck
from backend.models import DeckPlan
from backend.exporter import generate_deck

content = Path("tests/fixtures/kaartech-capabilities.md").read_text(encoding="utf-8")
plan = DeckPlan.model_validate(
    plan_deck(
        "KaarTech",
        content,
        use_ai=False,
        design={"human_touch": True, "section_dividers": False},
        progress=lambda _: None,
    )
)
output = Path("output/KaarTech-Capabilities-Upgraded.pptx")
print(generate_deck(plan, output))
output.with_suffix(".json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
