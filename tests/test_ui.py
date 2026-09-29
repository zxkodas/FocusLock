"""Pruebas de la interfaz, con Qt en modo offscreen.

Instancian la ventana y el tray de verdad, contra un servicio simulado. Asi los
errores de API de PySide6 (metodos que no existen, firmas distintas) aparecen en
los tests y no cuando el usuario escribe `python -m focuslock gui`.
"""
from __future__ import annotations

import ast
import contextlib
import inspect
import os
import sys
import textwrap
import time
import unittest
from pathlib import Path

# Modo headless: sin display, Qt usa el plugin offscreen.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from focuslock.ipc import IpcError  # noqa: E402


class FakeClient:
    """Doble de IpcClient con la superficie que la UI consume."""

    def __init__(self, available: bool = True) -> None:
        self.available = available
        # Arranca desbloqueado, que es el estado por defecto real.
        self.locked = False
        self.calls: list[tuple[str, dict]] = []
        self.config = {
            "ticktick": {
                "project_name": "Estudios",
                "project_id": "",
                "task_prefix": "Lectura",
                "required": 2,
                "poll_seconds": 45,
            },
            "programs": {
                "blocked": ["steam.exe", "discord.exe"],
                "allowed": ["opencode.exe", "focuslock.exe"],
                "use_ifeo": True,
            },
            "sites": {
                "blocked": ["youtube.com", "reddit.com"],
                "allowed": ["upt.edu.ar"],
            },
            "emergency": {"min_words": 300, "min_minutes": 5, "unlock_minutes": 20},
            "general": {"start_locked": True},
        }

    def call(self, command: str, **payload):
        self.calls.append((command, payload))
        if not self.available:
            raise IpcError("No se pudo contactar al servicio.")
        if command == "status":
            return {
                "locked": self.locked,
                "enforcement": True,
                "checked_at": time.time(),
                "credits": 1,
                "required": 2,
                "remaining": 1,
                "reason": "",
                "modules": {"Analisis Matematico": 19, "Produccion": 16},
                "pending": [
                    {"id": "a", "title": "Lectura 1", "module": "Analisis Matematico"},
                    {"id": "b", "title": "Lectura 2", "module": "Produccion"},
                ],
                "error": "",
                "ticktick_ok": True,
                "port": 41234,
                "token": "tok_secreto",
                "ifeo": ["steam.exe"],
                "guard": {"scans": 10, "kills": 2, "running": True},
                "guard_armed": True,
                "state": {},
            }
        if command == "poll":
            return {
                "locked": self.locked,
                "enforcement": True,
                "checked_at": time.time(),
                "credits": 2 if self.locked else 0,
                "required": 2,
                "remaining": 0,
                "reason": "TickTick: 2 Lecturas completadas",
                "modules": {},
                "pending": [],
                "error": "",
            }
        if command == "config_get":
            return {"config": self.config}
        if command == "history":
            return {
                "emergencies": [
                    {
                        "at": 1700000000,
                        "words": 320,
                        "seconds": 330,
                        "commitment": "texto del compromiso " * 20,
                    }
                ],
                "blocks": [{"at": 1700000000, "process": "steam.exe", "pid": 1234, "method": "watchdog"}],
            }
        if command.endswith("_add"):
            section, field, _ = command.rsplit("_", 2)
            value = payload.get("value", "")
            if command == "programs_blocked_add" and value.lower() == "explorer.exe":
                return {"ok": False, "immutable": True, "message": "proceso protegido"}
            if command == "programs_blocked_add" and value.lower() == "cmd.exe":
                return {"ok": False, "needs_confirm": True, "message": "critico"}
            self.config[section][field] = [*self.config[section][field], value]
            return {"ok": True, "list": self.config[section][field]}
        if command.endswith("_del"):
            section, field, _ = command.rsplit("_", 2)
            value = payload.get("value", "")
            self.config[section][field] = [
                v for v in self.config[section][field] if v != value
            ]
            return {"ok": True, "list": self.config[section][field]}
        if command == "config_set":
            self.config[payload["section"]].update(payload.get("values", {}))
            return {"ok": True}
        if command == "ticktick_set_token":
            return {"ok": True, "projects": 4, "names": ["Estudios"]}
        if command == "emergency":
            # El servicio devuelve los errores YA traducidos (el lo sabe: lee
            # el idioma de la config antes de validar) y la UI los muestra tal
            # cual. Por eso aca van en español aunque la ventana este en
            # inglés: lo que se verifica aca es que lleguen, no que se traduzcan.
            return {
                "granted": False,
                "errors": [
                    "Te faltan 200 palabras (escribiste 100 de 300).",
                    "El texto parece pegado desde el portapapeles.",
                ],
                "words": 100,
            }
        if command == "lock":
            self.locked = True
            return {"ok": True, "locked": True, "message": "Bloqueo activado."}
        if command == "unlock":
            self.locked = False
            return {"ok": True, "locked": False, "message": "Bloqueo desactivado."}
        if command in ("relock", "ifeo_sync"):
            return {"ok": True, "locked": True}
        return {"ok": True}


