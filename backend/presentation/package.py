"""PowerPoint relationship graph, original layouts, and package validation."""

import posixpath
from zipfile import ZipFile
from lxml import etree as E
from ..ooxml import NS, REL, CT, q, parse, xml, relpath, resolve, relationships
from .drawing import el

RELBASE = NS["r"] + "/"


def retain_layouts(z, bound_layouts, changed, pres, rels, plan):
    # Retain the actual selected layouts and their original names/slots.
    # Slide objects are materialized for editability; showMasterSp=0 prevents
    # the original background furniture from being drawn a second time.
    for master, parts in bound_layouts.items():
        mr = parse(z.read(master))
        ml = mr.find("p:sldLayoutIdLst", NS)
        if ml is not None:
            mr.remove(ml)
        ml = el("p:sldLayoutIdLst")
        mr.insert(2, ml)
        mrels = relationships(z, master)
        for r in list(mrels):
            if r.get("Type", "").endswith("/slideLayout"):
                mrels.remove(r)
        for i, part in enumerate(sorted(parts), 1):
            rid = f"rIdSelectedLayout{i}"
            node = E.SubElement(ml, q("p:sldLayoutId"), id=str(2147483648 + i))
            node.set(q("r:id"), rid)
            E.SubElement(
                mrels,
                "{" + REL + "}Relationship",
                Id=rid,
                Type=RELBASE + "slideLayout",
                Target=posixpath.relpath(part, posixpath.dirname(master)),
            )
        changed[master] = xml(mr)
        changed[relpath(master)] = xml(mrels)
    changed["ppt/presentation.xml"] = xml(pres)
    changed["ppt/_rels/presentation.xml.rels"] = xml(rels)
    if "docProps/app.xml" in z.namelist():
        app_props = parse(z.read("docProps/app.xml"))
        for prop in list(app_props):
            local = E.QName(prop).localname
            if local == "Slides":
                prop.text = str(len(plan.slides))
            elif local in ("HeadingPairs", "TitlesOfParts"):
                app_props.remove(prop)
        changed["docProps/app.xml"] = xml(app_props)


def package_parts(z, changed, new_types):
    # Follow package relationships to include only referenced artwork and parts.
    rootrels = parse(z.read("_rels/.rels"))
    for r in list(rootrels):
        if r.get("Type", "").endswith("/thumbnail"):
            rootrels.remove(r)
    changed["_rels/.rels"] = xml(rootrels)
    source_names = set(z.namelist())
    kept = set()
    queue = [""]

    def read(name):
        return changed[name] if name in changed else z.read(name)

    while queue:
        part = queue.pop()
        rp = "_rels/.rels" if not part else relpath(part)
        if rp in kept:
            continue
        if rp not in changed and rp not in source_names:
            continue
        kept.add(rp)
        for r in parse(read(rp)):
            if r.get("TargetMode") == "External":
                continue
            target = resolve(part, r.get("Target"))
            if target not in source_names and target not in changed:
                raise ValueError("Missing PowerPoint resource: " + target)
            if target not in kept:
                kept.add(target)
                queue.append(target)
    types = parse(z.read("[Content_Types].xml"))
    for node in list(types):
        if (
            node.tag.endswith("Override")
            and node.get("PartName", "").lstrip("/") not in kept
        ):
            types.remove(node)
    for part, ctype in new_types.items():
        E.SubElement(
            types, "{" + CT + "}Override", PartName="/" + part, ContentType=ctype
        )
    changed["[Content_Types].xml"] = xml(types)
    kept.add("[Content_Types].xml")
    return kept, read


def validate_package(path, expected_count, expected_layouts=None):
    with ZipFile(path) as z:
        if z.testzip():
            raise ValueError("PowerPoint package checksum failed.")
        names = set(z.namelist())
        pres = parse(z.read("ppt/presentation.xml"))
        if len(pres.find("p:sldIdLst", NS)) != expected_count:
            raise ValueError("Slide count validation failed.")
        if expected_layouts is not None:
            for index, number in enumerate(expected_layouts, 1):
                part = f"ppt/slides/generated{index}.xml"
                bindings = [
                    r
                    for r in relationships(z, part)
                    if r.get("Type", "").endswith("/slideLayout")
                ]
                if (
                    len(bindings) != 1
                    or resolve(part, bindings[0].get("Target"))
                    != f"ppt/slideLayouts/slideLayout{number}.xml"
                ):
                    raise ValueError(
                        f"Slide {index} is not bound to its selected company layout."
                    )
        for name in names:
            if name.endswith((".xml", ".rels")):
                root = parse(z.read(name))
                for graphic in root.findall(".//a:graphicData", NS):
                    if (
                        graphic.find("a:tbl", NS) is not None
                        and graphic.get("uri")
                        != "http://schemas.openxmlformats.org/drawingml/2006/table"
                    ):
                        raise ValueError("Invalid native PowerPoint table namespace.")
            if name.endswith(".rels"):
                part = (
                    "" if name == "_rels/.rels" else name.replace("/_rels/", "/")[:-5]
                )
                for r in parse(z.read(name)):
                    if (
                        r.get("TargetMode") != "External"
                        and resolve(part, r.get("Target")) not in names
                    ):
                        raise ValueError("Broken package relationship: " + name)
