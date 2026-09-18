"""Plan inside verified company layouts; decoration never determines semantics."""

import re
from .catalog import PROFILES, get_layout
from .design import (
    assignments,
    fitted_size,
    geometry_override,
    text_treatment,
    label_parts,
)
from .richtext import parse_item, plain_text, is_structured


def branded_text(value):
    for pattern, replacement in [
        (r"\bazure\b", "Azure"),
        (r"\bkaar\s*tech\b", "KaarTech"),
        (r"\bgcp\b", "GCP"),
        (r"\baws\b", "AWS"),
    ]:
        value = re.sub(pattern, replacement, value, flags=re.I)
    return value


def role(slide):
    title = slide["title"].lower()
    if re.search(r"conclusion|takeaway|next steps|recommendation|closing", title):
        return "conclusion"
    if re.search(
        r"introduction|overview|strategic role|what is|what are|fundamentals", title
    ):
        return "introduction"
    if re.search(
        r"lifecycle|life cycle|migration|roadmap|implementation|adoption|deployment|stages",
        title,
    ):
        return "delivery"
    if slide.get("diagram"):
        return "architecture"
    if re.search(r"security|governance|identity|risk|compliance", title):
        return "governance"
    if slide.get("table") or slide["kind"] == "comparison":
        return "options"
    return "concepts"


def labelled(item):
    """Expose a supplied subject as a label, preserving every word and qualifier."""
    if parse_item(item)["role"] != "bullet" or parse_item(item)["level"]:
        return item
    label, sep, desc = label_parts(item)
    if sep:
        return item
    # Only split a short subject from a finite verb. No model-written summary.
    from .editorial import VERBS

    match = re.match(r"^(.{3,38}?)\s+((?:" + VERBS + r")\b.+)$", item)
    return f"**{match[1]}:** {match[2]}" if match else item


def organize(body, prompt, warnings, complete=True, preserve_order=False):
    from .editorial import consolidate, synthesize
    from .quality import heading_case

    body = [
        dict(
            s,
            title=heading_case(branded_text(s["title"])),
            section=heading_case(s["section"]) if s.get("section") else None,
            items=[
                "### " + heading_case(parse_item(x)["plain"])
                if parse_item(x)["role"] == "subheading"
                else branded_text(x)
                for x in s["items"]
            ],
        )
        for s in body
    ]
    # An AI-supplied agenda/thank-you is replaced by the single generated one.
    body = [
        s
        for s in body
        if not re.fullmatch(r"agenda|table of contents|thank\s*you", s["title"], re.I)
    ]
    body, withheld = consolidate(body, warnings)
    if not body:
        return body
    if complete:
        introductions = [
            s for s in body if role(s) == "introduction" and s["kind"] != "section"
        ]
        conclusions = [
            s for s in body if role(s) == "conclusion" and s["kind"] != "section"
        ]
        middle = [s for s in body if s not in introductions and s not in conclusions]
        # Keep chapter blocks intact, and preserve the supplied order within them.
        if not preserve_order and not any(s.get("section") for s in middle):
            rank = {
                "concepts": 0,
                "options": 1,
                "architecture": 2,
                "governance": 3,
                "delivery": 4,
            }
            middle.sort(key=lambda s: rank.get(role(s), 0))
        had_introduction = bool(introductions)
        had_conclusion = bool(conclusions)
        if not introductions:
            headings = list(
                dict.fromkeys(
                    s["title"].removesuffix(" (continued)")
                    for s in body
                    if s["kind"] != "section"
                )
            )
            items = [f"Topic: {branded_text(prompt)}"] + [
                "Scope: " + x for x in headings[:3]
            ]
            introductions = [
                dict(
                    title="Introduction",
                    kind="content",
                    items=items,
                    source_text="Overview assembled from supplied headings.",
                )
            ]
        if not conclusions:
            conclusion = synthesize(body)
            if conclusion:
                conclusions = [conclusion]
            else:
                warnings.append(
                    "Add an author-written conclusion. These notes do not support a reliable synthesis, so no sampled takeaways slide was inserted."
                )
        if preserve_order:
            body = (
                ([] if had_introduction else introductions)
                + body
                + ([] if had_conclusion else conclusions)
            )
        else:
            body = introductions + middle + conclusions
    return body


