"""Verifica que lo que se guarda en la ventana quede en el disco.

Esto se manifesto de la forma mas incomoda posible: no habia ningun sintoma
visible. El servicio respondia, la ventana decia 'Guardado', y los valores
volvian correctos si los mirabas en el momento. Solo se perdian al reiniciar,
que es exactamente cuando nadie esta mirando.

El caso de prueba usa un directorio temporal, no ProgramData: los tests no
tienen por que tocar los datos reales del usuario para comprobar que un
archivo se escribe.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from focuslock import config as config_mod
from focuslock.daemon import Engine


class TestConfigPersists(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.config_path = self.dir / "config.json"
        self.state_path = self.dir / "state.json"
        # El token va con la forma correcta pero es inventado. Un token real
        # en un archivo de test ya paso una vez y hubo que limpiar el
        # historial de git.
        self.config = config_mod.Config(self.config_path)
        self.config.save()

    def test_save_sin_load_no_borra_la_config(self):
        """La trampa: Config(path).save() escribia {} y perdia el token.

        Config.__init__ deja _data vacio y no lee el disco, asi que un save()
        sin load() previo escribia un objeto vacio ENCIMA de la config real.
        """
        self.config.set("ticktick", {"project_name": "Estudios"})
        self.config.save()

        # Un Config nuevo sobre el mismo archivo, como haria un call site.
        fresco = config_mod.Config(self.config_path)
        fresco.save()

        en_disco = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(
            "Estudios", en_disco["ticktick"]["project_name"],
            "un save() sin load() previo borro la config",
        )

    def test_save_sin_load_sobre_archivo_nuevo_da_defaults(self):
        """Si el archivo no existe, los defaults son lo correcto."""
        nuevo = config_mod.Config(self.dir / "no-existe.json")
        nuevo.save()
        en_disco = json.loads(
            (self.dir / "no-existe.json").read_text(encoding="utf-8")
        )
        self.assertEqual("en", en_disco["general"]["language"])

    def _daemon(self) -> Engine:
        """Un Engine minimo: solo lo que _cmd_config_set llega a tocar.

        No se construye de verdad porque eso levanta el cliente de TickTick, el
        guard y el pipe. Aca interesa una sola cosa: que el handler escriba el
        archivo.
        """
        d = Engine.__new__(Engine)
        d.config = self.config

        class _Gate:
            def poll(self):
                return type("S", (), {"credits": 0, "required": 2})()

        d.gate = _Gate()
        d._sync_ifeo = lambda force=False: None
        d._publish_language = lambda: None
        return d

    def test_config_set_escribe_en_el_archivo(self):
        """El bug: config.set() hace merge pero no guarda.

        Se comprueba releendo el archivo, no preguntándole al objeto: el
        objeto tiene el valor en memoria y por eso seemedia funcionar.
        """
        d = self._daemon()
        d._cmd_config_set({"section": "ticktick", "values": {"poll_seconds": 77}})

        en_disco = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(
            77, en_disco["ticktick"]["poll_seconds"],
            "el cambio quedo solo en memoria: se pierde al reiniciar el servicio",
        )

    def test_config_set_no_olvida_lo_que_no_se_toca(self):
        """Guardar una seccion no puede borrar el resto."""
        self.config.set("ticktick", {"project_name": "Estudios"})
        self.config.save()

        d = self._daemon()
        d._cmd_config_set({"section": "emergency", "values": {"min_words": 42}})

        en_disco = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(42, en_disco["emergency"]["min_words"])
        self.assertEqual("Estudios", en_disco["ticktick"]["project_name"])

    def test_config_set_rechaza_lo_mal_formedo(self):
        """Sin 'section', o con 'values' que no es un dict, se rechaza.

        Un 'values' vacio NO se rechaza: es un no-op, no una corrupcion, y
        hacerlo explícito obliga al que llama a chequear de mas. Lo que si
        tiene que aguantar es que un request raro no escriba basura.
        """
        d = self._daemon()
        for malo in ({"values": {"poll_seconds": 9}}, {"section": "", "values": {}}, {}):
            with self.subTest(req=malo):
                with self.assertRaises(ValueError):
                    d._cmd_config_set(malo)

        # Un dict vacio no rompe nada: devuelve ok y no cambia ningun valor.
        d._cmd_config_set({"section": "ticktick", "values": {"poll_seconds": 45}})
        antes = json.loads(self.config_path.read_text(encoding="utf-8"))
        d._cmd_config_set({"section": "ticktick", "values": {}})
        despues = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(antes, despues)

    def test_guardar_todas_las_secciones_persiste(self):
        """Cada seccion que la ventana puede tocar."""
        for seccion, valores in (
            ("ticktick", {"required": 3}),
            ("emergency", {"unlock_minutes": 45}),
            ("programs", {"use_ifeo": False}),
            ("sites", {"blocked": ["example.com"]}),
            ("general", {"language": "es"}),
        ):
            with self.subTest(seccion=seccion):
                d = self._daemon()
                d._cmd_config_set({"section": seccion, "values": valores})
                en_disco = json.loads(self.config_path.read_text(encoding="utf-8"))
                for clave, valor in valores.items():
                    self.assertEqual(
                        valor, en_disco[seccion][clave],
                        f"{seccion}.{clave} no llego al disco",
                    )


if __name__ == "__main__":
    unittest.main()
