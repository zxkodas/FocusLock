"""Verifica que la traduccion no se desincronice.

El riesgo real de meter dos idiomas no es traducir mal: es olvidar una cadena
nueva. Se escribe en ingles, funciona, y queda en ingles para siempre sin que
nadie se entere hasta que un usuario lo reporta.

Estos tests vuelven eso visible:

- toda cadena que pasa por tr() tiene su entrada en la tabla ES
- no hay entradas en la tabla que ya use nadie
- el stub, que NO puede importar i18n, tiene sus textos en los dos idiomas
- cambiar el idioma no rompe la ventana (lo cubre test_ui tambien)
"""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from focuslock import i18n

ROOT = Path(__file__).resolve().parents[1]

# Archivos quetranslated UI. El stub va aparte: no puede importar i18n.
ARCHIVOS_TRADUCIBLES = (
    "focuslock/ui/app.py",
    "focuslock/ui/emergency.py",
    "focuslock/emergency.py",
    "focuslock/daemon.py",
    "focuslock/gate.py",
    "focuslock/__main__.py",
)
STUB = "focuslock/stub.py"


def _literales_tr() -> set[str]:
    """Todas las cadenas que se le pasan a tr(), en los archivos marcados.

    Se busca en el codigo, no en los docstrings: los comentarios explica por
    que algo se traduce, y no son cadenas que haya que traducir.
    """
    usadas: set[str] = set()
    for rel in ARCHIVOS_TRADUCIBLES:
        arbol = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call):
                continue
            f = nodo.func
            nombre = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if nombre != "tr":
                continue
            for a in nodo.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    usadas.add(a.value)

    # Las tres preguntas del dialogo viven en tablas (focuslock.emergency) y
    # llegan por tr(hint), o sea con una variable: el escaneo del AST no las
    # ve. Son texto de UI aunque esten en el modulo de logica.
    from focuslock import emergency as em

    usadas.update(hint for _, hint in em.PROMPTS)
    usadas.update(em.PROMPT_LABELS.values())

    # Lo mismo con las etiquetas y los subtitulos del menu: se indexan por ID
    # y se pasan por tr(self.ETIQUETAS[etiqueta]), nunca como literal.
    from focuslock.ui.app import MainWindow

    usadas.update(MainWindow.ETIQUETAS.values())
    usadas.update(MainWindow.SUBTITULOS.values())
    return usadas


class TestTablaDeTraduccion(unittest.TestCase):
    def test_no_hay_traducciones_sin_usar(self):
        """Entradas huerfanas: la tabla crecio y nadie las limpio."""
        sobrantes = i18n.sobrantes(_literales_tr())
        self.assertEqual(
            [], sobrantes,
            "entradas en la tabla ES que ya no usa ningun tr(): "
            f"{sobrantes[:8]}"
        )

    def test_el_default_es_ingles(self):
        self.assertEqual("en", i18n.set_lang("en"))
        self.assertEqual("Hola", i18n.tr("Hola"))  # sin traducir, pasa igual

    def test_un_idioma_desconocido_cae_en_ingles(self):
        """Una config editada a mano con language: 'fr' no puede romper nada."""
        self.assertEqual("en", i18n.set_lang("fr"))
        self.assertEqual("en", i18n.lang())

    def test_tr_en_espanol_devuelve_la_traduccion(self):
        i18n.ES["Cadena de prueba"] = "Cadena probada"
        try:
            i18n.set_lang("es")
            self.assertEqual("Cadena probada", i18n.tr("Cadena de prueba"))
            # Y lo que no esta traducido sale igual, no desaparece.
            self.assertEqual("Sin traducir", i18n.tr("Sin traducir"))
        finally:
            del i18n.ES["Cadena de prueba"]
            i18n.set_lang("en")

    def test_todas_las_cadenas_tr_esten_traducidas(self):
        """La red de seguridad: ninguna cadena sin su entrada en ES."""
        faltan = i18n.faltantes(_literales_tr())
        self.assertEqual(
            [], faltan,
            f"cadenas que se muestran pero no estan en la tabla ES: {faltan[:8]}"
        )


