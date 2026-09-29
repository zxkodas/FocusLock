"""Arregla los permisos de los archivos de FocusLock en ProgramData.

El instalador corre elevado, asi que los archivos que crea quedan con ACL de
solo lectura para el usuario normal. Consecuencia: la GUI en modo standalone
puede guardar el token (va a state.json, que ya tiene FullControl) pero NO la
configuracion, y falla con "Acceso denegado" sin explicar nada.

La solucion es que el instalador devuelva la propiedad de los archivos al
usuario que los va a editar. El servicio corre como LocalSystem, asi que
sigue teniendo acceso de lectura/escritura para el bloqueo.
"""
from __future__ import annotations

import sys

import win32api
import win32con
import win32file
import win32security

# Las constantes de acceso a archivos viven en win32file y win32con, NO en
# win32security. Los SID conocidos y las ACEs, en win32security.
FILE_ALL_ACCESS = win32file.FILE_ALL_ACCESS
FILE_GENERIC_READ = win32file.FILE_GENERIC_READ
WRITE_DAC = win32con.WRITE_DAC
OBJECT_INHERIT_ACE = win32con.OBJECT_INHERIT_ACE
CONTAINER_INHERIT_ACE = win32con.CONTAINER_INHERIT_ACE
ACL_REVISION = win32security.ACL_REVISION
DACL_SECURITY_INFORMATION = win32con.DACL_SECURITY_INFORMATION


def build_acl():
    """DACL: el usuario edita sus archivos, el servicio los lee/escribe.

    SYSTEM y Administradores conservan control total para el servicio y el
    desinstalador. Todos los demas quedan en solo lectura.
    """
    user = win32api.GetUserName()
    admins = win32security.CreateWellKnownSid(win32security.WinBuiltinAdministratorsSid)
    system = win32security.CreateWellKnownSid(win32security.WinLocalSystemSid)
    everyone = win32security.CreateWellKnownSid(win32security.WinWorldSid)
    user_sid = win32security.LookupAccountName(None, user)[0]

    flags = OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE
    dacl = win32security.ACL()

    for sid in (system, admins):
        dacl.AddAccessAllowedAceEx(ACL_REVISION, flags, FILE_ALL_ACCESS, sid)
    dacl.AddAccessAllowedAceEx(ACL_REVISION, flags, FILE_ALL_ACCESS, user_sid)
    dacl.AddAccessAllowedAceEx(ACL_REVISION, flags, FILE_GENERIC_READ, everyone)
    # Nadie cambia la ACL salvo quien ya tiene control sobre ella.
    dacl.AddAccessDeniedAceEx(ACL_REVISION, flags, WRITE_DAC, everyone)
    return dacl


def fix_paths(paths: list[str]) -> list[tuple[str, bool]]:
    """Aplica la ACL. Devuelve (ruta, exito)."""
    dacl = build_acl()
    results = []
    for path in paths:
        try:
            sd = win32security.GetFileSecurity(path, DACL_SECURITY_INFORMATION)
            # segundo argumento: 1 = DACL presente y protegido (no heredado)
            sd.SetSecurityDescriptorDacl(1, dacl, 0)
            win32security.SetFileSecurity(path, DACL_SECURITY_INFORMATION, sd)
            results.append((path, True))
        except Exception as exc:  # noqa: BLE001
            results.append((f"{path} -> {exc}", False))
    return results


if __name__ == "__main__":
    from . import paths

    targets = [str(paths.program_data())]
    for name in ("config.json", "state.json"):
        targets.append(str(paths.program_data() / name))

    print(f"Usuario: {win32api.GetUserName()}")
    print("Aplicando permisos...")
    ok = True
    for target, success in fix_paths(targets):
        print(f"  {'OK  ' if success else 'FALLA'} {target}")
        ok = ok and success
    sys.exit(0 if ok else 1)
