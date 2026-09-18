from typing import Literal
from pydantic import BaseModel, Field

Kind = Literal[
    "cover",
    "agenda",
    "content",
    "comparison",
    "timeline",
    "process",
    "architecture",
    "pointers",
    "goals",
    "metrics",
    "table",
    "closing",
    "section",
]


class DesignOptions(BaseModel):
    typography: Literal["modern", "corporate", "editorial"] = "modern"
    effects: Literal["subtle", "none"] = "subtle"
    unique_layouts: bool = True
    images: bool = False
    section_dividers: bool = True
    human_touch: bool = False
    agenda: bool = True
    complete_story: bool = True


class ImageRef(BaseModel):
    id: str = Field(pattern=r"^[a-f0-9]{64}$")
    title: str
    source_url: str
    license: str
    author: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class PicturePlacement(BaseModel):
    image: ImageRef
    target: str = Field(min_length=1, max_length=120)


class DiagramSpec(BaseModel):
    nodes: list[str] = Field(min_length=2, max_length=6)
    edges: list[tuple[int, int]] = Field(default_factory=list, max_length=12)
    descriptions: list[str] = Field(default_factory=list, max_length=6)


class TemplateRef(BaseModel):
    id: str = Field(pattern=r"^KTC-L\d{3}$")
    name: str
    number: int = Field(ge=1, le=999)
    source_slides: list[int] = []


class SlidePlan(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    kind: Kind
    items: list[str] = Field(default_factory=list, max_length=12)
    source_text: str = Field(default="", max_length=60000)
    selection_reason: str = Field(default="", max_length=2000)
    agenda_topics: list[list[str]] = Field(default_factory=list, max_length=8)
    # The top-level heading this slide sits under, when the document has section dividers.
    section: str | None = Field(default=None, max_length=120)
    template: TemplateRef
    table: list[list[str]] | None = None
    generated_draft: bool = False
    image: ImageRef | None = None
    diagram: DiagramSpec | None = None
    layout_variant: str | None = Field(default=None, pattern=r"^v\d{3}$")
    composition: (
        Literal[
            "cover",
            "closing",
            "section",
            "agenda",
            "reading",
            "focus",
            "comparison",
            "steps",
            "image",
            "table",
            "diagram",
            "catalog",
            "grouped",
        ]
        | None
    ) = None
    citations: list[str] = Field(default_factory=list, max_length=12)


class DeckPlan(BaseModel):
    template_engine: int = 0
    title: str = Field(min_length=1, max_length=500)
    slides: list[SlidePlan] = Field(min_length=2, max_length=150)
    warnings: list[str] = []
    planner: str = "deterministic"
    source_kind: str = "user_content"
    design: DesignOptions = Field(default_factory=DesignOptions)
