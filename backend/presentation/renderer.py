"""Lossless template packaging using the public Office Open XML format.

Copy the company's artwork and theme bytes verbatim. Materialize layout shapes
as slide objects so the generated text is editable in normal PowerPoint view.
No Office license or paid presentation SDK is required to generate a deck.
"""

from copy import deepcopy
import posixpath
from lxml import etree as E
from ..catalog import PROFILES
from ..ooxml import (
    NS,
    REL,
    q,
    parse,
    resolve,
    relationships,
    materialized_layout,
    shape_id,
    geometry,
)
from ..design import (
    FONT_PAIRS,
    assignments,
    fitted_size,
    text_treatment,
    geometry_override,
)
from ..visuals import add_diagram, add_picture

RELBASE = NS["r"] + "/"
ACCENT = "A90000"
from .drawing import el, textbox, set_text, add_table


def populate_shapes(
    plan,
    slide,
    index,
    n,
    profile,
    root,
    st,
    shapes,
    assigned,
    body,
    items,
    mode,
    link_rel,
):
    for ident, shape in list(shapes.items()):
        if ident in profile.get("drop", []):
            shape.getparent().remove(shape)
            continue
        ph = shape.find("p:nvSpPr/p:nvPr/p:ph", NS)
        phtype = ph.get("type", "body") if ph is not None else None
        if phtype == "pic":
            shape.getparent().remove(shape)
            continue
        # Rectangular placeholders inherit their geometry from the layout
        # in PowerPoint. Once materialized as ordinary slide shapes that
        # inheritance is gone: write the rectangle explicitly, preserving
        # its original fill, line, effects and dimensions.
        sppr = shape.find("p:spPr", NS)
        if (
            ph is not None
            and sppr is not None
            and sppr.find("a:prstGeom", NS) is None
            and sppr.find("a:custGeom", NS) is None
        ):
            geom = el("a:prstGeom", prst="rect")
            E.SubElement(geom, q("a:avLst"))
            sppr.insert(1 if sppr.find("a:xfrm", NS) is not None else 0, geom)
        if ident in assigned:
            if ident in profile.get("text_overlay", []):
                # Some supplied placeholders are corner-shaped borders.
                # Keep the border artwork and place text in its open area;
                # text inside a corner shape collapses into a thin column.
                set_text(shape, "")
                if ph is not None:
                    ph.getparent().remove(ph)
                    ph = None
                bounds = geometry(shape)
                shape = textbox(10000 + int(ident), "Template panel content", bounds)
                st.append(shape)
                shapes[ident] = shape
            shape.find("p:nvSpPr/p:cNvPr", NS).set(
                "descr", "Generated presentation content"
            )
            value = assigned[ident]
            bounds = geometry_override(n, ident, geometry(shape), profile)
            xf = shape.find("p:spPr/a:xfrm", NS)
            if xf is not None:
                xf.find("a:off", NS).set("x", str(bounds[0]))
                xf.find("a:off", NS).set("y", str(bounds[1]))
                xf.find("a:ext", NS).set("cx", str(bounds[2]))
                xf.find("a:ext", NS).set("cy", str(bounds[3]))
            treatment = text_treatment(n, profile, ident, plan.design.typography, items)
            family = treatment["family"]
            preferred = treatment["preferred"]
            minimum = treatment["minimum"]
            bullets = treatment["bullets"]
            is_title = ident == profile["title"]
            is_label = ident in profile.get("labels", [])
            structural = not is_title and not is_label
            try:
                size = fitted_size(
                    bounds,
                    value,
                    preferred,
                    minimum,
                    family,
                    bullets,
                    structural=structural,
                    paragraph_after=treatment["paragraph_after"],
                )
            except ValueError as exc:
                raise ValueError(
                    f"Slide {index}, {slide.title}, text slot {ident}: {exc}"
                ) from exc
            inherit = bool(profile.get("inherit_style"))
            color = (
                "FFFFFF"
                if mode == "closing"
                else ("242429" if is_title else profile.get("text_color", "34343A"))
            )
            if is_title:
                color = profile.get("title_color", color)
            if ident in body:
                color = profile.get("body_color", color)
            if is_label:
                color = profile.get("label_color", color)
            if inherit:
                color = None
            set_text(
                shape,
                value,
                size,
                bullets=bullets,
                color=color,
                family=family,
                bold=None if inherit else (is_title or is_label),
                structural=structural,
                inherit=inherit,
                accent=ACCENT,
                link_rel=link_rel,
                paragraph_after=treatment["paragraph_after"],
                anchor=treatment["anchor"]
                or (
                    profile.get("label_anchor", "t")
                    if is_label
                    else ("ctr" if mode == "closing" or n == 104 else "t")
                ),
                align=None
                if inherit
                else (
                    profile.get("label_align", "l")
                    if is_label
                    else ("ctr" if mode == "closing" else "l")
                ),
            )
        elif ident in profile.get("numbers", []) and mode == "items":
            i = profile["numbers"].index(ident)
            if n == 97:
                set_text(
                    shape,
                    str(i + 1) if i < len(items) else "",
                    20,
                    anchor="ctr",
                    align="ctr",
                    color="34343A",
                    family=FONT_PAIRS[plan.design.typography][0],
                )
            else:
                set_text(shape, str(i + 1) if i < len(items) else "", 20)
        elif ph is not None or ident in profile.get("clear", []):
            set_text(shape, "")
        if ph is not None and ph.getparent() is not None:
            ph.getparent().remove(ph)
        if (
            ident not in assigned
            and phtype in ("title", "ctrTitle")
            and not shape.xpath(".//a:t/text()", namespaces=NS)
        ):
            shape.getparent().remove(shape)
    # Keep decorative borders, but remove their unused text containers.
    # Empty label fields should not survive as editable text placeholders.
    for shape in root.findall(".//p:sp", NS):
        tx = shape.find("p:txBody", NS)
        if (
            tx is not None
            and not "".join(tx.xpath(".//a:t/text()", namespaces=NS)).strip()
        ):
            props = shape.find("p:nvSpPr/p:cNvPr", NS)
            if props is not None and props.get("name", "").lower().startswith("title "):
                shape.getparent().remove(shape)
                continue
            shape.remove(tx)
            if props is not None:
                props.set("name", "Company artwork " + props.get("id", ""))
    for props in root.findall(".//p:cNvPr", NS):
        if not props.get("name", "").isascii():
            props.set("name", "Company artwork " + props.get("id", ""))
    # Source layouts sometimes place title placeholders below opaque artwork.
    # Bring populated content above that artwork without moving illustrations.
    for ident in assigned:
        shape = shapes.get(ident)
        if shape is not None and shape.getparent() is st:
            st.remove(shape)
            st.append(shape)
    if mode == "stages" and len(items) < 5:
        # The source has five columns. Remove whole unused column objects,
        # including their original flags and diamonds, without new artwork.
        cutoff = 270000 + 2340000 * len(items)
        for node in list(st):
            xf = node.find("p:spPr/a:xfrm", NS)
            if xf is None:
                xf = node.find("p:grpSpPr/a:xfrm", NS)
            if xf is None:
                continue
            off = xf.find("a:off", NS)
            if (
                off is not None
                and int(off.get("x", "0")) >= cutoff
                and 900000 < int(off.get("y", "0")) < 6000000
            ):
                st.remove(node)


