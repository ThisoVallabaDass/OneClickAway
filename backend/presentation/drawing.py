"""Lossless template packaging using the public Office Open XML format.

Copy the company's artwork and theme bytes verbatim. Materialize layout shapes
as slide objects so the generated text is editable in normal PowerPoint view.
No Office license or paid presentation SDK is required to generate a deck.
"""

from copy import deepcopy
from lxml import etree as E
from ..ooxml import NS, q
from ..design import (
    FONT_PAIRS,
    CODE_FONT,
    ROLE_SCALE,
    ROLE_SPACE_BEFORE,
    ROLE_SPACE_AFTER,
    LEVEL_INDENT_PT,
    QUOTE_INDENT_PT,
)
from ..richtext import parse_item, BLANK_RUN

RELBASE = NS["r"] + "/"
ACCENT = "A90000"
# Bullet glyph and left margin per nesting level. Level 0 keeps the original round bullet.
BULLET_CHARS = ["\u2022", "\u2013", "\u00b7"]
BULLET_MARGIN = [
    270000,
    270000 + LEVEL_INDENT_PT[1] * 12700,
    270000 + LEVEL_INDENT_PT[2] * 12700,
]
# a:pPr children must appear in schema order or PowerPoint reports a repair.
PPR_ORDER = [
    "lnSpc",
    "spcBef",
    "spcAft",
    "buClrTx",
    "buClr",
    "buSzTx",
    "buSzPct",
    "buSzPts",
    "buFontTx",
    "buFont",
    "buNone",
    "buAutoNum",
    "buChar",
    "tabLst",
    "defRPr",
    "extLst",
]
RPR_ORDER = [
    "ln",
    "noFill",
    "solidFill",
    "gradFill",
    "blipFill",
    "pattFill",
    "grpFill",
    "effectLst",
    "effectDag",
    "highlight",
    "uLnTx",
    "uLn",
    "uFillTx",
    "uFill",
    "latin",
    "ea",
    "cs",
    "sym",
    "hlinkClick",
    "hlinkMouseOver",
    "rtl",
    "extLst",
]


def el(name, **attrs):
    return E.Element(q(name), **{k: str(v) for k, v in attrs.items()})


def ordered_child(parent, name, order=None, **attrs):
    """Insert a child at its schema position instead of appending blindly."""
    order = order or PPR_ORDER
    node = el(name, **attrs)
    rank = order.index(name.split(":")[1])
    for index, existing in enumerate(parent):
        local = E.QName(existing).localname
        if local in order and order.index(local) > rank:
            parent.insert(index, node)
            return node
    parent.append(node)
    return node


def label_runs(block):
    """Bold a supplied ``Label:`` lead-in without changing any wording."""
    if len(block["runs"]) != 1 or block["emphasis"] or block["code"] or block["link"]:
        return block["runs"]
    label, sep, rest = block["runs"][0]["text"].partition(":")
    if not sep or len(label) >= 45:
        return block["runs"]
    return [
        dict(block["runs"][0], text=label + sep, bold=True, explicit=True),
        dict(block["runs"][0], text=rest, bold=False, explicit=True),
    ]


def run_properties(template, run, paragraph_bold=False):
    rp = deepcopy(template)
    if run["explicit"] or run["bold"]:
        rp.set("b", "1" if run["bold"] or paragraph_bold else "0")
    if run["italic"]:
        rp.set("i", "1")
    if run["underline"]:
        rp.set("u", "sng")
    if run["strike"]:
        rp.set("strike", "sngStrike")
    latin = rp.find("a:latin", NS)
    if run["code"] and latin is not None:
        latin.set("typeface", CODE_FONT)
        for extra in ("a:ea", "a:cs"):
            node = rp.find(extra, NS)
            if node is not None:
                node.set("typeface", CODE_FONT)
    return rp


