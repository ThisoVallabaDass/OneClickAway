"""Native editable diagrams and contained image placement."""

from lxml import etree as E
from .ooxml import q, NS
from .design import FONT_PAIRS, fitted_size


def add_diagram(tree, spec, first_id, orientation, style, human=False):
    from .exporter import textbox, set_text

    count = len(spec.nodes)
    if any(a < 0 or b < 0 or a >= count or b >= count or a == b for a, b in spec.edges):
        raise ValueError("Architecture connector references an invalid node.")
    heading, body = FONT_PAIRS[style]
    positions = []
    node_ids = []
    next_id = first_id
    if orientation == "vertical":
        gap = 180000
        h = min(710000, (5100000 - (count - 1) * gap) // count)
        positions = [
            [650000, 1100000 + i * (h + gap), 3500000, h] for i in range(count)
        ]
    else:
        gap = 300000
        w = (11200000 - (count - 1) * gap) // count
        positions = [
            [450000 + i * (w + gap), 1950000, w, 1250000] for i in range(count)
        ]
    colors = ["A90000", "E55300", "303136", "727478", "A90000", "303136"]
    for i, (label, bounds) in enumerate(zip(spec.nodes, positions)):
        node = textbox(next_id, f"Architecture node {i + 1}", bounds)
        node_ids.append(next_id)
        next_id += 1
        sp = node.find("p:spPr", NS)
        sp.remove(sp.find("a:noFill", NS))
        geom = E.SubElement(sp, q("a:prstGeom"), prst="roundRect")
        E.SubElement(geom, q("a:avLst"))
        fill = E.SubElement(sp, q("a:solidFill"))
        E.SubElement(fill, q("a:srgbClr"), val=colors[i])
        size = fitted_size(
            bounds, label, 24 if human else 19, 20 if human else 14, heading
        )
        set_text(
            node,
            label,
            size,
            color="FFFFFF",
            family=heading,
            bold=True,
            align="ctr",
            anchor="ctr",
        )
        tree.append(node)
        desc = spec.descriptions[i] if i < len(spec.descriptions) else ""
        if desc:
            if orientation == "vertical":
                db = [4600000, bounds[1], 6900000, bounds[3]]
            else:
                db = [bounds[0], 3500000, bounds[2], 2200000]
            shape = textbox(next_id, f"Architecture detail {i + 1}", db)
            next_id += 1
            size = fitted_size(db, desc, 22 if human else 17, 20 if human else 14, body)
            set_text(shape, desc, size, color="303136", family=body)
            tree.append(shape)
    for source, target in spec.edges:
        a, b = positions[source], positions[target]
        if orientation == "vertical":
            x1, y1 = a[0] + a[2] // 2, a[1] + a[3]
            x2, y2 = b[0] + b[2] // 2, b[1]
            start_idx, end_idx = "2", "0"
        else:
            x1, y1 = a[0] + a[2], a[1] + a[3] // 2
            x2, y2 = b[0], b[1] + b[3] // 2
            start_idx, end_idx = "3", "1"
        connector = E.Element(q("p:cxnSp"))
        nv = E.SubElement(connector, q("p:nvCxnSpPr"))
        E.SubElement(
            nv,
            q("p:cNvPr"),
            id=str(next_id),
            name=f"Connection {source + 1} to {target + 1}",
        )
        next_id += 1
        cp = E.SubElement(nv, q("p:cNvCxnSpPr"))
        E.SubElement(cp, q("a:stCxn"), id=str(node_ids[source]), idx=start_idx)
        E.SubElement(cp, q("a:endCxn"), id=str(node_ids[target]), idx=end_idx)
        E.SubElement(nv, q("p:nvPr"))
        sp = E.SubElement(connector, q("p:spPr"))
        xf = E.SubElement(sp, q("a:xfrm"))
        if x2 < x1:
            xf.set("flipH", "1")
        if y2 < y1:
            xf.set("flipV", "1")
        E.SubElement(xf, q("a:off"), x=str(min(x1, x2)), y=str(min(y1, y2)))
        E.SubElement(xf, q("a:ext"), cx=str(abs(x2 - x1)), cy=str(abs(y2 - y1)))
        g = E.SubElement(sp, q("a:prstGeom"), prst="line")
        E.SubElement(g, q("a:avLst"))
        ln = E.SubElement(sp, q("a:ln"), w="22000")
        fill = E.SubElement(ln, q("a:solidFill"))
        E.SubElement(fill, q("a:srgbClr"), val="7D7D82")
        E.SubElement(ln, q("a:tailEnd"), type="triangle", w="sm", len="sm")
        tree.append(connector)
    return next_id


def add_picture(tree, ref, bounds, ident, relationship):
    # Contain the original image. Diagrams, faces and text are never cropped away.
    x, y, w, h = bounds
    scale = min(w / ref.width, h / ref.height)
    iw = round(ref.width * scale)
    ih = round(ref.height * scale)
    x += (w - iw) // 2
    y += (h - ih) // 2
    pic = E.Element(q("p:pic"))
    nv = E.SubElement(pic, q("p:nvPicPr"))
    E.SubElement(
        nv,
        q("p:cNvPr"),
        id=str(ident),
        name=ref.title,
        descr=f"{ref.title}. {ref.license}. {ref.source_url}",
    )
    cp = E.SubElement(nv, q("p:cNvPicPr"))
    E.SubElement(cp, q("a:picLocks"), noChangeAspect="1")
    E.SubElement(nv, q("p:nvPr"))
    fill = E.SubElement(pic, q("p:blipFill"))
    blip = E.SubElement(fill, q("a:blip"))
    blip.set(q("r:embed"), relationship)
    stretch = E.SubElement(fill, q("a:stretch"))
    E.SubElement(stretch, q("a:fillRect"))
    sp = E.SubElement(pic, q("p:spPr"))
    xf = E.SubElement(sp, q("a:xfrm"))
    E.SubElement(xf, q("a:off"), x=str(x), y=str(y))
    E.SubElement(xf, q("a:ext"), cx=str(iw), cy=str(ih))
    geom = E.SubElement(sp, q("a:prstGeom"), prst="rect")
    E.SubElement(geom, q("a:avLst"))
    tree.append(pic)
