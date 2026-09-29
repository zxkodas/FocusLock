"""Configuración compartida (sin secretos) + acceso atómico y thread-safe."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from . import paths

_LOCK = threading.RLock()

DEFAULTS: dict[str, Any] = {
    "version": 1,
    "ticktick": {
        # Solo se usa si el proyecto se renombra o se borra. Con project_name
        # vacío la app resuelve el ID por nombre en cada consulta.
        "project_id": "",
        "project_name": "Estudios",
        # Ya NO se filtra por el nombre de la tarea: cuenta cualquier tarea
        # del proyecto. Se conserva la clave por compatibilidad.
        "task_prefix": "",
        # Cuántas hay que completar para desbloquear.
        "required": 2,
        "poll_seconds": 45,
    },
    "programs": {
        # VACIA a proposito. El bloqueo es opt-in: se activa apretando un
        # boton en la app, no por abrirla. Si por defecto VINIERA bloqueado,
        # un dia sin ganas de leer lecturas te dejaria encerrado sin haberlo
        # pedido. Para bloquear algo, agregalo desde la pestana Programas.
        "blocked": [],
        # NUNCA se bloquean, esten donde esten. Si pones una app_acá, FocusLock
        # no la va a tocar. Nota: explorer.exe NO va acá a proposito: es el shell
        # de Windows y esta protegido a nivel de codigo (rules.NEVER_BLOCK),
        # que es una proteccion que vos no podes desactivar desde la config.
        "allowed": [
            "notepad.exe",
            "Code.exe",
            "pycharm64.exe",
            "devenv.exe",
            "opencode.exe",
            "focuslock.exe",
        ],
        "use_ifeo": True,
    },
    "sites": {
        "blocked": [
            "youtube.com",
            "reddit.com",
            "instagram.com",
            "x.com",
            "twitter.com",
            "twitch.tv",
            "netflix.com",
            "tiktok.com",
        ],
        "allowed": [
            "docs.python.org",
            "stackoverflow.com",
            "upt.edu.ar",
        ],
    },
    "emergency": {
        "min_words": 300,
        "min_minutes": 5,
        "unlock_minutes": 20,
        "history_limit": 50,
    },
    "general": {
        # False = arrancar FocusLock NO activa el bloqueo. El usuario tiene que
        # apretar "Activar bloqueo". Esto es lo que evita quedar encerrado sin
        # haberlo pedido.
        "start_locked": False,
        "show_block_notice": True,
    },
}


def config_path() -> Path:
    return paths.program_data() / "config.json"


def _deep_merge(base: dict, incoming: dict) -> dict:
    out = dict(base)
    for key, value in (incoming or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class Config:
    """Envoltura con load/save atómico. Seguro entre hilos.

    `reload_if_changed()` vuelve a leer el archivo si su fecha cambió en disco.
    El servicio la llama antes de sincronizar el IFEO: si alguien edita
    config.json a mano (o la GUI lo hace mientras el servicio corre), el
    bloqueo tiene que reflejar ese cambio. Sin esto, el servicio queda con la
    config que leyo al arrancar y las claves de registro no se ajustan nunca.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or config_path()
        self._data: dict[str, Any] = {}
        self._stamp: tuple[float, int] = (0.0, -1)

    @property
    def path(self) -> Path:
        return self._path

    def _disk_stamp(self) -> tuple[float, int]:
        """Huella del archivo: (mtime, tamaño).

        Se compara como tupla y no como float: sumar el tamaño al mtime en
        coma flotante hace que dos escrituras distintas den el mismo valor
        cuando el archivo es chico y el mtime tiene poca resolución.
        """
        try:
            stat = self._path.stat()
        except OSError:
            return (0.0, -1)
        return (stat.st_mtime, stat.st_size)

    def reload_if_changed(self) -> bool:
        """Relee el archivo si cambio en disco. True si hubo recarga."""
        with _LOCK:
            if not self._data:
                self.load()
                return True
            stamp = self._disk_stamp()
            if stamp == self._stamp:
                return False
            self.load()
            return True

    def load(self) -> dict[str, Any]:
        with _LOCK:
            raw: dict[str, Any] = {}
            if self._path.exists():
                try:
                    raw = json.loads(self._path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    raw = {}
            self._data = _deep_merge(DEFAULTS, raw)
            self._stamp = self._disk_stamp()
            return self._data

    def save(self, data: dict[str, Any] | None = None) -> None:
        with _LOCK:
            if data is not None:
                self._data = _deep_merge(DEFAULTS, data)
            payload = json.dumps(self._data, indent=2, ensure_ascii=False)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            handle, tmp = tempfile.mkstemp(
                dir=str(self._path.parent), prefix=".config-", suffix=".tmp"
            )
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as fh:
                    fh.write(payload)
                os.replace(tmp, self._path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            # El sello se actualiza aca: si no, un save propio podria
            # disparar una recarga unnecessary.
            self._stamp = self._disk_stamp()

    # -- acceso por sección -------------------------------------------------
    def get(self, section: str) -> dict[str, Any]:
        with _LOCK:
            if not self._data:
                self.load()
            return self._data.get(section, {})

    def set(self, section: str, values: dict[str, Any]) -> None:
        with _LOCK:
            if not self._data:
                self.load()
            self._data[section] = _deep_merge(self._data.get(section, {}), values)

    def all(self) -> dict[str, Any]:
        with _LOCK:
            if not self._data:
                self.load()
            return self._data


_instance: Config | None = None


def instance() -> Config:
    global _instance
    if _instance is None:
        _instance = Config()
        _instance.load()
    return _instance
