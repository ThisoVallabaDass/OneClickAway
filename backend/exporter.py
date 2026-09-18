"""Lossless template packaging using the public Office Open XML format.

Copy the company's artwork and theme bytes verbatim. Materialize layout shapes
as slide objects so the generated text is editable in normal PowerPoint view.
No Office license or paid presentation SDK is required to generate a deck.
"""

import posixpath
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E
from .config import TEMPLATE
from .ooxml import NS, REL, q, parse, xml, relpath, relationships, related
from .presentation.drawing import el, notes_xml
from .presentation.renderer import render_slide
from .presentation.package import (
    retain_layouts,
    package_parts,
    validate_package as validate_package,
)

RELBASE = NS["r"] + "/"


def generate_deck(plan, destination, progress=lambda _: None):
    adjusted = 0
    if plan.template_engine >= 5:
        from .template_engine import repair_edits

        adjusted = repair_edits(plan, progress)
    if plan.template_engine >= 7:
        from .quality import lint_deck

        for severity, message in lint_deck([s.model_dump() for s in plan.slides]):
            if severity == "error":
                raise ValueError(message)
            if message not in plan.warnings:
                plan.warnings.append(message)
    # Covers, dividers, agendas and closings are navigation furniture and repeat by design.
    # The no-repeat rule applies to the layouts that carry content.
    # Layout variety is a preference. Readable, semantically appropriate company
    # layouts may repeat when their family has no fitting alternative.
    if any(len(item) > 800 for s in plan.slides for item in s.items):
        raise ValueError("One outline item is too long. Break it into shorter points.")
    changed = {}
    new_types = {}
    bound_layouts = {}
    slide_parts = []
    with ZipFile(TEMPLATE) as z:
        pres = parse(z.read("ppt/presentation.xml"))
        rels = relationships(z, "ppt/presentation.xml")
        # Drop the source slide list, section references and hidden guide metadata.
        for tag in ["sldIdLst", "custShowLst", "extLst"]:
            for node in pres.findall("p:" + tag, NS):
                pres.remove(node)
        ids = el("p:sldIdLst")
        master_list = pres.find("p:sldMasterIdLst", NS)
        pres.insert(list(pres).index(master_list) + 1, ids)
        for r in list(rels):
            if r.get("Type", "").endswith(("/slide", "/customXml")):
                rels.remove(r)
        notes_master = related(z, "ppt/presentation.xml", "notesMaster")
        for index, slide in enumerate(plan.slides, 1):
            progress(
                dict(
                    message="Building editable text, artwork and slide numbering…",
                    stage="export",
                    current=index,
                    total=len(plan.slides),
                    title=slide.title,
                )
            )
            root, sr, master, part, imagepart = render_slide(
                z, plan, slide, index, changed, new_types
            )
            bound_layouts.setdefault(master, set()).add(part)
            slidepart = f"ppt/slides/generated{index}.xml"
            slide_parts.append(slidepart)
            changed[slidepart] = xml(root)
            new_types[slidepart] = (
                "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"
            )
            if imagepart:
                E.SubElement(
                    sr,
                    "{" + REL + "}Relationship",
                    Id="rIdDownloadedImage",
                    Type=RELBASE + "image",
                    Target=posixpath.relpath(imagepart, "ppt/slides"),
                )
            E.SubElement(
                sr,
                "{" + REL + "}Relationship",
                Id="rIdGeneratedLayout",
                Type=RELBASE + "slideLayout",
                Target=posixpath.relpath(part, "ppt/slides"),
            )
            notepart = f"ppt/notesSlides/generated{index}.xml"
            changed[notepart] = xml(notes_xml(slide, index))
            new_types[notepart] = (
                "application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"
            )
            E.SubElement(
                sr,
                "{" + REL + "}Relationship",
                Id="rIdGeneratedNotes",
                Type=RELBASE + "notesSlide",
                Target=posixpath.relpath(notepart, "ppt/slides"),
            )
            changed[relpath(slidepart)] = xml(sr)
            nr = E.Element("{" + REL + "}Relationships")
            E.SubElement(
                nr,
                "{" + REL + "}Relationship",
                Id="rIdSlide",
                Type=RELBASE + "slide",
                Target=posixpath.relpath(slidepart, "ppt/notesSlides"),
            )
            if notes_master:
                E.SubElement(
                    nr,
                    "{" + REL + "}Relationship",
                    Id="rIdMaster",
                    Type=RELBASE + "notesMaster",
                    Target=posixpath.relpath(notes_master, "ppt/notesSlides"),
                )
            changed[relpath(notepart)] = xml(nr)
            rid = f"rIdGenerated{index}"
            E.SubElement(
                rels,
                "{" + REL + "}Relationship",
                Id=rid,
                Type=RELBASE + "slide",
                Target="slides/generated" + str(index) + ".xml",
            )
            node = E.SubElement(ids, q("p:sldId"), id=str(255 + index))
            node.set(q("r:id"), rid)
        retain_layouts(z, bound_layouts, changed, pres, rels, plan)
        kept, read = package_parts(z, changed, new_types)
        destination.parent.mkdir(parents=True, exist_ok=True)
        progress(
            dict(
                message="Compressing slides and embedded assets into the PowerPoint file…",
                stage="packaging",
                current=len(plan.slides),
                total=len(plan.slides),
                title=None,
            )
        )
        temp = destination.with_suffix(".tmp")
        try:
            with ZipFile(temp, "w", ZIP_DEFLATED, compresslevel=6) as out:
                for name in sorted(kept):
                    out.writestr(name, read(name))
            progress(
                dict(
                    message="Checking the PowerPoint package and all slide relationships…",
                    stage="validation",
                    current=len(plan.slides),
                    total=len(plan.slides),
                    title=None,
                )
            )
            validate_package(
                temp, len(plan.slides), [s.template.number for s in plan.slides]
            )
            temp.replace(destination)
        finally:
            temp.unlink(missing_ok=True)
    return {
        "slide_count": len(plan.slides),
        "bytes": destination.stat().st_size,
        "adjusted_slides": adjusted,
    }


# Compatibility exports used by drawing consumers and regression tests.
from .presentation.drawing import (
    group_tree as group_tree,
    set_text as set_text,
    textbox as textbox,
)
