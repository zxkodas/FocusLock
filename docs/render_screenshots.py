"""Genera los screenshots del README a partir de la app real.

Por que esto existe: los PNG del README eran placeholders que decian
"replace this file", y despues se reemplazaron a mano con renders que
mostraban valores que no eran los reales (1 Lectura, puerto 14123).
Un screenshot que miente es peor que ningun screenshot.

Este script construye la ventana de verdad, la recorre y la graba. Ahi no
hay nada dibujado a mano: si la interfaz cambia, los PNG quedan viejos y el
script se vuelve a correr.

    python docs/render_screenshots.py

Usa los DEFAULTS del producto (2 Lecturas, 45 s, 300 palabras) y el puerto
real, para que el README no muestre numeros que el usuario no tiene.

Un cliente falso, no el servicio real, por dos razones: el render tiene que
ser reproducible sin el servicio corriendo, y sobre todo no debe filtrar el
token ni los nombres de las tareas de nadie.

NO se usa QT_QPA_PLATFORM=offscreen: en Windows ese plugin no tiene base de
fuentes y todos los textos salen como cuadritos. Se renderiza con la
plataforma real, asi que aparece una ventana un instante en el escritorio.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "docs" / "screenshots"

# (fila del menu lateral, nombre del archivo, texto alternativo)
#
# El primero se llama "estado" y no "estado-bloqueado": el render muestra el
# bloqueo apagado, que es el estado en que abre la app. El nombre viejo
# venia del placeholder y describia algo que la imagen no muestra.
PAGINAS = [
    (0, "01-estado.png", "Main window"),
    (1, "02-programas.png", "Programs tab"),
    (2, "03-sitios.png", "Sites tab"),
    (3, "04-ajustes.png", "Settings tab"),
    (4, "06-bitacora.png", "Log tab"),
]

PUERTO = 47821


def _epoch(anio: int, mes: int, dia: int, hora: int = 0, minuto: int = 0) -> int:
    """Fecha fija en epoch, para que el render sea reproducible.

    Con time.time() el screenshot cambiaria cada vez que se corre y no se
    podria comparar un render con otro para ver que cambio.
    """
    import datetime

    return int(
        datetime.datetime(anio, mes, dia, hora, minuto, tzinfo=datetime.timezone.utc).timestamp()
    )


class ClienteDemo:
    """Responde lo que la ventana consulta, con datos de ejemplo.

    Los defaults son los que documenta el README. Si se cambia un default en
    config.py hay que cambiarlo aca tambien, o el screenshot va a mentir.
    """

    def __init__(self) -> None:
        self.disponible = True
        self.bloqueado = False
        self.config = {
            "version": 1,
            "ticktick": {
                "project_id": "demo",
                "project_name": "Estudios",
                "task_prefix": "",
                "required": 2,
                "poll_seconds": 45,
            },
            "programs": {
                "blocked": ["steam.exe", "discord.exe", "twitch.exe"],
                "allowed": ["notepad.exe", "code.exe"],
                "use_ifeo": True,
            },
            "sites": {
                "blocked": ["youtube.com", "reddit.com", "x.com"],
                "allowed": ["docs.python.org"],
            },
            "emergency": {
                "min_words": 300,
                "min_minutes": 5,
                "unlock_minutes": 20,
                "history_limit": 50,
            },
            "general": {"start_locked": False, "show_block_notice": True},
        }

    def call(self, command: str, **payload):
        if command == "status":
            return {
                "locked": self.bloqueado,
                "enforcement": True,
                "checked_at": time.time(),
                "credits": 1 if self.bloqueado else 0,
                "required": 2,
                "remaining": 1 if self.bloqueado else 2,
                "reason": "",
                "modules": {"Analisis Matematico": 19, "Produccion": 16},
                "pending": [
                    {"id": "a", "title": "Ejercicio 3", "module": "Analisis Matematico"},
                    {"id": "b", "title": "Tp 2", "module": "Produccion"},
                ],
                "error": "",
                "ticktick_ok": True,
                "port": PUERTO,
                "token": "tok_0000000000000000000000000000000",
                "ifeo": ["steam.exe", "discord.exe"],
                "guard": {"scans": 0, "kills": 0, "running": True},
                "guard_armed": True,
                "state": {},
            }
        if command == "config_get":
            return {"config": self.config}
        if command == "history":
            return {
                "emergencies": [
                    {
                        "at": _epoch(2026, 9, 28, 21, 40),
                        "words": 342,
                        "seconds": 371,
                        "commitment": (
                            "Terminar los ejercicios de analisis y no volver a "
                            "YouTube hasta despues de cenar."
                        ),
                    },
                    {
                        "at": _epoch(2026, 9, 27, 18, 5),
                        "words": 305,
                        "seconds": 318,
                        "commitment": "Sacar la production del viernes y dormir.",
                    },
                ],
                "blocks": [
                    {
                        "at": _epoch(2026, 9, 29, 15, 12),
                        "process": "steam.exe",
                        "pid": 8124,
                        "method": "watchdog",
                    },
                    {
                        "at": _epoch(2026, 9, 28, 22, 3),
                        "process": "discord.exe",
                        "pid": 4471,
                        "method": "watchdog",
                    },
                    {
                        "at": _epoch(2026, 9, 28, 14, 51),
                        "process": "twitch.exe",
                        "pid": 9930,
                        "method": "ifeo",
                    },
                ],
            }
        return {"ok": True}


def main() -> int:
    sys.path.insert(0, str(RAIZ))
    from PySide6.QtWidgets import QApplication

    from focuslock.ui import app as ui

    qt = QApplication.instance() or QApplication([])

    # El tema lo aplica TrayApp, no MainWindow. Sin esto la ventana sale con
    # el estilo por defecto de Qt: fondo claro, sin colores, y el README
    # muestra algo que el usuario nunca ve.
    qt.setStyleSheet(ui.STYLE)

    ventana = ui.MainWindow(ClienteDemo())
    ventana.resize(1200, 1000)
    ventana.show()

    # El timer de sondeo quedaria pintando mientras se graba. Se detiene, pero
    # OJO: refresh() es lo que llena los campos, asi que hay que llamarlo a
    # mano. Sin esto los campos salen vacios y el screenshot miente.
    if hasattr(ventana, "_timer"):
        ventana._timer.stop()
    ventana.refresh()
    # _fill_rules() es lo que carga la pagina Ajustes; refresh() no la toca.
    # Con nombre privado y todo: es el unico metodo que puebla esos campos, y
    # duplicar su logica aca seria una copia que se desincroniza sola.
    if hasattr(ventana, "_fill_rules"):
        ventana._fill_rules()
    # La bitacora no se carga sola: hay que pedirla, como hace el boton
    # "Actualizar bitacora". Sin esto la pagina sale vacia y el screenshot no
    # muestra nada de lo que dice el titulo.
    if hasattr(ventana, "_load_history"):
        ventana._load_history()

    DESTINO.mkdir(parents=True, exist_ok=True)
    qt.processEvents()

    for fila, nombre, _alt in PAGINAS:
        ventana.nav.setCurrentRow(fila)
        ventana.refresh()
        # Tres vueltas: la primera reparte, la segunda resuelve, la tercera
        # fija. Sin esto el grab sale con el layout a medio hacer.
        for _ in range(3):
            qt.processEvents()
        pixmap = ventana.grab()
        salida = DESTINO / nombre
        pixmap.save(str(salida))
        print(f"  {salida.relative_to(RAIZ)}  {salida.stat().st_size:,} B")

    ventana.close()
    ventana.deleteLater()
    qt.processEvents()
    print("\n  Listo. Revisá las imágenes antes de subirlas al repo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
