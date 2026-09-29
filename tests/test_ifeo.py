"""Pruebas del valor `Debugger` de IFEO.

El bug que estas pruebas cubren: el stub ya venia entrecomillado y
`set_blocker` lo envolvia otra vez. Windows no podia parsear el valor, el
programa no arrancaba y se veia un error de "parametro no es correcto" en vez
del aviso de TickFence.

Estas pruebas no tocan el registro: verifican la construccion del string.
"""
from __future__ import annotations

import unittest

from focuslock import ifeo
from focuslock.daemon import stub_command


class TestDebuggerValue(unittest.TestCase):
    def test_already_quoted_is_not_requoted(self):
        command = '"C:\\Python\\pythonw.exe" "C:\\app\\stub.py"'
        value = ifeo._debugger_value(command)
        self.assertEqual(value, f"{command} --ifeo-stub")
        # el bug: comillas dobles al principio
        self.assertFalse(value.startswith('""'), f"comillas duplicadas: {value}")

    def test_bare_path_gets_quoted_once(self):
        value = ifeo._debugger_value(r"C:\Python\pythonw.exe")
        self.assertEqual(value, r'"C:\Python\pythonw.exe" --ifeo-stub')
        self.assertFalse(value.startswith('""'))

    def test_always_has_ifeo_stub_flag(self):
        for command in (
            r'"C:\a\pythonw.exe" "C:\b\stub.py"',
            r"C:\a\pythonw.exe",
            "  C:\\a\\pythonw.exe  ",
        ):
            with self.subTest(command=command):
                self.assertTrue(ifeo._debugger_value(command).endswith("--ifeo-stub"))

    def test_empty_is_rejected(self):
        for empty in ("", "   ", None):
            with self.subTest(value=empty):
                with self.assertRaises(ValueError):
                    ifeo._debugger_value(empty)

    def test_quote_count_is_balanced(self):
        """Windows necesita el par de comillas cerrado antes de los args."""
        command = '"C:\\Python\\pythonw.exe" "C:\\app\\stub.py"'
        value = ifeo._debugger_value(command)
        self.assertEqual(value.count('"') % 2, 0, f"comillas desbalanceadas: {value}")
        self.assertEqual(value.count('"'), command.count('"'))

    def test_real_stub_command_is_valid(self):
        """El comando que genera la app tiene que estar bien formado."""
        value = ifeo._debugger_value(stub_command())
        self.assertFalse(value.startswith('""'), f"comillas duplicadas: {value}")
        self.assertEqual(value.count('"') % 2, 0)
        self.assertIn("--ifeo-stub", value)
        self.assertIn("stub.py", value)

    def test_value_contains_focuslock_marker(self):
        """list_blocked() busca 'focuslock' en el valor para reconocerlo."""
        value = ifeo._debugger_value(
            '"C:\\Users\\x\\focuslock\\stub.py.exe"'
        )
        self.assertIn("focuslock", value.lower())


class TestSyncSemantics(unittest.TestCase):
    def test_empty_stub_only_cleans(self):
        """Con stub vacio, sync() no debe escribir nada nuevo.

        Es el modo del comando de emergencia: limpiar sin dejar nada puesto.
        """
        result = ifeo.sync(["spotify.exe"], [], "")
        self.assertEqual(result["applied"], [], "no debe aplicar con stub vacio")
        self.assertIsInstance(result["removed"], list)
        self.assertIsInstance(result["failed"], list)

    def test_never_block_excluded_from_wanted(self):
        """explorer.exe nunca debe entrar en la lista a escribir."""
        from focuslock.rules import NEVER_BLOCK, norm_program

        want = {norm_program(p) for p in ["explorer.exe", "steam.exe"]}
        want -= {norm_program(p) for p in NEVER_BLOCK}
        self.assertNotIn("explorer.exe", want)
        self.assertIn("steam.exe", want)


class TestNormalizeInIfeo(unittest.TestCase):
    def test_exe_names_normalized(self):
        from focuslock.rules import norm_program

        self.assertEqual(norm_program("Spotify.EXE"), "spotify.exe")
        self.assertEqual(norm_program(r"C:\x\Spotify.exe"), "spotify.exe")
        self.assertEqual(norm_program("spotify"), "spotify.exe")


if __name__ == "__main__":
    unittest.main(verbosity=2)
