"""Devuelve TickFence al estado de fábrica.

Deja todo desbloqueado y limpio, para empezar de cero: sin créditos, sin
lectura base, sin ciclo de bloqueo activo y sin claves IFEO. Se puede correr
con el servicio detenido; el comando de reconciliación afterward se encarga de
las claves del registro.

    python -m focuslock reset

Si el servicio está corriendo, lo reinicia para que tome el estado limpio.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from .config import DEFAULTS, Config
from .store import DEFAULT_STATE, Store


def reset(config_path: Path | None = None, state_path: Path | None = None) -> dict:
    from . import paths

    cfg_path = config_path or (paths.program_data() / "config.json")
    st_path = state_path or (paths.program_data() / "state.json")

    # --- config: lista de bloqueados vacía, arranque sin bloquear ---
    cfg = Config(cfg_path)
    cfg.load()
    backup_cfg = cfg_path.with_suffix(".json.bak")
    if cfg_path.exists():
        backup_cfg.write_text(
            cfg_path.read_text(encoding="utf-8"), encoding="utf-8"
        )

    cfg.set("programs", {"blocked": [], "allowed": list(DEFAULTS["programs"]["allowed"]),
                         "use_ifeo": DEFAULTS["programs"]["use_ifeo"]})
    cfg.set("general", {"start_locked": False})
    cfg.save()

    # --- estado: desbloqueado, contador en cero, línea base limpia ---
    st = Store(st_path)
    st.read()
    backup_st = st_path.with_suffix(".json.bak")
    if st_path.exists():
        backup_st.write_text(st_path.read_text(encoding="utf-8"), encoding="utf-8")

    st.update(
        locked=False,
        credits=0,
        required=2,
        lock_started=0.0,
        unlock_until=0.0,
        unlock_reason="",
        lectura_status={},
        lectura_seeded=False,
        last_poll=0.0,
        last_error="",
        # historial limpio: el registro de emergency no se borra al reset
        server_port=st.get("server_port", 0),
        ticktick_token=st.get("ticktick_token", ""),
        server_token=st.get("server_token", ""),
        emergencies=[],
        block_events=[],
    )
    st.write()

    return {
        "config": str(cfg_path),
        "config_backup": str(backup_cfg),
        "state": str(st_path),
        "state_backup": str(backup_st),
        "blocked": [],
        "locked": False,
        "credits": 0,
    }


def main() -> int:
    from . import ifeo
    from .paths import program_data

    cfg_path = program_data() / "config.json"

    # Limpiar el registro ANTES de reiniciar el servicio: si el servicio está
    # corriendo, vuelve a aplicar IFEO y reintroduce las claves.
    try:
        before = ifeo.list_blocked()
    except Exception:
        before = []
    for exe in before:
        ifeo.clear(exe)
    if before:
        print(f"  liberadas {len(before)} claves IFEO: {', '.join(before)}")

    result = reset()

    # Reiniciar el servicio para que tome el estado limpio.
    try:
        from . import service

        if service._is_installed():
            service.stop()
            service.start()
            print("  servicio reiniciado")
        else:
            print("  el servicio no está instalado")
    except Exception as exc:  # noqa: BLE001
        print(f"  no se pudo reiniciar el servicio: {exc}")

    print()
    print(f"  config    : {result['config']}  (respaldo: {result['config_backup']})")
    print(f"  estado    : {result['state']}  (respaldo: {result['state_backup']})")
    print("  bloqueados: (ninguno)")
    print("  bloqueado : False | créditos: 0")
    print()
    print("Listo. Abrí TickFence y usá 'Activar bloqueo' cuando quieras probar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
