"""Optional keyless Commons image search, licensed downloads and local cache."""

import hashlib
import html
import io
import json
import re
import urllib.parse
import urllib.request
from PIL import Image
from .config import DATA

ASSETS = DATA / "uploads"
ASSETS.mkdir(exist_ok=True)
HOSTS = {"commons.wikimedia.org", "upload.wikimedia.org", "thumb.wikimedia.org"}
USER_AGENT = "KaarTechPresentationStudio/2.0 (local presentation builder; Wikimedia Commons image search)"
TOPICS = [
    (r"\bai\b|artificial intelligence|generative|neural", "artificial intelligence"),
    (r"data center|cloud|server", "data center server racks"),
    (r"robot|manufactur|factory", "industrial robot factory"),
    (r"health|hospital|medical", "medical laboratory"),
    (r"solar|renewable|energy", "solar panels"),
    (r"logistics|warehouse", "warehouse logistics"),
    (r"finance|banking", "financial district skyline"),
    (r"education|learning", "university library"),
]


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlparse(newurl)
        if parsed.scheme != "https" or parsed.hostname not in HOSTS:
            raise ValueError("Unapproved image redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, limit=8_000_000):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in HOSTS:
        raise ValueError("Unapproved image host")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.build_opener(SafeRedirect()).open(req, timeout=15) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Image exceeds download limit")
    return data


def clean(value):
    return html.unescape(re.sub("<[^>]+>", "", value or "")).strip()


def find_image(subject, used=None):
    used = used or set()
    query = next(
        (topic for pattern, topic in TOPICS if re.search(pattern, subject, re.I)), None
    )
    if not query:
        return None
    cache = ASSETS / (hashlib.sha256(query.encode()).hexdigest() + ".json")
    if cache.exists():
        records = json.loads(cache.read_text(encoding="utf8"))
        hit = next(
            (
                r
                for r in records
                if r["id"] not in used and (ASSETS / (r["id"] + ".img")).exists()
            ),
            None,
        )
        if hit:
            return hit
    params = {
        "action": "query",
        "format": "json",
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|mime|size",
        "iiurlwidth": 1280,
    }
    if query == "artificial intelligence":
        params["titles"] = "File:Artificial-Intelligence.jpg|File:NeuralNetwork.png"
    else:
        params.update(
            generator="search",
            gsrsearch=query + " filetype:bitmap",
            gsrnamespace=6,
            gsrlimit=8,
        )
    payload = json.loads(
        fetch(
            "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params),
            2_000_000,
        )
    )
    records = []
    for page in payload.get("query", {}).get("pages", {}).values():
        info = next(iter(page.get("imageinfo", [])), {})
        meta = info.get("extmetadata", {})
        license = clean(meta.get("LicenseShortName", {}).get("value", ""))
        if not re.match(r"^(CC0|Public domain|CC BY(?:-SA)? [\d.]+)$", license):
            continue
        if (
            info.get("mime") not in ("image/png", "image/jpeg")
            or info.get("width", 0) < 500
        ):
            continue
        url = info.get("thumburl") or info.get("url")
        try:
            data = fetch(url)
            with Image.open(io.BytesIO(data)) as picture:
                if (
                    picture.format not in ("JPEG", "PNG")
                    or picture.width * picture.height > 25_000_000
                ):
                    continue
                width, height = picture.size
                picture.verify()
            ident = hashlib.sha256(data).hexdigest()
            if ident in used:
                continue
            (ASSETS / (ident + ".img")).write_bytes(data)
            record = {
                "id": ident,
                "title": page["title"].removeprefix("File:"),
                "source_url": info["descriptionurl"],
                "license": license,
                "author": clean(meta.get("Artist", {}).get("value", "Unknown author"))[
                    :600
                ],
                "width": width,
                "height": height,
            }
            (ASSETS / (ident + ".metadata.json")).write_text(
                json.dumps(record, indent=2), encoding="utf8"
            )
            records.append(record)
            break
        except (OSError, ValueError):
            continue
    if records:
        cache.write_text(json.dumps(records), encoding="utf8")
    return next(iter(records), None)


def image_bytes(ident):
    if not re.fullmatch("[a-f0-9]{64}", ident):
        raise ValueError("Invalid image ID")
    data = (ASSETS / (ident + ".img")).read_bytes()
    if hashlib.sha256(data).hexdigest() != ident:
        raise ValueError("Image cache checksum failed")
    return data


def save_upload(data, name):
    """Validate local uploads and re-encode pixels without embedded metadata."""
    if len(data) > 8_000_000:
        raise ValueError("Choose a PNG or JPEG smaller than 8 MB.")
    try:
        opened = Image.open(io.BytesIO(data))
    except Image.DecompressionBombError as exc:
        raise ValueError(
            "Choose a picture with no more than 25 million pixels."
        ) from exc
    with opened as picture:
        if (
            picture.format not in ("PNG", "JPEG")
            or picture.width * picture.height > 25_000_000
        ):
            raise ValueError(
                "Choose a PNG or JPEG with no more than 25 million pixels."
            )
        picture.load()
        from PIL import ImageOps

        picture = ImageOps.exif_transpose(picture)
        picture = picture.convert("RGBA" if "A" in picture.getbands() else "RGB")
        buf = io.BytesIO()
        picture.save(buf, format="PNG")
        data = buf.getvalue()
        width, height = picture.size
    ident = hashlib.sha256(data).hexdigest()
    record = dict(
        id=ident,
        title=name[:160] or "Uploaded picture",
        source_url="",
        license="User supplied",
        author="User",
        width=width,
        height=height,
    )
    (ASSETS / (ident + ".img")).write_bytes(data)
    (ASSETS / (ident + ".metadata.json")).write_text(
        json.dumps(record), encoding="utf8"
    )
    return record
