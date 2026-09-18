from copy import deepcopy
import posixpath
from lxml import etree as E

NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"


def q(name):
    prefix, local = name.split(":")
    return "{" + NS[prefix] + "}" + local


def parse(data):
    return E.fromstring(data, E.XMLParser(resolve_entities=False, no_network=True))


def xml(root):
    return E.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def relpath(part):
    directory, name = posixpath.split(part)
    return posixpath.join(directory, "_rels", name + ".rels")


def resolve(part, target):
    return posixpath.normpath(posixpath.join(posixpath.dirname(part), target)).lstrip(
        "/"
    )


def relationships(z, part):
    path = relpath(part)
    return (
        parse(z.read(path))
        if path in z.namelist()
        else E.Element("{" + REL + "}Relationships")
    )


def related(z, part, kind):
    return next(
        (
            resolve(part, r.get("Target"))
            for r in relationships(z, part)
            if r.get("Type", "").endswith("/" + kind)
        ),
        None,
    )


def shape_id(shape):
    node = shape.find("p:nvSpPr/p:cNvPr", NS)
    return node.get("id") if node is not None else None


def text(shape):
    return "\n".join(
        "".join(p.xpath(".//a:t/text()", namespaces=NS))
        for p in shape.findall(".//a:p", NS)
    )


def materialized_layout(z, part):
    root = parse(z.read(part))
    master_part = related(z, part, "slideMaster")
    master = parse(z.read(master_part))
    for shape in root.findall(".//p:sp", NS):
        ph = shape.find("p:nvSpPr/p:nvPr/p:ph", NS)
        if ph is None:
            continue
        kind = ph.get("type", "body")
        match = None
        for candidate in master.findall(".//p:sp", NS):
            cp = candidate.find("p:nvSpPr/p:nvPr/p:ph", NS)
            if cp is not None and cp.get("type", "body") == kind:
                match = candidate
                break
        sppr = shape.find("p:spPr", NS)
        if match is not None and sppr is not None and sppr.find("a:xfrm", NS) is None:
            geom = match.find("p:spPr/a:xfrm", NS)
            if geom is not None:
                sppr.insert(0, deepcopy(geom))
        tx = shape.find("p:txBody", NS)
        if tx is not None:
            style_kind = "titleStyle" if kind in ("title", "ctrTitle") else "bodyStyle"
            style = master.find("p:txStyles/p:" + style_kind, NS)
            lst = tx.find("a:lstStyle", NS)
            if style is not None and lst is not None and len(lst) == 0:
                for node in style:
                    lst.append(deepcopy(node))
    return root, master_part


def geometry(shape):
    xf = shape.find("p:spPr/a:xfrm", NS)
    if xf is None:
        return [0, 0, 0, 0]
    off, ext = xf.find("a:off", NS), xf.find("a:ext", NS)
    if off is None or ext is None:
        return [0, 0, 0, 0]
    return [
        int(off.get("x")),
        int(off.get("y")),
        int(ext.get("cx")),
        int(ext.get("cy")),
    ]
