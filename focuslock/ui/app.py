"""Interfaz gráfica: ventana principal + ícono en el área de notificación."""
from __future__ import annotations

import sys
import time
from datetime import datetime

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QBrush, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QSystemTrayIcon,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..ipc import IpcClient
from .emergency import EmergencyDialog

# Los colores de esta hoja no se eligen a ojo: hay ratios medidos.
#
#   texto  #e6e8ee sobre fondo #15171c       14.64:1   (pide 4.5)
#   hint   #8f98ad sobre fondo #15171c        6.20:1   (pide 4.5)
#   blanco sobre primario #2a6df4            4.57:1   (pide 4.5)
#   blanco sobre hover    #2560d8            5.61:1   (pide 4.5)
#   borde  #656f88 sobre #15171c / #1b1e25    3.57:1 / 3.32:1  (pide 3, borde)
#
# El hover OSCURECE a proposito: aclarar el azul lo aleja del blanco y
# dejaba el texto en 3.93:1, por debajo del minimo. El borde subio de
# #656f88 porque el anterior daba 1.24:1 y los campos de texto quedaban
# dibujados por una linea casi invisible.
# tests/test_ui.py::TestStyleContrast falla si alguno de estos numeros se mueve.
STYLE = """
QWidget { background:#15171c; color:#e6e8ee; font-size:13px; }
QGroupBox { border:1px solid #656f88; border-radius:8px; margin-top:14px; padding:10px; }
QGroupBox::title { subcontrol-origin: margin; left:10px; color:#8f98ad; }
QLabel#hint { color:#8f98ad; }
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QListWidget {
  background:#1b1e25; border:1px solid #656f88; border-radius:6px; padding:6px; }
QPushButton { background:#2a6df4; border:none; border-radius:6px; padding:8px 14px; color:white; }
QPushButton:hover { background:#2560d8; }
QPushButton:disabled { background:#333842; color:#6b7280; }
QPushButton#danger { background:#b3402f; }
QPushButton#ghost { background:#242832; }
QTabWidget::pane { border:1px solid #656f88; border-radius:8px; }
QTabBar::tab { background:#1b1e25; padding:9px 18px; border-top-left-radius:6px;
               border-top-right-radius:6px; }
QTabBar::tab:selected { background:#2a6df4; color:white; }
QProgressBar { border:1px solid #656f88; border-radius:6px; text-align:center; background:#1b1e25; }
QProgressBar::chunk { background:#2a6df4; border-radius:5px; }
"""


def make_icon(color: str = "#e5484d", unlocked: bool = False) -> QIcon:
    size = 64
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    if unlocked:
        p.setBrush(QBrush(QColor("#30a46c")))
        p.setPen(QPen(QColor("#0d1a14"), 5))
        p.drawEllipse(6, 6, size - 12, size - 12)
        p.setPen(QPen(QColor("#ffffff"), 7))
        p.drawLine(20, 33, 29, 43)
        p.drawLine(29, 43, 45, 23)
    else:
        p.setBrush(QBrush(QColor(color)))
        p.setPen(QPen(QColor("#2a0f10"), 5))
        p.drawEllipse(6, 6, size - 12, size - 12)
        p.setPen(QPen(QColor("#ffffff"), 5))
        p.drawRoundedRect(24, 28, 16, 20, 3, 3)
        p.drawArc(16, 10, 32, 32, 0, 180 * 16)
    p.end()
    return QIcon(pix)