def fitted_layout_sizes(s, n, style, human=False):
    """Measure the same populated slots and typography used by the exporter."""
    p = PROFILES[n]
    if p.get("exact") and len(s["items"]) != p["exact"]:
        raise ValueError("This layout needs every original content slot populated.")
    if s.get("table"):
        from .tables import table_layout

        table_layout(s["table"], style, human)
    values = assignments(p, s["title"], s["items"])
    slots = {v["shape_id"]: v["geometry"] for v in get_layout(n)["slots"]}
    sizes = {}
    for ident, value in values.items():
        bounds = geometry_override(
            n, ident, slots.get(ident, [450000, 190000, 11200000, 700000]), p
        )
        treatment = text_treatment(n, p, ident, style, s["items"])
        sizes[ident] = fitted_size(
            bounds,
            value,
            treatment["preferred"],
            treatment["minimum"],
            treatment["family"],
            treatment["bullets"],
            structural=ident != p["title"] and ident not in p.get("labels", []),
            paragraph_after=treatment["paragraph_after"],
        )
    return sizes


def fits(s, n, style, human=False):
    try:
        fitted_layout_sizes(s, n, style, human)
        return True
    except ValueError:
        return False


def readable_layouts(measured):
    """Keep comparable neutral layouts before considering visual repetition.

    An 18pt row fitting is not a reason to ignore a 22pt text layout. At the
    same time, a 20pt panel remains a useful peer of a 24pt content block.
    Labels count too: squeezing a long subject into a caption is not a win.
    """
    scores = {}
    for n, sizes in measured.items():
        p = PROFILES[n]
        content = p["body"] + p.get("labels", [])
        scores[n] = min(
            (sizes[k] for k in content if k in sizes), default=sizes.get(p["title"], 20)
        )
    floor = min(20, max(scores.values()))
    return [n for n in measured if scores[n] >= floor], scores


def select_layout(measured, history, vary):
    # These layouts encode an explicit relation or required evidence. Their
    # semantic meaning takes precedence over neutral text with larger letters.
    first = next(iter(measured))
    if first in (14, 17, 19, 20, 69, 87):
        return first
    peers, _ = readable_layouts(measured)
    if not vary:
        return peers[0]
    # Reuse suitable layouts after a short interval. A layout used earlier in
    # the deck never becomes permanently unavailable or forces a tiny fallback.
    recent = history[-2:]
    return min(
        peers,
        key=lambda n: (
            recent.count(n),
            n == history[-1] if history else False,
            peers.index(n),
        ),
    )


def candidates(s, enhanced):
    from .human_design import groups_for
    from .planner import explicit_steps
    from .quality import explicit_contrast

    if s.get("table"):
        return [14]
    if s.get("diagram"):
        return [20]
    if s.get("image"):
        return [19]
    lead, groups = groups_for(s["items"])
    if len(groups) == 2 and not lead and all(g[1] for g in groups):
        return [17, 16, 13] if explicit_contrast(s) else [16, 13]
    if is_structured(s["items"]):
        return [13, 16]
    count = len(s["items"])
    pairs = all(label_parts(x)[1] for x in s["items"])
    if count == 2 and pairs and explicit_contrast(s):
        return [17, 16, 13]
    if explicit_steps(s) and 2 <= count <= 5:
        return [69, 13]
    if (
        re.search(
            r"\blifecycle\b|life cycle|feedback loop|continuous cycle", s["title"], re.I
        )
        and count == 4
        and pairs
    ):
        return [87, 104, 13]
    if enhanced:
        if count == 2 and pairs:
            return [13, 16]
        if count == 3:
            return [77, 13, 16]
        if count == 4:
            return ([119, 104, 97] if pairs else [104, 97]) + [13]
        if count == 5 and pairs:
            return [153, 16, 13]
        if count == 6:
            return [99, 16, 13]
    # Neutral company infographics also serve standard mode. Eligibility is
    # based on content structure, not a blanket Content Slide fallback.
    if count == 3:
        return [77, 13, 16]
    if count == 4:
        return [97, 104, 13, 16]
    if count == 5 and pairs:
        return [153, 13, 16]
    if count == 6:
        return [99, 13, 16]
    return [13, 16]


