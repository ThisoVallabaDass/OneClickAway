"""Conservative, source-preserving editorial passes before layout selection."""

import re
from .richtext import plain_text, is_structured
from .design import label_parts

TOPICS = {
    "Compute": r"\bcomput(?:e|ing)\b|\bvirtualization\b",
    "Storage": r"\bstorage\b",
    "Databases": r"\bdatabases?\b",
    "Networking": r"\bnetwork(?:ing)?\b",
    "Identity and governance": r"\bidentity\b",
}
UNCERTAIN = re.compile(
    r"^\s*(?:assumption|to verify|unverified|draft)\s*:|\([^)]*\b(?:assumption|verify|unverified|draft|placeholder|TBD)\b[^)]*\)|\[verify\]|\bTBD\b",
    re.I,
)
VERBS = r"provides?|offers?|manages?|supports?|enables?|delivers?|uses?|stores?|runs?|extends?|controls?|protects?|connects?|isolates?|hosts?|allows?|integrates?|optimizes?|filters?|creates?|establishes?|enforces?|evaluates?|distributes?|operates?|is|are|serves?"


def topic(title):
    matches = [
        name for name, pattern in TOPICS.items() if re.search(pattern, title, re.I)
    ]
    return matches[0] if len(matches) == 1 else None


def subject(item):
    """Only identify an explicit subject, never guess it from a bare verb."""
    text = plain_text(item).strip()
    label, sep, detail = label_parts(text)
    if not sep:
        match = re.match(r"^(.{3,65}?)\s+((?:" + VERBS + r")\b.+)$", text)
        if not match:
            return None, text, ""
        label, detail = match.groups()
    key = re.sub(r"[^a-z0-9]", "", label.lower())
    # Product spelling variants describe the same service, not separate topics.
    key = key.removeprefix("azure")
    aliases = {
        "vms": "virtualmachines",
        "diskstorage": "manageddisks",
        "virtualnetworkvnet": "virtualnetwork",
        "rolebasedaccesscontrolrbac": "rbac",
        "rolebasedaccesscontrol": "rbac",
    }
    return aliases.get(key, key), label, detail.strip()


def consolidate(body, warnings):
    """Merge repeated topic blocks and explicit service subjects; retain details."""
    output = []
    groups = {}
    merged = 0
    for original in body:
        s = dict(original, items=list(original["items"]))
        s["source_text"] = original.get("source_text", "")
        uncertain = [x for x in s["items"] if UNCERTAIN.search(plain_text(x))]
        if uncertain:
            s["items"] = [x for x in s["items"] if x not in uncertain]
            s["source_text"] += (
                "\nUnverified statements withheld from visible slides:\n"
                + "\n".join(uncertain)
            )
            warnings.append(
                f"Unverified content on “{s['title']}” was moved to speaker notes for review."
            )
        if (
            not s["items"]
            and not s.get("table")
            and not s.get("diagram")
            and s["kind"] != "section"
        ):
            # Retain the note on the adjacent slide when there is nothing verified to show.
            if output:
                output[-1]["source_text"] += "\n" + s["source_text"]
            else:
                groups.setdefault("_withheld", []).append(s["source_text"])
            continue
        key = (s.get("section"), topic(s["title"]))
        eligible = (
            key[1]
            and not any(s.get(x) for x in ("table", "diagram", "image"))
            and s["kind"] != "section"
            and not is_structured(s["items"])
        )
        if (
            eligible
            and key in groups
            and groups[key]["title"].removesuffix(" (continued)")
            != s["title"].removesuffix(" (continued)")
        ):
            existing = groups[key]
            existing["items"].extend(s["items"])
            existing["source_text"] += (
                "\nMerged source section: " + s["title"] + "\n" + s["source_text"]
            )
            existing["title"] = key[1] + " — services and capabilities"
            existing["_consolidated"] = True
            merged += 1
        else:
            output.append(s)
            if eligible:
                groups[key] = s
    for s in output:
        if (
            s.get("_consolidated")
            and not is_structured(s["items"])
            and not s.get("table")
            and not s.get("diagram")
        ):
            items = []
            subjects = {}
            exact = set()
            for item in s["items"]:
                normalized = plain_text(item).casefold().strip()
                if normalized in exact:
                    continue
                exact.add(normalized)
                key, label, detail = subject(item)
                if key and key in subjects:
                    index, old_label, details = subjects[key]
                    if detail.casefold().rstrip(".") not in [
                        x.casefold().rstrip(".") for x in details
                    ]:
                        details.append(detail)
                    items[index] = (
                        old_label
                        + ": "
                        + "; ".join(x.rstrip(".;") for x in details)
                        + "."
                    )
                else:
                    if key:
                        subjects[key] = (len(items), label, [detail])
                    items.append(item)
            s["items"] = items
    if groups.get("_withheld") and output:
        output[0]["source_text"] += "\n" + "\n".join(groups["_withheld"])
    if merged:
        warnings.append(
            f"Consolidated {merged} repeated topic section(s). Distinct service details are retained; longer sections use continuation slides."
        )
    return output, groups.get("_withheld", []) if not output else []


def synthesize(body):
    """Grounded editorial recommendations, never a sample of existing bullets.

    Only known cross-section relationships are synthesized. Sparse or unrelated
    notes require an author-written conclusion instead of a fabricated finding.
    """
    themes = {topic(s["title"]) for s in body}
    points = []
    sources = []
    services = [
        name.lower() for name in ("Compute", "Storage", "Databases") if name in themes
    ]
    if len(services) >= 2:
        points.append(
            "Workload fit: Choose "
            + ", ".join(services[:-1])
            + " and "
            + services[-1]
            + " together around the needs of each workload."
        )
        sources.extend(
            s["title"]
            for s in body
            if topic(s["title"]) in ("Compute", "Storage", "Databases")
        )
    if "Networking" in themes and "Identity and governance" in themes:
        points.append(
            "Shared controls: Plan connectivity, access and governance together across the services you adopt."
        )
        sources.extend(
            s["title"]
            for s in body
            if topic(s["title"]) in ("Networking", "Identity and governance")
        )
    for s in body:
        labels = [label_parts(x)[0] for x in s["items"]]
        if len(labels) >= 3 and all(
            re.match(r"(?:stage|step|phase)\s*\d+", x, re.I) for x in labels
        ):
            names = [
                re.sub(
                    r"^(?:stage|step|phase)\s*\d+\s*[:.\-—–]*\s*", "", x, flags=re.I
                ).strip()
                for x in labels
            ]
            if all(names):
                points.append(
                    "Delivery sequence: Connect "
                    + ", ".join(x.lower() for x in names[:-1])
                    + " and "
                    + names[-1].lower()
                    + " in one delivery plan."
                )
                sources.append(s["title"])
                break
    if len(points) < 2:
        return None
    return dict(
        title="Conclusion",
        kind="content",
        items=points[:3],
        source_text="Editorial synthesis: recommendations inferred from the supplied sections, not new product claims.\nSources: "
        + "; ".join(dict.fromkeys(sources)),
    )
