"""Interfaz gráfica: ventana principal + ícono en el área de notificación."""
from __future__ import annotations

import sys
import time
from datetime import datetime

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QIcon,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFormLayout,
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
    QFormLayout,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..ipc import IpcClient
from .emergency import EmergencyDialog

# Gris oscuro NEUTRO, sin tinte azul. Jerarquia de TickTick, contencion de
# Apple: un solo acento, y en tres lugares.
#
# Ratios medidos, no estimados a ojo:
#   texto   #eceef1 sobre fondo #1c1d20       14.50:1  (pide 4.5)
#   texto   #eceef1 sobre superficie #242629  13.05:1  (pide 4.5)
#   texto 2 #9ea3ab sobre fondo #1c1d20        6.65:1  (pide 4.5)
#   texto 2 #9ea3ab sobre sidebar #161719      7.07:1  (pide 4.5)
#   blanco  sobre acento  #2f6fe0              4.70:1  (pide 4.5)
#   blanco  sobre hover   #2560d8              6.29:1  (pide 4.5)
#   blanco  sobre peligro #b8503a              4.95:1  (pide 4.5)
#   borde   #6e737d sobre superficie #242629   3.19:1  (pide 3, borde de control)
#   borde   #6e737d sobre fondo #1c1d20        3.54:1  (pide 3, borde de control)
#
# DIVIDER no es un borde de control sino decorativo, por eso puede ser tenue.
# tests/test_ui.py::TestStyleContrast falla si alguno de estos numeros se mueve.
STYLE = """
QWidget { background:#1c1d20; color:#eceef1; font-size:13px; }

#sidebar      { background:#161719; border-right:1px solid #2b2d31; }
#sidebarTitle { font-size:20px; font-weight:600; }
#sidebarSub   { font-size:12px; color:#9ea3ab; }
#sidebarFoot  { font-size:12px; color:#9ea3ab; }
#pageTitle    { font-size:26px; font-weight:600; }

#nav { background:transparent; border:none; outline:none; }
#nav::item {
  color:#9ea3ab; padding:11px 12px; margin:2px 10px; border-radius:10px; }
#nav::item:hover    { background:#2c2e32; color:#eceef1; }
#nav::item:selected { background:#2f6fe0; color:#ffffff; }

QLabel#hint  { color:#9ea3ab; }
QLabel#count { color:#eceef1; font-size:14px; font-weight:600; }

/* Sin esto los QLabel heredan el fondo de QWidget y se pintan como parches
   negros sobre las tarjetas #242629. */
QLabel, QCheckBox { background:transparent; }

#card { background:#242629; border-radius:14px; }
QLabel#cardTitle { font-size:15px; font-weight:600; color:#eceef1; }
#page { background:#1c1d20; }
#cuerpo { background:#1c1d20; }

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QListWidget {
  background:#242629; color:#eceef1;
  border:1px solid #6e737d; border-radius:8px; padding:7px;
  selection-background-color:#2f6fe0; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {
  border:1px solid #2f6fe0; }

QPushButton {
  background:#2f6fe0; border:none; border-radius:10px;
  padding:11px 18px; color:#ffffff; font-size:14px; }
QPushButton:hover   { background:#2560d8; }
QPushButton:pressed { background:#1f52ba; }
QPushButton:disabled {
  background:#242629; color:#6c7078; border:1px solid #2b2d31; }
QPushButton#danger { background:#b8503a; }
QPushButton#danger:hover { background:#a84530; }
QPushButton#danger:disabled {
  background:#242629; color:#6c7078; border:1px solid #2b2d31; }
QPushButton#ghost {
  background:#242629; border:1px solid #6e737d; color:#eceef1; }
QPushButton#ghost:hover { background:#2c2e32; }
QPushButton#ghost:disabled {
  background:#1c1d20; color:#6c7078; border:1px solid #2b2d31; }

QProgressBar {
  border:none; border-radius:7px; text-align:center;
  background:#2c2e32; min-height:14px; max-height:14px; }
QProgressBar::chunk { background:#2f6fe0; border-radius:7px; }

QScrollBar:vertical { background:transparent; width:10px; margin:0; }
QScrollBar::handle:vertical {
  background:#3a3d42; border-radius:5px; min-height:30px; }
QScrollBar::handle:vertical:hover { background:#4a4e55; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
  background:transparent; }
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
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- barra de estado a lo ancho, arriba de todo ------------------------
        shell = QWidget()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        self.banner = QLabel()
        self.banner.setWordWrap(True)
        # El estado ya esta en la barra de progreso y en el titulo de la
        # pagina. Este aviso es solo para lo que no se ve en ningun otro
        # lado: que el servicio murio, o que TickTick no contesta. Cuando
        # no hay nada que avisar no ocupa nada.
        self.banner.setMinimumHeight(0)
        self.banner.setAlignment(Qt.AlignCenter)
        self.banner.setContentsMargins(24, 10, 24, 10)
        self.banner.hide()
        shell_layout.addWidget(self.banner)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # --- menu lateral ----------------------------------------------------
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(244)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 26, 0, 18)
        side.setSpacing(0)

        brand = QVBoxLayout()
        brand.setContentsMargins(28, 0, 24, 0)
        brand.setSpacing(0)
        # El nombre va con su icono, en una sola fila. Solo el texto, con todo
        # el aire de la barra alrededor, se leia como un titulo suelto.
        linea = QHBoxLayout()
        linea.setContentsMargins(0, 0, 0, 0)
        linea.setSpacing(9)
        marca = QLabel()
        marca.setPixmap(make_icon(unlocked=True).pixmap(26, 26))
        linea.addWidget(marca)
        title = QLabel("FocusLock")
        title.setObjectName("sidebarTitle")
        linea.addWidget(title)
        linea.addStretch(1)
        brand.addLayout(linea)
        brand.addSpacing(3)
        sub = QLabel("Frená lo que elijas hasta trabajar")
        sub.setObjectName("sidebarSub")
        sub.setWordWrap(True)
        brand.addWidget(sub)
        wrapper = QWidget()
        wrapper.setLayout(brand)
        wrapper.setContentsMargins(0, 0, 0, 0)
        side.addWidget(wrapper)

        side.addSpacing(28)

        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFocusPolicy(Qt.StrongFocus)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for etiqueta in self.PAGINAS:
            self.nav.addItem(etiqueta)
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self._ir_a)
        side.addWidget(self.nav, 1)

        foot = QLabel("Servicio: LocalSystem")
        foot.setObjectName("sidebarFoot")
        foot.setContentsMargins(28, 0, 0, 0)
        side.addWidget(foot)

        body_layout.addWidget(sidebar)

        # --- contenido -------------------------------------------------------
        self.stack = QStackedWidget()
        for etiqueta in self.PAGINAS:
            self.stack.addWidget(self._pagina(etiqueta))
        body_layout.addWidget(self.stack, 1)

        shell_layout.addWidget(body, 1)
        outer.addWidget(shell)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(8000)

        # Atajos: la app se usa en un momento de tension, y buscar el boton
        # con el mouse en ese momento es un paso de mas.
        for secuencia, destino in (("Ctrl+L", self._toggle_lock),
                                   ("Ctrl+E", self._emergency)):
            atajo = QShortcut(QKeySequence(secuencia), self)
            atajo.activated.connect(destino)

        self.quit_action = QAction("Salir", self)
        self.quit_action.triggered.connect(self._quit)

    # ------------------------------------------------------------- navegacion
    PAGINAS = ("Estado", "Programas", "Sitios", "Ajustes", "Bitácora")

    SUBTITULOS = {
        "Estado": "El bloqueo está apagado. Prendelo cuando quieras estudiar.",
        "Programas": "Elegí qué programas no arrancan mientras el bloqueo está activo.",
        "Sitios": "Dominios que no cargan y excepciones que siempre pasan.",
        "Ajustes": "Token de TickTick, cuánto cuesta desbloquear y la extensión.",
        "Bitácora": "Cada desbloqueo de emergencia y cada intento de bloqueo.",
    }

    def _pagina(self, etiqueta: str) -> QWidget:
        """Envuelve cada pagina con su titulo y su margen.

        El titulo se agrega aca y no en cada constructor: son cinco paginas y
        el titulo es una regla del diseno, no algo de cada pantalla.
        """
        constructor = {
            "Estado": self._tab_status,
            "Programas": self._tab_programs,
            "Sitios": self._tab_sites,
            "Ajustes": self._tab_settings,
            "Bitácora": self._tab_history,
        }[etiqueta]

        # Estado ya trae su propio titulo y su propio margen: se usa tal cual.
        if etiqueta == "Estado":
            page = constructor()
            page.setObjectName("page")
            return page

        cont = QWidget()
        cont.setObjectName("page")
        v = QVBoxLayout(cont)
        v.setContentsMargins(36, 32, 36, 32)
        v.setSpacing(18)

        # Titulo y subtitulo van juntos en su propio bloque, con espaciado
        # corto. Con el espaciado general de la pagina quedaban a doble de
        # distancia y los dos parecian textos sueltos. Margenes negativos
        # parecian la solucion y recortaban el subtitulo: no lo son.
        cabecera = QVBoxLayout()
        cabecera.setContentsMargins(0, 0, 0, 0)
        cabecera.setSpacing(1)
        titulo = QLabel(etiqueta)
        titulo.setObjectName("pageTitle")
        cabecera.addWidget(titulo)
        sub = QLabel(self.SUBTITULOS[etiqueta])
        sub.setObjectName("hint")
        sub.setWordWrap(True)
        cabecera.addWidget(sub)
        v.addLayout(cabecera)

        # El contenido de cada pagina no lleva margenes propios.
        cuerpo = constructor()
        cuerpo.setObjectName("cuerpo")
        cuerpo.layout().setContentsMargins(0, 8, 0, 0)
        v.addWidget(cuerpo, 1)
        return cont

    def _ir_a(self, fila: int) -> None:
        if 0 <= fila < self.stack.count():
            self.stack.setCurrentIndex(fila)

    # ------------------------------------------------------------------ Estado
    def _tab_status(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(36, 32, 36, 32)
        v.setSpacing(18)

        # Titulo y refresco en la misma fila: "Actualizar" es una accion
        # secundaria y al lado del titulo deja de competir con las dos
        # acciones de verdad. Titulo y subtitulo van en un bloque propio para
        # que el subtitulo quede pegado al titulo.
        cabecera = QVBoxLayout()
        cabecera.setContentsMargins(0, 0, 0, 0)
        cabecera.setSpacing(1)
        fila_titulo = QHBoxLayout()
        fila_titulo.setContentsMargins(0, 0, 0, 0)
        titulo = QLabel("Estado")
        titulo.setObjectName("pageTitle")
        self.btn_poll = QPushButton("Actualizar TickTick ahora")
        self.btn_poll.setObjectName("ghost")
        self.btn_poll.setToolTip("Consultar TickTick ahora (no espera el intervalo)")
        self.btn_poll.clicked.connect(lambda: self.refresh(force=True))
        fila_titulo.addWidget(titulo)
        fila_titulo.addStretch(1)
        fila_titulo.addWidget(self.btn_poll)
        cabecera.addLayout(fila_titulo)

        self.estado_sub = QLabel()
        self.estado_sub.setObjectName("hint")
        self.estado_sub.setWordWrap(True)
        cabecera.addWidget(self.estado_sub)
        v.addLayout(cabecera)

        prog_box = QWidget()
        prog_box.setObjectName("card")
        pv = QVBoxLayout(prog_box)
        pv.setContentsMargins(26, 20, 26, 22)
        pv.setSpacing(10)

        # Titulo del grupo y contador en la misma fila: el numero va arriba a
        # la derecha, no encima de la barra, donde compite con el color.
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        etiqueta = QLabel("Progreso hacia el desbloqueo")
        etiqueta.setObjectName("cardTitle")
        self.count = QLabel()
        self.count.setObjectName("count")
        head.addWidget(etiqueta)
        head.addStretch(1)
        head.addWidget(self.count)
        pv.addLayout(head)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setMinimumHeight(14)
        self.progress.setMaximumHeight(14)
        self.progress.setTextVisible(False)
        self.progress.setFormat("")  # el contador vive en self.count
        pv.addWidget(self.progress)

        self.modules = QLabel()
        self.modules.setWordWrap(True)
        self.modules.setObjectName("hint")
        pv.addWidget(self.modules)
        v.addWidget(prog_box)

        # Un solo boton primario. "Actualizar" vive arriba con el titulo, asi
        # que aca solo quedan las dos acciones de verdad.
        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn_toggle = QPushButton("Activar bloqueo")
        self.btn_toggle.clicked.connect(self._toggle_lock)
        self.btn_emergency = QPushButton("Desbloqueo de emergencia")
        self.btn_emergency.setObjectName("danger")
        self.btn_emergency.setToolTip("Ctrl+E")
        self.btn_emergency.clicked.connect(self._emergency)
        row.addWidget(self.btn_toggle)
        row.addWidget(self.btn_emergency)
        row.addStretch(1)
        v.addLayout(row)

        self.nota = QLabel(
            "El bloqueo está apagado por defecto. Prendelo cuando quieras "
            "estudiar; te vas a poder liberar con las Lecturas o con el "
            "desbloqueo de emergencia."
        )
        self.nota.setWordWrap(True)
        self.nota.setObjectName("hint")
        v.addWidget(self.nota)

        atajos = QWidget()
        atajos.setObjectName("card")
        av = QVBoxLayout(atajos)
        av.setContentsMargins(26, 18, 26, 20)
        av.setSpacing(4)
        at = QLabel("Atajos")
        at.setObjectName("cardTitle")
        av.addWidget(at)
        lista = QLabel("Ctrl+L  activar bloqueo        Ctrl+E  desbloqueo de emergencia")
        lista.setObjectName("hint")
        av.addWidget(lista)
        v.addWidget(atajos)

        v.addStretch(1)
        return page

    # --------------------------------------------------------------- Programas
    def _tab_programs(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(16)

        split = QSplitter()
        self.prog_blocked = self._rule_list("Bloqueados", "programs", "blocked")
        self.prog_allowed = self._rule_list("Permitidos (nunca se bloquean)", "programs", "allowed")
        split.addWidget(self.prog_blocked["holder"])
        split.addWidget(self.prog_allowed["holder"])
        v.addWidget(split, 1)

        # La explicacion de IFEO va aca y no arriba: es una nota del control,
        # no un subtitulo de la pagina (que ya dice que elegiste que bloquear).
        self.ifeo_check = QCheckBox("Usar IFEO — el programa ni siquiera llega a arrancar")
        v.addWidget(self.ifeo_check)
        self.ifeo_note = QLabel(
            "Sin IFEO el bloqueo es mas suave: el vigilante de procesos lo remata "
            "si logra colarse. Con IFEO hace falta haber instalado FocusLock como "
            "administrador."
        )
        self.ifeo_note.setWordWrap(True)
        self.ifeo_note.setObjectName("hint")
        v.addWidget(self.ifeo_note)
        return page

    # ------------------------------------------------------------------ Sitios
    def _tab_sites(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(16)

        split = QSplitter()
        self.site_blocked = self._rule_list("Dominios bloqueados", "sites", "blocked")
        self.site_allowed = self._rule_list("Permitidos (exentos)", "sites", "allowed")
        split.addWidget(self.site_blocked["holder"])
        split.addWidget(self.site_allowed["holder"])
        v.addWidget(split, 1)

        # Nota util, no subtitulo: el ejemplo de como escribir el dominio.
        info = QLabel(
            "Se aceptan nombres sueltos: escribir 'youtube.com' alcanza para "
            "www., m., music. y shorts."
        )
        info.setObjectName("hint")
        info.setWordWrap(True)
        self.site_info = info
        v.addWidget(info)
        return page

    def _rule_list(self, title: str, section: str, field: str) -> dict:
        # Tarjeta: el titulo va DENTRO del marco. Afuera quedaba suelto, como
        # un texto flotando sobre una caja que no le pertenece.
        holder = QWidget()
        holder.setObjectName("card")
        lay = QVBoxLayout(holder)
        lay.setContentsMargins(22, 18, 22, 20)
        lay.setSpacing(10)
        lbl = QLabel(title)
        lbl.setObjectName("cardTitle")
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
        row.setSpacing(8)
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
    def _card(self, titulo_texto: str) -> tuple:
        """Tarjeta con su titulo DENTRO. Devuelve (tarjeta, layout del cuerpo).

        El QGroupBox anterior dibujaba el titulo sobre el borde, que se leia
        como una etiqueta suelta arriba de otra caja. Ademas cada pagina
        usaba un contenedor distinto; ahora todas usan el mismo.
        """
        card = QWidget()
        card.setObjectName("card")
        outer = QVBoxLayout(card)
        outer.setContentsMargins(22, 18, 22, 20)
        outer.setSpacing(14)
        t = QLabel(titulo_texto)
        t.setObjectName("cardTitle")
        outer.addWidget(t)
        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)
        outer.addLayout(body)
        return card, body

    def _tab_settings(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(16)

        tt, tt_body = self._card("TickTick")
        tf = QFormLayout()
        tf.setContentsMargins(0, 0, 0, 0)
        tf.setVerticalSpacing(12)
        tt_body.addLayout(tf)
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
        row.setContentsMargins(0, 0, 0, 0)
        # `addRow(layout)` a secas mete la fila en la sola columna de los
        # campos y los botones quedan estrujados contra el borde. Con un
        # widget contenedor que ocupa las dos columnas, cada boton conserva
        # su ancho. (SpanningRole no sirve: PySide6 expone insertRow, no setRow.)
        fila = QWidget()
        fila.setLayout(row)
        fila.setContentsMargins(0, 0, 0, 0)
        tf.addRow(fila)

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

        em_box, em_body = self._card("Emergencia")
        ef = QFormLayout()
        ef.setContentsMargins(0, 0, 0, 0)
        ef.setVerticalSpacing(12)
        em_body.addLayout(ef)
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

        ext, ext_body = self._card("Extensión del navegador")
        xf = QFormLayout()
        xf.setContentsMargins(0, 0, 0, 0)
        xf.setVerticalSpacing(12)
        ext_body.addLayout(xf)
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
        # A la derecha y de ancho natural: estirado a todo el ancho el boton
        # primario de la pagina parece un banner, no una accion.
        fila = QHBoxLayout()
        fila.addStretch(1)
        fila.addWidget(save)
        v.addLayout(fila)
        v.addStretch(1)
        return page

    # --------------------------------------------------------------- Bitácora
    def _tab_history(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(16)

        def bloque(titulo_texto, attr) -> None:
            card = QWidget()
            card.setObjectName("card")
            cv = QVBoxLayout(card)
            cv.setContentsMargins(22, 18, 22, 20)
            cv.setSpacing(10)
            t = QLabel(titulo_texto)
            t.setObjectName("cardTitle")
            cv.addWidget(t)
            area = QPlainTextEdit()
            area.setReadOnly(True)
            cv.addWidget(area, 1)
            setattr(self, attr, area)
            v.addWidget(card, 1)

        bloque("Desbloqueos de emergencia", "hist_em")
        bloque("Intentos de bloqueo de procesos", "hist_blocks")

        refresh = QPushButton("Actualizar bitácora")
        refresh.setObjectName("ghost")
        refresh.clicked.connect(self._load_history)
        fila = QHBoxLayout()
        fila.addStretch(1)
        fila.addWidget(refresh)
        v.addLayout(fila)
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
            self.count.setText(f"{credits} de {required} tareas")
            faltan = max(0, required - credits)
            self.estado_sub.setText(
                "Te faltan "
                + (f"{faltan} tarea" if faltan == 1 else f"{faltan} tareas")
                + " para desbloquear."
            )
        else:
            self.progress.setValue(100)
            self.count.setText("Desbloqueado")
            self.estado_sub.setText(
                "No hay bloqueo activo. Podés usar lo que quieras."
            )

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
            self.banner.setStyleSheet(self._ERROR_STYLE)
            self._aviso(
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

    _ERROR_STYLE = ("background:#2a0f10;border:1px solid #e5484d;"
                    "border-radius:0px;padding:8px 24px;")

    def _aviso(self, texto: str) -> None:
        """Muestra el banner solo si hay algo que avisar."""
        if texto:
            self.banner.setText(texto)
            self.banner.show()
        else:
            self.banner.clear()
            self.banner.hide()

    def _apply_banner(self, locked: bool, offline: str = "") -> None:
        # El estado normal NO va en el banner. Bloqueado o no se lee en el
        # titulo de la pagina, en la barra de progreso y en el boton. Este
        # espacio queda para lo que no se ve en ningun otro lado: que el
        # servicio no responde o que TickTick fallo. Repetir "DESBLOQUEADO"
        # arriba de una pagina que ya lo dice era ruido.
        if offline:
            # Sin servicio no se sabe el estado real: se avisa, no se afirma.
            self.banner.setStyleSheet(self._ERROR_STYLE)
            self._aviso(
                "<b style='color:#e5484d'>SIN SERVICIO</b> — no se puede "
                f"consultar el estado.<br>{offline}<br>"
                "Instalalo con administrador: <code>install.ps1</code>"
            )
            return
        self._aviso("")

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