class TestStub(unittest.TestCase):
    """El stub es stdlib puro: sus textos no pueden venir de i18n."""

    def test_el_stub_no_importa_i18n(self):
        """El stub no puede depender del paquete.

        Se comprueba con AST y no buscando la palabra: el docstring menciona
        i18n justamente para explicar por que NO lo importa, y un assertNotIn
        sobre el texto entero se dispara solo.
        """
        arbol = ast.parse((ROOT / STUB).read_text(encoding="utf-8"))
        importados = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                importados.update(a.name for a in nodo.names)
            elif isinstance(nodo, ast.ImportFrom):
                importados.add(nodo.module or "")
        self.assertEqual(
            [], sorted(m for m in importados if m.split(".")[0] in ("focuslock", "i18n")),
            "el stub importa el paquete: lo arranca Windows fuera de el, y "
            "tiene que funcionar aunque focuslock no sea importable."
        )

    def test_el_stub_tiene_textos_en_los_dos_idiomas(self):
        texto = (ROOT / STUB).read_text(encoding="utf-8")
        # El stub define sus tablas como dicts ES/EN. Basta con que existan
        # las dos y que no esten vacias.
        # (?m) es obligatorio: assertRegex no pone MULTILINE, asi que sin el
        # "^" solo matchea al principio del archivo y falla siempre.
        for idioma in ("ES", "EN"):
            self.assertRegex(
                texto, rf"(?m)^{idioma}\s*(?::[^=]*)?=",
                f"el stub no define la tabla {idioma}")

    def test_las_tablas_del_stub_coinciden(self):
        """Si el stub agrega un texto a ES y no a EN, se rompe en ingles."""
        texto = (ROOT / STUB).read_text(encoding="utf-8")
        es = self._claves(texto, "ES")
        en = self._claves(texto, "EN")
        self.assertEqual(
            [], sorted(es - en),
            f"el stub tiene {sorted(es - en)[:5]} en español pero no en inglés")
        self.assertEqual(
            [], sorted(en - es),
            f"el stub tiene {sorted(en - es)[:5]} en inglés pero no en español")

    def _claves(self, texto: str, nombre: str) -> set[str]:
        m = re.search(rf"^{nombre}\s*(?::[^=]*)?=\s*\{{(.*?)^\}}", texto,
                      re.MULTILINE | re.DOTALL)
        if not m:
            return set()
        return set(re.findall(r'^\s{4}"([^"]+)"\s*:', m.group(1), re.MULTILINE))


class TestHigieneDeTexto(unittest.TestCase):
    """Catch-all de caracteres que no tienen nada que ver aca."""

    def test_no_hay_caracteres_cjk_en_el_codigo(self):
        """Se me colaron varias veces al escribir y siempre en comentarios.

        No rompe nada, pero delata un texto que nadie leyo. Sale barato
        revisarlo una vez por lote.
        """
        intrusos = []
        for archivo in sorted((ROOT / "focuslock").rglob("*.py")):
            for n, linea in enumerate(
                archivo.read_text(encoding="utf-8").splitlines(), 1
            ):
                if re.search(r"[\u4e00-\u9fff]", linea):
                    intrusos.append(f"{archivo.relative_to(ROOT)}:{n}")
        self.assertEqual([], intrusos, f"caracteres CJK en: {intrusos[:5]}")

    def test_el_default_de_config_es_ingles(self):
        """La config nueva tiene que salir en ingles sin tocar nada."""
        from focuslock import config as config_mod

        defaults = config_mod.DEFAULTS["general"]
        self.assertEqual("en", defaults["language"])


class TestCadenasHuerfanas(unittest.TestCase):
    """Detecta texto de usuario que se quedo AFUERA de tr().

    Este es el agujero que los otros tests de este archivo no cubren, y
    aparecio de verdad: un f-string con la razon del desbloqueo nunca paso
    por tr(), asi que seguia en espanol mientras todo lo demas ya estaba
    traducido. Los tests estaban verdes.

    La diferencia es sutil pero es la que importa: los otros tests verifican
    que lo que ENTRÓ a tr() tenga su traduccion. Este verifica lo contrario,
    que nada deberia haber quedado afuera sin querer.

    La heuristica es "tiene tildes, eñes o interrogacion de apertura", que
    para ingles no aplica. Cuesta un falso positivo si alguien escribe un
    nombre propio en espanol, y esa es una exception que vale la pena
    agregar aca abajo en vez de relajar el patron.
    """
    ESP = re.compile(r"[áéíóúñÁÉÍÓÚÑ¿¡]")

    def test_no_hay_texto_en_espanol_fuera_de_tr(self):
        huerfanas = []
        for rel in ARCHIVOS_TRADUCIBLES:
            ruta = ROOT / rel
            arbol = ast.parse(ruta.read_text(encoding="utf-8"))

            dentro = set()
            for nodo in ast.walk(arbol):
                if isinstance(nodo, ast.Call):
                    f = nodo.func
                    nombre = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                    if nombre == "tr":
                        for a in list(nodo.args) + [k.value for k in nodo.keywords]:
                            for sub in ast.walk(a):
                                if isinstance(sub, ast.Constant):
                                    dentro.add(id(sub))

            docstrings = set()
            for nodo in ast.walk(arbol):
                if isinstance(nodo, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                    cuerpo = getattr(nodo, "body", [])
                    if (cuerpo and isinstance(cuerpo[0], ast.Expr)
                            and isinstance(cuerpo[0].value, ast.Constant)
                            and isinstance(cuerpo[0].value.value, str)):
                        docstrings.add(id(cuerpo[0].value))

            stylesheet = {
                nodo.value.lineno
                for nodo in ast.walk(arbol)
                if isinstance(nodo, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "STYLE" for t in nodo.targets)
                and isinstance(nodo.value, ast.Constant)
            }

            for nodo in ast.walk(arbol):
                if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
                    texto = nodo.value
                elif isinstance(nodo, ast.JoinedStr):
                    texto = ast.unparse(nodo)
                else:
                    continue
                if not self.ESP.search(texto):
                    continue
                if id(nodo) in dentro or id(nodo) in docstrings:
                    continue
                if nodo.lineno in stylesheet:
                    continue
                huerfanas.append(f"  {rel}:{nodo.lineno}  {texto[:70]}")

        self.assertEqual(
            [], huerfanas,
            "texto en espanol que no pasa por tr():\n" + "\n".join(huerfanas[:10]),
        )


if __name__ == "__main__":
    unittest.main()