def prepare_slide(z, slide):
    n = slide.template.number
    if slide.template.id != f"KTC-L{n:03}" or n not in PROFILES:
        raise ValueError(
            "This layout has not been configured for automatic generation."
        )
    profile = PROFILES[n]
    part = f"ppt/slideLayouts/slideLayout{n}.xml"
    if slide.layout_variant:
        if n != 13 or slide.table or slide.image or slide.diagram:
            raise ValueError(
                "Generated variants require the blank content layout and plain content."
            )
        profile = {
            "mode": "variant",
            "kind": slide.kind,
            "title": "generated-title",
            "body": [],
            "clear_art": True,
        }
    if slide.composition:
        profile = {
            "mode": "human",
            "kind": slide.kind,
            "title": "generated-title",
            "body": [],
            "clear_art": True,
            "picture": [5750000, 1900000, 5700000, 3950000],
        }
    layout, master = materialized_layout(z, part)
    root = el("p:sld", showMasterSp="0")
    root.append(deepcopy(layout.find("p:cSld", NS)))
    override = layout.find("p:clrMapOvr", NS)
    if override is not None:
        root.append(deepcopy(override))
    st = root.find("p:cSld/p:spTree", NS)
    if profile.get("row_lines"):
        for node in list(st.findall("p:cxnSp", NS)):
            ident = node.find("p:nvCxnSpPr/p:cNvPr", NS).get("id")
            if ident not in profile["row_lines"]:
                continue
            row = profile["row_lines"].index(ident)
            if row >= len(slide.items):
                st.remove(node)
                continue
            bounds = profile["bounds"][profile["body"][row]]
            xf = node.find("p:spPr/a:xfrm", NS)
            xf.find("a:off", NS).set("y", str(bounds[1] + 700000))
            xf.find("a:ext", NS).set("cx", str(bounds[2]))
    if profile.get("rows"):
        unused = {ident for row in profile["rows"][len(slide.items) :] for ident in row}
        for node in list(st):
            if shape_id(node) in unused:
                st.remove(node)
    if n == 35:
        # Remove complete unused agenda rows, including their original
        # number artwork. The black title panel remains unchanged.
        rows = [
            ["28", "29", "56", "57"],
            ["32", "33", "60", "61"],
            ["36", "37", "64", "65"],
            ["40", "41", "68", "69"],
            ["44", "45", "74", "75"],
        ]
        unused = {ident for row in rows[len(slide.items) :] for ident in row}
        for node in list(st):
            if shape_id(node) in unused:
                st.remove(node)
    if slide.kind in ("cover", "closing"):
        # These are sample-date/social-footer objects, not presentation content.
        # Keep the supplied cover artwork and remove its dated footer furniture.
        root.set("showMasterSp", "0")
        for node in list(st)[2:]:
            bounds = geometry(node)
            group_off = node.find("p:grpSpPr/a:xfrm/a:off", NS)
            y = int(group_off.get("y")) if group_off is not None else bounds[1]
            if y > 6200000:
                st.remove(node)
    if profile.get("clear_art"):
        for node in list(st)[2:]:
            st.remove(node)
        bg = root.find("p:cSld/p:bg", NS)
        if bg is not None:
            bg.getparent().remove(bg)
    if slide.composition:
        root.set("showMasterSp", "0")
        bg = E.Element(q("p:bg"))
        props = E.SubElement(bg, q("p:bgPr"))
        fill = E.SubElement(props, q("a:solidFill"))
        E.SubElement(fill, q("a:srgbClr"), val="FFFFFF")
        E.SubElement(props, q("a:effectLst"))
        root.find("p:cSld", NS).insert(0, bg)
    if profile["mode"] == "diagram":
        fresh = textbox(9000, "Architecture title", [450000, 190000, 11200000, 700000])
        st.append(fresh)
        profile = {**profile, "title": "9000"}
    return root, st, master, part, profile