class MainWindow(QMainWindow):
    def __init__(self, client) -> None:
        super().__init__()
        self.client = client
        self._data: dict = {}
        self.setWindowTitle("FocusLock")
        self.resize(880, 640)
        self.setWindowIcon(make_icon())

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.setMinimumHeight(64)
        self.banner.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.banner)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.tabs.addTab(self._tab_status(), "Estado")
        self.tabs.addTab(self._tab_programs(), "Programas")
        self.tabs.addTab(self._tab_sites(), "Sitios")
        self.tabs.addTab(self._tab_settings(), "Ajustes")
        self.tabs.addTab(self._tab_history(), "Bitácora")

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(8000)

        self.quit_action = QAction("Salir", self)
        self.quit_action.triggered.connect(self._quit)

    # ------------------------------------------------------------------ Estado
    def _tab_status(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)

        prog_box = QGroupBox("Progreso hacia el desbloqueo")
        pv = QVBoxLayout(prog_box)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setMinimumHeight(28)
        pv.addWidget(self.progress)
        self.modules = QLabel()
        self.modules.setWordWrap(True)
        self.modules.setObjectName("hint")
        pv.addWidget(self.modules)
        v.addWidget(prog_box)

        row = QHBoxLayout()
        self.btn_poll = QPushButton("Actualizar TickTick ahora")
        self.btn_poll.clicked.connect(lambda: self.refresh(force=True))
        self.btn_toggle = QPushButton("Activar bloqueo")
        self.btn_toggle.clicked.connect(self._toggle_lock)
        self.btn_emergency = QPushButton("Desbloqueo de emergencia…")
        self.btn_emergency.setObjectName("danger")
        self.btn_emergency.clicked.connect(self._emergency)
        row.addWidget(self.btn_poll)
        row.addWidget(self.btn_toggle)
        row.addStretch(1)
        row.addWidget(self.btn_emergency)
        v.addLayout(row)

        note = QLabel(
            "El bloqueo está apagado por defecto. Prendelo cuando quieras "
            "estudiar; te vas a poder liberar con las Lecturas o con el "
            "desbloqueo de emergencia."
        )
        note.setWordWrap(True)
        note.setObjectName("hint")
        v.addWidget(note)

        return page

    # --------------------------------------------------------------- Programas
    def _tab_programs(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        hint = QLabel(
            "Se bloquea lo que esté en la lista izquierda, salvo que esté en la de "
            "permitidos. Con IFEO activo el programa ni siquiera llega a arrancar; el "
            "vigilante de procesos lo remata si logra colarse."
        )
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        v.addWidget(hint)

        split = QSplitter()
        self.prog_blocked = self._rule_list("Bloqueados", "programs", "blocked")
        self.prog_allowed = self._rule_list("Permitidos (nunca se bloquean)", "programs", "allowed")
        split.addWidget(self.prog_blocked["holder"])
        split.addWidget(self.prog_allowed["holder"])
        v.addWidget(split, 1)

        self.ifeo_check = QCheckBox("Usar IFEO (requiere instalación con administrador)")
        v.addWidget(self.ifeo_check)
        return page

    # ------------------------------------------------------------------ Sitios
    def _tab_sites(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        hint = QLabel(
            "Dominios bloqueados por la extensión del navegador. Se aceptan nombres "
            "sueltos: escribir 'youtube.com' alcanza para www., m., music. y shorts."
        )
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        v.addWidget(hint)

        split = QSplitter()
        self.site_blocked = self._rule_list("Dominios bloqueados", "sites", "blocked")
        self.site_allowed = self._rule_list("Permitidos (exentos)", "sites", "allowed")
        split.addWidget(self.site_blocked["holder"])
        split.addWidget(self.site_allowed["holder"])
        v.addWidget(split, 1)

        info = QLabel()
        info.setObjectName("hint")
        info.setWordWrap(True)
        self.site_info = info
        v.addWidget(info)
        return page

    def _rule_list(self, title: str, section: str, field: str) -> dict:
        holder = QWidget()
        lay = QVBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(title)
        lbl.setObjectName("hint")
        lay.addWidget(lbl)

        listing = QListWidget()
        lay.addWidget(listing, 1)

        entry = QLineEdit()
        entry.setPlaceholderText("Ej: steam.exe" if section == "programs" else "Ej: tiktok.com")
        entry.returnPressed.connect(
            lambda: self._rule_add(section, field, listing, entry, False)
        )
        lay.addWidget(entry)

        row = QHBoxLayout()
        add = QPushButton("Agregar")
        add.clicked.connect(lambda: self._rule_add(section, field, listing, entry, False))
        add.setObjectName("ghost")
        remove = QPushButton("Quitar")
        remove.setObjectName("ghost")
        remove.clicked.connect(lambda: self._rule_del(section, field, listing))
        row.addWidget(add)
        row.addWidget(remove)
        lay.addLayout(row)

        return {
            "holder": holder,
            "list": listing,
            "entry": entry,
            "section": section,
            "field": field,
        }

    # ----------------------------------------------------------------- Ajustes
    def _tab_settings(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)

        tt = QGroupBox("TickTick")
        tf = QFormLayout(tt)
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.Password)
        self.token.setPlaceholderText("Token tp_…  (se guarda cifrado con DPAPI)")
        tf.addRow("Token", self.token)
        row = QHBoxLayout()
        row = QHBoxLayout()
        self.btn_token = QPushButton("Probar conexión y guardar")
        self.btn_token.setObjectName("ghost")
        self.btn_token.clicked.connect(self._test_token)
        clear = QPushButton("Borrar token")
        clear.setObjectName("ghost")
        clear.clicked.connect(self._clear_token)
        row.addWidget(self.btn_token)
        row.addWidget(clear)
        row.addStretch(1)
        tf.addRow(row)

        self.project_name = QLineEdit()
        self.project_name.setPlaceholderText("Ej: Estudios")
        tf.addRow("Proyecto de TickTick", self.project_name)

        hint = QLabel(
            "Se cuenta cualquier tarea del proyecto, sin mirar el nombre. "
            "Tachá 2 tareas en TickTick y se desbloquea."
        )
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        tf.addRow(hint)

        self.required = QSpinBox()
        self.required.setRange(1, 50)
        tf.addRow("Lecturas necesarias", self.required)
        self.poll_secs = QSpinBox()
        self.poll_secs.setRange(15, 600)
        self.poll_secs.setSingleStep(15)
        self.poll_secs.setSuffix(" s")
        tf.addRow("Frecuencia de consulta", self.poll_secs)
        v.addWidget(tt)

        em_box = QGroupBox("Emergencia")
        ef = QFormLayout(em_box)
        self.em_words = QSpinBox()
        self.em_words.setRange(50, 5000)
        self.em_words.setSingleStep(50)
        ef.addRow("Palabras mínimas", self.em_words)
        self.em_minutes = QSpinBox()
        self.em_minutes.setRange(1, 120)
        ef.addRow("Minutos de escritura", self.em_minutes)
        self.em_unlock = QSpinBox()
        self.em_unlock.setRange(1, 480)
        ef.addRow("Minutos que desbloquea", self.em_unlock)
        v.addWidget(em_box)

        ext = QGroupBox("Extensión del navegador")
        xf = QFormLayout(ext)
        ext_hint = QLabel(
            "Copiá esta dirección en la página de opciones de la extensión.\n"
            "Chrome: chrome://extensions → Modo de desarrollador → Cargar descomprimida "
            "→ carpeta extension/chrome.\n"
            "Firefox: about:debugging#/runtime/this-firefox → Cargar complemento temporal "
            "→ extension/firefox/manifest.json"
        )
        ext_hint.setWordWrap(True)
        ext_hint.setObjectName("hint")
        xf.addRow(ext_hint)
        self.ext_url = QLineEdit()
        self.ext_url.setReadOnly(True)
        xf.addRow("Dirección", self.ext_url)
        row = QHBoxLayout()
        copy = QPushButton("Copiar dirección")
        copy.setObjectName("ghost")
        copy.clicked.connect(self._copy_endpoint)
        open_dir = QPushButton("Abrir carpeta de la extensión")
        open_dir.setObjectName("ghost")
        open_dir.clicked.connect(self._open_ext_dir)
        row.addWidget(copy)
        row.addWidget(open_dir)
        row.addStretch(1)
        xf.addRow(row)
        v.addWidget(ext)

        save = QPushButton("Guardar ajustes")
        save.clicked.connect(self._save_settings)
        v.addWidget(save)
        v.addStretch(1)
        return page

    # --------------------------------------------------------------- Bitácora
    def _tab_history(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.addWidget(QLabel("Desbloqueos de emergencia"))
        self.hist_em = QPlainTextEdit()
        self.hist_em.setReadOnly(True)
        v.addWidget(self.hist_em, 1)
        v.addWidget(QLabel("Intentos de bloqueo de procesos"))
        self.hist_blocks = QPlainTextEdit()
        self.hist_blocks.setReadOnly(True)
        v.addWidget(self.hist_blocks, 1)
        refresh = QPushButton("Actualizar bitácora")
        refresh.setObjectName("ghost")
        refresh.clicked.connect(self._load_history)
        v.addWidget(refresh)
        return page

    # =================================================================== Datos
    def refresh(self, force: bool = False) -> None:
        try:
            data = self.client.call("poll" if force else "status")
        except Exception as exc:  # noqa: BLE001
            self._data = {}
            self._apply_banner(locked=True, offline=str(exc))
            return
        self._data = data
        self._render(data)
        self._update_endpoint(data)

    def _render(self, data: dict) -> None:
        locked = bool(data.get("locked"))
        self._apply_banner(locked)

        required = max(1, int(data.get("required", 2)))
        credits = int(data.get("credits", 0))
        if locked:
            self.progress.setValue(int(min(1.0, credits / required) * 100))
            self.progress.setFormat(f"{credits} de {required} Lecturas")
        else:
            self.progress.setValue(100)
            self.progress.setFormat("Desbloqueado")

        checked = float(data.get("checked_at") or 0)
        fresh = checked > 0

        mods = data.get("modules") or {}
        if not fresh:
            # Todavía no se consultó TickTick. Decir "no hay Lecturas
            # pendientes" sería inventar: lo correcto es decir que no sabe.
            self.modules.setText("Consultando TickTick…")
        elif mods:
            self.modules.setText(
                "Pendientes por módulo: "
                + " · ".join(f"{name} ({n})" for name, n in mods.items())
            )
        else:
            self.modules.setText("No hay Lecturas pendientes en TickTick.")

        if data.get("error"):
            self.modules.setText(f"TickTick: {data['error']}")
            # Un fallo de polling silencioso es como worse el bug de creditos:
            # el contador se queda en 0 y no se explica por que.
            self.banner.setStyleSheet(self._LOCKED_STYLE)
            self.banner.setText(
                "<b style='color:#e5484d'>ERROR al consultar TickTick</b><br>"
                f"{data['error']}<br>"
                "El contador de Lecturas no se está actualizando."
            )

        # El boton solo activa; no hay forma de desactivar desde la UI.
        if hasattr(self, "btn_toggle"):
            if locked:
                self.btn_toggle.setText("Bloqueo activo")
                self.btn_toggle.setEnabled(False)
            else:
                self.btn_toggle.setText("Activar bloqueo")
                self.btn_toggle.setEnabled(True)

        # La emergencia solo tiene sentido con un bloqueo activo: sin bloqueo
        # no hay nada que desbloquear.
        if hasattr(self, "btn_emergency"):
            self.btn_emergency.setEnabled(locked)
            self.btn_emergency.setToolTip(
                "" if locked else "Solo se puede usar con el bloqueo activo."
            )

        self.site_info.setText(
            f"Extensión conectada a http://127.0.0.1:{data.get('port', 0)}/state · "
            f"IFEO activo en {len(data.get('ifeo', []))} ejecutables · "
            f"{data.get('guard', {}).get('scans', 0)} barridos, "
            f"{data.get('guard', {}).get('kills', 0)} detenciones."
        )

    def _update_endpoint(self, data: dict) -> None:
        if not hasattr(self, "ext_url"):
            return
        port, token = data.get("port", 0), data.get("token", "")
        if port and token:
            self.ext_url.setText(f"http://127.0.0.1:{port}/state?token={token}")

    def _copy_endpoint(self) -> None:
        QApplication.clipboard().setText(self.ext_url.text())
        QMessageBox.information(
            self, "Copiado",
            "Dirección copiada. Abrí la página de opciones de la extensión y pegala.",
        )

    def _open_ext_dir(self) -> None:
        import os
        from pathlib import Path

        root = Path(__file__).resolve().parents[2] / "extension"
        if not root.exists():
            QMessageBox.warning(self, "No encontrado", f"No existe {root}")
            return
        os.startfile(str(root))  # noqa: S606
        QMessageBox.information(self, "Extensiones", f"Carpeta abierta:\n{root}")

    _LOCKED_STYLE = ("background:#2a0f10;border:1px solid #e5484d;"
                     "border-radius:8px;padding:10px;")
    _OPEN_STYLE = ("background:#0d1a14;border:1px solid #30a46c;"
                   "border-radius:8px;padding:10px;")

    def _apply_banner(self, locked: bool, offline: str = "") -> None:
        if offline:
            # Sin servicio no se sabe el estado real: se avisa, no se afirma.
            self.banner.setStyleSheet(self._LOCKED_STYLE)
            self.banner.setText(
                "<b style='color:#e5484d'>SIN SERVICIO</b> — no se puede "
                f"consultar el estado.<br>{offline}<br>"
                "Instalalo con administrador: <code>install.ps1</code>"
            )
            return
        if locked:
            self.banner.setStyleSheet(self._LOCKED_STYLE)
            self.banner.setText(
                "<b style='color:#e5484d'>BLOQUEADO</b> — completá las Lecturas en TickTick."
            )
            return
        self.banner.setStyleSheet(self._OPEN_STYLE)
        reason = self._data.get("reason", "")
        self.banner.setText(
            f"<b style='color:#30a46c'>DESBLOQUEADO</b> — {reason or 'sin tareas pendientes'}"
        )

    # ================================================================= Acciones
    def _toggle_lock(self) -> None:
        """Activa el bloqueo.

        No hay botón para desactivarlo a propósito: si activaste el bloqueo es
        porque querés concentrarte y hacer las Lecturas. La única salida es
        completarlas o el desbloqueo de emergencia. Si un día no querés
        trabajar, no lo actives.
        """
        if self._data.get("locked", False):
            QMessageBox.information(
                self,
                "Ya está bloqueado",
                "El bloqueo ya está activo.\n\n"
                "Completá las Lecturas en TickTick o usá el desbloqueo de "
                "emergencia si necesitás salir.",
            )
            return

        enforcement = self._data.get("enforcement", True)
        if not enforcement:
            QMessageBox.information(
                self,
                "Sin enforcement",
                "El servicio de Windows no está corriendo, así que activar el "
                "bloqueo solo reinicia el contador de Lecturas. Para bloquear "
                "de verdad instalá el servicio con install.ps1.",
            )

        blocked = self._data.get("ifeo") or []
        if not blocked:
            answer = QMessageBox.question(
                self,
                "Activar el bloqueo",
                "No hay ningún programa en la lista de bloqueados, así que "
                "activarlo no va a encerrarte de nada.\n\n"
                "Igual va a contar tus Lecturas.\n\n"
                "¿Activarlo igual?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        else:
            answer = QMessageBox.question(
                self,
                "Activar el bloqueo",
                f"Se van a bloquear {len(blocked)} programa(s) hasta que "
                "completes las Lecturas:\n\n"
                + "\n".join(f"  · {name}" for name in blocked)
                + "\n\nLa única salida son las Lecturas o el desbloqueo de "
                "emergencia.\n\n¿Activarlo?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        try:
            result = self.client.call("lock")
            self.refresh(force=True)
            message = result.get("message")
            if message:
                QMessageBox.information(self, "Listo", message)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "No se pudo activar el bloqueo", str(exc))

    def _emergency(self) -> None:
        try:
            cfg = self.client.call("config_get")["config"]
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "No se pudo leer la configuración", str(exc))
            return
        dlg = EmergencyDialog(cfg, self.client, self)
        dlg.exec()
        result = dlg.granted
        if not result:
            return
        if result.get("granted"):
            QMessageBox.information(
                self, "Desbloqueado", result.get("message", "Desbloqueado por emergencia.")
            )
        else:
            # Cumple los requisitos pero no hay enforcement: se registra igual.
            QMessageBox.information(
                self,
                "Compromiso registrado",
                "\n\n".join(result.get("errors", [])),
            )
        self.refresh(force=True)

    def _rule_add(
        self,
        section: str,
        field: str,
        listing: QListWidget,
        entry: QLineEdit,
        force: bool,
    ) -> None:
        value = entry.text().strip()
        if not value:
            return
        try:
            res = self.client.call(f"{section}_{field}_add", value=value, force=force)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "No se pudo agregar", str(exc))
            return

        if res.get("immutable"):
            QMessageBox.information(self, "Proceso protegido", res.get("message", ""))
            return

        if res.get("needs_confirm"):
            answer = QMessageBox.warning(
                self,
                "Esto puede romper Windows",
                res.get("message", "El proceso es crítico."),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer == QMessageBox.Yes:
                self._rule_add(section, field, listing, entry, True)
                return
            return

        entry.clear()
        self._fill_rules()

    def _rule_del(self, section: str, field: str, listing: QListWidget) -> None:
        item = listing.currentItem()
        if not item:
            return
        try:
            self.client.call(f"{section}_{field}_del", value=item.text())
            self._fill_rules()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "No se pudo quitar", str(exc))

    def _fill_rules(self) -> None:
        try:
            cfg = self.client.call("config_get")["config"]
        except Exception:
            return
        for holder, path in (
            (self.prog_blocked, ("programs", "blocked")),
            (self.prog_allowed, ("programs", "allowed")),
            (self.site_blocked, ("sites", "blocked")),
            (self.site_allowed, ("sites", "allowed")),
        ):
            holder["list"].clear()
            holder["list"].addItems(cfg.get(path[0], {}).get(path[1], []) or [])
        self.ifeo_check.setChecked(bool(cfg.get("programs", {}).get("use_ifeo", True)))
        tt = cfg.get("ticktick", {})
        self.project_name.setText(tt.get("project_name", ""))
        self.required.setValue(int(tt.get("required", 2)))
        self.poll_secs.setValue(int(tt.get("poll_seconds", 45)))
        e = cfg.get("emergency", {})
        self.em_words.setValue(int(e.get("min_words", 300)))
        self.em_minutes.setValue(int(e.get("min_minutes", 5)))
        self.em_unlock.setValue(int(e.get("unlock_minutes", 20)))

    def _test_token(self) -> None:
        """Guarda el token y consulta TickTick.

        Distingue tres casos que antes se confundian en un unico error:
        el token esta mal, la red fallo, o no hay servicio.
        """
        token = self.token.text().strip()
        if not token:
            QMessageBox.warning(self, "Falta el token", "Pegá el token de TickTick.")
            return

        self.btn_token.setEnabled(False)
        self.btn_token.setText("Probando…")
        try:
            res = self.client.call("ticktick_set_token", token=token)
        except Exception as exc:  # noqa: BLE001
            self.btn_token.setEnabled(True)
            self.btn_token.setText("Probar conexión")
            self._show_token_error(str(exc))
            return

        self.btn_token.setEnabled(True)
        self.btn_token.setText("Probar conexión")

        # A veces el backend devuelve (ok, error) en vez de lanzar.
        if not res.get("ok", False):
            detail = res.get("error", "El token fue rechazado.")
            self._show_token_error(detail, rejected=True)
            return

        self.token.clear()
        self._save_ticktick_settings()
        names = "\n".join(str(n) for n in (res.get("names") or []) if n)
        extra = ""
        if res.get("enforcement") is False:
            extra = (
                "\n\nOjo: el servicio no está corriendo, así que el token quedó "
                "guardado pero no se está bloqueando nada todavía.\n"
                "Instalalo como administrador: install.ps1"
            )
        QMessageBox.information(
            self,
            "Conectado",
            f"Token guardado y cifrado.\nProyectos visibles: {res.get('projects')}\n{names}{extra}",
        )
        self.refresh(force=True)

    def _show_token_error(self, detail: str, rejected: bool = False) -> None:
        """El error que mas confunde es 'no hay servicio': no es el token."""
        lowered = (detail or "").lower()
        looks_like_missing_service = (
            "servicio" in lowered
            or "pipe" in lowered
            or "contactar" in lowered
            or "conectar" in lowered
        )
        if not rejected and looks_like_missing_service:
            QMessageBox.warning(
                self,
                "No hay servicio corriendo",
                "El token no se pudo guardar porque el servicio de Windows no "
                "está corriendo.\n\n"
                "Instalalo como administrador:\n"
                "    powershell -ExecutionPolicy Bypass -File install.ps1\n\n"
                f"Detalle técnico: {detail}",
            )
            return
        QMessageBox.warning(self, "Token rechazado", detail or "Revisá el token.")

    def _save_ticktick_settings(self) -> None:
        """Guarda proyecto/prefijo/cantidad sin depender del servicio."""
        try:
            self.client.call("config_set", section="ticktick", values={
                "project_name": self.project_name.text().strip(),
                "project_id": "",
                "required": self.required.value(),
                "poll_seconds": self.poll_secs.value(),
            })
        except Exception:  # noqa: BLE001
            pass

    def _clear_token(self) -> None:
        try:
            self.client.call("ticktick_set_token", token="")
            self.token.clear()
            self.refresh(force=True)
        except Exception as exc:  # noqa: BLE001
            self._show_token_error(str(exc))

    def _save_settings(self) -> None:
        try:
            self._save_ticktick_settings()
            self.client.call("config_set", section="emergency", values={
                "min_words": self.em_words.value(),
                "min_minutes": self.em_minutes.value(),
                "unlock_minutes": self.em_unlock.value(),
            })
            self.client.call("config_set", section="programs", values={
                "use_ifeo": self.ifeo_check.isChecked(),
            })
            QMessageBox.information(self, "Guardado", "Ajustes guardados.")
            self.refresh(force=True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "No se pudo guardar", str(exc))

    def _load_history(self) -> None:
        try:
            data = self.client.call("history")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "No se pudo", str(exc))
            return
        em = data.get("emergencies", [])
        if em:
            lines = []
            for e in reversed(em):
                when = datetime.fromtimestamp(e.get("at", 0)).strftime("%Y-%m-%d %H:%M")
                lines.append(
                    f"── {when} · {e.get('words', 0)} palabras · "
                    f"{int(e.get('seconds', 0) // 60)} min\n{e.get('commitment', '')}\n"
                )
            self.hist_em.setPlainText("\n".join(lines))
        else:
            self.hist_em.setPlainText("Sin desbloqueos de emergencia registrados.")

        blocks = data.get("blocks", [])
        if blocks:
            rows = [
                f"{datetime.fromtimestamp(b.get('at', 0)).strftime('%m-%d %H:%M:%S')}  "
                f"{b.get('process', '?'):<24} pid={b.get('pid', '?'):<7} {b.get('method', '')}"
                for b in reversed(blocks)
            ]
            self.hist_blocks.setPlainText("\n".join(rows))
        else:
            self.hist_blocks.setPlainText("Ningún proceso detenido.")

    # ------------------------------------------------------------------ cierre
    def closeEvent(self, event) -> None:  # noqa: N802
        event.ignore()
        self.hide()

    def _quit(self) -> None:
        QApplication.quit()


