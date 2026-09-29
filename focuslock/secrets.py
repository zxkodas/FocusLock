"""Cifrado de secretos con DPAPI de Windows (scope local machine).

El token de TickTick y el token del servidor local nunca se guardan en texto
plano. Se cifran con CryptProtectData usando CRYPTPROTECT_LOCAL_MACHINE para
que el servicio (LocalSystem) y la GUI (usuario) puedan leerlos.
"""
from __future__ import annotations

import base64
import ctypes
import sys
from ctypes import wintypes

_PREFIX = "dpapi1:"
_PLAIN_PREFIX = "plain1:"

CRYPTPROTECT_LOCAL_MACHINE = 0x04
CRYPTPROTECT_UI_FORBIDDEN = 0x01


class _BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _to_blob(data: bytes):
    buf = ctypes.create_string_buffer(data, max(len(data), 1))
    blob = _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    return blob, buf


def _configure_protect():
    fn = ctypes.windll.crypt32.CryptProtectData
    fn.argtypes = [
        ctypes.POINTER(_BLOB),
        wintypes.LPCWSTR,
        ctypes.POINTER(_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_BLOB),
    ]
    fn.restype = wintypes.BOOL
    return fn


def _configure_unprotect():
    fn = ctypes.windll.crypt32.CryptUnprotectData
    fn.argtypes = [
        ctypes.POINTER(_BLOB),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_BLOB),
    ]
    fn.restype = wintypes.BOOL
    return fn


def protect(plain: str) -> str:
    """Cifra un string y lo devuelve como texto seguro para persistir."""
    if not sys.platform.startswith("win"):
        return _PLAIN_PREFIX + base64.b64encode(plain.encode("utf-8")).decode("ascii")
    data = plain.encode("utf-8")
    blob, buf = _to_blob(data)
    out = _BLOB()
    if not _configure_protect()(
        ctypes.byref(blob),
        "FocusLock",
        None,
        None,
        None,
        CRYPTPROTECT_LOCAL_MACHINE | CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out),
    ):
        raise ctypes.WinError()
    try:
        raw = ctypes.string_at(out.pbData, out.cbData)
        return _PREFIX + base64.b64encode(raw).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def unprotect(token: str) -> str:
    """Descifra un valor producido por protect()."""
    if token.startswith(_PLAIN_PREFIX):
        return base64.b64decode(token[len(_PLAIN_PREFIX) :]).decode("utf-8")
    if not token.startswith(_PREFIX):
        raise ValueError("Formato de secreto desconocido")
    raw = base64.b64decode(token[len(_PREFIX) :])
    blob, buf = _to_blob(raw)
    out = _BLOB()
    if not _configure_unprotect()(
        ctypes.byref(blob), None, None, None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out.pbData, out.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def wipe(token: str | None) -> str:
    """Devuelve un token vacío, ignorando errores de descifrado."""
    if not token:
        return ""
    try:
        return unprotect(token)
    except Exception:
        return ""
