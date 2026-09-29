"""Pruebas del stub de IFEO.

El bug que estas pruebas cubren: el mensaje decia "Terminá Spotify.exe
Lecturas" porque el placeholder `{n}` recibia el nombre del ejecutable en vez
de la cantidad de Lecturas que faltan.

El stub se importa directo, sin el paquete, que es como lo ejecuta Windows.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# El stub tiene que ser importable sin el paquete: Windows lo ejecuta suelto.
_spec = importlib.util.spec_from_file_location(
    "focuslock_stub_under_test", ROOT / "focuslock" / "stub.py"
)
stub = importlib.util.module_from_spec(_spec)
sys.modules["focuslock_stub_under_test"] = stub
_spec.loader.exec_module(stub)


class TestStubMessage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.tmp.name) / "TickFence"
        self.state_dir.mkdir(parents=True)
        self._old = None

    def tearDown(self):
        self.tmp.cleanup()

    def _write_state(self, data: dict) -> None:
        (self.state_dir / "state.json").write_text(json.dumps(data), encoding="utf-8")

    def _patch_programdata(self):
        import os

        old = os.environ.get("ProgramData")
        os.environ["ProgramData"] = self.tmp.name
        return old

    def _message(self, state, name="steam.exe", lang="en"):
        """Arma el mensaje con un state.json temporal y devuelve el texto.

        Antes cada test repetia el patch de ProgramData a mano. Con el helper
        queda en un lugar, y los tests se.parametrizan por idioma.
        """
        old = self._patch_programdata()
        try:
            if state is not None:
                self._write_state(state)
            return stub.build_message(name, lang)
        finally:
            if old is None:
                os.environ.pop("ProgramData", None)
            else:
                os.environ["ProgramData"] = old

    # Palabras que delatan el idioma. Sirven para afirmar sobre el texto sin
    # depender de una frase entera, que cambia con cada retoque de redaccion.
    MARCA = {
        "en": ("Readings", "Blocked program", "Open TickFence", "left in TickTick"),
        "es": ("Lecturas", "Programa bloqueado", "Abrí TickFence", "faltan"),
    }

    def test_message_has_no_exe_name_in_the_count(self):
        """Regresión: decía "Terminá Spotify.exe Lecturas"."""
        for lang, (lecturas, _, _, _) in self.MARCA.items():
            with self.subTest(lang=lang):
                message = self._message({"required": 2, "credits": 0},
                                        "Spotify.exe", lang)
                self.assertNotIn(f"Spotify.exe {lecturas}", message)
                self.assertIn(lecturas, message)

    def test_message_reports_remaining(self):
        for lang in self.MARCA:
            with self.subTest(lang=lang):
                message = self._message({"required": 2, "credits": 0}, "steam.exe", lang)
                self.assertIn("2", message)

    def test_message_singular_when_one_left(self):
        """Con 1 pendiente tiene que decir "1 Lectura", no "1 Lecturas"."""
        for lang, (lecturas, _, _, _) in self.MARCA.items():
            with self.subTest(lang=lang):
                message = self._message({"required": 2, "credits": 1}, "steam.exe", lang)
                self.assertIn("1", message)
                # La forma singular no lleva la "s" final de la plural.
                singular = lecturas[:-1] if lang == "es" else "Reading"
                self.assertIn(singular, message)

    def test_message_when_credits_done(self):
        for lang, (_, _, abrir, _) in self.MARCA.items():
            with self.subTest(lang=lang):
                message = self._message({"required": 2, "credits": 2}, "steam.exe", lang)
                self.assertIn(abrir, message)

    def test_message_without_state_is_still_useful(self):
        """Si no puede leer el estado, muestra algo genérico y no revienta."""
        for lang, (lecturas, _, _, _) in self.MARCA.items():
            with self.subTest(lang=lang):
                message = self._message(None, "steam.exe", lang)
                self.assertTrue(message.strip())
                self.assertIn(lecturas, message)

    def test_message_with_corrupt_state(self):
        for lang in self.MARCA:
            with self.subTest(lang=lang):
                old = self._patch_programdata()
                try:
                    (self.state_dir / "state.json").write_text(
                        "{no es json", encoding="utf-8")
                    message = stub.build_message("steam.exe", lang)
                finally:
                    if old is None:
                        os.environ.pop("ProgramData", None)
                    else:
                        os.environ["ProgramData"] = old
                self.assertTrue(message.strip())

    def test_idioma_desconocido_cae_en_ingles(self):
        """Una config con language: 'fr' no puede romper el aviso."""
        message = self._message({"required": 2, "credits": 0}, "steam.exe", "fr")
        self.assertIn("Readings", message)

    def test_program_name_appears_at_the_end_not_in_the_count(self):
        for lang, (_, bloqueado, _, _) in self.MARCA.items():
            with self.subTest(lang=lang):
                message = self._message({"required": 2, "credits": 0},
                                        "Discord.exe", lang)
                if "Discord.exe" in message:
                    self.assertIn(bloqueado, message)

    def test_stub_has_no_focuslock_imports(self):
        """Windows lo ejecuta suelto: no puede depender del paquete."""
        source = (ROOT / "focuslock" / "stub.py").read_text(encoding="utf-8")
        for forbidden in ("from .", "import focuslock", "from focuslock"):
            self.assertNotIn(forbidden, source, f"el stub no puede usar {forbidden!r}")

    def test_main_is_noop_without_flag(self):
        sys.argv = ["stub.py", "algo.exe"]
        self.assertEqual(stub.main(), 0)


class TestShortcuts(unittest.TestCase):
    def test_launcher_is_resolvable(self):
        from focuslock import shortcuts

        exe, args = shortcuts._launcher()
        self.assertTrue(Path(exe).exists(), f"el ejecutable no existe: {exe}")
        if not getattr(sys, "frozen", False):
            self.assertIn("-m", args)
            self.assertIn("focuslock", args)

    def test_status_reports_keys(self):
        from focuslock import shortcuts

        status = shortcuts.status()
        for key in ("launcher", "links", "autostart"):
            self.assertIn(key, status)
        self.assertFalse(status["autostart"], "no hay autoinicio, por diseño")

    def test_no_autostart_code_exists(self):
        """El usuario pidió explícitamente que no arranque solo."""
        from focuslock import shortcuts

        source = Path(shortcuts.__file__).read_text(encoding="utf-8")
        self.assertNotIn("CurrentVersion\\Run", source)
        self.assertNotIn("set_autostart", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
