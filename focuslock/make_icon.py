"""Genera el icono de TickFence (.ico) a partir del dibujo del tray.

Sin esto el acceso directo de Windows muestra el icono de Python, que en el
Menu Inicio y en la busqueda se ve como algo que no es la app.

make_icon() usa QPixmap, asi que hace falta una QApplication viva: sin ella Qt
aborta el proceso con un stack overflow.
"""
import os
import sys
import traceback
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parents[1] if __file__ else Path.cwd()
sys.path.insert(0, str(RAIZ))

from PySide6.QtWidgets import QApplication

aplicacion = QApplication.instance() or QApplication(sys.argv)

from focuslock.ui.app import make_icon  # noqa: E402

DESTINO = Path(
    sys.argv[1] if len(sys.argv) > 1
    else Path(os.environ["LOCALAPPDATA"]) / "Programs" / "TickFence" / "tickfence.ico"
)


def main() -> int:
    try:
        DESTINO.parent.mkdir(parents=True, exist_ok=True)
        # La version con candado: representa la app abierta.
        imagen = make_icon(unlocked=True).pixmap(256, 256).toImage()
        if not imagen.save(str(DESTINO), "ICO"):
            print("  Qt no pudo escribir el .ico", file=sys.stderr)
            return 1
        print(f"  icono: {DESTINO} ({DESTINO.stat().st_size} bytes, {imagen.width()}px)")
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
