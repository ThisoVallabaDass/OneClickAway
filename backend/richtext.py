"""Markdown structure and inline formatting shared by the planner, capacity checks and export.

Two separate concerns live here.

*Block structure* answers "what is this line": a heading and at which depth, a
subheading inside a slide, a quoted callout, a nested bullet, or a slide break.
Heading depths are ranked per document rather than fixed, so a deck written with
`#`/`##` and a deck written with `###`/`**Bold**` both produce the same three
tiers: section divider, slide title, subheading.

*Inline formatting* answers "how does this text read": bold, italic, underline,
strikethrough, monospace and links become separate PowerPoint runs. Delimiters
are formatting, never content, so they are removed from the rendered text while
every supplied word and number is preserved.

Nothing here rewrites wording. Parsing only classifies and splits.
"""

import re

MAX_LEVEL = 2
INDENT_SPACES = 2

ATX = re.compile(r"^(#{1,6})\s*(.*)$")
BOLD_LINE = re.compile(r"^(?:\*\*|__)((?:(?!\*\*|__).)+)(?:\*\*|__)$")
LABEL_LINE = re.compile(r"^([^\n]{1,88}):$")
BREAK_LINE = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})$")
SUBHEADING_ITEM = re.compile(r"^(#{1,6})\s*(.*)$")
QUOTE_ITEM = re.compile(r"^>\s?(.*)$")
LIST_MARKER = re.compile(r"^(?:[-*\u2022\u2023\u25e6]\s+|\d+[.)]\s+)")

# Depths 1-6 are ATX headings. Bold-only and "Label:" lines are weaker markers so a
# document that mixes them with ATX headings still ranks the ATX headings above them.
BOLD_DEPTH = 7
LABEL_DEPTH = 8

BLANK_RUN = {
    "bold": False,
    "italic": False,
    "underline": False,
    "strike": False,
    "code": False,
    "link": None,
    "explicit": False,
}

# Emphasis delimiters must hug their text, so "5 * 3 * 2" and "a_b_c" stay literal.
RULES = [
    (re.compile(r"`([^`\n]+)`"), {"code": True}),
    (re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+|mailto:[^\s)]+)\)"), "link"),
    (re.compile(r"<u>(.+?)</u>", re.S), {"underline": True}),
    (re.compile(r"\+\+(?!\s)(.*?)(?<!\s)\+\+", re.S), {"underline": True}),
    (re.compile(r"~~(?!\s)(.*?)(?<!\s)~~", re.S), {"strike": True}),
    (re.compile(r"\*\*(?!\s)(.*?)(?<!\s)\*\*", re.S), {"bold": True}),
    (re.compile(r"(?<![\w])__(?!\s)(.*?)(?<!\s)__(?![\w])", re.S), {"bold": True}),
    (re.compile(r"\*(?!\s)([^*\n]*?)(?<!\s)\*"), {"italic": True}),
    (re.compile(r"(?<![\w])_(?!\s)([^_\n]*?)(?<!\s)_(?![\w])"), {"italic": True}),
]
ESCAPE = re.compile(r"\\([*_~`+\[\]<>\\#>])")


def inline_runs(value, depth=0, **style):
    """Split one line into formatting runs. Delimiters are consumed, words are not."""
    base = dict(BLANK_RUN, **style)
    runs = []
    buffer = []

    def flush():
        if buffer:
            runs.append(dict(base, text="".join(buffer)))
            buffer.clear()

    value = "" if value is None else str(value)
    index = 0
    while index < len(value):
        escaped = ESCAPE.match(value, index)
        if escaped:
            buffer.append(escaped.group(1))
            index = escaped.end()
            continue
        for pattern, effect in RULES if depth < 4 else []:
            match = pattern.match(value, index)
            if match is None or not match.group(1):
                continue
            flush()
            if effect == "link":
                runs.extend(
                    inline_runs(
                        match.group(1),
                        depth + 1,
                        **dict(base, underline=True, link=match.group(2)),
                    )
                )
            elif effect.get("code"):
                # Monospace spans are literal by definition; no nested parsing.
                runs.append(dict(base, code=True, text=match.group(1)))
            else:
                runs.extend(
                    inline_runs(match.group(1), depth + 1, **dict(base, **effect))
                )
            index = match.end()
            break
        else:
            buffer.append(value[index])
            index += 1
    flush()
    return [run for run in runs if run["text"]]


