"""Arma el .xpi de la extensión para Firefox y Chrome.

Un .xpi no es más que un zip con el manifest en la raíz. Sirve para:
  - "Instalar complemento desde archivo…" en Firefox
  - distribución manual

OJO: Firefox exige que el .xpi esté FIRMADO. Armarlo bien no garantiza que
lo acepte: eso depende de la versión de Firefox. La función devuelve el
archivo igual y el que decide es el navegador al instalarlo.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "extension"
OUT_DIR = ROOT / "dist"

# Lo que va dentro del paquete.
CONTENTS = (
    "manifest.json",
    "sw.js",
    "options.html",
    "options.js",
    "popup.html",
    "popup.js",
)


def _read_manifest(browser: str) -> dict:
    import json

    return json.loads((EXT / browser / "manifest.json").read_text(encoding="utf-8"))


def build(browser: str = "firefox") -> Path:
    source = EXT / browser
    manifest = _read_manifest(browser)
    version = manifest.get("version", "0.0.0")
    suffix = "xpi" if browser == "firefox" else "zip"
    out = OUT_DIR / f"tickfence-{browser}-{version}.{suffix}"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    # El manifest va primero y sin comprimir: algunos lectores asumen eso.
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(source / "manifest.json", "manifest.json",
                 compress_type=zipfile.ZIP_STORED)
        for name in CONTENTS[1:]:
            path = source / name
            if not path.exists():
                raise FileNotFoundError(f"falta {path}")
            zf.write(path, name)

    return out


def verify(path: Path) -> dict:
    """Abre el .xpi y comprueba que tenga lo mínimo."""
    import json

    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        bad = zf.testzip()
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))

    return {
        "archivo": str(path),
        "bytes": path.stat().st_size,
        "contenido": names,
        "zip_integro": bad is None,
        "manifest_en_raiz": "manifest.json" in names,
        "faltan": [n for n in CONTENTS if n not in names],
        "version": manifest.get("version"),
        "id": manifest.get("browser_specific_settings", {}).get("gecko", {}).get("id")
        or manifest.get("name"),
    }


def main() -> int:
    ok = True
    for browser in ("firefox", "chrome"):
        path = build(browser)
        info = verify(path)
        print(f"--- {browser} ---")
        print(f"  archivo  : {info['archivo']}")
        print(f"  tamaño   : {info['bytes']:,} bytes")
        print(f"  version  : {info['version']}")
        print(f"  integro  : {info['zip_integro']}")
        print(f"  contenido: {', '.join(info['contenido'])}")
        if info["faltan"]:
            print(f"  FALTAN   : {info['faltan']}")
            ok = False
        print()

    print("Firefox exige .xpi firmado. Si al instalarlo dice que no está")
    print("firmado, es lo esperado: sin firma solo funciona la carga temporal.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