class TrayApp:
    """Arranca la GUI y elige backend: servicio de Windows o modo local.

    El servicio es preferible (es el que bloquea de verdad), pero si no esta
    instalado la app tiene que seguir siendo utilizable: se ve el estado, se
    guarda el token, se editan las listas. Lo que no se puede es bloquear, y
    la UI lo dice.
    """

    def __init__(self, force_local: bool = False) -> None:
        # Reutiliza la instancia existente: Qt solo admite un QApplication por
        # proceso y crear un segundo lanza RuntimeError.
        self.qt = QApplication.instance() or QApplication(sys.argv)
        self.qt.setQuitOnLastWindowClosed(False)
        self.qt.setStyleSheet(STYLE)

        self.client = IpcClient()
        self.local = None
        self.using_service = False

        if not force_local:
            try:
                self.client.call("status", retries=0)
                self.using_service = True
            except Exception:
                self.using_service = False

        if not self.using_service:
            from ..local import LocalBackend

            self.local = LocalBackend()
            self.client = self.local

        self.window = MainWindow(self.client)
        self.tray = QSystemTrayIcon(make_icon(), self.qt)
        menu = QMenu()
        menu.addAction("Abrir FocusLock", self.window.show)
        menu.addAction("Actualizar ahora", lambda: self.window.refresh(force=True))
        menu.addSeparator()
        menu.addAction(self.window.quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray)
        self.tray.show()

    def _on_tray(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.window.show()
            self.window.raise_()
            self.window.activateWindow()

    def run(self) -> int:
        self.window.show()
        self.window._fill_rules()
        self.window._load_history()
        self.window.refresh()
        if not self.using_service:
            self._show_standalone_notice()
        return self.qt.exec()

    def _show_standalone_notice(self) -> None:
        """Sin servicio la app funciona, pero no bloquea. Hay que decirlo."""
        QMessageBox.information(
            self.window,
            "FocusLock en modo sin bloqueo",
            "El servicio de Windows no está corriendo, así que FocusLock va a "
            "mostrarte el estado de tus Lecturas y a guardar la configuración, "
            "pero NO va a bloquear ningún programa.\n\n"
            "Para que bloquee de verdad, instalalo una vez como administrador:\n\n"
            "    powershell -ExecutionPolicy Bypass -File install.ps1\n\n"
            "Mientras tanto podés pegar el token en Ajustes y verlo funcionar.",
        )


def main(force_local: bool = False) -> int:
    return TrayApp(force_local=force_local).run()


if __name__ == "__main__":
    sys.exit(main())