def set_text(
    shape,
    values,
    size=None,
    bullets=False,
    color=None,
    family=None,
    bold=None,
    align="l",
    anchor="t",
    structural=False,
    literal=False,
    inherit=False,
    accent=None,
    link_rel=None,
    paragraph_after=None,
):
    """Write generated text as real PowerPoint runs.

    ``structural`` honours the outline's block grammar: ``### `` subheadings, ``> ``
    quotes and two-space nesting. Inline ``**bold**``, ``*italic*``, ``++underline++``,
    ``~~strikethrough~~``, ``` `code` ``` and ``[text](url)`` become separate runs.
    ``literal`` writes the string untouched, which speaker notes use so the supplied
    source is reproduced exactly. ``inherit`` keeps the template's own colour and
    paragraph properties, which the section dividers rely on for contrast.
    """
    tx = shape.find("p:txBody", NS)
    if tx is None:
        return
    if isinstance(values, str):
        values = [values]
    first = tx.find("a:p", NS)
    base_p = first.find("a:pPr", NS) if first is not None else None
    base_r = first.find("a:r/a:rPr", NS) if first is not None else None
    if base_r is None:
        base_r = tx.find("a:lstStyle/a:lvl1pPr/a:defRPr", NS)
    keep_base = base_r is not None and (inherit or not family)
    rpr = deepcopy(base_r) if keep_base else el("a:rPr", lang="en-US")
    rpr.tag = q("a:rPr")
    if size:
        rpr.set("sz", str(round(size * 100)))
    if bold is not None:
        rpr.set("b", "1" if bold else "0")
    if color:
        for fill in rpr.findall("a:solidFill", NS):
            rpr.remove(fill)
        fill = el("a:solidFill")
        E.SubElement(fill, q("a:srgbClr"), val=color)
        rpr.insert(1 if rpr.find("a:ln", NS) is not None else 0, fill)
    for link in rpr.findall("a:hlinkClick", NS) + rpr.findall("a:hlinkMouseOver", NS):
        rpr.remove(link)
    if rpr.find("a:latin", NS) is None:
        E.SubElement(rpr, q("a:latin"), typeface="+mn-lt")
    if family:
        rpr.find("a:latin", NS).set("typeface", family)
        if not inherit:
            # Explicit formatting isolates generated text from source placeholder quirks.
            lst = tx.find("a:lstStyle", NS)
            if lst is not None:
                lst.clear()
    for p in list(tx.findall("a:p", NS)):
        tx.remove(p)
    bp = tx.find("a:bodyPr", NS)
    if bp is not None:
        for af in list(bp):
            if E.QName(af).localname in ("spAutoFit", "normAutofit", "noAutofit"):
                bp.remove(af)
        E.SubElement(bp, q("a:normAutofit"))
        bp.set("wrap", "square")
        if family:
            bp.set("anchor", anchor)
            bp.set("lIns", "100000")
            bp.set("rIns", "100000")
            bp.set("tIns", "60000")
            bp.set("bIns", "60000")
    blocks = [
        {
            "role": "bullet",
            "level": 0,
            "runs": [dict(BLANK_RUN, text="" if v is None else str(v))],
            "emphasis": False,
            "code": False,
            "link": False,
        }
        if literal
        else parse_item(v, structural)
        for v in (values or [""])
    ]
    for index, block in enumerate(blocks):
        role = block["role"]
        level = block["level"]
        p = E.SubElement(tx, q("a:p"))
        pp = (
            deepcopy(base_p)
            if base_p is not None and (inherit or not family)
            else el("a:pPr")
        )
        pp.set("lvl", "0")
        if family and align:
            pp.set("algn", align)
        for ch in list(pp):
            if E.QName(ch).localname.startswith("bu") or E.QName(ch).localname in (
                "spcBef",
                "spcAft",
            ):
                pp.remove(ch)
        if role in ("subheading", "quote") or bullets:
            if index:
                ordered_child(pp, "a:spcBef").append(
                    el("a:spcPts", val=str(ROLE_SPACE_BEFORE[role] * 100))
                )
            after = (
                ROLE_SPACE_AFTER[role]
                if paragraph_after is None
                else (paragraph_after if index < len(blocks) - 1 else 0)
            )
            ordered_child(pp, "a:spcAft").append(el("a:spcPts", val=str(after * 100)))
        if role == "subheading":
            pp.set("marL", str(LEVEL_INDENT_PT[level] * 12700))
            pp.set("indent", "0")
            ordered_child(pp, "a:buNone")
        elif role == "quote":
            pp.set("marL", str((LEVEL_INDENT_PT[level] + QUOTE_INDENT_PT) * 12700))
            pp.set("indent", "0")
            ordered_child(pp, "a:buNone")
        elif bullets:
            pp.set("marL", str(BULLET_MARGIN[level]))
            pp.set("indent", "-190000")
            pp.set("defTabSz", "270000")
            if level:
                ordered_child(pp, "a:buFont", typeface="Arial")
            ordered_child(pp, "a:buChar", char=BULLET_CHARS[level])
        else:
            pp.set("marL", str(LEVEL_INDENT_PT[level] * 12700))
            pp.set("indent", "0")
            ordered_child(pp, "a:buNone")
        p.append(pp)
        paragraph = deepcopy(rpr)
        # Identical rounding to design.fitted_size, so measurement and rendering cannot drift.
        if size:
            paragraph.set("sz", str(max(round(size * ROLE_SCALE[role]), 1) * 100))
        if role == "subheading":
            paragraph.set("u", "sng")
            if accent and (color or "").upper() not in ("FFFFFF",):
                for fill in paragraph.findall("a:solidFill", NS):
                    paragraph.remove(fill)
                fill = el("a:solidFill")
                E.SubElement(fill, q("a:srgbClr"), val=accent)
                paragraph.insert(
                    1 if paragraph.find("a:ln", NS) is not None else 0, fill
                )
        if role == "quote":
            paragraph.set("i", "1")
        runs = (
            label_runs(block)
            if structural and not literal and role == "bullet"
            else block["runs"]
        )
        for run in runs or [dict(BLANK_RUN, text="")]:
            if not run["text"] and len(runs or []) > 1:
                continue
            node = E.SubElement(p, q("a:r"))
            rp = run_properties(paragraph, run, role == "subheading" or bool(bold))
            if role == "subheading":
                rp.set("b", "1")
            if run["link"] and link_rel:
                ordered_child(rp, "a:hlinkClick", RPR_ORDER).set(
                    q("r:id"), link_rel(run["link"])
                )
            node.append(rp)
            E.SubElement(node, q("a:t")).text = run["text"]
        E.SubElement(p, q("a:endParaRPr"), lang="en-US")


