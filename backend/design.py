"""Layout compatibility, typography and content assignment shared by plan/export."""

import os
import re
from functools import lru_cache
from pathlib import Path
from PIL import ImageFont
from .richtext import parse_item, plain_text

FONT_PAIRS = {
    "modern": ("Bahnschrift", "Segoe UI"),
    "corporate": ("Arial", "Calibri"),
    "editorial": ("Georgia", "Calibri"),
}
FONT_FILES = {
    "Bahnschrift": "bahnschrift.ttf",
    "Segoe UI": "segoeui.ttf",
    "Arial": "arial.ttf",
    "Calibri": "calibri.ttf",
    "Georgia": "georgia.ttf",
}
CODE_FONT = "Consolas"

# A subheading reads one step above its bullets; a quote matches them.
# Export applies exactly these numbers, so measurement and rendering cannot drift.
ROLE_SCALE = {"bullet": 1.0, "subheading": 1.1, "quote": 1.0}
# Paragraph spacing in points. Export writes exactly these values as spcBef/spcAft.
ROLE_SPACE_BEFORE = {"bullet": 0, "subheading": 9, "quote": 7}
ROLE_SPACE_AFTER = {"bullet": 10, "subheading": 3, "quote": 4}
LEVEL_INDENT_PT = [0, 20, 36]
QUOTE_INDENT_PT = 14
# Bold and monospace runs set wider than the measured regular face.
EMPHASIS_STRETCH = 1.05
CODE_STRETCH = 1.12


@lru_cache(maxsize=128)
def font(family, points):
    root = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    path = root / FONT_FILES.get(family, "calibri.ttf")
    if not path.exists():
        # Linux installs can supply equivalent open fonts through this directory.
        path = (
            Path(os.getenv("PPT_FONT_DIR", "/usr/share/fonts/truetype/dejavu"))
            / "DejaVuSans.ttf"
        )
    try:
        return ImageFont.truetype(str(path), round(points * 4))
    except OSError:
        return ImageFont.load_default(size=round(points * 4))


def wrapped_lines(value, width, family, size, stretch=1.0):
    face = font(family, size)
    lines = 0
    width = width / max(stretch, 1e-6)
    for paragraph in str(value).split("\n"):
        line = ""
        for word in paragraph.split():
            if face.getlength(word) / 4 > width:
                # Long URLs and identifiers must not overrun the text box.
                if line:
                    lines += 1
                    line = ""
                segment = ""
                for char in word:
                    if segment and face.getlength(segment + char) / 4 > width:
                        lines += 1
                        segment = ""
                    segment += char
                line = segment
                continue
            candidate = (line + " " + word).strip()
            if line and face.getlength(candidate) / 4 > width:
                lines += 1
                line = word
            else:
                line = candidate
        lines += 1
    return lines


def block_metrics(values, structural=False, literal=False):
    """Measurable description of each paragraph: plain wording, indent and scaling.

    Formatting delimiters never consume space, and a subheading or nested bullet
    is measured at the size and indent the exporter will actually apply.
    """
    values = values if isinstance(values, list) else [values]
    metrics = []
    for value in values or [""]:
        if literal:
            metrics.append(
                {
                    "plain": "" if value is None else str(value),
                    "role": "bullet",
                    "level": 0,
                    "stretch": 1.0,
                }
            )
            continue
        block = parse_item(value, structural)
        stretch = 1.0
        if block["emphasis"]:
            stretch = EMPHASIS_STRETCH
        if block["code"]:
            stretch = max(stretch, CODE_STRETCH)
        metrics.append(
            {
                "plain": block["plain"],
                "role": block["role"],
                "level": block["level"],
                "stretch": stretch,
            }
        )
    return metrics


