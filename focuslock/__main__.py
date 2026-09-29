"""Punto de entrada de la línea de comandos.

    python -m focuslock gui         abre la ventana (no necesita admin)
    python -m focuslock install     instala el servicio (necesita admin, 1 vez)
    python -m focuslock console     motor en primer plano, para depurar
    python -m focuslock status      consulta el estado al servicio
    python -m focuslock uninstall   desinstala todo
"""
from __future__ import annotations

import argparse
import os
import sys
import time

from .paths import is_elevated, is_windows
from .rules import norm_program


def _need_admin(action: str) -> None:
    if not is_windows():
        print("TickFence solo funciona en Windows.")
        sys.exit(2)
    if not is_elevated():
        print(f"'{action}' necesita permisos de administrador.", file=sys.stderr)
        print("Cerrá esto y volvé a abrirlo como administrador.", file=sys.stderr)
        sys.exit(3)


def _wait_for_service(seconds: float = 25.0) -> bool:
    from .ipc import IpcClient

    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            IpcClient(timeout=5).call("status")
            return True
        except Exception:
            time.sleep(1.0)
    return False


def cmd_install(args) -> int:
    _need_admin("install")
    from . import config as config_mod
    from . import ifeo
    from . import paths
    from .paths import APP_VERSION
    from .service import install as install_service

    print(f"TickFence {APP_VERSION} — instalación")
    print(f"  datos en: {paths.program_data()}")

    paths.program_data().mkdir(parents=True, exist_ok=True)
    cfg = config_mod.instance()
    cfg.save()
    print(f"  config   : {cfg.path}")

    if getattr(sys, "frozen", False):
        print("  modo     : ejecutable empaquetado")
    else:
        print(f"  modo     : código fuente ({sys.executable})")

    print("  instalando el paquete para el servicio…")
    from .install_pkg import install as install_pkg

    if install_pkg() != 0:
        print("  ERROR: el servicio no podría encontrar el paquete.", file=sys.stderr)
        return 1

    print("  registrando el servicio…")
    install_service()
    print("  arrancando servicio…")

    if not _wait_for_service():
        print("  ERROR: el servicio no respondió.", file=sys.stderr)
        print("  Revisá el visor de eventos o probá: python -m focuslock console",
              file=sys.stderr)
        return 1
    print("  servicio listo.")

    from .ipc import IpcClient

    client = IpcClient()
    if args.token:
        try:
            res = client.call("ticktick_set_token", token=args.token)
            if res.get("ok"):
                print(f"  token    : guardado y cifrado ({res.get('projects')} proyectos)")
            else:
                print(f"  token    : ERROR {res.get('error')}", file=sys.stderr)
        except Exception as exc:
            print(f"  token    : ERROR {exc}", file=sys.stderr)

    from .daemon import stub_command
    print(f"  IFEO stub: {stub_command()}")
    blocked = ifeo.list_blocked()
    print(f"  IFEO     : {len(blocked)} ejecutables bloqueados a nivel Windows")
    if not blocked:
        print("  (ninguno: con la maquina desbloqueada el IFEO esta limpio)")

    # Acceso desde Inicio/Escritorio e autoinicio: sin esto el ícono del área
    # de notificación no existe después de reiniciar y no hay forma de abrir
    # la app para desbloquear.
    print("  creando accesos directos…")
    try:
        from .shortcuts import install as install_shortcuts

        result = install_shortcuts()
        for path in result.get("shortcuts", []):
            print(f"    acceso: {path}")
    except Exception as exc:  # noqa: BLE001
        print(f"  AVISO: no se pudieron crear los accesos directos: {exc}")
        print("  La app se abre igual con: python -m focuslock gui")
    return 0


def cmd_uninstall(args) -> int:
    _need_admin("uninstall")
    from . import ifeo
    from .service import uninstall as uninstall_service

    print("Quitando bloqueos IFEO…")
    for exe in ifeo.list_blocked():
        ifeo.clear(exe)
        print(f"  liberado: {exe}")
    print("Deteniendo y eliminando el servicio…")
    uninstall_service()
    print("Listo. Podés borrar C:\\ProgramData\\TickFence si querés.")
    return 0


def cmd_console(args) -> int:
    """Motor en primer plano, para depurar.

    Por seguridad el vigilante de procesos NO se levanta en este modo salvo que
    se pida explicitamente con --armar-guard. Levantar un killer de procesos
    contra la sesion interactiva del usuario desde una consola de desarrollo es
    exactamente como se te cae el escritorio.
    """
    if not is_windows():
        print("TickFence solo funciona en Windows.")
        return 2

    from .service import run_console

    if not is_elevated():
        print("AVISO: sin permisos de administrador.")
        print("       Las claves IFEO no se pueden escribir y el bloqueo duro")
        print("       quedara desactivado. Usa 'install' desde una consola elevada.")
        print("")

    if not getattr(args, "armar_guard", False):
        print("MODO SEGURO: el vigilante de procesos esta DESACTIVADO.")
        print("  Estaria matando programas de tu sesion de escritorio.")
        print("  Para probarlo a proposito:")
        print("     python -m focuslock console --armar-guard")
        print("")
    return run_console(arm_guard=bool(getattr(args, "armar_guard", False)))


def cmd_gui(args) -> int:
    from .ui import main

    return main()


