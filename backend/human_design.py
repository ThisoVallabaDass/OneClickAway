"""Legacy composition rendering and shared content helpers.

New Human touch plans use template_engine. The older renderer remains only for
compatibility with previously saved outlines; it is not selected for new decks.
"""

from .design import FONT_PAIRS, fitted_size, label_parts
from .richtext import parse_item, plain_text


def groups_for(items):
    lead = []
    groups = []
    for item in items:
        parsed = parse_item(item)
        if parsed["role"] == "subheading":
            groups.append((parsed["plain"], []))
        elif groups:
            groups[-1][1].append(item)
        else:
            lead.append(item)
    return lead, groups


def composition_for(s):
    import re

    if s["kind"] in ("cover", "closing", "section", "agenda", "table"):
        return s["kind"]
    if s.get("image"):
        return "image"
    if s.get("diagram"):
        return "diagram"
    lead, groups = groups_for(s["items"])
    values = [x for x in s["items"] if parse_item(x)["role"] != "subheading"]
    if 2 <= len(values) <= 4 and all(
        re.match(r"^(?:Stage|Step|Phase)\s+\d+[^:]*:", plain_text(x), re.I)
        for x in values
    ):
        return "steps"
    if len(groups) == 2 and all(g[1] for g in groups) and len(lead) <= 2:
        return "grouped"
    if (
        s["kind"] == "comparison"
        or any(re.search(r"\bvs\b|versus|comparison", g[0], re.I) for g in groups)
    ) and 2 <= len(values) <= 3:
        return "comparison"
    if (
        not groups
        and 2 <= len(values) <= 4
        and all(label_parts(x)[1] and len(label_parts(x)[0]) <= 65 for x in values)
    ):
        return "catalog"
    if len(s["items"]) == 1 and len(plain_text(s["items"][0])) < 230:
        return "focus"
    return "reading"


