"""Rebuild the audited deck's input through the normal planner in both modes."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.planner import plan_deck
from backend.models import DeckPlan
from backend.exporter import generate_deck

source = Path("output/0dedc9a6271e4de1a775d36755e64851.json")
old = json.loads(source.read_text(encoding="utf-8"))
sections = []
for slide in old["slides"]:
    if slide["kind"] in ("cover", "agenda", "closing"):
        continue
    if "Takeaways selected verbatim" in slide["source_text"]:
        continue
    # Recover source items, retaining the original table and all repeated topics.
    content = "\n".join(slide["items"])
    if slide.get("table"):
        rows = slide["table"]
        content = "\n".join(
            [
                "| " + " | ".join(rows[0]) + " |",
                "| " + " | ".join(["---"] * len(rows[0])) + " |",
            ]
            + ["| " + " | ".join(row) + " |" for row in rows[1:]]
        )
    sections.append("## " + slide["title"] + "\n" + content)
content = "\n\n".join(sections)
Path("output/Azure-Audited-Source.md").write_text(content, encoding="utf-8")
for human in (False, True):
    mode = "Enhanced" if human else "Standard"
    plan = DeckPlan.model_validate(
        plan_deck(
            old["title"],
            content,
            use_ai=False,
            design={**old["design"], "human_touch": human},
            progress=lambda _: None,
        )
    )
    result = generate_deck(plan, Path(f"output/Azure-{mode}-Corrected.pptx"))
    Path(f"output/Azure-{mode}-Corrected.json").write_text(
        plan.model_dump_json(indent=2), encoding="utf-8"
    )
    print(mode, result)
    for i, s in enumerate(plan.slides, 1):
        print(i, s.template.number, s.title, len(s.items))
    print("WARNINGS", plan.warnings)