def fitted_size(
    bounds,
    values,
    preferred=22,
    minimum=14,
    family="Segoe UI",
    bullets=False,
    structural=False,
    literal=False,
    paragraph_after=None,
):
    width = max(bounds[2] / 12700 - 20 - (16 if bullets else 0), 1)
    height = max(bounds[3] / 12700 - 12, 1)
    metrics = block_metrics(values, structural, literal)
    last = len(metrics) - 1
    for size in range(int(preferred), minimum - 1, -1):
        used = 0.0
        for index, block in enumerate(metrics):
            scaled = max(round(size * ROLE_SCALE[block["role"]]), 1)
            indent = LEVEL_INDENT_PT[block["level"]] + (
                QUOTE_INDENT_PT if block["role"] == "quote" else 0
            )
            usable = max(width - indent, 20)
            used += (
                wrapped_lines(block["plain"], usable, family, scaled, block["stretch"])
                * scaled
                * 1.27
            )
            if index:
                used += ROLE_SPACE_BEFORE[block["role"]]
            if index != last:
                used += (
                    ROLE_SPACE_AFTER[block["role"]]
                    if paragraph_after is None
                    else paragraph_after
                )
        if used <= height:
            return size
    raise ValueError(
        "Text exceeds the readable capacity of this layout. Shorten the edited text or replan the presentation."
    )


def label_parts(item):
    """Split a formatted label without cutting through its emphasis markers."""
    item = str(item).strip()
    match = re.match(r"^(\*\*|__)(.+?):\1\s*(.*)$", item, re.S)
    if match:
        return plain_text(match[2]), ":", match[3].strip()
    match = re.match(r"^(\*\*|__)(.+?)\1:\s*(.*)$", item, re.S)
    if match:
        return plain_text(match[2]), ":", match[3].strip()
    label, sep, body = item.partition(":")
    if sep and ("**" in label or "__" in label):
        label, sep, body = plain_text(item).partition(":")
    return plain_text(label).strip(), sep, body.strip()


def split_label(item, index, stage=False):
    label, sep, body = label_parts(item)
    if stage and sep:
        label = re.sub(
            r"^(?:Stage|Step|Phase)\s+\d+\s*[—–-]?\s*", "", label, flags=re.I
        )
    if sep and len(label) <= 38:
        return label.strip(), body.strip()
    # Do not summarize away any words to make a heading.
    return (f"Step {index + 1}" if stage else f"{index + 1:02}"), item


def column_split(items):
    """Where a two-column layout should break, keeping each subheading with its points.

    Returns None when no break respects the subheadings, so the layout is skipped
    rather than splitting a heading away from the content it introduces.
    """
    roles = [parse_item(item)["role"] for item in items]
    mid = (len(items) + 1) // 2
    if "subheading" not in roles:
        return mid
    marks = [
        index for index, role in enumerate(roles) if role == "subheading" and index
    ]
    if not marks:
        return None
    return min(marks, key=lambda index: (abs(index - mid), index))


def assignments(profile, title, items):
    out = {profile["title"]: title}
    body = profile["body"]
    mode = profile["mode"]
    if mode == "groups":
        from .human_design import groups_for

        lead, groups = groups_for(items)
        if lead or len(groups) != 2 or not all(g[1] for g in groups):
            raise ValueError("This comparison needs two named, populated groups.")
        for i, (label, values) in enumerate(groups):
            out[profile["labels"][i]] = label
            out[body[i]] = values
    elif mode in ("bullets", "image"):
        out[body[0]] = items
    elif mode == "columns":
        mid = column_split(items)
        if mid is None:
            raise ValueError(
                "A two-column layout would separate a subheading from its points."
            )
        out[body[0]] = items[:mid]
        out[body[1]] = items[mid:]
    elif mode in ("items", "pairs", "stages"):
        if len(items) > len(body):
            raise ValueError("Too many items for this layout.")
        for i, item in enumerate(items):
            if mode in ("pairs", "stages"):
                label, desc = split_label(item, i, mode == "stages")
                out[profile["labels"][i]] = label
                out[body[i]] = desc
                if mode == "stages" and profile.get("numbers"):
                    out[profile["numbers"][i]] = str(i + 1).zfill(2)
            else:
                out[body[i]] = item
    return out