def plain_text(value):
    """The supplied wording with formatting delimiters removed."""
    return "".join(run["text"] for run in inline_runs(value))


def indent_level(raw):
    body = str(raw).replace("\t", " " * INDENT_SPACES)
    return min((len(body) - len(body.lstrip(" "))) // INDENT_SPACES, MAX_LEVEL)


def heading_depth(raw):
    """Depth of a heading marker, or None for ordinary body text."""
    line = str(raw).strip()
    if not line or BREAK_LINE.fullmatch(line):
        return None
    atx = ATX.match(line)
    if atx:
        return len(atx.group(1))
    if len(line) < 160 and BOLD_LINE.fullmatch(line):
        return BOLD_DEPTH
    if not line.startswith(("-", "*", "\u2022", ">", "|")) and LABEL_LINE.fullmatch(
        line
    ):
        return LABEL_DEPTH
    return None


def heading_text(raw, default=""):
    line = str(raw).strip()
    atx = ATX.match(line)
    if atx:
        line = atx.group(2)
    else:
        bold = BOLD_LINE.fullmatch(line)
        if bold:
            line = bold.group(1)
    return plain_text(line).rstrip(":").strip() or default


def heading_roles(content):
    """Rank the heading markers a document actually uses into three tiers.

    Returns a mapping of raw depth to 'document', 'section', 'slide' or
    'subheading'. A lone top-level heading is the document title rather than a
    section divider, so a deck with one `#` title and many `##` topics does not
    gain a pointless divider slide.
    """
    counts = {}
    for raw in str(content).replace("\r", "").split("\n"):
        depth = heading_depth(raw)
        if depth:
            counts[depth] = counts.get(depth, 0) + 1
    order = sorted(counts)
    if not order:
        return {}
    if len(order) == 1:
        return {order[0]: "slide"}
    # The marker used most often carries the slide titles. Without a clear winner the
    # second-shallowest marker does, which is the ordinary "# part / ## topic" shape.
    leaders = [depth for depth in order if counts[depth] == max(counts.values())]
    slide = leaders[0] if len(leaders) == 1 else order[1]
    above = [depth for depth in order if depth < slide]
    roles = {depth: "document" for depth in above[:-1]}
    if above:
        roles[above[-1]] = "section" if counts[above[-1]] > 1 else "document"
    roles[slide] = "slide"
    for depth in order:
        if depth > slide:
            roles[depth] = "subheading"
    return roles


def parse_item(value, structural=True):
    """Describe one outline item: its role, nesting level and formatting runs.

    Items stay plain strings so the browser outline can round-trip them. The
    prefixes below are the round-trippable encoding of block structure:

    * two leading spaces per nesting level
    * ``### `` for a subheading inside the slide body
    * ``> `` for a quoted callout
    """
    raw = "" if value is None else str(value)
    body = raw.replace("\t", " " * INDENT_SPACES)
    level = indent_level(body) if structural else 0
    payload = body.strip()
    role = "bullet"
    if structural:
        subheading = SUBHEADING_ITEM.match(payload)
        quote = QUOTE_ITEM.match(payload)
        if subheading:
            role, payload = "subheading", subheading.group(2).strip()
        elif quote:
            role, payload = "quote", quote.group(1).strip()
    runs = inline_runs(payload)
    return {
        "raw": raw,
        "role": role,
        "level": level,
        "runs": runs,
        "plain": "".join(run["text"] for run in runs),
        "emphasis": any(
            r["bold"] or r["italic"] or r["underline"] or r["strike"] for r in runs
        ),
        "code": any(r["code"] for r in runs),
        "link": any(r["link"] for r in runs),
    }


def item_prefix(value):
    """The structural prefix of an item, used when a long item must be split."""
    body = str(value).replace("\t", " " * INDENT_SPACES)
    indent = body[: len(body) - len(body.lstrip(" "))]
    marker = re.match(r"(?:#{1,6}\s*|>\s?)", body.lstrip(" "))
    return indent + (marker.group(0) if marker else ""), indent


def encode_subheading(text, level=0):
    return " " * (INDENT_SPACES * level) + "### " + text


def is_structured(items):
    """True when the supplied items carry subheadings, quotes or nesting."""
    for item in items or []:
        block = parse_item(item)
        if block["role"] != "bullet" or block["level"]:
            return True
    return False
