"""Diálogo de compromiso escrito: la única puerta de salida sin completar tareas.

Reglas duras (no negociables desde la UI):
  - hay que escribir de verdad (se cuentan pulsaciones, se detecta el pegado)
  - el tiempo se mide entre la primera y la última pulsación
  - cerrar y reabrir el diálogo NO reinicia el cronómetro
  - cada intento queda registrado en el servicio
"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .. import emergency as em

# Sesión persistente: sobrevive al cierre del diálogo.
_SESSION: dict = {"first": None, "last": None, "keys": 0, "times": [], "draft": "", "prompts": {}}
# Una pausa de más de esto se considera "se fue a hacer otra cosa", no pensar.
_BREAK_GAP = 900.0


class Tracker:
    def __init__(self) -> None:
        self.count = 0
        self.first: float | None = None
        self.last: float | None = None
        self.times: list[float] = []
        self.longest_idle = 0.0

    def key(self) -> None:
        now = time.time()
        if _SESSION["first"] is None:
            _SESSION["first"] = now
        if self.last is not None:
            gap = now - self.last
            if gap < _BREAK_GAP and gap > self.longest_idle:
                self.longest_idle = gap
        self.last = now
        self.count += 1
        self.times.append(now)

    def typing_seconds(self, now: float | None = None) -> float:
        first = _SESSION.get("first")
        last = self.last
        if first is None or last is None:
            return 0.0
        return max(0.0, (last or first) - first)


class TrackedEdit(QTextEdit):
    """QTextEdit que delega cada pulsación al tracker compartido."""

    def __init__(self, tracker: Tracker, placeholder: str = "") -> None:
        super().__init__()
        self._tracker = tracker
        self.setPlaceholderText(placeholder)
        self.setAcceptRichText(False)
        self.textChanged.connect(self._sync)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        super().keyPressEvent(event)
        self._tracker.key()

    def _sync(self) -> None:
        if self.objectName() == "commitment":
            _SESSION["draft"] = self.toPlainText()


class EmergencyDialog(QDialog):
    granted = None

    def __init__(self, config: dict, client, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Desbloqueo de emergencia")
        self.setModal(True)
        self.resize(760, 720)

        self._config = config
        self._client = client
        self._tracker = Tracker()
        self.min_words, self.min_minutes = em.requirements(config)
        self.unlock_minutes = int(config.get("emergency", {}).get("unlock_minutes", 20))
        self.granted = None
        self._busy = False

        self._build()
        self._restore()
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._refresh)
        self._tick.start(1000)
        self._refresh()

    # -- construcción ------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)

        warn = QLabel(
            f"Atent@: esto es una salida de emergencia, no un atajo. "
            f"Desbloquea {self.unlock_minutes} minutos y queda registrado con fecha y texto. "
            f"Releelo la próxima vez."
        )
        warn.setWordWrap(True)
        warn.setObjectName("warn")
        outer.addWidget(warn)

        req = QGroupBox("Requisitos")
        form = QFormLayout(req)
        self.lbl_words = QLabel()
        self.lbl_time = QLabel()
        self.lbl_keys = QLabel()
        form.addRow("Palabras", self.lbl_words)
        form.addRow("Tiempo de escritura", self.lbl_time)
        form.addRow("Pulsaciones", self.lbl_keys)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        form.addRow(self.progress)
        outer.addWidget(req)

        area = QScrollArea()
        area.setWidgetResizable(True)
        holder = QWidget()
        box = QVBoxLayout(holder)

        self.edits: dict[str, TrackedEdit] = {}

        commit_box = QGroupBox("1. ¿Por qué necesitás desbloquear ahora?")
        cform = QVBoxLayout(commit_box)
        self.commit = TrackedEdit(self._tracker, f"Mínimo {self.min_words} palabras.")
        self.commit.setObjectName("commitment")
        self.commit.setMinimumHeight(220)
        cform.addWidget(self.commit)
        box.addWidget(commit_box)

        for i, (key, hint) in enumerate(em.PROMPTS, start=2):
            label = em.PROMPT_LABELS.get(key, key)
            group = QGroupBox(f"{i}. {label}")
            gform = QVBoxLayout(group)
            lbl = QLabel(hint)
            lbl.setWordWrap(True)
            lbl.setObjectName("hint")
            gform.addWidget(lbl)
            edit = TrackedEdit(self._tracker, f"Mínimo {em.MIN_PROMPT_WORDS} palabras.")
            edit.setObjectName(key)
            edit.setMinimumHeight(90)
            gform.addWidget(edit)
            self.edits[key] = edit
            box.addWidget(group)

        self.summary = QLineEdit()
        self.summary.setPlaceholderText("Resumen en una línea (queda en la bitácora)")
        box.addWidget(QLabel("Resumen"))
        box.addWidget(self.summary)

        area.setWidget(holder)
        outer.addWidget(area, 1)

        self.msg = QLabel()
        self.msg.setWordWrap(True)
        outer.addWidget(self.msg)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.btn_cancel = QPushButton("Seguir studying")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_submit = QPushButton("Verificar y desbloquear")
        self.btn_submit.clicked.connect(self._submit)
        buttons.addWidget(self.btn_cancel)
        buttons.addWidget(self.btn_submit)
        outer.addLayout(buttons)

    def _restore(self) -> None:
        self.commit.setPlainText(_SESSION.get("draft", ""))
        for title, text in (_SESSION.get("prompts") or {}).items():
            if title in self.edits:
                self.edits[title].setPlainText(text)

    # -- estado en vivo ----------------------------------------------------
    def _refresh(self) -> None:
        words = em.count_words(self.commit.toPlainText())
        seconds = self._tracker.typing_seconds()
        self.lbl_words.setText(f"{words} / {self.min_words}")
        self.lbl_time.setText(f"{int(seconds // 60)}:{int(seconds % 60):02d} / {self.min_minutes}:00")
        self.lbl_keys.setText(str(self._tracker.count))

        progress = (
            min(1.0, words / self.min_words) * 0.4
            + min(1.0, seconds / (self.min_minutes * 60)) * 0.5
            + min(1.0, em.count_words(self.commit.toPlainText()) / max(1, self.min_words)) * 0.1
        )
        self.progress.setValue(int(progress * 100))

        prompts_ok = all(
            em.count_words(self.edits[t].toPlainText()) >= em.MIN_PROMPT_WORDS for t in self.edits
        )
        ready = words >= self.min_words and seconds >= self.min_minutes * 60 and prompts_ok
        self.btn_submit.setEnabled(ready and not self._busy)
        if not self._busy:
            if words < self.min_words:
                self.msg.setText(f"Faltan {self.min_words - words} palabras.")
            elif seconds < self.min_minutes * 60:
                self.msg.setText("Seguí escribiendo hasta completar el tiempo.")
            elif not prompts_ok:
                self.msg.setText("Completá las tres preguntas.")
            else:
                self.msg.setText("Podés verificar. El servicio va a confirmar.")

    # -- envío -------------------------------------------------------------
    def _collect(self) -> dict:
        _SESSION["prompts"] = {t: e.toPlainText() for t, e in self.edits.items()}
        _SESSION["draft"] = self.commit.toPlainText()
        return {
            "text": _SESSION["draft"],
            "prompts": _SESSION["prompts"],
            "keystrokes": self._tracker.count,
            "elapsed": self._tracker.typing_seconds(),
            "longest_idle": self._tracker.longest_idle,
            "started_at": _SESSION.get("first") or time.time(),
        }

    def _submit(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.btn_submit.setEnabled(False)
        self.msg.setText("Verificando…")
        try:
            result = self._client.call("emergency", **self._collect())
        except Exception as exc:  # noqa: BLE001
            self._busy = False
            self.msg.setText(f"No se pudo contactar al servicio: {exc}")
            self._refresh()
            return

        if result.get("granted"):
            _SESSION.update({"first": None, "last": None, "keys": 0, "times": [],
                             "draft": "", "prompts": {}})
            self.granted = result
            self.accept()
            return

        self._busy = False
        errores = result.get("errors", ["Error desconocido"])
        self.msg.setText("Todavía no:\n" + "\n".join(f"• {e}" for e in errores))
        self.msg.setObjectName("err")
        self._refresh()