def group_tree():
    st = el("p:spTree")
    nv = E.SubElement(st, q("p:nvGrpSpPr"))
    E.SubElement(nv, q("p:cNvPr"), id="1", name="")
    E.SubElement(nv, q("p:cNvGrpSpPr"))
    E.SubElement(nv, q("p:nvPr"))
    gp = E.SubElement(st, q("p:grpSpPr"))
    xf = E.SubElement(gp, q("a:xfrm"))
    for tag, attrs in [
        ("off", {"x": "0", "y": "0"}),
        ("ext", {"cx": "0", "cy": "0"}),
        ("chOff", {"x": "0", "y": "0"}),
        ("chExt", {"cx": "0", "cy": "0"}),
    ]:
        E.SubElement(xf, q("a:" + tag), **attrs)
    return st


def textbox(ident, label, bounds):
    s = el("p:sp")
    nv = E.SubElement(s, q("p:nvSpPr"))
    E.SubElement(nv, q("p:cNvPr"), id=str(ident), name=label)
    E.SubElement(nv, q("p:cNvSpPr"), txBox="1")
    E.SubElement(nv, q("p:nvPr"))
    sp = E.SubElement(s, q("p:spPr"))
    xf = E.SubElement(sp, q("a:xfrm"))
    E.SubElement(xf, q("a:off"), x=str(bounds[0]), y=str(bounds[1]))
    E.SubElement(xf, q("a:ext"), cx=str(bounds[2]), cy=str(bounds[3]))
    E.SubElement(sp, q("a:noFill"))
    tx = E.SubElement(s, q("p:txBody"))
    E.SubElement(tx, q("a:bodyPr"))
    E.SubElement(tx, q("a:lstStyle"))
    E.SubElement(tx, q("a:p"))
    return s