def text_specs(profile, ident, style="modern"):
    heading, body = FONT_PAIRS[style]
    mode = profile["mode"]
    if ident in profile.get("sizes", {}):
        preferred, minimum = profile["sizes"][ident]
        return (
            (
                heading
                if ident == profile["title"] or ident in profile.get("labels", [])
                else body
            ),
            preferred,
            minimum,
            mode == "groups" and ident in profile["body"],
        )
    if ident == profile["title"]:
        if mode == "cover":
            return heading, 48, 30, False
        if mode == "closing":
            return heading, 44, 32, False
        if mode == "section":
            return (
                heading,
                profile.get("title_size", 34),
                profile.get("title_min", 18),
                False,
            )
        return heading, 28, 20, False
    if ident in profile.get("labels", []):
        return heading, 18, 14, False
    if mode in ("bullets", "columns", "image", "groups"):
        return body, 22, 17, True
    return body, 18 if mode == "items" else 16, 14, False


def text_treatment(number, profile, ident, style="modern", items=None):
    """Content-aware typography inside the original neutral text placeholders.

    Eligibility uses the whole slide, so a dense six-point slide does not become
    a sparse slide merely because each column contains three points. Structured
    outlines keep their existing hierarchy, spacing and top alignment.
    """
    family, preferred, minimum, bullets = text_specs(profile, ident, style)
    treatment = dict(
        family=family,
        preferred=preferred,
        minimum=minimum,
        bullets=bullets,
        anchor=None,
        paragraph_after=None,
    )
    if (
        number not in (13, 16)
        or ident not in profile["body"]
        or not items
        or len(items) > 3
    ):
        return treatment
    blocks = [parse_item(item, True) for item in items]
    words = [len(block["plain"].split()) for block in blocks]
    if (
        not all(0 < count <= 40 for count in words)
        or sum(words) > 80
        or any(
            block["role"] != "bullet"
            or block["level"]
            or block["code"]
            or "\n" in block["plain"]
            for block in blocks
        )
    ):
        return treatment
    # A body point may match the title size, but never exceed its fixed 28pt.
    # The fitter still checks wrapping and may reduce this preference if needed.
    treatment.update(preferred=28, anchor="ctr", paragraph_after=24)
    return treatment


def geometry_override(number, ident, bounds, profile):
    b = list(bounds)
    if ident == profile["title"]:
        if profile["mode"] == "cover":
            b = [6096000, 2300000, 5500000, 2600000]
        elif profile["mode"] == "closing":
            b = [4200000, 2800000, 3800000, 1200000]
        elif profile["mode"] == "section":
            # Grow the splitter caption downward only. Every divider caption sits inside
            # a panel that continues below it, so longer section names stay on the panel.
            b[3] = max(b[3], profile.get("title_height", 1250000))
        elif profile.get("normalize_title", True) and profile["mode"] not in (
            "closing",
            "section",
            "image",
        ):
            b = [450000, 190000, 11200000, 700000]
    if number == 97 and ident in profile["body"]:
        end = b[0] + b[2]
        b[0] = 2000000
        b[2] = end - b[0]
    # These original decorative boxes use text inset past an overlapping circle.
    if number == 99 and ident in profile["body"]:
        b[0] += 370000
        b[2] -= 370000
    # The three-circle template has clear space beneath each original caption.
    # Use it for readable copy instead of rejecting ordinary 20-word descriptions.
    if number == 77 and ident in profile["body"]:
        b[3] = 1900000
    if profile["kind"] == "agenda" and ident in profile["body"]:
        b[3] = max(b[3], 450000)
    if ident in profile.get("labels", []):
        b[3] = max(b[3], 400000)
    if number == 114 and ident in profile["labels"]:
        b[1] = 2500000
        b[3] = 1100000
    return profile.get("bounds", {}).get(ident, b)


