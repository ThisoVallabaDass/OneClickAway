"""Bounded request ingestion and browser-session ownership."""

import hashlib
import re
import secrets
from http.cookies import SimpleCookie

from starlette.responses import JSONResponse


class BrowserBoundary:
    def __init__(self, app, origins, secure=False):
        self.app = app
        self.origins = set(origins)
        self.secure = secure

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        origin = headers.get(b"origin", b"").decode("latin1")
        if scope["method"] not in ("GET", "HEAD", "OPTIONS") and (
            origin
            and origin not in self.origins
            or headers.get(b"sec-fetch-site") == b"cross-site"
        ):
            return await JSONResponse(
                {"detail": "This origin cannot submit requests."}, 403
            )(scope, receive, send)
        cookies = SimpleCookie()
        try:
            cookies.load(headers.get(b"cookie", b"").decode("latin1"))
            token = (
                cookies["studio_session"].value if "studio_session" in cookies else ""
            )
        except Exception:
            token = ""
        new = not re.fullmatch(r"[a-f0-9]{64}", token)
        if new:
            token = secrets.token_hex(32)
        scope.setdefault("state", {})["owner"] = hashlib.sha256(
            token.encode()
        ).hexdigest()

        async def respond(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", []))
                if new:
                    cookie = f"studio_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=2592000"
                    if self.secure:
                        cookie += "; Secure"
                    message["headers"].append((b"set-cookie", cookie.encode()))
                if scope["path"].startswith("/api/"):
                    message["headers"].append((b"cache-control", b"no-store"))
            await send(message)

        await self.app(scope, receive, respond)


class RequestLimit:
    """Buffer at most the endpoint budget, before JSON parsing or route dispatch."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)
        limit = 8_000_000 if scope["path"] == "/api/images/upload" else 1_000_000
        headers = dict(scope["headers"])
        try:
            length = int(headers.get(b"content-length", b"0"))
            if length < 0:
                raise ValueError
        except ValueError:
            return await JSONResponse({"detail": "Invalid Content-Length."}, 400)(
                scope, receive, send
            )
        if length > limit:
            return await JSONResponse(
                {"detail": "Request exceeds the upload limit."}, 413
            )(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > limit:
                return await JSONResponse(
                    {"detail": "Request exceeds the upload limit."}, 413
                )(scope, receive, send)
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