class QtTestCase(unittest.TestCase):
    app = None

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])


class TestMainWindow(QtTestCase):
    def setUp(self):
        from focuslock.ui.app import MainWindow

        self.client = FakeClient()
        self.window = MainWindow(self.client)
        self.window.resize(900, 700)
        self.window.show()

    def tearDown(self):
        self.window.nav.setCurrentRow(0)
        self.window._timer.stop()
        self.window.close()
        self.window.deleteLater()

    def test_window_builds(self):
        self.assertIsNotNone(self.window.nav)
        self.assertIsNotNone(self.window.stack)
        self.assertEqual(self.window.nav.count(), 5)
        self.assertEqual(self.window.stack.count(), 5)
        titles = [
            self.window.nav.item(i).text()
            for i in range(self.window.nav.count())
        ]
        self.assertEqual(
            titles, ["Estado", "Programas", "Sitios", "Ajustes", "Bitácora"]
        )

    def test_nav_and_stack_stay_in_sync(self):
        """Cada fila del menu tiene que mostrar su pagina."""
        for fila in range(self.window.stack.count()):
            with self.subTest(fila=fila):
                self.window.nav.setCurrentRow(fila)
                self.assertEqual(self.window.stack.currentIndex(), fila)

    def test_nav_ignores_out_of_range(self):
        """Una fila imposible no debe romper la app."""
        self.window.nav.setCurrentRow(99)
        self.window.nav.setCurrentRow(-1)
        self.assertLess(
            self.window.stack.currentIndex(), self.window.stack.count()
        )

    def test_the_tab_bar_is_gone_for_good(self):
        """QTabWidget no debe volver: el diseno aprobado es menu lateral."""
        import inspect

        from focuslock.ui import app as app_mod

        source = inspect.getsource(app_mod)
        self.assertNotIn("QTabWidget", source)
        self.assertNotIn("QTabBar", source)

    def test_refresh_renders_locked_state(self):
        self.client.locked = True
        self.window.refresh()
        # El estado ya no vive en el banner: vive en el titulo de la pagina y
        # en la barra. El banner quedo solo para lo que no se ve en otro lado.
        self.assertIn("1", self.window.count.text())
        self.assertIn("Analisis Matematico", self.window.modules.text())
        self.assertFalse(
            self.window.banner.isVisibleTo(self.window),
            "sin servicio caido ni error de TickTick el banner no se muestra",
        )

    def test_the_banner_appears_only_when_something_is_wrong(self):
        """El estado normal no ocupa una franja entera arriba de todo.

        El banner arranca oculto y solo aparece con el servicio caido o con
        un error de TickTick. Antes decia DESBLOQUEADO siempre, sobre una
        pagina que ya lo decia, y se llevaba ~64px de altura para eso.
        """
        self.client.locked = False
        self.window.refresh()
        self.assertFalse(self.window.banner.isVisibleTo(self.window))

        self.window.client = FakeClient(available=False)
        self.window.refresh()
        self.assertTrue(
            self.window.banner.isVisibleTo(self.window),
            "sin servicio el banner tiene que avisar",
        )
        self.assertIn("SIN SERVICIO", self.window.banner.text())

    def test_task_lists_are_gone(self):
        """Las listas de pendientes/completadas se eliminaron a pedido."""
        self.assertFalse(hasattr(self.window, "pending"))
        self.assertFalse(hasattr(self.window, "done"))

    def test_emergency_disabled_when_unlocked(self):
        self.client.locked = False
        self.window.refresh()
        self.assertFalse(
            self.window.btn_emergency.isEnabled(),
            "la emergencia debe estar gris si no hay bloqueo activo",
        )

    def test_emergency_enabled_when_locked(self):
        self.client.locked = True
        self.window.refresh()
        self.assertTrue(
            self.window.btn_emergency.isEnabled(),
            "con el bloqueo activo la emergencia tiene que estar disponible",
        )

    def test_refresh_renders_unlocked_state(self):
        self.client.locked = False
        self.window.refresh(force=True)
        # Desbloqueado se lee en la barra y en el subtitulo, no en el banner.
        self.assertIn("Desbloqueado", self.window.count.text())
        self.assertIn("No hay bloqueo", self.window.estado_sub.text())

    def test_progress_reflects_credits(self):
        self.client.locked = True
        self.window.refresh()
        # El numero va en la etiqueta, no encima de la barra: encima compite
        # con el color y en el renderApproved quedaba ilegible.
        self.assertIn("1", self.window.count.text())
        self.assertEqual(self.window.progress.value(), 50)
        self.assertEqual(
            self.window.progress.format(), "",
            "la barra no debe llevar el contador dentro",
        )

    def test_the_status_subtitle_says_what_is_missing(self):
        """El numero solo no dice si falta mucho o poco."""
        self.client.locked = True
        self.window.refresh()
        self.assertIn("falta", self.window.estado_sub.text().lower())

    def test_the_shortcuts_exist(self):
        """Ctrl+L y Ctrl+E, como dice la tarjeta de atajos."""
        from PySide6.QtGui import QShortcut

        atajos = {s.key().toString() for s in self.window.findChildren(QShortcut)}
        self.assertIn("Ctrl+L", atajos)
        self.assertIn("Ctrl+E", atajos)

    def test_default_state_is_unlocked(self):
        """Abrir la app no debe activar el bloqueo."""
        self.client.locked = False
        self.window.refresh()
        self.assertEqual(self.window.btn_toggle.text(), "Activar bloqueo")
        self.assertFalse(self.window.btn_emergency.isEnabled())

    def test_offline_does_not_claim_blocked_state(self):
        """Sin servicio no sabemos si esta bloqueado: no hay que afirmarlo."""
        self.window.client = FakeClient(available=False)
        self.window.refresh()
        text = self.window.banner.text()
        self.assertIn("SIN SERVICIO", text)
        self.assertNotIn("BLOQUEADO<", text)
        self.assertNotIn("completá las Lecturas", text)

    def test_fill_rules_populates_lists(self):
        self.window._fill_rules()
        self.assertEqual(self.window.prog_blocked["list"].count(), 2)
        self.assertEqual(self.window.prog_allowed["list"].count(), 2)
        self.assertEqual(self.window.site_blocked["list"].count(), 2)
        self.assertEqual(self.window.site_allowed["list"].count(), 1)
        self.assertTrue(self.window.ifeo_check.isChecked())

    def test_settings_fields_load_config(self):
        self.window._fill_rules()
        self.assertEqual(self.window.project_name.text(), "Estudios")
        self.assertEqual(self.window.required.value(), 2)
        self.assertEqual(self.window.em_words.value(), 300)
        self.assertEqual(self.window.em_minutes.value(), 5)
        self.assertEqual(self.window.em_unlock.value(), 20)

    def test_endpoint_field_is_filled_from_status(self):
        self.window.refresh()
        text = self.window.ext_url.text()
        self.assertTrue(text.startswith("http://127.0.0.1:41234/state?token="))
        self.assertIn("tok_secreto", text)

    def test_history_loads(self):
        self.window._load_history()
        self.assertIn("320 palabras", self.window.hist_em.toPlainText())
        self.assertIn("steam.exe", self.window.hist_blocks.toPlainText())

    def test_save_settings_sends_expected_payload(self):
        self.window._fill_rules()
        self.window.required.setValue(3)
        self.window.em_words.setValue(400)
        with self.patch_message_box():
            self.window._save_settings()
        sent = [c for c, p in self.client.calls if c == "config_set"]
        self.assertTrue(sent)
        values = [p["values"] for c, p in self.client.calls if c == "config_set"]
        self.assertTrue(any(v.get("required") == 3 for v in values))
        self.assertTrue(any(v.get("min_words") == 400 for v in values))

    def test_immutable_program_is_refused(self):
        """Un proceso protegido no debe llegar a la lista."""
        self.window.prog_blocked["entry"].setText("explorer.exe")
        with self.patch_message_box():
            self.window._rule_add("programs", "blocked", self.window.prog_blocked["list"],
                                  self.window.prog_blocked["entry"], False)
        self.assertNotIn("explorer.exe", self.client.config["programs"]["blocked"])

    def test_dangerous_program_asks_confirmation(self):
        self.window.prog_blocked["entry"].setText("cmd.exe")
        with self.patch_message_box(answer="No"):
            self.window._rule_add("programs", "blocked", self.window.prog_blocked["list"],
                                  self.window.prog_blocked["entry"], False)
        self.assertNotIn("cmd.exe", self.client.config["programs"]["blocked"])

    def test_toggle_lock_calls_the_right_command(self):
        """Desbloqueado -> 'lock'."""
        self.client.locked = False
        self.window.refresh()
        self.client.calls.clear()
        with self.patch_message_box():
            self.window._toggle_lock()
        commands = [c for c, _ in self.client.calls]
        self.assertIn("lock", commands, f"esperaba 'lock', hubo {commands}")

    def test_toggle_lock_when_blocked_does_not_unlock(self):
        """Ya bloqueado, el boton no debe mandar 'unlock'.

        El usuario pidió que no haya forma de desactivar el bloqueo desde la
        UI: la unica salida son las Lecturas o la emergencia.
        """
        self.client.locked = True
        self.window.refresh()
        self.client.calls.clear()
        with self.patch_message_box():
            self.window._toggle_lock()
        commands = [c for c, _ in self.client.calls]
        self.assertNotIn("unlock", commands, "no debe haber via para desactivar")
        self.assertNotIn("lock", commands, "ya estaba bloqueado")

    @staticmethod
    def _mainwindow_ast():
        """AST de la clase MainWindow, parseable.

        `inspect.getsource` de una clase no se puede parsear directo: arranca
        con la linea `class MainWindow(...)` sin cuerpo. Hay que deduplicar
        la sangria y envolverla.
        """
        from focuslock.ui import app

        source = textwrap.dedent(inspect.getsource(app.MainWindow))
        return ast.parse(source)

    def test_no_unlock_button_in_ui(self):
        """No debe quedar ningun boton que desactive el bloqueo.

        El usuario lo pidió explicitamente: si activa el bloqueo es porque
        quiere concentrarse. La unica salida son las Lecturas o la emergencia.
        """
        tree = self._mainwindow_ast()

        called: set[str] = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "call"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                called.add(node.args[0].value)

        self.assertNotIn(
            "unlock", called, f"la UI no debe llamar a 'unlock'; llama a {sorted(called)}"
        )
        self.assertIn("lock", called, "debe poder activar el bloqueo")

    def test_no_duplicate_methods(self):
        """Un metodo definido dos veces: el segundo pisa al primero en silencio."""
        tree = self._mainwindow_ast()
        names = [
            n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
        ]
        duplicates = {n for n in names if names.count(n) > 1}
        self.assertEqual(duplicates, set(), f"metodos duplicados: {duplicates}")

    def test_toggle_respects_declining(self):
        """Si el usuario dice que no, no se manda nada."""
        self.client.locked = False
        self.window.refresh()
        self.client.calls.clear()
        with self.patch_message_box(answer="No"):
            self.window._toggle_lock()
        commands = [c for c, _ in self.client.calls]
        self.assertNotIn("lock", commands, "no debe bloquear si el usuario dice no")

    def test_button_label_reflects_state(self):
        self.client.locked = False
        self.window.refresh()
        self.assertEqual(self.window.btn_toggle.text(), "Activar bloqueo")
        self.assertTrue(self.window.btn_toggle.isEnabled())
        self.client.locked = True
        self.window.refresh()
        self.assertEqual(self.window.btn_toggle.text(), "Bloqueo activo")
        self.assertFalse(
            self.window.btn_toggle.isEnabled(),
            "con el bloqueo activo el boton no debe poder usarse",
        )

    def test_close_hides_instead_of_exiting(self):
        """Cerrar la ventana la esconde: el tray sigue vivo."""
        self.window.close()
        self.assertFalse(self.window.isVisible())

    def patch_message_box(self, answer="Yes"):
        from unittest import mock

        from PySide6.QtWidgets import QMessageBox

        # question devuelve un StandardButton, no un string.
        buttons = {
            "Yes": QMessageBox.Yes,
            "No": QMessageBox.No,
            "Ok": QMessageBox.Ok,
        }
        reply = buttons.get(answer, QMessageBox.Yes)

        stack = contextlib.ExitStack()
        for name in ("information", "warning", "critical"):
            stack.enter_context(
                mock.patch.object(QMessageBox, name, return_value=answer)
            )
        # question tiene que respetar la respuesta: si no, el test de
        # "el usuario dice que no" no probaria nada.
        stack.enter_context(
            mock.patch.object(QMessageBox, "question", return_value=reply)
        )
        self.addCleanup(stack.close)
        return stack