# Original "Slide Splitter" designs that carry a top-level heading. Each keeps the
# template's own caption colour, so the generator never guesses contrast against the
# artwork behind it, and caption sizes follow each design's own declared size.
# Splitters 1, 3, 6 and 8 are excluded: their decoration is a multi-megabyte bitmap,
# and including one would multiply the size of every deck that has dividers. The
# order below is lightest first, so a two-division deck stays close to the reference size.
SECTION_LAYOUTS = {
    22: {"title": "30", "title_size": 34, "title_min": 18, "title_height": 1300000},
    30: {"title": "4", "title_size": 26, "title_min": 14, "title_height": 1300000},
    27: {"title": "2", "title_size": 26, "title_min": 14, "title_height": 1300000},
    25: {"title": "3", "title_size": 32, "title_min": 16, "title_height": 1300000},
    # This caption box starts a fraction left of the canvas in the source design.
    29: {
        "title": "4",
        "title_size": 26,
        "title_min": 14,
        "title_height": 1300000,
        "bounds": {"4": [0, 3429000, 3238285, 1300000]},
    },
}
SECTION_ORDER = [22, 30, 27, 25, 29]


def add_profiles(profiles):
    # Visually duplicate text layouts stay searchable but do not consume variety.
    profiles.pop(15, None)
    for number, spec in SECTION_LAYOUTS.items():
        profiles[number] = {
            "kind": "section",
            "body": [],
            "mode": "section",
            "inherit_style": True,
            **spec,
        }
    profiles[32] = {
        "kind": "agenda",
        "title": "5",
        "body": ["86", "88", "90", "92", "102", "104", "106", "108"],
        "mode": "items",
    }
    profiles[32]["sizes"] = {ident: (22, 17) for ident in profiles[32]["body"]}
    profiles[32]["bounds"] = {
        ident: [x, y, 2981021, 1160000]
        for ident, x, y in zip(
            profiles[32]["body"],
            [2817436] * 4 + [8194979] * 4,
            [1053805, 2338319, 3611947, 4896462] * 2,
        )
    }
    profiles[32]["rows"] = [
        ["2", "3", "85", "86"],
        ["4", "6", "87", "88"],
        ["7", "8", "89", "90"],
        ["9", "10", "91", "92"],
        ["19", "20", "101", "102"],
        ["21", "22", "103", "104"],
        ["23", "24", "105", "106"],
        ["25", "26", "107", "108"],
    ]
    profiles[37]["bounds"] = {
        ident: [359353, 1100000 + i * 740000, 11200000, 720000]
        for i, ident in enumerate(profiles[37]["body"])
    }
    profiles[37]["sizes"] = {ident: (22, 17) for ident in profiles[37]["body"]}
    profiles[37]["row_lines"] = ["4", "5", "10", "11", "19", "20", "21"]
    profiles[31] = {
        "kind": "agenda",
        "title": "5",
        "body": ["36", "40", "42", "44", "46", "48"],
        "mode": "items",
    }
    profiles[18] = {
        "kind": "content",
        "title": "2",
        "body": ["4", "3"],
        "mode": "columns",
        "normalize_title": False,
    }
    profiles[19] = {
        "kind": "content",
        "title": "2",
        "body": ["4"],
        "mode": "image",
        "picture": [5067300, 900000, 6679958, 4500000],
    }
    profiles[99] = {
        "kind": "pointers",
        "title": "2",
        "body": ["7", "13", "8", "12", "10", "16"],
        "mode": "items",
        "exact": 6,
    }
    profiles[104] = {
        "kind": "blocks",
        "title": "2",
        "body": ["4", "5", "6", "7"],
        "mode": "items",
        "exact": 4,
        "text_color": "FFFFFF",
    }
    pairs = {
        114: ("pointers", ["18", "19", "20"], ["26", "27", "55"]),
        116: ("circle", ["40", "32", "36"], ["41", "33", "37"]),
        80: ("circle", ["41", "45", "39", "43"], ["42", "46", "40", "44"]),
        87: ("cycle", ["53", "43", "47", "55"], ["54", "44", "48", "56"]),
        126: ("comparison", ["40", "44"], ["41", "45"]),
        149: ("goals", ["46", "48", "50", "52"], ["47", "49", "51", "53"]),
        151: ("goals", ["55", "65", "67", "69"], ["56", "66", "68", "70"]),
        160: ("blocks", ["41", "44", "42", "43"], ["33", "34", "35", "36"]),
        162: ("blocks", ["47", "51", "49", "53"], ["48", "52", "50", "54"]),
        163: (
            "blocks",
            ["164", "174", "166", "170", "168", "172"],
            ["165", "175", "167", "171", "169", "173"],
        ),
    }
    for n, (kind, labels, body) in pairs.items():
        profiles[n] = {
            "kind": kind,
            "title": "5",
            "body": body,
            "labels": labels,
            "mode": "pairs",
            "exact": len(body),
        }
    for n in [126, 149, 151]:
        profiles[n]["text_color"] = "FFFFFF"
    profiles[87]["clear"] = ["84"]  # Source design's stray "x" in its centre.
    profiles[160]["body_color"] = "FFFFFF"
    profiles[114].update(label_color="FFFFFF", label_align="ctr", label_anchor="ctr")
    # Blank source content layouts supply the KaarTech theme for editable graphs.
    profiles[20] = {
        "kind": "architecture",
        "title": "generated-title",
        "body": [],
        "mode": "diagram",
        "orientation": "horizontal",
    }
    profiles[9] = {
        "kind": "process",
        "title": "generated-title",
        "body": [],
        "mode": "diagram",
        "orientation": "vertical",
        "clear_art": True,
    }
    # Verified against the 2024 guide. These profiles retain the source artwork
    # and use only existing text placeholders, with no generic white overlay.
    profiles[17] = {
        "kind": "comparison",
        "title": "10",
        "body": ["4", "6"],
        "labels": ["3", "5"],
        "mode": "groups",
        "normalize_title": False,
        "sizes": {"3": (24, 20), "5": (24, 20)},
    }
    profiles[77] = {
        "kind": "content",
        "title": "2",
        "body": ["68", "62", "66"],
        "mode": "items",
        "exact": 3,
        "normalize_title": False,
        "sizes": {k: (20, 17) for k in ["68", "62", "66"]},
    }
    profiles[119] = {
        "kind": "content",
        "title": "2",
        "body": ["12", "16", "19", "22"],
        "labels": ["10", "18", "21", "24"],
        "mode": "pairs",
        "exact": 4,
        "normalize_title": False,
        "label_color": "FFFFFF",
        "text_overlay": ["12", "16", "19", "22"],
        "sizes": {
            **{k: (20, 17) for k in ["12", "16", "19", "22"]},
            **{k: (20, 17) for k in ["10", "18", "21", "24"]},
        },
    }
    profiles[153] = {
        "kind": "content",
        "title": "5",
        "body": ["37", "38", "39", "40", "41"],
        "labels": ["27", "28", "29", "30", "31"],
        "mode": "pairs",
        "exact": 5,
        "normalize_title": False,
        "label_color": "FFFFFF",
        "sizes": {k: (19, 16) for k in ["37", "38", "39", "40", "41"]},
    }
    profiles[104]["sizes"] = {k: (24, 18) for k in profiles[104]["body"]}
    # The circular fields carry the item numbers themselves. The separate
    # overlaid number text boxes from the template are removed during export.
    profiles[97]["numbers"] = ["4", "6", "7", "8"]
    profiles[97]["drop"] = ["15", "16", "17", "18"]
    agenda_slots = ["56", "60", "64", "68", "74"]
    profiles[35] = {
        "kind": "agenda",
        "title": "2",
        "body": agenda_slots,
        "mode": "items",
        "normalize_title": False,
        "title_color": "FFFFFF",
        "bounds": {
            "2": [900000, 2900000, 3450000, 900000],
            **{
                ident: [7031531, y, 4400000, 840000]
                for ident, y in zip(
                    agenda_slots, [488696, 1729668, 2959754, 4222497, 5463468]
                )
            },
        },
        "sizes": {"2": (32, 28), **{ident: (24, 20) for ident in agenda_slots}},
    }
    # The two large blank comparison columns belong to the official template.
    # Their headings and body groups are populated independently.
    return profiles
