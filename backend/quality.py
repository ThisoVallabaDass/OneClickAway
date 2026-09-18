"""Editorial checks shared by planning and export; source text is always data."""

import re
from .richtext import plain_text, parse_item
from .design import label_parts

BRANDS = (
    "Google Cloud Platform",
    "Google Cloud",
    "Microsoft Azure",
    "Microsoft Entra ID",
    "KaarTech",
    "Azure",
    "SAP Basis",
    "SAP GUI",
    "SAP S/4HANA",
    "S/4HANA",
    "SAP BTP",
    "SAP Fiori",
    "SAP HXM",
    "SAP PartnerEdge",
    "RISE with SAP",
    "KTern.AI",
    "Kubernetes",
    "PostgreSQL",
    "MySQL",
    "Cosmos DB",
    "Data Lake Storage Gen2",
    "NoSQL",
    "DevOps",
    "MLOps",
    "PowerPoint",
)
ACRONYMS = set(
    "SAP ABAP DEV QAS PRD TMS AWS GCP AI ML ERP API APIs UI UX CX HXM BTP SQL SMB NFS VM VMs VPN RBAC NSG IP IT BI KPI KPIs SDK URL HTTP HTTPS REST LAMP CPU GPU".split()
)
META = re.compile(
    r"^(?:context\s+chain|prompt\s+(?:used|instructions)|generated\s+(?:by|with)|generation\s+notes|end\s+of\s+(?:presentation|response))\s*[:：—–-]",
    re.I,
)


def metadata_line(line):
    # Remove only recognized authoring labels. A meaningful emoji, URL, quote,
    # citation or architecture arrow remains presentation content.
    text = plain_text(line).strip()
    text = re.sub(r"^[^\w]+", "", text)
    return bool(META.match(text))


def clean_source(content):
    kept = []
    removed = []
    chain_pending = False
    for line in content.splitlines():
        if metadata_line(line):
            removed.append(line)
            chain_pending = bool(
                re.search(r"context\s+chain\s*[:：]?\s*$", plain_text(line), re.I)
            )
            continue
        if chain_pending and not line.strip():
            continue
        if chain_pending and re.search(r"→|->", line):
            removed.append(line)
            chain_pending = False
            continue
        chain_pending = False
        kept.append(line)
    return "\n".join(kept), removed


def heading_case(value):
    text = plain_text(value).strip().rstrip(".")
    protected = {}
    pattern = "|".join(re.escape(x) for x in sorted(BRANDS, key=len, reverse=True))

    def protect(match):
        canonical = next(x for x in BRANDS if x.casefold() == match[0].casefold())
        key = f"\ue000{len(protected)}\ue001"
        protected[key] = canonical
        return key

    text = re.sub(r"(?<!\w)(?:" + pattern + r")(?!\w)", protect, text, flags=re.I)
    text = re.sub(
        r"[A-Za-z][A-Za-z0-9]*",
        lambda m: (
            m[0]
            if m[0] in ACRONYMS
            or (not m[0].isupper() and any(c.isupper() for c in m[0][1:]))
            else m[0].lower()
        ),
        text,
    )
    if text and text[0].isalpha():
        text = text[0].upper() + text[1:]
    for key, value in protected.items():
        text = text.replace(key, value)
    return text


def explicit_contrast(slide):
    title = plain_text(slide["title"])
    if re.search(
        r"\b(?:vs\.?|versus|compared? with|pros?\s*(?:/|and|&)\s*cons?)\b", title, re.I
    ):
        return True
    labels = []
    for item in slide["items"]:
        block = parse_item(item)
        if block["role"] == "subheading":
            labels.append(block["plain"].lower())
        elif label_parts(item)[1]:
            labels.append(label_parts(item)[0].lower())
    # Labels need to express actual alternatives; not merely two named facts.
    for left, right in [
        ("traditional", "proposed"),
        ("before", "after"),
        ("pros", "cons"),
        ("option a", "option b"),
        ("current", "proposed"),
    ]:
        if any(
            re.fullmatch(left + r"(?: approach| state| model)?", x) for x in labels
        ) and any(
            re.fullmatch(right + r"(?: approach| state| model)?", x) for x in labels
        ):
            return True
    return False


def agenda_titles(body):
    return list(
        dict.fromkeys(
            s.get("section") or s["title"].removesuffix(" (continued)")
            for s in body
            if s["kind"] not in ("cover", "agenda", "closing")
        )
    )


def lint_deck(slides):
    issues = []
    agendas = [s for s in slides if s["kind"] == "agenda"]
    if len(agendas) > 1:
        issues.append(("error", "The deck contains more than one agenda."))
    for index, s in enumerate(slides, 1):
        values = (
            [s["title"]] + s["items"] + [x for row in s.get("table") or [] for x in row]
        )
        if s.get("diagram"):
            values += s["diagram"]["nodes"] + s["diagram"].get("descriptions", [])
        if any(metadata_line(x) for x in values):
            issues.append(
                (
                    "error",
                    f"Slide {index} contains an AI authoring footer. Remove it from the reviewed outline.",
                )
            )
        n = s.get("template", {}).get("number")
        if n in (17, 126) and not explicit_contrast(s):
            issues.append(
                (
                    "error",
                    f"Slide {index} uses a comparison layout without an explicit contrast. Review its layout.",
                )
            )
        if s["kind"] not in ("cover", "closing", "agenda", "section"):
            if len(s["items"]) > 5:
                issues.append(
                    (
                        "warning",
                        f"“{s['title']}” contains {len(s['items'])} points. Review its density before presenting.",
                    )
                )
            for x in s["items"]:
                if (
                    re.match(r"^(?:Delivers|Provides|Enables|Offers)\b", plain_text(x))
                    and not label_parts(x)[1]
                ):
                    issues.append(
                        (
                            "warning",
                            f"“{s['title']}” has a point without an explicit subject. Review the wording.",
                        )
                    )
                    break
    return issues