class TestEmergencyDialog(QtTestCase):
    def setUp(self):
        from focuslock.ui.emergency import EmergencyDialog

        self.config = {
            "emergency": {"min_words": 300, "min_minutes": 5, "unlock_minutes": 20}
        }
        self.client = FakeClient()
        self.dialog = EmergencyDialog(self.config, self.client)
        self.dialog.show()

    def tearDown(self):
        self.dialog.close()
        self.dialog.deleteLater()

    def test_dialog_builds_with_prompts(self):
        from focuslock import emergency as em

        self.assertEqual(len(self.dialog.edits), len(em.PROMPTS))
        for key in ("motivo", "costo", "plan"):
            self.assertIn(key, self.dialog.edits)

    def test_submit_disabled_until_requirements_met(self):
        self.assertFalse(self.dialog.btn_submit.isEnabled())

    def test_typing_enables_button_when_satisfied(self):
        text = "palabra " * 330
        self.dialog.commit.setPlainText(text)
        for key in self.dialog.edits:
            self.dialog.edits[key].setPlainText("respuesta " * 35)
        # Simulamos 5 minutos de escritura real ya cumplidos.
        self.dialog._tracker.count = len(text)
        self.dialog._tracker.last = time.time()
        self._session_first(time.time() - 330)
        self.dialog._refresh()
        self.assertTrue(
            self.dialog.btn_submit.isEnabled(),
            "con los requisitos cubiertos el boton deberia habilitarse",
        )

    def test_short_text_keeps_button_disabled(self):
        self.dialog.commit.setPlainText("corto")
        self.dialog._refresh()
        self.assertFalse(self.dialog.btn_submit.isEnabled())

    def test_rejected_submission_shows_the_service_errors(self):
        """El veredicto del servicio tiene que LLEGAR a la etiqueta.

        Antes este test afirmaba 'palabras', y pasaba: _submit() escribia los
        errores del servicio y enseguida _refresh() los pisaba con 'faltan N
        palabras'. Dos textos con la misma palabra, y el test creia estar
        verificando el veredicto cuando verificaba el mensaje generico.
        """
        self.dialog.commit.setPlainText("muy corto")
        with self.patch_box():
            self.dialog._submit()
        texto = self.dialog.msg.text()
        self.assertIn("200", texto, "no llega la cantidad que falta")
        self.assertIn("escribiste", texto, "no llega el detalle del error")
        self.assertIn("portapapeles", texto, "no llega el aviso de texto pegado")
        self.assertEqual("err", self.dialog.msg.objectName())

    def test_escribir_de_nuevo_limpia_el_veredicto(self):
        """El error no puede quedar pegado mientras el usuario corrige."""
        self.dialog.commit.setPlainText("muy corto")
        with self.patch_box():
            self.dialog._submit()
        self.assertEqual("err", self.dialog.msg.objectName())

        self.dialog.commit.setPlainText("otra cosa distinta")
        self.dialog._refresh()
        self.assertEqual("", self.dialog.msg.objectName())
        self.assertNotIn("escribiste", self.dialog.msg.text())

    @staticmethod
    def _session_first(value: float) -> None:
        from focuslock.ui import emergency as module

        module._SESSION["first"] = value

    def patch_box(self):
        from unittest import mock

        from PySide6.QtWidgets import QMessageBox

        # ExitStack: start() y stop() por separado dejan el parche a medias si
        # algo lanza en el medio, y el siguiente test falla con "already started".
        stack = contextlib.ExitStack()
        for name in ("information", "warning", "critical"):
            stack.enter_context(
                mock.patch.object(QMessageBox, name, return_value="ok")
            )
        self.addCleanup(stack.close)
        return stack


