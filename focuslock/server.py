"""Servidor HTTP local que consultan las extensiones del navegador.

Bind a 127.0.0.1 con puerto efímero + token aleatorio + validación de Origin.
Las extensiones preguntan '¿estoy bloqueado?' y qué dominios bloquear.
"""
from __future__ import annotations

import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

ALLOWED_ORIGIN_PREFIXES = (
    "chrome-extension://",
    "moz-extension://",
    "safari-web-extension://",
)

# Firefox manda `Origin: null` en algunas peticiones de extensionesMV3
# (típicamente desde el popup). Rechazarla daba 403 y el popup mostraba
# "sin conexión" aunque el servicio estuviera perfecto.
#
# El token sigue siendo la vraie protección: es un secreto de 32 bytes que
# solo está en el servicio y en la extensión del usuario. El Origin es una
# capa extra, no la barrierа.
ALLOWED_ORIGINS = frozenset({"null", ""})


def new_token() -> str:
    return secrets.token_urlsafe(32)


class _Handler(BaseHTTPRequestHandler):
    server_version = "TickFence"
    sys_version = ""

    def log_message(self, fmt: str, *args: Any) -> None:  # silencia el log a stderr
        return

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin or origin in ALLOWED_ORIGINS:
            return True
        return origin.startswith(ALLOWED_ORIGIN_PREFIXES)

    def _send(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send({"ok": True})

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        token = (query.get("token") or [self.headers.get("X-TickFence-Token", "")])[0]

        if parsed.path == "/health":
            self._send({"ok": True, "service": "TickFence"})
            return

        if not self._origin_ok():
            self._send({"error": "origin no permitido"}, 403)
            return
        if not token or token != self.server.expected_token:  # type: ignore[attr-defined]
            self._send({"error": "token invalido"}, 403)
            return
        if parsed.path != "/state":
            self._send({"error": "ruta desconocida"}, 404)
            return
        self._send(self.server.provider())  # type: ignore[attr-defined]


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


class StateServer:
    """Expone el estado de bloqueo en http://127.0.0.1:<puerto>/state

    El puerto es FIJO a propósito. Las extensiones guardan la dirección con el
    puerto adentro, y si el servicio eligiera uno efímero, cada reinicio
    invalidaría la dirección pegada por el usuario y la extensión dejaría de
    bloquear en silencio.
    """

    def __init__(
        self,
        provider: Callable[[], dict[str, Any]],
        token: str | None = None,
        port: int = 47821,
    ) -> None:
        self._provider = provider
        self.token = token or new_token()
        self.port = 0
        self._requested_port = port
        self._httpd: _Server | None = None
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def start(self) -> int:
        httpd = _Server(("127.0.0.1", self._requested_port), _Handler)
        httpd.expected_token = self.token  # type: ignore[attr-defined]
        httpd.provider = self._provider  # type: ignore[attr-defined]
        self.port = httpd.server_address[1]
        self._httpd = httpd
        self._thread = threading.Thread(target=httpd.serve_forever, name="state-http", daemon=True)
        self._thread.start()
        return self.port

    def stop(self) -> None:
        if self._httpd:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None
