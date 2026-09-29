"""Acceso a TickFence desde el menú Inicio y el Escritorio.

Solo accesos directos. NO hay autoinicio: si TickFence se abriera solo con
Windows, seamlanzaría en cada inicio de sesión solo para vivir en el área de
notificación. Abrir la app es una decisión del usuario.
"""
from __future__ import annotations

import sys
from pathlib import Path

START_MENU = Path(__import__("os").environ.get("APPDATA", "")) / (
    "Microsoft/Windows/Start Menu/Programs"
)
DESKTOP = Path(__import__("os").environ.get("USERPROFILE", "")) / "Desktop"


def _icon_path() -> Path:
    """Donde vive el .ico de la app.

    Se busca en AppData y en la carpeta del proyecto, para que funcione tanto
    instalado como corriendo desde el codigo.
    """
    import os

    candidatos = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "TickFence" / "tickfence.ico",
        Path(__file__).resolve().parents[1] / "dist" / "tickfence.ico",
    ]
    for c in candidatos:
        if c.exists():
            return c
    return candidatos[0]


def _launcher() -> tuple[str, str]:
    """(ejecutable, argumentos) para abrir la GUI.

    Si estamos empaquetados, el .exe. Si no, el interprete con -m.
    """
    if getattr(sys, "frozen", False):
        return sys.executable, ""
    return sys.executable, "-m focuslock gui"


# Nombres de acceso de versiones anteriores. Tras un rebrandeo quedan los
# viejos en el Escritorio y en el Menú Inicio, y Windows los sigue
# mostrando: se ven dos íconos y la búsqueda devuelve el nombre viejo.
NOMBRES_ANTIGUOS = ("FocusLock.lnk",)


def _link_paths() -> list[Path]:
    return [START_MENU / "TickFence.lnk", DESKTOP / "TickFence.lnk"]


def _stale_link_paths() -> list[Path]:
    """Accesos de nombres anteriores, que hay que borrar al desinstalar."""
    actuales = {p.name.lower() for p in _link_paths()}
    return [
        carpeta / nombre
        for carpeta in (START_MENU, DESKTOP)
        for nombre in NOMBRES_ANTIGUOS
        if nombre.lower() not in actuales
    ]


def create_shortcuts() -> list[Path]:
    """Crea el acceso directo del menú Inicio y del Escritorio."""
    import pythoncom
    from win32com.shell import shell

    created: list[Path] = []
    target, args = _launcher()

    for link_path in _link_paths():
        link_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            link = pythoncom.CoCreateInstance(
                shell.CLSID_ShellLink,
                None,
                pythoncom.CLSCTX_INPROC_SERVER,
                shell.IID_IShellLink,
            )
            link.SetPath(target)
            link.SetArguments(args)
            link.SetDescription("TickFence - bloqueador de foco")
            link.SetWorkingDirectory(str(Path.home()))
            # Sin icono propio, Windows muestra el de python.exe: en el Menu
            # Inicio y en la busqueda se ve algo que no es la app.
            icono = _icon_path()
            if icono.exists():
                link.SetIconLocation(str(icono), 0)
            link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(link_path), 0)
            created.append(link_path)
        except Exception:
            continue
    return created


def remove_shortcuts() -> list[str]:
    removed: list[str] = []
    for link_path in _link_paths() + _stale_link_paths():
        if link_path.exists():
            try:
                link_path.unlink()
                removed.append(str(link_path))
            except OSError:
                pass
    return removed


def status() -> dict:
    return {
        "launcher": " ".join(_launcher()),
        "links": {str(p): p.exists() for p in _link_paths()},
        "autostart": False,
    }


def install() -> dict:
    created = create_shortcuts()
    return {"shortcuts": [str(p) for p in created], "autostart": False}


def uninstall() -> dict:
    return {"removed": remove_shortcuts(), "autostart": False}


if __name__ == "__main__":
    import json

    print(json.dumps(install(), indent=2))
