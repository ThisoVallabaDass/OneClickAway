"""Rebuild the reviewed SAP Basis example using the application engine."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.models import DeckPlan, DiagramSpec, TemplateRef
from backend.planner import plan_deck, template_ref
from backend.exporter import generate_deck

LEARNING = "https://learning.sap.com/courses/"
OPERATIONS = (
    LEARNING
    + "technical-implementation-and-operation-ii-of-sap-s-4hana-and-sap-business-suite/"
)
FUNDAMENTALS = (
    LEARNING
    + "technical-implementation-and-operation-i-of-sap-s-4hana-and-sap-business-suite/"
)
SOURCES = [
    [FUNDAMENTALS + "describing-as-abap"],
    [FUNDAMENTALS + "describing-as-abap", OPERATIONS + "sap-system-landscape-1"],
    [
        LEARNING
        + "introducing-sap-abap-platform-fundamentals/defining-the-abap-platform-landscape"
    ],
    [OPERATIONS + "sap-system-landscape-1"],
    [
        OPERATIONS + name
        for name in (
            "monitoring-background-processing-1",
            "monitoring-and-troubleshooting-printing-issues-1",
            "client-copy-and-client-transport-tools-1",
        )
    ],
    [FUNDAMENTALS + "describing-as-abap"],
    [
        OPERATIONS + "system-landscape-options-1",
        OPERATIONS + "setting-up-the-transport-management-system-tms--1",
    ],
    [OPERATIONS + "sap-system-landscape-1"],
]
NOTES = [
    "Scope: introductory administration of ABAP-based SAP systems. Task ownership across Basis, security and infrastructure teams depends on the operating model.",
    "Administration, change control and operational support overlap in practice. Responsibilities depend on the operating model.",
    "Three logical tiers. Presentation communicates with application services; application services access the database. Requests and responses travel across these connections. Each logical tier may span multiple physical machines. Basis is an administration discipline across the environment.",
    "This table illustrates a standard three-system arrangement. Larger or different landscapes are possible. DEV, QAS and PRD are illustrative system identifiers.",
    "Examples of routine technical administration. Job logs, output errors and client settings support investigation and maintenance.",
    "Monitoring supports investigation; it does not by itself guarantee availability. Authorization ownership depends on the organization.",
    "Example with a quality gate. TMS can configure quality assurance approval before delivery to subsequent systems. Approval steps and owners depend on organizational policy and configuration. Respect import order and dependencies.",
    "Editorial synthesis of the preceding slides. The final point is a suggested discussion activity, not an empirical claim.",
]


def build(destination):
    content = (ROOT / "tests/fixtures/sap-basis-refined.md").read_text(encoding="utf-8")
    plan = DeckPlan.model_validate(
        plan_deck(
            "SAP Basis",
            content,
            use_ai=False,
            design={
                "human_touch": True,
                "section_dividers": False,
                "complete_story": False,
            },
            progress=lambda _: None,
        )
    )
    body = [s for s in plan.slides if s.kind not in ("cover", "agenda", "closing")]
    if len(body) != 8:
        raise ValueError(
            f"The reviewed example requires 8 content slides, received {len(body)}."
        )
    for index, slide in enumerate(body):
        slide.citations = SOURCES[index]
        slide.source_text += "\n\nPresenter context:\n" + NOTES[index]
    architecture = body[2]
    architecture.diagram = DiagramSpec(
        nodes=["Presentation", "Application", "Database"],
        edges=[(0, 1), (1, 2)],
        descriptions=[item.split(":", 1)[1].strip() for item in architecture.items],
    )
    architecture.template = TemplateRef.model_validate(template_ref(20))
    architecture.kind = "architecture"
    # Close with a calm reading layout so the recommended next review stands
    # out, while the routine-administration page retains the template artwork.
    body[-1].template = TemplateRef.model_validate(template_ref(13))
    result = generate_deck(plan, destination)
    destination.with_suffix(".json").write_text(
        plan.model_dump_json(indent=2), encoding="utf-8"
    )
    print(result)
    print([(s.title, s.template.number) for s in plan.slides])
    return plan


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=ROOT / "output/SAP-Basis-Engine-Example.pptx"
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    build(args.output)