def add_structured_content(
    plan, slide, st, sr, profile, next_id, link_rel, changed, new_types
):
    mode = profile["mode"]
    if slide.composition:
        from ..human_design import add_human
        from ..config import ROOT
        from ..models import ImageRef
        from PIL import Image

        next_id = add_human(st, slide, plan.design.typography, next_id, link_rel)
        logo_path = ROOT / "static/kaar-logo.png"
        with Image.open(logo_path) as logo:
            lw, lh = logo.size
        logo_ref = ImageRef(
            id="0" * 64,
            title="KaarTech",
            source_url="",
            license="Company logo",
            author="KaarTech",
            width=lw,
            height=lh,
        )
        logo_bounds = (
            [750000, 400000, 1600000, 1600000]
            if slide.kind in ("cover", "closing", "section")
            else [10800000, 260000, 1000000, 1000000]
        )
        add_picture(st, logo_ref, logo_bounds, next_id, "rIdCompanyLogo")
        next_id += 1
        changed["ppt/media/kaar-studio-logo.png"] = logo_path.read_bytes()
        new_types["ppt/media/kaar-studio-logo.png"] = "image/png"
        E.SubElement(
            sr,
            "{" + REL + "}Relationship",
            Id="rIdCompanyLogo",
            Type=RELBASE + "image",
            Target="../media/kaar-studio-logo.png",
        )
        if slide.table:
            add_table(st, slide.table, next_id, plan.design.typography, human=True)
            next_id += 1
        if slide.composition == "diagram":
            if not slide.diagram:
                from ..planner import diagram_for
                from ..models import DiagramSpec

                slide.diagram = DiagramSpec.model_validate(diagram_for(slide.items))
            next_id = add_diagram(
                st,
                slide.diagram,
                next_id,
                "horizontal",
                plan.design.typography,
                human=True,
            )
    if slide.layout_variant:
        from ..variants import add_variant

        next_id = add_variant(
            st,
            slide.layout_variant,
            slide.title,
            slide.items,
            plan.design.typography,
            next_id,
            link_rel,
        )
    if mode == "table":
        add_table(
            st,
            slide.table,
            next_id,
            plan.design.typography,
            human=plan.design.human_touch,
        )
        next_id += 1
    if mode == "diagram":
        if not slide.diagram:
            from ..planner import diagram_for
            from ..models import DiagramSpec

            slide.diagram = DiagramSpec.model_validate(diagram_for(slide.items))
        next_id = add_diagram(
            st, slide.diagram, next_id, profile["orientation"], plan.design.typography
        )
    return next_id