def add_table(st, rows, ident, style="modern", human=False):
    from ..tables import table_layout

    measured = table_layout(rows, style, human)
    frame = el("p:graphicFrame")
    nv = E.SubElement(frame, q("p:nvGraphicFramePr"))
    E.SubElement(nv, q("p:cNvPr"), id=str(ident), name="Editable data table")
    E.SubElement(nv, q("p:cNvGraphicFramePr"))
    E.SubElement(nv, q("p:nvPr"))
    table_height = measured["height"]
    xf = E.SubElement(frame, q("p:xfrm"))
    E.SubElement(xf, q("a:off"), x="450000", y="1800000" if human else "1100000")
    E.SubElement(xf, q("a:ext"), cx="11200000", cy=str(table_height))
    graphic = E.SubElement(frame, q("a:graphic"))
    data = E.SubElement(
        graphic,
        q("a:graphicData"),
        uri="http://schemas.openxmlformats.org/drawingml/2006/table",
    )
    table = E.SubElement(data, q("a:tbl"))
    E.SubElement(table, q("a:tblPr"), firstRow="1", bandRow="1")
    grid = E.SubElement(table, q("a:tblGrid"))
    w = measured["widths"][0]
    for _ in rows[0]:
        E.SubElement(grid, q("a:gridCol"), w=str(w))
    for ri, row in enumerate(rows):
        h = measured["heights"][ri]
        tr = E.SubElement(table, q("a:tr"), h=str(h))
        for value in row:
            tc = E.SubElement(tr, q("a:tc"))
            tx = E.SubElement(tc, q("a:txBody"))
            E.SubElement(tx, q("a:bodyPr"), anchor="ctr")
            E.SubElement(tx, q("a:lstStyle"))
            family = FONT_PAIRS[style][0 if ri == 0 else 1]
            size = measured["size"]
            p = E.SubElement(tx, q("a:p"))
            # Cell wording keeps inline emphasis, so a bolded figure stays bold in the table.
            block = parse_item(value, structural=False)
            for run in block["runs"] or [dict(BLANK_RUN, text="")]:
                r = E.SubElement(p, q("a:r"))
                rp = E.SubElement(
                    r,
                    q("a:rPr"),
                    lang="en-US",
                    sz=str(size * 100),
                    b="1" if ri == 0 or run["bold"] else "0",
                )
                if run["italic"]:
                    rp.set("i", "1")
                if run["underline"]:
                    rp.set("u", "sng")
                if run["strike"]:
                    rp.set("strike", "sngStrike")
                fill = E.SubElement(rp, q("a:solidFill"))
                E.SubElement(
                    fill, q("a:srgbClr"), val="FFFFFF" if ri == 0 else "252525"
                )
                E.SubElement(
                    rp, q("a:latin"), typeface=CODE_FONT if run["code"] else family
                )
                E.SubElement(r, q("a:t")).text = run["text"]
            props = E.SubElement(
                tc,
                q("a:tcPr"),
                marL="100000",
                marR="100000",
                marT="80000",
                marB="80000",
            )
            fill = E.SubElement(props, q("a:solidFill"))
            E.SubElement(
                fill,
                q("a:srgbClr"),
                val="AB0000" if ri == 0 else ("F1F1F1" if ri % 2 else "FFFFFF"),
            )
    st.append(frame)


def notes_xml(slide, index):
    root = el("p:notes")
    cs = E.SubElement(root, q("p:cSld"))
    st = group_tree()
    cs.append(st)
    shape = textbox(2, "Source content", [0, 0, 6000000, 5000000])
    E.SubElement(shape.find("p:nvSpPr/p:nvPr", NS), q("p:ph"), type="body", idx="1")
    provenance = f"Slide {index}. Bound original template {slide.template.id}: {slide.template.name}.\n"
    provenance += (
        f"Selection: {slide.selection_reason or slide.kind + ' structural layout'}.\n"
    )
    if slide.layout_variant:
        provenance += (
            f"Generated KaarTech-themed composition: {slide.layout_variant}.\n"
        )
    if slide.generated_draft:
        provenance += "AI-generated draft; factual review required.\n"
    if slide.image:
        provenance += f"Image: {slide.image.title}\nAuthor: {slide.image.author}\nLicense: {slide.image.license}\nSource: {slide.image.source_url}\nImage contained without cropping.\n"
    if slide.diagram:
        provenance += "Diagram connections follow the supplied sequence.\n"
    if slide.section:
        provenance += f"Section: {slide.section}.\n"
    if slide.citations:
        provenance += "Sources:\n" + "\n".join(slide.citations) + "\n"
    # Notes reproduce the supplied source exactly, including any Markdown the author wrote.
    set_text(
        shape,
        provenance + "\nOriginal supplied content:\n" + slide.source_text,
        12,
        literal=True,
    )
    st.append(shape)
    root.append(el("p:clrMapOvr"))
    E.SubElement(root[-1], q("a:masterClrMapping"))
    return root


STRUCTURAL_KINDS = {"cover", "section", "agenda", "closing"}