def make_agenda(body, style):
    from .planner import template_ref
    from .quality import agenda_titles

    titles = agenda_titles(body)
    if not titles:
        return None
    groups = [[x] for x in titles]

    def caption(group):
        return " / ".join(
            re.sub(r" — services and capabilities$", "", x) for x in group
        )

    # Merge adjacent short topics only when the largest verified agenda is full.
    # Every actual topic stays represented, in final deck order.
    while len(groups) > 8:
        at = min(
            range(len(groups) - 1),
            key=lambda i: len(caption(groups[i] + groups[i + 1])),
        )
        groups[at : at + 2] = [groups[at] + groups[at + 1]]
    for n in [35, 32, 37] if len(groups) <= 5 else [32, 37]:
        if n == 37 and len(groups) > 7:
            at = min(
                range(len(groups) - 1),
                key=lambda i: len(caption(groups[i] + groups[i + 1])),
            )
            groups[at : at + 2] = [groups[at] + groups[at + 1]]
        slide = dict(
            title="Agenda",
            kind="agenda",
            items=[caption(g) for g in groups],
            agenda_topics=groups,
            source_text="Agenda generated from final slide headings.\n"
            + "\n".join(titles),
            template=template_ref(n),
            selection_reason=f"{len(groups)} populated topic rows from {len(titles)} actual headings; selected original layout {n}.",
        )
        if fits(slide, n, style):
            return slide
    raise ValueError(
        "The agenda headings are too long for one readable slide. Shorten the topic titles or turn off the agenda."
    )


def plan_templates(
    prompt, body, design, pictures, warnings, progress, preserve_order=False
):
    from .planner import template_ref, cover_title, section_layout, report
    from .human_design import place_pictures
    from .editorial import UNCERTAIN

    withheld = [x for s in body for x in s["items"] if UNCERTAIN.search(plain_text(x))]
    body = organize(body, prompt, warnings, design.complete_story, preserve_order)
    cover_source = prompt + (
        "\nUnverified source statements withheld from visible slides:\n"
        + "\n".join(withheld)
        if withheld
        else ""
    )
    slides = [
        dict(
            title=cover_title(branded_text(prompt), body),
            kind="cover",
            items=[],
            source_text=cover_source,
            template=template_ref(180),
        )
    ]
    if design.agenda:
        agenda = make_agenda(body, design.typography)
        if agenda:
            slides.append(agenda)
    pending = list(body)
    history = []
    reused = False
    sections = 0
    while pending:
        s = dict(pending.pop(0))
        s.pop("composition", None)
        s.pop("layout_variant", None)
        if s["kind"] == "section":
            s["template"] = template_ref(
                section_layout(s["title"], design.typography, sections)
            )
            sections += 1
            slides.append(s)
            continue
        if design.human_touch and not s.get("table") and not s.get("diagram"):
            s["items"] = [labelled(x) for x in s["items"]]
        report(
            progress,
            "Fitting content into the original company template…",
            "layout",
            len(slides) + 1,
            len(slides) + len(pending) + 2,
            s["title"],
        )
        options = candidates(s, design.human_touch)
        # A two-item labelled comparison uses the original comparison placeholders.
        if options[0] == 17 and not any(
            parse_item(x)["role"] == "subheading" for x in s["items"]
        ):
            s["items"] = [
                part
                for x in s["items"]
                for part in ("### " + label_parts(x)[0], label_parts(x)[2])
            ]
        measured = {}
        for n in options:
            try:
                measured[n] = fitted_layout_sizes(
                    s, n, design.typography, design.human_touch
                )
            except ValueError:
                continue
        viable = list(measured)
        if not viable:
            if s.get("table") or s.get("diagram"):
                raise ValueError(
                    f"“{s['title']}” exceeds its layout capacity. Shorten the heading or cells."
                )
            breaks = [
                i
                for i in range(1, len(s["items"]))
                if parse_item(s["items"][i])["level"] == 0
                and parse_item(s["items"][i - 1])["role"] != "subheading"
            ]
            if not breaks:
                raise ValueError(
                    f"“{s['title']}” needs a shorter paragraph. No text has been discarded."
                )
            mid = min(breaks, key=lambda i: abs(i - len(s["items"]) / 2))
            pending[0:0] = [
                dict(s, items=s["items"][:mid]),
                dict(
                    s,
                    items=s["items"][mid:],
                    title=s["title"].removesuffix(" (continued)")[:108]
                    + " (continued)",
                ),
            ]
            continue
        vary = design.unique_layouts or design.human_touch
        n = select_layout(measured, history, vary)
        reused |= vary and n in history
        history.append(n)
        s["template"] = template_ref(n)
        reason = (
            "editable table"
            if s.get("table")
            else "explicit connected architecture"
            if s.get("diagram")
            else "user picture with supporting text"
            if s.get("image")
            else "ordered stages"
            if n == 69
            else "explicit four-stage cycle"
            if n == 87
            else "explicit contrast between two named alternatives"
            if n == 17
            else f"{len(s['items'])} content items"
        )
        s["selection_reason"] = (
            f"{reason}; eligible layouts {options}; readable fits {viable}; selected original layout {n}."
        )
        if options[0] not in (14, 17, 19, 20, 69, 87):
            peers, sizes = readable_layouts(measured)
            s["selection_reason"] += (
                f" Smallest populated content sizes {sizes} pt; comparable readable layouts {peers}."
            )
        if n in (13, 16):
            s["selection_reason"] += (
                " A text layout preserves the supplied hierarchy or accommodates the measured text length."
            )
        slides.append(s)
        if len(slides) > 149:
            raise ValueError(
                "This content needs more than 150 readable slides. Split it into smaller presentations."
            )
    slides.append(
        dict(
            title="Thank you",
            kind="closing",
            items=[],
            source_text="",
            template=template_ref(170),
        )
    )
    if design.agenda:
        slides = [s for s in slides if s["kind"] != "agenda"]
        agenda = make_agenda(slides[1:-1], design.typography)
        if agenda:
            slides.insert(1, agenda)
    if pictures:
        place_pictures(slides, pictures, design.typography)
    if design.images:
        from .images import find_image

        candidate = next(
            (
                s
                for s in slides
                if s["kind"] == "content"
                and len(s["items"]) <= 2
                and not s.get("image")
            ),
            None,
        )
        if candidate:
            try:
                ref = find_image(prompt + " " + candidate["title"])
                if ref:
                    place_pictures(
                        slides,
                        [dict(image=ref, target=candidate["title"])],
                        design.typography,
                    )
            except (OSError, ValueError):
                warnings.append(
                    "Online image search was unavailable. The original company artwork is preserved."
                )
    if reused:
        warnings.append(
            "A suitable original layout was reused to preserve meaning and readability. No unrelated diagrams were added for variety."
        )
    report(
        progress,
        "Company-template outline ready for review.",
        "outline",
        len(slides),
        len(slides),
        slides[-1]["title"],
    )
    return slides


