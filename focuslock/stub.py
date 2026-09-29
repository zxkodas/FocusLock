"""Stub de IFEO. Deliberadamente autonomo: lo ejecuta Windows fuera del paquete
y tiene que arrancar aunque focuslock no sea importable.

Cuando Windows encuentra un .exe bloqueado, lanza este stub con la linea de
comandos original pegada atras. Mostramos el aviso y salimos: el programa
nunca arranca.

El stub lee el estado solo para saber cuantas Lecturas faltan. Si no puede
leerlo, muestra un texto generico en vez de fallar.
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
from pathlib import Path

MB_OK = 0x00000000
MB_ICONWARNING = 0x00000030
MB_TOPMOST = 0x00040000

TITLE = "TickFence · bloqueo activo"

HEADER = "Este programa está bloqueado por TickFence."


def _target(argv: list[str]) -> str:
    for arg in reversed(argv):
        if arg.startswith("--") or not arg:
            continue
        return os.path.basename(arg)
    return ""


def _state() -> dict:
    """Lee state.json solo para required/credits. Nunca toca el token.

    El estado vive en ProgramData. La UI no siempre esta abierta, asi que
    leerlo desde el stub es la unica forma de que el aviso diga algo util.
    """
    base = os.environ.get("ProgramData") or r"C:\ProgramData"
    path = Path(base) / "TickFence" / "state.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def build_message(name: str) -> str:
    data = _state()
    required = data.get("required")
    credits = data.get("credits")

    try:
        required = int(required)
    except (TypeError, ValueError):
        required = 0
    try:
        credits = int(credits)
    except (TypeError, ValueError):
        credits = 0

    lines = [HEADER, ""]

    if required > 0:
        faltan = max(0, required - credits)
        if faltan:
            lines.append(
                f"Te falta{'n' if faltan == 1 else 'n'} {faltan} Lectura"
                f"{'s' if faltan != 1 else ''} en TickTick y se desbloquea solo."
            )
        else:
            lines.append(
                "Ya completaste las Lecturas. Abrí TickFence para que tome "
                "el cambio (tarda hasta medio minuto)."
            )
    else:
        lines.append("Terminá las Lecturas pendientes en TickTick para desbloquear.")

    lines.append("")
    if name:
        lines.append(f"Programa bloqueado: {name}")
        lines.append("")

    lines.append(
        "Para desbloquear sin completar las Lecturas: abrí TickFence desde el "
        "acceso directo del Escritorio, o con:\n"
        "    python -m focuslock gui\n"
        "y escribí tu compromiso (300 palabras, 5 minutos de escritura real)."
    )
    return "\n".join(lines)


def main() -> int:
    argv = sys.argv[1:]
    if "--ifeo-stub" not in argv:
        return 0
    name = _target([a for a in argv if a != "--ifeo-stub"])
    try:
        ctypes.windll.user32.MessageBoxW(
            None, build_message(name), TITLE, MB_OK | MB_ICONWARNING | MB_TOPMOST
        )
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