def cmd_doctor(args) -> int:
    """Diagnostico: responde el servicio, hay IFEO, estaticktock conectado."""
    from .ipc import IpcClient

    client = IpcClient()
    try:
        info = client.call("install_ready")
    except Exception as exc:  # noqa: BLE001
        print(f"El servicio NO responde: {exc}")
        return 1

    print("Servicio respondsiendo.")
    print(f"  pid           {info.get('service_pid')}")
    print(f"  python        {info.get('python')}")
    print(f"  config        {info.get('config_path')}")
    print(f"  estado        {info.get('state_path')}")
    print(f"  servidor HTTP puerto {info.get('port')}")
    print(f"  IFEO aplicado {len(info.get('ifeo_applied') or [])} ejecutables")
    print(f"  guardia       {info.get('guard')}")
    print(f"  stub IFEO     {info.get('stub')}")
    print(f"  ticktick      {'configurado' if info.get('ticktick_ok') else 'SIN TOKEN'}")
    try:
        st = client.call("status")
    except Exception as exc:  # noqa: BLE001
        print(f"  status falló: {exc}")
        return 1
    print(f"  estado actual {'BLOQUEADO' if st.get('locked') else 'DESBLOQUEADO'} "
          f"{st.get('credits')}/{st.get('required')}")
    if st.get("error"):
        print(f"  error: {st['error']}")
    return 0


def cmd_ifeo_reconcile(args) -> int:
    """Reconcilia las claves IFEO con la config. Funciona con el servicio parado.

    Es el escape de emergencia: si el servicio dejo claves de programas que ya
    no queres bloquear y no podés abrir la app, esto las limpia.
    """
    from . import ifeo
    from .config import Config
    from .paths import program_data

    cfg = Config(program_data() / "config.json")
    cfg.load()
    blocked = [norm_program(v) for v in cfg.get("programs").get("blocked", [])]
    allowed = [norm_program(v) for v in cfg.get("programs").get("allowed", [])]

    before = ifeo.list_blocked()
    print(f"  configurado : {', '.join(blocked) or '(nada)'}")
    print(f"  IFEO actual : {', '.join(before) or '(nada)'}")

    # sync con stub vacio: solo importa que quite lo que sobra.
    from .daemon import stub_command

    result = ifeo.sync(blocked, allowed, stub_command())
    after = ifeo.list_blocked()
    print(f"  aplicado    : {', '.join(result.get('applied', [])) or '-'}")
    print(f"  liberados   : {', '.join(result.get('removed', [])) or '-'}")
    if result.get("failed"):
        print(f"  fallaron    : {'; '.join(result['failed'])}")
    print(f"  IFEO final  : {', '.join(after) or '(nada)'}")
    return 0


def _safe(text: object) -> str:
    """Convierte a texto que la consola de Windows pueda imprimir.

    Los proyectos de TickTick traen emoji (📖Estudios) y cp1252 no los
    encodea: sin esto, `status` revienta con UnicodeEncodeError apenas el
    servicio responde.
    """
    value = str(text)
    encoding = getattr(sys.stdout, "encoding", None) or "cp1252"
    return value.encode(encoding, errors="replace").decode(encoding, errors="replace")


def cmd_status(args) -> int:
    from .ipc import IpcClient

    try:
        data = IpcClient().call("status")
    except Exception as exc:  # noqa: BLE001
        print(f"Sin servicio: {_safe(exc)}")
        return 1
    estado = "BLOQUEADO" if data.get("locked") else "DESBLOQUEADO"
    print(f"{estado}  ·  {data.get('credits')}/{data.get('required')} Lecturas")
    print(f"  razón      : {_safe(data.get('reason') or '-')}")
    print(f"  pendientes : {sum((data.get('modules') or {}).values())}")
    print(f"  IFEO       : {len(data.get('ifeo', []))} ejecutables")
    print(f"  servidor   : http://127.0.0.1:{data.get('port')}/state")
    if data.get("error"):
        print(f"  error      : {_safe(data['error'])}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="focuslock", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command")

    p_install = sub.add_parser("install", help="instala el servicio (admin)")
    p_install.add_argument("--token", help="token de TickTick (tp_...) para configurarlo de una")
    p_install.set_defaults(func=cmd_install)

    p_uninstall = sub.add_parser("uninstall", help="desinstala (admin)")
    p_uninstall.set_defaults(func=cmd_uninstall)

    p_console = sub.add_parser(
        "console",
        help="motor en primer plano (vigilante apagado salvo --armar-guard)",
    )
    p_console.add_argument(
        "--armar-guard",
        action="store_true",
        help="activa el vigilante de procesos. MATA PROGRAMAS de tu sesion.",
    )
    p_console.set_defaults(func=cmd_console)

    p_gui = sub.add_parser("gui", help="abre la ventana")
    p_gui.set_defaults(func=cmd_gui)

    p_status = sub.add_parser("status", help="estado actual")
    p_status.set_defaults(func=cmd_status)

    p_doctor = sub.add_parser("doctor", help="diagnostico completo del servicio")
    p_doctor.set_defaults(func=cmd_doctor)

    p_reconcile = sub.add_parser(
        "ifeo-reconcile",
        help="limpia claves IFEO huerfanas (funciona con el servicio parado)",
    )
    p_reconcile.set_defaults(func=cmd_ifeo_reconcile)

    p_reset = sub.add_parser(
        "reset",
        help="vuelve todo al estado de fabrica (desbloqueado, contadores en 0)",
    )
    p_reset.set_defaults(func=lambda a: __import__("focuslock.reset", fromlist=["main"]).main())

    if "--ifeo-stub" in (argv if argv is not None else sys.argv):
        from .stub import main as stub_main

        return stub_main()

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        args = parser.parse_args(["gui"] if argv is None else argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