def repair_edits(plan, progress):
    """Re-fit reviewed edits without leaving empty decorative slots or losing text."""
    from .models import SlidePlan

    output = []
    adjusted = 0
    design = plan.design.model_copy(
        update={"agenda": False, "complete_story": False, "images": False}
    )
    for slide in plan.slides:
        if plan.template_engine >= 7 and slide.kind != "agenda":
            from .quality import heading_case

            slide.title = heading_case(slide.title)
            if slide.section:
                slide.section = heading_case(slide.section)
            slide.items = [
                "### " + heading_case(parse_item(x)["plain"])
                if parse_item(x)["role"] == "subheading"
                else x
                for x in slide.items
            ]
        s = slide.model_dump()
        n = slide.template.number
        if n == 20 and not s.get("diagram"):
            from .planner import diagram_for
            from .models import DiagramSpec

            s["diagram"] = diagram_for(s["items"])
            slide.diagram = DiagramSpec.model_validate(s["diagram"])
        if slide.kind in ("cover", "closing", "section"):
            output.append(slide)
            continue
        if slide.kind == "agenda":
            if not 1 <= len(slide.items) <= len(PROFILES[n]["body"]) or not fits(
                s, n, design.typography
            ):
                raise ValueError(
                    "Keep the agenda within its populated topic rows. Shorten its headings and generate again."
                )
            output.append(slide)
            continue
        if n in candidates(s, design.human_touch) and fits(
            s, n, design.typography, design.human_touch
        ):
            output.append(slide)
            continue
        replacements = plan_templates(
            plan.title, [s], design, [], plan.warnings, progress
        )[1:-1]
        output.extend(SlidePlan.model_validate(x) for x in replacements)
        adjusted += 1
    if len(output) > 150:
        raise ValueError(
            "The edited deck exceeds 150 readable slides. Split it into smaller presentations."
        )
    plan.slides = output
    from .quality import agenda_titles

    for i, slide in enumerate(plan.slides):
        if slide.kind == "agenda" and slide.agenda_topics:
            body = [s.model_dump() for s in plan.slides if s.kind != "agenda"]
            if [x for g in slide.agenda_topics for x in g] != agenda_titles(body):
                plan.slides[i] = SlidePlan.model_validate(
                    make_agenda(body, design.typography)
                )
                adjusted += 1
    if adjusted:
        plan.warnings.append(
            f"Re-fitted {adjusted} edited slide(s) into suitable company layouts. All edited content was retained."
        )
    return adjusted
