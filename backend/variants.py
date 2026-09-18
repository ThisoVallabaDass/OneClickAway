"""Distinct, readable company-themed compositions for long presentations.

These are explicitly identified generated variants, not unconfigured source layouts.
The source blank layout supplies the original master and logo.
"""

import math
from .design import FONT_PAIRS, fitted_size

COLORS = ["A90000", "D94B00", "303136", "62656B"]
STRUCTURES = [
    "Reading panels",
    "Two columns",
    "Three columns",
    "Cards across",
    "Cards down",
    "Numbered rows",
]
VARIANT_COUNT = 72


def variant_spec(code, title, items, style):
    index = int(code[1:])
    if not 0 <= index < VARIANT_COUNT:
        raise ValueError("Unknown generated layout variant")
    composition = index % 6
    accent = COLORS[(index // 6) % 4]
    header = index // 24
    heading, body = FONT_PAIRS[style]
    title_box = [450000, 250000, 11200000, 800000]
    title_size = fitted_size(title_box, title, 28, 20, heading)
    count = len(items)
    if not 1 <= count <= 8:
        raise ValueError("Generated content layouts support 1–8 points.")
    boxes = []
    groups = []
    left, top, width, height, gap = 450000, 1450000, 11200000, 4500000, 250000
    if composition in (0, 1, 2):
        columns = composition + 1
        step = math.ceil(count / columns)
        w = (width - gap * (columns - 1)) // columns
        for i in range(columns):
            values = items[i * step : (i + 1) * step]
            if values:
                boxes.append([left + i * (w + gap), top, w, height])
                groups.append(values)
    else:
        columns = 3 if composition == 3 else 2 if composition == 4 else 1
        columns = min(columns, count)
        rows = math.ceil(count / columns)
        w = (width - gap * (columns - 1)) // columns
        h = (height - gap * (rows - 1)) // rows
        for i, value in enumerate(items):
            boxes.append(
                [
                    left + (i % columns) * (w + gap),
                    top + (i // columns) * (h + gap),
                    w,
                    h,
                ]
            )
            groups.append([value])
    sizes = []
    for b, values in zip(boxes, groups):
        inner = [b[0] + 180000, b[1] + 50000, b[2] - 360000, b[3] - 100000]
        sizes.append(
            fitted_size(
                inner,
                values,
                22 if composition < 3 else 19,
                16,
                body,
                composition < 3,
                structural=True,
            )
        )
    return dict(
        composition=composition,
        accent=accent,
        header=header,
        title_box=title_box,
        title_size=title_size,
        boxes=boxes,
        groups=groups,
        sizes=sizes,
        name=f"{STRUCTURES[composition]} · {accent} · header {header + 1}",
    )


def choose_variant(title, items, style, used):
    for i in range(VARIANT_COUNT):
        code = f"v{i:03}"
        if code in used:
            continue
        try:
            variant_spec(code, title, items, style)
        except ValueError:
            continue
        return code
    raise ValueError(
        "This section needs more space than the available layout variations. Split it into shorter sections."
    )


def add_variant(tree, code, title, items, style, first_id=9000, link_rel=None):
    from lxml import etree as E
    from .exporter import textbox, set_text
    from .ooxml import NS, q

    spec = variant_spec(code, title, items, style)
    heading, body = FONT_PAIRS[style]
    ident = first_id

    def rectangle(bounds, fill):
        nonlocal ident
        shape = textbox(ident, "Brand accent", bounds)
        ident += 1
        sp = shape.find("p:spPr", NS)
        sp.remove(sp.find("a:noFill", NS))
        f = E.SubElement(sp, q("a:solidFill"))
        E.SubElement(f, q("a:srgbClr"), val=fill)
        tree.append(shape)
        return shape

    if spec["header"] == 0:
        rectangle([450000, 1190000, 11200000, 45000], spec["accent"])
    elif spec["header"] == 1:
        rectangle([0, 0, 12192000, 1200000], spec["accent"])
    else:
        rectangle([0, 0, 200000, 6100000], spec["accent"])
    shape = textbox(ident, "Generated variant title", spec["title_box"])
    ident += 1
    shape.find("p:nvSpPr/p:cNvPr", NS).set("descr", "Generated presentation content")
    set_text(
        shape,
        title,
        spec["title_size"],
        color="FFFFFF" if spec["header"] == 1 else "242429",
        family=heading,
        bold=True,
    )
    tree.append(shape)
    for i, (b, values, size) in enumerate(
        zip(spec["boxes"], spec["groups"], spec["sizes"])
    ):
        if spec["composition"] >= 3:
            rectangle(b, "F3F3F4")
            rectangle([b[0], b[1], 45000, b[3]], spec["accent"])
        inner = [b[0] + 180000, b[1] + 50000, b[2] - 360000, b[3] - 100000]
        shape = textbox(ident, f"Generated content panel {i + 1}", inner)
        ident += 1
        shape.find("p:nvSpPr/p:cNvPr", NS).set(
            "descr", "Generated presentation content"
        )
        set_text(
            shape,
            values,
            size,
            bullets=spec["composition"] < 3,
            color="303136",
            family=body,
            structural=True,
            accent=spec["accent"],
            link_rel=link_rel,
        )
        tree.append(shape)
    return ident
