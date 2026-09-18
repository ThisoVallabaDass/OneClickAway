from contextlib import contextmanager
import hashlib
import json
import re
import sqlite3
from zipfile import ZipFile
import numpy as np
from .config import TEMPLATE, DB, EMBED_MODEL
from .ooxml import NS, parse, related, materialized_layout, geometry, text, shape_id
from . import local_ai

DESCRIPTIONS = {
    "cover": "presentation opening title introduction",
    "content": "overview explanation bullet points summary risks benefits metrics",
    "section": "section divider transition topic chapter",
    "agenda": "agenda contents topics outline",
    "quote": "quotation statement insight",
    "pyramid": "hierarchy tiers maturity levels priorities",
    "timeline": "roadmap milestones schedule phases implementation plan chronological",
    "circle": "components concepts related ideas ecosystem",
    "cycle": "cycle iterative loop feedback continuous improvement",
    "pointers": "list key points use cases risks benefits",
    "arrow": "steps directions progression sequence process",
    "table": "tabular data rows columns numbers metrics",
    "comparison": "compare versus alternatives differences pros cons",
    "flow": "workflow process decision sequence architecture",
    "device": "product software screen demo",
    "goal": "goals objectives targets outcomes",
    "blocks": "content groups pillars features use cases",
    "team": "people team members roles",
    "closing": "thank you conclusion closing questions",
}
# Generation uses verified slot mappings. Every other layout remains indexed and searchable.
PROFILES = {
    180: {"kind": "cover", "title": "2", "body": [], "clear": ["6"], "mode": "cover"},
    13: {"kind": "content", "title": "2", "body": ["3"], "mode": "bullets"},
    15: {"kind": "content", "title": "2", "body": ["3"], "mode": "bullets"},
    16: {"kind": "comparison", "title": "2", "body": ["3", "4"], "mode": "columns"},
    37: {
        "kind": "agenda",
        "title": "12",
        "body": ["15", "16", "17", "18", "23", "24", "25"],
        "mode": "items",
    },
    170: {"kind": "closing", "title": "918", "body": [], "mode": "closing"},
    69: {
        "kind": "timeline",
        "title": "2",
        "body": ["26", "27", "28", "29", "30"],
        "labels": ["38", "39", "40", "41", "42"],
        "numbers": ["3", "5", "11", "12", "13"],
        "mode": "stages",
    },
    97: {
        "kind": "pointers",
        "title": "2",
        "body": ["10", "11", "12", "13"],
        "numbers": ["15", "16", "17", "18"],
        "mode": "items",
    },
    14: {"kind": "table", "title": "2", "body": [], "mode": "table"},
}
from .design import add_profiles

add_profiles(PROFILES)


def category(name):
    n = name.lower()
    for token, cat in [
        ("thank you", "closing"),
        ("title slide", "cover"),
        ("content block", "blocks"),
        ("content slide", "content"),
        ("splitter", "section"),
        ("flow diagram", "flow"),
        ("laptop", "device"),
        ("team", "team"),
    ]:
        if token in n:
            return cat
    return next((k for k in DESCRIPTIONS if k in n), "content")


def fingerprint():
    s = TEMPLATE.stat()
    return f"{s.st_size}:{s.st_mtime_ns}"


@contextmanager
def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        with con:
            yield con
    finally:
        con.close()


def stats():
    if not DB.exists():
        return {"documents": 0, "slides": 0, "layouts": 0}
    with connect() as con:
        counts = dict(
            con.execute("SELECT kind, count(*) FROM documents GROUP BY kind").fetchall()
        )
        meta = dict(con.execute("SELECT key,value FROM metadata").fetchall())
    return {
        "documents": sum(counts.values()),
        "slides": counts.get("slide", 0),
        "layouts": counts.get("layout", 0),
        "generation_profiles": len(PROFILES),
        **meta,
    }


def lexical_vector(s, dimensions=768):
    vec = np.zeros(dimensions, dtype=np.float32)
    for word in re.findall(r"\w+", s.lower()):
        h = hashlib.blake2b(word.encode(), digest_size=8).digest()
        vec[int.from_bytes(h, "little") % dimensions] += 1
    return (vec / max(float(np.linalg.norm(vec)), 1e-9)).tolist()


