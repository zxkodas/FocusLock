"""Cliente mínimo de la TickTick Open API (sin dependencias externas)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

BASE = "https://api.ticktick.com/open/v1"
USER_AGENT = "FocusLock/1.0"
DEFAULT_TIMEOUT = 20


class TickTickError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class TickTickClient:
    """Token estilo 'tp_...' usado directamente como Bearer."""

    def __init__(self, token: str, timeout: int = DEFAULT_TIMEOUT) -> None:
        self._token = (token or "").strip()
        self._timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self._token)

    def _request(self, method: str, path: str, payload: dict | None = None) -> Any:
        if not self._token:
            raise TickTickError("No hay token de TickTick configurado.")
        url = f"{BASE}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self._token}")
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", USER_AGENT)
        if data is not None:
            req.add_header("Content-Type", "application/json")

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                if not body.strip():
                    return None
                return json.loads(body)
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")[:200]
                if exc.code in (401, 403):
                    raise TickTickError(
                        "TickTick rechazó el token (401/403). Regeneralo.", exc.code
                    ) from exc
                if exc.code == 429 and attempt < 2:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise TickTickError(f"HTTP {exc.code}: {body}", exc.code) from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
        raise TickTickError(f"No se pudo contactar a TickTick: {last_error}")

    # -- endpoints ----------------------------------------------------------
    def projects(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/project") or []
        return data if isinstance(data, list) else []

    def project_data(self, project_id: str) -> dict[str, Any]:
        data = self._request("GET", f"/project/{project_id}/data") or {}
        return data if isinstance(data, dict) else {}

    def complete_task(self, project_id: str, task_id: str) -> bool:
        """Lo usa la app solo como utilidad. El flujo normal es completar en TickTick."""
        self._request("POST", f"/project/{project_id}/task/{task_id}/complete")
        return True

    # -- helpers ------------------------------------------------------------
    def find_project(self, name: str, projects: list[dict] | None = None) -> dict | None:
        from .rules import norm_key

        target = norm_key(name)
        for project in projects if projects is not None else self.projects():
            if norm_key(project.get("name", "")) == target:
                return project
        return None

    def test_connection(self) -> dict[str, Any]:
        projects = self.projects()
        return {"ok": True, "projects": len(projects), "names": [p.get("name") for p in projects]}