def embed_image(plan, slide, st, profile, next_id, changed, new_types):
    mode = profile["mode"]
    imagepart = None
    if slide.image:
        if mode != "image" and slide.composition != "image":
            raise ValueError(
                "This layout has no image slot. Replan after changing the image setting."
            )
        from ..images import image_bytes

        data = image_bytes(slide.image.id)
        extension = "jpg" if data[:2] == b"\xff\xd8" else "png"
        imagepart = f"ppt/media/downloaded-{slide.image.id}.{extension}"
        changed[imagepart] = data
        new_types[imagepart] = "image/jpeg" if extension == "jpg" else "image/png"
        add_picture(st, slide.image, profile["picture"], next_id, "rIdDownloadedImage")
        next_id += 1
        if slide.image.source_url:
            credit = textbox(
                next_id,
                "Image attribution",
                [5750000, 5940000, 5700000, 330000]
                if slide.composition
                else [5067300, 5540000, 6679958, 440000],
            )
            next_id += 1
            set_text(
                credit,
                f"{slide.image.license} · Source in speaker notes",
                9,
                color="666666",
                family=FONT_PAIRS[plan.design.typography][1],
            )
            st.append(credit)
    return next_id, imagepart


def repeat_original_brand(z, slide, master, sr, st, next_id):
    if slide.kind not in ("cover", "closing") and not slide.composition:
        # Full-slide white artwork in some layouts covers the master's
        # wordmark. Repeat that exact original SVG above the artwork,
        # at its original position, so branding remains visible.
        master_root = parse(z.read(master))
        master_rels = {r.get("Id"): r for r in relationships(z, master)}
        for picture in master_root.findall("p:cSld/p:spTree/p:pic", NS):
            off = picture.find("p:spPr/a:xfrm/a:off", NS)
            if off is None or int(off.get("y", "0")) < 6300000:
                continue
            logo = deepcopy(picture)
            logo.find("p:nvPicPr/p:cNvPr", NS).set("id", str(next_id))
            next_id += 1
            for element in logo.iter():
                for attr in [q("r:embed"), q("r:link")]:
                    old = element.get(attr)
                    if old not in master_rels:
                        continue
                    relation = master_rels[old]
                    new_id = f"rIdOriginalBrand{next_id}"
                    next_id += 1
                    target = resolve(master, relation.get("Target"))
                    E.SubElement(
                        sr,
                        "{" + REL + "}Relationship",
                        Id=new_id,
                        Type=relation.get("Type"),
                        Target=posixpath.relpath(target, "ppt/slides"),
                    )
                    element.set(attr, new_id)
            st.append(logo)
    return next_id


def render_slide(z, plan, slide, index, changed, new_types):
    root, st, master, part, profile = prepare_slide(z, slide)
    n = slide.template.number
    shapes = {shape_id(s): s for s in root.findall(".//p:sp", NS)}
    assigned = (
        {}
        if slide.layout_variant or slide.composition
        else assignments(profile, slide.title, slide.items)
    )
    body = profile["body"]
    items = slide.items
    mode = profile["mode"]
    # Slide relationships are opened before text, so a supplied link can register one.
    sr = relationships(z, part)
    for r in list(sr):
        if r.get("Type", "").endswith("/slideMaster"):
            sr.remove(r)
    link_ids = {}

    def link_rel(url, rels=sr, seen=link_ids):
        if url not in seen:
            seen[url] = f"rIdLink{len(seen) + 1}"
            E.SubElement(
                rels,
                "{" + REL + "}Relationship",
                Id=seen[url],
                Type=RELBASE + "hyperlink",
                Target=url,
                TargetMode="External",
            )
        return seen[url]

    populate_shapes(
        plan,
        slide,
        index,
        n,
        profile,
        root,
        st,
        shapes,
        assigned,
        body,
        items,
        mode,
        link_rel,
    )
    next_id = max([int(x.get("id")) for x in root.findall(".//p:cNvPr", NS)] + [1]) + 1
    next_id = add_structured_content(
        plan, slide, st, sr, profile, next_id, link_rel, changed, new_types
    )
    next_id, imagepart = embed_image(
        plan, slide, st, profile, next_id, changed, new_types
    )
    if plan.design.effects == "subtle":
        transition = E.SubElement(root, q("p:transition"), spd="med", advClick="1")
        effect = (
            "push" if mode == "diagram" else ("wipe" if mode == "stages" else "fade")
        )
        E.SubElement(
            transition, q("p:" + effect), **({"dir": "l"} if effect != "fade" else {})
        )
    next_id = repeat_original_brand(z, slide, master, sr, st, next_id)
    foot = textbox(next_id, "Slide number", [350000, 6400000, 2200000, 240000])
    set_text(
        foot,
        f"{index:02} / {len(plan.slides):02}",
        10,
        color="777777" if mode not in ("cover", "closing") else "999999",
    )
    st.append(foot)
    return root, sr, master, part, imagepart
