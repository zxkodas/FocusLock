"""Rutas y constantes globales compartidas entre el servicio y la GUI."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "TickFence"
APP_VERSION = "1.0.0"

SERVICE_NAME = "TickFenceSvc"
SERVICE_DISPLAY_NAME = "TickFence Enforcement Service"
PIPE_NAME = r"\\.\pipe\TickFence"

IFEO_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options"

# Extensiones de navegador que sirve la app para instalar.
EXTENSION_IDS = {
    "chrome": "tickfence-blocker",
    "firefox": "tickfence-blocker",
}


def program_data() -> Path:
    base = os.environ.get("ProgramData") or r"C:\ProgramData"
    return Path(base) / APP_NAME


def app_data() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / APP_NAME


def is_windows() -> bool:
    return sys.platform.startswith("win")


def is_elevated() -> bool:
    """True si el proceso actual corre como Administrador."""
    if not is_windows():
        return True
    import ctypes

    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False