class TestTrayApp(QtTestCase):
    def test_tray_app_constructs(self):
        """Regresion: QApplication no tiene createMenu()."""
        from focuslock.ui.app import TrayApp

        app = TrayApp()
        try:
            self.assertIsNotNone(app.tray)
            self.assertIsNotNone(app.window)
            self.assertIsNotNone(app.tray.contextMenu())
        finally:
            app.tray.hide()
            app.qt.quit()


class TestStyleContrast(unittest.TestCase):
    """El contraste de la hoja de estilo, medido. No estimado a ojo.

    Los valores salieron de calcularlos, no de elegirlos. Este test existe
    para que un cambio de color "que se ve bien" no rompa la accesibilidad
    en silencio: dos de estos ratios estaban por debajo del minimo.
    """

    # (nombre, primer plano, fondo, minimo WCAG AA)
    CASES = (
        ("texto normal sobre fondo", "#eceef1", "#1c1d20", 4.5),
        ("texto normal sobre superficie", "#eceef1", "#242629", 4.5),
        ("texto secundario sobre fondo", "#9ea3ab", "#1c1d20", 4.5),
        ("texto secundario sobre superficie", "#9ea3ab", "#242629", 4.5),
        ("texto secundario sobre sidebar", "#9ea3ab", "#161719", 4.5),
        ("texto sobre sidebar", "#eceef1", "#161719", 4.5),
        ("blanco sobre acento", "#ffffff", "#2f6fe0", 4.5),
        ("blanco sobre hover del acento", "#ffffff", "#2560d8", 4.5),
        ("blanco sobre peligro", "#ffffff", "#b8503a", 4.5),
        ("borde sobre superficie", "#6e737d", "#242629", 3.0),
        ("borde sobre fondo", "#6e737d", "#1c1d20", 3.0),
    )

    @staticmethod
    def _luminance(hex_color: str) -> float:
        h = hex_color.lstrip("#")
        channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        channels = [
            c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
            for c in channels
        ]
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    @classmethod
    def _ratio(cls, fg: str, bg: str) -> float:
        a, b = cls._luminance(fg), cls._luminance(bg)
        hi, lo = max(a, b), min(a, b)
        return (hi + 0.05) / (lo + 0.05)

    def test_every_pair_meets_its_minimum(self):
        for name, fg, bg, minimum in self.CASES:
            with self.subTest(par=name):
                value = self._ratio(fg, bg)
                self.assertGreaterEqual(
                    value, minimum,
                    f"{name}: {value:.2f}:1 con {fg} sobre {bg}, "
                    f"por debajo del minimo {minimum}:1",
                )

    def test_hover_does_not_reduce_contrast(self):
        """Pasar el mouse no puede empeorar la legibilidad.

        El hover solia aclarar el azul (#3b7bf5) y el texto blanco caia a
        3.93:1. Oscurecer es lo correcto.
        """
        resting = self._ratio("#ffffff", "#2f6fe0")
        hover = self._ratio("#ffffff", "#2560d8")
        self.assertGreater(hover, resting)

    def test_the_measured_colors_are_in_the_stylesheet(self):
        """Si cambia la hoja, este test hay que actualizarlo, y se nota."""
        from focuslock.ui.app import STYLE

        sheet = STYLE.lower()
        for _, fg, _bg, _minimum in self.CASES:
            if fg == "#ffffff":
                continue  # el blanco viene de `color:#ffffff`, no de un hex
            with self.subTest(color=fg):
                self.assertIn(fg, sheet)


class TestIcon(unittest.TestCase):
    def test_icon_renders_both_states(self):
        from focuslock.ui.app import make_icon

        locked = make_icon()
        unlocked = make_icon(unlocked=True)
        self.assertFalse(locked.isNull())
        self.assertFalse(unlocked.isNull())
        self.assertFalse(locked.pixmap(64, 64).isNull())


if __name__ == "__main__":
    unittest.main(verbosity=2)
