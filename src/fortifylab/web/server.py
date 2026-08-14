"""HTTP serving primitives for the companion web console."""

from __future__ import annotations

from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .app import WebConsoleApp, WebConsoleConfig


TOKEN_COOKIE = "fortifylab_token"


def build_http_server(config: WebConsoleConfig, *, app: WebConsoleApp | None = None) -> ThreadingHTTPServer:
    web_app = app or WebConsoleApp(config)
    handler = make_handler(web_app)
    return ThreadingHTTPServer((config.bind_host, config.port), handler)


def serve_web_console(config: WebConsoleConfig, *, once: bool = False, static_dir: Path | None = None) -> int:
    issues = config.validate()
    if issues:
        for issue in issues:
            print(issue)
        return 1
    server = build_http_server(config, app=WebConsoleApp(config, static_dir=static_dir))
    url = f"http://{config.bind_host}:{server.server_port}"
    print(f"Fortify Lab web console listening on {url}")
    try:
        if once:
            server.timeout = 30
            server.handle_request()
        else:
            server.serve_forever()
    except KeyboardInterrupt:
        return 130
    finally:
        server.server_close()
    return 0


def make_handler(app: WebConsoleApp) -> type[BaseHTTPRequestHandler]:
    class WebConsoleRequestHandler(BaseHTTPRequestHandler):
        server_version = "FortifyLabWeb/4.1"

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlparse(self.path)
            token = extract_request_token(self)
            authenticated = app.authorize_request(token)
            set_cookie = bool(token and authenticated and parse_qs(parsed.query).get("token"))
            if not authenticated:
                if parsed.path.startswith("/api/"):
                    write_json(self, 401, app.error_envelope("unauthorized", "A valid web console token is required."))
                else:
                    write_text(self, 401, "text/plain; charset=utf-8", "A valid web console token is required.\n")
                return
            if parsed.path.startswith("/api/"):
                status, body = app.api_envelope(parsed.path)
                write_json(self, status, body, set_cookie=set_cookie, token=token)
                return
            relative = "index.html" if parsed.path in ("", "/") else unquote(parsed.path.lstrip("/"))
            try:
                content_type, body = app.static_asset(relative)
            except FileNotFoundError:
                write_text(self, 404, "text/plain; charset=utf-8", "not found\n")
                return
            write_text(self, 200, content_type, body, set_cookie=set_cookie, token=token)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return WebConsoleRequestHandler


def extract_request_token(handler: BaseHTTPRequestHandler) -> str | None:
    auth = handler.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip() or None
    header_token = handler.headers.get("X-FortifyLab-Token")
    if header_token:
        return header_token.strip()
    parsed = urlparse(handler.path)
    query_token = parse_qs(parsed.query).get("token", [None])[0]
    if query_token:
        return query_token
    cookie_header = handler.headers.get("Cookie")
    if cookie_header:
        jar = cookies.SimpleCookie(cookie_header)
        morsel = jar.get(TOKEN_COOKIE)
        if morsel:
            return morsel.value
    return None


def write_json(
    handler: BaseHTTPRequestHandler,
    status: int,
    body: dict[str, Any],
    *,
    set_cookie: bool = False,
    token: str | None = None,
) -> None:
    payload = json.dumps(body, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    _maybe_cookie(handler, set_cookie=set_cookie, token=token)
    handler.end_headers()
    handler.wfile.write(payload)


def write_text(
    handler: BaseHTTPRequestHandler,
    status: int,
    content_type: str,
    body: str,
    *,
    set_cookie: bool = False,
    token: str | None = None,
) -> None:
    payload = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(payload)))
    _maybe_cookie(handler, set_cookie=set_cookie, token=token)
    handler.end_headers()
    handler.wfile.write(payload)


def _maybe_cookie(handler: BaseHTTPRequestHandler, *, set_cookie: bool, token: str | None) -> None:
    if not set_cookie or not token:
        return
    handler.send_header("Set-Cookie", f"{TOKEN_COOKIE}={token}; HttpOnly; SameSite=Lax; Path=/")
