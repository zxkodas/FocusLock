"""Verifica los archivos de la extensión sin depender de un navegador.

No podemos cargar la extensión en Firefox ni en Chrome desde acá, así que
al menos comprobamos lo que sí es verificable: que el JSON parsea, que el JS
tiene las llaves balanceadas, y que el service worker declara la API que el
popup necesita.

La sintaxis completa de JS requeriría Node, que no está instalado. Este test
detecta el error más común: un llave o paréntesis desbalanceado.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "extension"
BROWSERS = ("chrome", "firefox")

REQUIRED_FILES = ("manifest.json", "sw.js", "options.html", "options.js",
                  "popup.html", "popup.js")


def _balance(path: Path) -> tuple[bool, dict[str, int]]:
    """Balance de llaves, ignorando comentarios, strings y template literals."""
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r'"(?:\\.|[^"\\])*"', '""', text)
    text = re.sub(r"'(?:\\.|[^'\\])*'", "''", text)
    text = re.sub(r"`(?:\\.|[^`\\])*`", "``", text)

    depth = {"{": 0, "(": 0, "[": 0}
    pairs = {"}": "{", ")": "(", "]": "["}
    for ch in text:
        if ch in depth:
            depth[ch] += 1
        elif ch in pairs:
            depth[pairs[ch]] -= 1
    return all(v == 0 for v in depth.values()), depth


class TestExtensionFiles(unittest.TestCase):
    def test_all_files_exist(self):
        for browser in BROWSERS:
            for name in REQUIRED_FILES:
                with self.subTest(browser=browser, file=name):
                    self.assertTrue(
                        (EXT / browser / name).exists(),
                        f"falta extension/{browser}/{name}",
                    )

    def test_manifests_are_valid_json(self):
        for browser in BROWSERS:
            with self.subTest(browser=browser):
                raw = (EXT / browser / "manifest.json").read_text(encoding="utf-8")
                manifest = json.loads(raw)  # revienta si esta mal
                self.assertEqual(manifest["manifest_version"], 3)
                self.assertEqual(manifest["name"], "FocusLock — bloqueo de sitios")

    def test_manifest_has_required_permissions(self):
        needed = {"declarativeNetRequest", "tabs", "storage", "alarms"}
        for browser in BROWSERS:
            with self.subTest(browser=browser):
                manifest = json.loads(
                    (EXT / browser / "manifest.json").read_text(encoding="utf-8")
                )
                perms = set(manifest.get("permissions", []))
                self.assertTrue(
                    needed <= perms, f"faltan permisos: {needed - perms}"
                )

    def test_manifest_can_reach_local_server(self):
        """La extension tiene que poder pegarle a 127.0.0.1."""
        for browser in BROWSERS:
            with self.subTest(browser=browser):
                manifest = json.loads(
                    (EXT / browser / "manifest.json").read_text(encoding="utf-8")
                )
                hosts = manifest.get("host_permissions", [])
                self.assertTrue(
                    any("127.0.0.1" in h for h in hosts),
                    "falta el permiso de host para 127.0.0.1",
                )

    def test_javascript_is_balanced(self):
        for browser in BROWSERS:
            for name in ("sw.js", "popup.js", "options.js"):
                with self.subTest(browser=browser, file=name):
                    ok, depth = _balance(EXT / browser / name)
                    self.assertTrue(
                        ok, f"{browser}/{name} desbalanceado: {depth}"
                    )

    def test_sw_uses_browser_or_chrome_namespace(self):
        """Firefox usa `browser`, Chrome `chrome`. El shim debe estar."""
        for browser in BROWSERS:
            with self.subTest(browser=browser):
                sw = (EXT / browser / "sw.js").read_text(encoding="utf-8")
                self.assertIn("typeof browser", sw)
                self.assertIn("alarms", sw)

    def test_popup_uses_the_shim_not_raw_chrome(self):
        """Un `chrome.` suelto en el popup rompe en Firefox."""
        for browser in BROWSERS:
            with self.subTest(browser=browser):
                popup = (EXT / browser / "popup.js").read_text(encoding="utf-8")
                self.assertNotRegex(
                    popup, r"(?<![\w.])chrome\.",
                    "el popup debe usar el shim `api`, no `chrome` directo",
                )

    def test_sw_handles_the_messages_popup_sends(self):
        """Cada mensaje que el popup manda tiene que tener handler en sw.js."""
        for browser in BROWSERS:
            popup = (EXT / browser / "popup.js").read_text(encoding="utf-8")
            sw = (EXT / browser / "sw.js").read_text(encoding="utf-8")
            sent = set(re.findall(r'type:\s*"([^"]+)"', popup))
            self.assertTrue(sent, "el popup no manda ningun mensaje")
            for msg in sent:
                with self.subTest(browser=browser, msg=msg):
                    self.assertIn(
                        f'"{msg}"', sw, f"sw.js no maneja el mensaje {msg!r}"
                    )

    def test_popup_fetches_directly_not_only_via_worker(self):
        """Regresión: el popup depender del worker se rompía siempre.

        En Firefox la event page se apaga sola, y `sendMessage` devolvía
        undefined: el popup decía "Sin respuesta" con el servicio sano. El
        popup tiene los mismos permisos de host, así que consulta el servidor
        directo y el worker solo queda avisado.
        """
        for browser in BROWSERS:
            with self.subTest(browser=browser):
                popup = (EXT / browser / "popup.js").read_text(encoding="utf-8")
                self.assertIn(
                    "fetch(", popup, "el popup debe hacer fetch al servidor"
                )
                self.assertIn("endpoint", popup)
                # Y el uso del worker no debe ser bloqueante.
                self.assertRegex(
                    popup,
                    r"catch\s*\([^)]*\)\s*\{[^}]*\*/",
                    "el mensaje al worker debe ir envuelto en un catch",
                )

    def test_sw_saves_state_to_storage(self):
        """El worker de Firefox se apaga: el estado tiene que quedar guardado."""
        for browser in BROWSERS:
            with self.subTest(browser=browser):
                sw = (EXT / browser / "sw.js").read_text(encoding="utf-8")
                self.assertIn("lastState", sw)
                self.assertRegex(sw, r"storage\.local\.set")

    def test_popup_reads_storage_first(self):
        """El popup no puede depender de que el worker esté vivo."""
        for browser in BROWSERS:
            with self.subTest(browser=browser):
                popup = (EXT / browser / "popup.js").read_text(encoding="utf-8")
                self.assertIn("lastState", popup)
                self.assertIn("storage.local.get", popup)

    def test_popup_shows_a_version(self):
        """Sin un numero de version no se puede saber si recargo."""
        for browser in BROWSERS:
            with self.subTest(browser=browser):
                popup = (EXT / browser / "popup.js").read_text(encoding="utf-8")
                self.assertRegex(popup, r'VERSION\s*=\s*"')

    def test_shipped_code_matches_development_code(self):
        """sw.js y popup.js se comparten: si divergen, el bug se repite."""
        for name in ("sw.js", "popup.js", "popup.html"):
            with self.subTest(file=name):
                chrome = (EXT / "chrome" / name).read_text(encoding="utf-8")
                firefox = (EXT / "firefox" / name).read_text(encoding="utf-8")
                if name == "popup.html":
                    # El HTML no lleva namespace, debe ser identico
                    self.assertEqual(chrome, firefox)
                else:
                    # Solo puede diferir en el shim de la primera linea
                    self.assertEqual(
                        chrome.splitlines()[2:],
                        firefox.splitlines()[2:],
                        f"{name} diverge entre Chrome y Firefox",
                    )

    def test_firefox_manifest_uses_event_page(self):
        """Firefox MV3 usa background.scripts, no service_worker."""
        manifest = json.loads(
            (EXT / "firefox" / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertIn("scripts", manifest["background"])
        self.assertNotIn("service_worker", manifest["background"])

    def test_chrome_manifest_uses_service_worker(self):
        manifest = json.loads(
            (EXT / "chrome" / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertIn("service_worker", manifest["background"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