def text_layout(s, style):
    """One shared measurement contract for planning and export. Values are EMUs."""
    comp = s.get("composition") or composition_for(s)
    heading, body = FONT_PAIRS[style]
    title = s["title"]
    items = s.get("items", [])
    blocks = []

    def add(
        name,
        bounds,
        value,
        size=24,
        minimum=20,
        family=body,
        color="303136",
        bold=False,
        bullets=False,
        structural=False,
    ):
        actual = fitted_size(
            bounds, value, size, minimum, family, bullets, structural=structural
        )
        blocks.append(
            dict(
                name=name,
                bounds=bounds,
                value=value,
                size=actual,
                family=family,
                color=color,
                bold=bold,
                bullets=bullets,
                structural=structural,
            )
        )

    if comp in ("cover", "closing", "section"):
        add(
            "Presentation title",
            [750000, 2200000, 10500000, 2600000],
            title,
            48,
            36,
            heading,
            "AD1723",
            True,
        )
        return blocks
    add(
        "Slide title",
        [650000, 500000, 9900000, 1150000],
        title,
        32,
        28,
        heading,
        "242429",
        True,
    )
    if comp == "table":
        from .tables import table_layout

        table_layout(s["table"], style, True)
        return blocks
    if comp == "diagram":
        from lxml import etree as E
        from .ooxml import q
        from .models import DiagramSpec
        from .visuals import add_diagram
        from .planner import diagram_for

        add_diagram(
            E.Element(q("p:spTree")),
            DiagramSpec.model_validate(s.get("diagram") or diagram_for(items)),
            1,
            "horizontal",
            style,
            human=True,
        )
        return blocks
    if comp == "image":
        add(
            "Image explanation",
            [650000, 2000000, 4700000, 3750000],
            items,
            24,
            20,
            bullets=len(items) > 1,
            structural=True,
        )
    elif comp == "focus":
        add(
            "Main idea",
            [850000, 2200000, 10200000, 3200000],
            items,
            32,
            26,
            structural=True,
        )
    elif comp == "comparison":
        values = [x for x in items if parse_item(x)["role"] != "subheading"]
        for i, item in enumerate(values[:2]):
            label, sep, desc = label_parts(item)
            x = 650000 + i * 5650000
            if sep and len(label) < 65:
                add(
                    f"Comparison heading {i + 1}",
                    [x, 2050000, 5100000, 900000],
                    label,
                    28,
                    24,
                    heading,
                    "AD1723",
                    True,
                )
                add(
                    f"Comparison text {i + 1}",
                    [x, 3100000, 5100000, 2300000],
                    desc,
                    24,
                    20,
                    structural=True,
                )
            else:
                add(
                    f"Comparison text {i + 1}",
                    [x, 2100000, 5100000, 3100000],
                    item,
                    26,
                    22,
                    structural=True,
                )
        if len(values) > 2:
            add(
                "Comparison context",
                [650000, 5550000, 10800000, 600000],
                values[2:],
                18,
                18,
                structural=True,
            )
        subtitles = [
            parse_item(x)["plain"]
            for x in items
            if parse_item(x)["role"] == "subheading"
        ]
        if subtitles:
            add(
                "Comparison subject",
                [650000, 1630000, 10800000, 370000],
                subtitles,
                18,
                18,
                color="746B6B",
            )
    elif comp == "catalog":
        columns = 3 if len(items) == 3 else 2
        rows = (len(items) + columns - 1) // columns
        width = (10800000 - (columns - 1) * 450000) // columns
        height = 3900000 // rows
        for i, item in enumerate(items):
            label, _, desc = label_parts(item)
            x = 650000 + (i % columns) * (width + 450000)
            y = 2050000 + (i // columns) * height
            label_height = 1100000 if rows == 1 else 800000
            add(
                f"Service label {i + 1}",
                [x, y, width, label_height],
                label,
                28,
                22,
                heading,
                "AD1723",
                True,
            )
            add(
                f"Service explanation {i + 1}",
                [x, y + label_height + 100000, width, height - label_height - 200000],
                desc,
                24,
                20,
                structural=True,
            )
    elif comp == "grouped":
        lead, groups = groups_for(items)
        top = 2000000
        if lead:
            add(
                "Shared context",
                [650000, 1800000, 10800000, 1150000],
                lead,
                20,
                18,
                structural=True,
            )
            top = 3100000
        for i, (label, values) in enumerate(groups):
            x = 650000 + i * 5650000
            add(
                f"Group heading {i + 1}",
                [x, top, 5100000, 650000],
                label,
                26,
                22,
                heading,
                "AD1723",
                True,
            )
            add(
                f"Group details {i + 1}",
                [x, top + 780000, 5100000, 6100000 - top - 780000],
                values,
                24,
                20,
                bullets=True,
                structural=True,
            )
    elif comp == "steps":
        values = [x for x in items if parse_item(x)["role"] != "subheading"]
        subtitles = [
            parse_item(x)["plain"]
            for x in items
            if parse_item(x)["role"] == "subheading"
        ]
        if subtitles:
            add(
                "Process subject",
                [650000, 1630000, 10800000, 450000],
                subtitles,
                18,
                18,
                color="746B6B",
            )
        for i, item in enumerate(values):
            import re

            label, _, desc = label_parts(item)
            y = 2200000 + i * 950000
            label = re.sub(
                r"^(?:Stage|Step|Phase)\s+\d+\s*[—–-]?\s*", "", label, flags=re.I
            )
            add(
                f"Step {i + 1}",
                [650000, y, 650000, 700000],
                f"{i + 1:02}",
                24,
                24,
                heading,
                "AD1723",
                True,
            )
            add(
                f"Step title {i + 1}",
                [1450000, y, 2900000, 850000],
                label,
                22,
                20,
                heading,
                "242429",
                True,
            )
            add(
                f"Step explanation {i + 1}",
                [4550000, y, 6900000, 900000],
                desc.strip(),
                22,
                20,
                structural=True,
            )
    else:
        add(
            "Slide content",
            [850000, 1950000, 10300000, 4150000],
            items,
            26,
            22,
            bullets=comp != "agenda",
            structural=True,
        )
    return blocks


def place_pictures(slides, pictures, style):
    from .planner import template_ref
    from .models import PicturePlacement
    from .images import image_bytes

    used = set()
    for raw in pictures:
        placement = PicturePlacement.model_validate(raw)
        key = placement.target.strip().casefold()
        matches = [
            s
            for s in slides
            if s["title"].strip().casefold() == key
            and s["kind"] not in ("cover", "closing", "section", "agenda")
        ]
        if not matches:
            raise ValueError(
                f'Picture "{placement.image.title}" needs a matching slide heading: "{placement.target}". Copy the heading from your content.'
            )
        target = matches[0]
        if id(target) in used:
            raise ValueError(
                "Choose a different slide for each picture. One picture per slide is supported."
            )
        if target.get("table") or target.get("diagram"):
            raise ValueError(
                "Pictures need a text slide. Choose a heading without a table or diagram."
            )
        image_bytes(placement.image.id)
        target.update(
            image=placement.image.model_dump(),
            composition=None,
            template=template_ref(19),
            layout_variant=None,
        )
        from .template_engine import fits

        if not fits(target, 19, style):
            raise ValueError(
                f'The picture and text on "{target["title"]}" need more room. Shorten that slide to 2–3 points or put the picture on a separate heading.'
            )
        used.add(id(target))


def plan_human(prompt, body, design, pictures, warnings, progress):
    # Compatibility entry point: new Human touch decks use original templates.
    from .template_engine import plan_templates

    return plan_templates(prompt, body, design, pictures, warnings, progress)


def add_human(tree, slide, style, first_id, link_rel):
    from .exporter import textbox, set_text
    from .ooxml import NS

    for spec in text_layout(slide.model_dump(), style):
        shape = textbox(first_id, spec["name"], spec["bounds"])
        first_id += 1
        shape.find("p:nvSpPr/p:cNvPr", NS).set(
            "descr", "Generated presentation content"
        )
        set_text(
            shape,
            spec["value"],
            spec["size"],
            family=spec["family"],
            color=spec["color"],
            bold=spec["bold"],
            bullets=spec["bullets"],
            structural=spec["structural"],
            accent="AD1723",
            link_rel=link_rel,
        )
        tree.append(shape)
    return first_id