def build_index(progress=print, semantic=True):
    if not TEMPLATE.exists():
        raise ValueError(
            "Template missing. Run scripts/setup.py with the company PPTX path."
        )
    progress("Reading every source slide and reusable layout…")
    docs = []
    with ZipFile(TEMPLATE) as z:
        presentation = parse(z.read("ppt/presentation.xml"))
        rels = {
            r.get("Id"): r.get("Target")
            for r in parse(z.read("ppt/_rels/presentation.xml.rels"))
        }
        from .ooxml import resolve

        slide_parts = [
            resolve("ppt/presentation.xml", rels[s.get("{" + NS["r"] + "}id")])
            for s in presentation.find("p:sldIdLst", NS)
        ]
        layout_slides = {}
        for i, part in enumerate(slide_parts, 1):
            layout = related(z, part, "slideLayout")
            layout_slides.setdefault(layout, []).append(i)
        layouts = sorted(
            [
                n
                for n in z.namelist()
                if re.fullmatch(r"ppt/slideLayouts/slideLayout\d+.xml", n)
            ],
            key=lambda n: int(re.search(r"(\d+)\.xml", n)[1]),
        )
        layout_data = {}
        for part in layouts:
            number = int(re.search(r"(\d+)\.xml", part)[1])
            root, _ = materialized_layout(z, part)
            name = root.find("p:cSld", NS).get("name", "Layout " + str(number))
            cat = category(name)
            slots = []
            for s in root.findall(".//p:sp", NS):
                ph = s.find("p:nvSpPr/p:nvPr/p:ph", NS)
                if ph is not None:
                    slots.append(
                        {
                            "shape_id": shape_id(s),
                            "type": ph.get("type", "body"),
                            "index": ph.get("idx", "0"),
                            "geometry": geometry(s),
                            "sample": text(s),
                        }
                    )
            content = "\n".join(root.xpath("//a:t/text()", namespaces=NS))
            data = {
                "id": f"KTC-L{number:03}",
                "kind": "layout",
                "number": number,
                "part": part,
                "name": name,
                "category": cat,
                "source_slides": layout_slides.get(part, []),
                "source_slide": next(iter(layout_slides.get(part, [])), None),
                "slots": slots,
                "text": content,
                "auto_supported": number in PROFILES,
                "reference_only": True,
                "description": DESCRIPTIONS[cat],
            }
            docs.append(data)
            layout_data[part] = data
        for i, part in enumerate(slide_parts, 1):
            layout = related(z, part, "slideLayout")
            base = layout_data[layout]
            own = "\n".join(parse(z.read(part)).xpath("//a:t/text()", namespaces=NS))
            docs.append(
                {
                    **base,
                    "id": f"KTC-S{i:03}",
                    "kind": "slide",
                    "number": i,
                    "source_slide": i,
                    "part": part,
                    "layout_id": base["id"],
                    "name": f"Slide {i}: {base['name']}",
                    "text": own + "\n" + base["text"],
                    "is_guide": "Guidelines:" in own,
                    "auto_supported": False,
                }
            )
    inputs = [
        f"search_document: {d['name']}. {d['category']}. {d['description']}. "
        f"{len(d['slots'])} text slots. {d['text'][:2000]}"
        for d in docs
    ]
    vectors = []
    model = EMBED_MODEL
    if semantic:
        try:
            for offset in range(0, len(inputs), 24):
                progress(
                    f"Embedding template records {offset + 1}–{min(offset + 24, len(inputs))} of {len(inputs)} locally…"
                )
                vectors.extend(local_ai.embed(inputs[offset : offset + 24]))
        except (OSError, ValueError, KeyError):
            progress(
                "Embedding model unavailable. Building a labeled lexical fallback index."
            )
            model = "local-hash-lexical-v1"
            vectors = []
    else:
        model = "local-hash-lexical-v1"
    if not vectors:
        vectors = [lexical_vector(s) for s in inputs]
    # One transaction publishes the complete index, never a partially embedded library.
    with connect() as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, kind TEXT, category TEXT, payload TEXT, vector BLOB)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)"
        )
        con.execute("DELETE FROM documents")
        con.execute("DELETE FROM metadata")
        for doc, vector in zip(docs, vectors, strict=True):
            v = np.array(vector, dtype=np.float32)
            v /= max(float(np.linalg.norm(v)), 1e-9)
            con.execute(
                "INSERT INTO documents VALUES (?,?,?,?,?)",
                (doc["id"], doc["kind"], doc["category"], json.dumps(doc), v.tobytes()),
            )
        con.executemany(
            "INSERT INTO metadata VALUES (?,?)",
            [
                ("embedding_model", model),
                ("fingerprint", fingerprint()),
                ("schema_version", "1"),
            ],
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_kind_category ON documents(kind,category)"
        )
    progress(f"Indexed {len(docs)} records.")
    return stats()


def ensure_index(progress=print):
    metadata = stats()
    if metadata.get("fingerprint") != fingerprint() or metadata.get(
        "embedding_model"
    ) not in (EMBED_MODEL, "local-hash-lexical-v1"):
        build_index(progress)


def get_layout(number):
    with connect() as con:
        row = con.execute(
            "SELECT payload FROM documents WHERE id=?", (f"KTC-L{number:03}",)
        ).fetchone()
    if row is None:
        raise ValueError("Layout is not indexed.")
    result = json.loads(row[0])
    result["auto_supported"] = number in PROFILES
    return result


def search(query, limit=8, kind=None, supported=False):
    if not DB.exists():
        return []
    model = stats().get("embedding_model")
    lexical = model == "local-hash-lexical-v1"
    try:
        if model not in (EMBED_MODEL, "local-hash-lexical-v1"):
            raise ValueError("Embedding model changed. Rebuild the index.")
        v = np.array(
            lexical_vector(query)
            if lexical
            else local_ai.embed(["search_query: " + query])[0],
            dtype=np.float32,
        )
        v /= max(float(np.linalg.norm(v)), 1e-9)
    except (OSError, ValueError, KeyError):
        v = None  # Never compare vectors from incompatible embedding spaces.
    with connect() as con:
        rows = con.execute(
            "SELECT payload,vector FROM documents" + (" WHERE kind=?" if kind else ""),
            (kind,) if kind else (),
        ).fetchall()
    ranked = []
    tokens = set(re.findall(r"\w+", query.lower()))
    for row in rows:
        d = json.loads(row["payload"])
        d["auto_supported"] = d["kind"] == "layout" and d["number"] in PROFILES
        if supported and (d["kind"] != "layout" or d["number"] not in PROFILES):
            continue
        if v is not None:
            stored = np.frombuffer(row["vector"], dtype=np.float32)
            score = float(v @ stored) if v.shape == stored.shape else 0.0
        else:
            score = len(
                tokens
                & set(re.findall(r"\w+", d["name"].lower() + " " + d["description"]))
            ) / max(len(tokens), 1)
        ranked.append(
            {
                **d,
                "score": round(score, 4),
                "search_mode": "lexical" if lexical or v is None else "semantic",
            }
        )
    return sorted(ranked, key=lambda d: d["score"], reverse=True)[:limit]
