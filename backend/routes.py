"""HTTP routes; generation and queue execution live in dedicated services."""

import uuid
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from .config import ROOT, GENERATED as OUTPUT, TEMPLATE
from . import local_ai
from .models import DesignOptions, PicturePlacement
from .job_store import QueueFull

router = APIRouter()


@router.get("/api/live")
def live():
    return {"status": "ok"}


@router.get("/api/ready")
def ready():
    if not TEMPLATE.is_file():
        raise HTTPException(503, "The presentation template has not been configured.")
    return {"status": "ready"}


def enqueue(request, kind, payload, images):
    try:
        ident = request.app.state.store.enqueue(
            request.state.owner, kind, payload, images
        )
    except QueueFull as exc:
        raise HTTPException(429, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"id": ident}


class PlanRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=500)
    content: str = Field(default="", max_length=60000)
    use_ai: bool = True
    allow_draft: bool = False
    design: DesignOptions = Field(default_factory=DesignOptions)
    pictures: list[PicturePlacement] = Field(default_factory=list, max_length=12)


@router.get("/")
def home():
    return FileResponse(ROOT / "static/index.html")


@router.get("/api/health")
def health():
    try:
        from .catalog import stats

        catalog = stats()
    except ImportError:
        catalog = {"documents": 0, "slides": 0, "layouts": 0}
    return {
        "template_present": TEMPLATE.exists(),
        "catalog": catalog,
        "ai": local_ai.status(),
    }


@router.post("/api/plan")
def plan(body: PlanRequest, request: Request):
    if not body.prompt.strip():
        raise HTTPException(422, "Enter a presentation topic.")
    if not body.content.strip() and not body.allow_draft:
        raise HTTPException(422, "Paste your content, or enable drafting from a topic.")
    return enqueue(
        request, "plan", body.model_dump(), [p.image.id for p in body.pictures]
    )


@router.post("/api/generate")
async def generate(request: Request):
    raw = await request.body()
    if len(raw) > 1_000_000:
        raise HTTPException(413, "The presentation outline is too large.")
    try:
        from .models import DeckPlan

        plan = DeckPlan.model_validate_json(raw)
    except ValueError as exc:
        raise HTTPException(422, "Invalid outline: " + str(exc)) from exc
    return enqueue(
        request,
        "generate",
        plan.model_dump(),
        [s.image.id for s in plan.slides if s.image],
    )


@router.get("/api/jobs/{ident}")
def get_job(ident: str, request: Request):
    state = request.app.state.store.get(ident, request.state.owner)
    if state is None:
        raise HTTPException(404, "Job not found or expired.")
    return state


@router.get("/api/download/{ident}")
def download(ident: str, request: Request):
    try:
        ident = uuid.UUID(ident).hex
    except ValueError:
        raise HTTPException(404, "Presentation not found.")
    if not request.app.state.store.owns("deck", ident, request.state.owner):
        raise HTTPException(404, "Presentation not found or expired.")
    path = OUTPUT / (ident + ".pptx")
    if not path.exists():
        raise HTTPException(404, "Presentation not found.")
    return FileResponse(
        path,
        filename="OneClick-Away-Presentation.pptx",
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


@router.get("/api/templates/search")
def search(q: str = ""):
    from .catalog import search as find

    return {"results": find(q[:500], limit=12)}


@router.get("/api/images/{ident}")
def get_image(ident: str, request: Request):
    import re
    from .images import ASSETS

    if not request.app.state.store.owns("image", ident, request.state.owner):
        raise HTTPException(404, "Image not found or expired.")
    if (
        not re.fullmatch("[a-f0-9]{64}", ident)
        or not (ASSETS / (ident + ".img")).is_file()
    ):
        raise HTTPException(404, "Image not found")
    return FileResponse(
        ASSETS / (ident + ".img"),
        media_type="image/jpeg"
        if (ASSETS / (ident + ".img")).read_bytes()[:2] == b"\xff\xd8"
        else "image/png",
    )


@router.post("/api/images/upload")
async def upload_image(request: Request):
    from .images import save_upload

    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 8_000_000:
            raise HTTPException(413, "Choose a PNG or JPEG smaller than 8 MB.")
    try:
        record = request.app.state.store.save_image(
            request.state.owner,
            lambda: save_upload(
                bytes(data), request.query_params.get("name", "Uploaded picture")
            ),
        )
        return record
    except QueueFull as exc:
        raise HTTPException(429, str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


class AIRequest(BaseModel):
    provider: str = Field(pattern="^(chatgpt|claude|gemini)$")
    topic: str = Field(min_length=1, max_length=500)
    slides: int = Field(default=8, ge=2, le=30)
    lines: int = Field(default=4, ge=2, le=5)


@router.post("/api/ai/prompt")
def ai_prompt(body: AIRequest):
    from .prompts import build_prompt

    if not body.topic.strip():
        raise HTTPException(422, "Enter a presentation topic first.")
    return {"prompt": build_prompt(body.topic, body.slides, body.lines)}


@router.post("/api/ai/generate")
def ai_generate():
    raise HTTPException(
        410,
        "Browser automation has been removed. Refresh the studio, copy your prompt, and paste the AI response manually.",
    )
