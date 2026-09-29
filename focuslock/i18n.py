"""Traducciones de la interfaz.

Por que el ingles es el literal en el codigo y no una clave: si la clave
fuera el ingles ("app.bloquear"), leer el codigo seria traducir mentalmente
en cada linea. Con el ingles como literal, `tr("Active lock")` se lee solo y
la tabla ES queda en un solo lugar.

El idioma vive en config.json y se fija una vez al arrancar con
`set_lang()`. Todo lo que se muestra despues pasa por `tr()`.

OJO con el stub: `focuslock/stub.py` NO importa este modulo. Ese archivo lo
lanza Windows fuera del paquete y tiene que arrancar aunque focuslock no sea
importable (por eso es solo stdlib). Sus textos estan duplicados alla a mano,
y `test_i18n` verifica que las dos copias no se separen.
"""
from __future__ import annotations

_IDIOMA = "en"

# Idiomas que la app acepta. "en" es el literal, asi que no necesita entrada.
IDIOMAS = ("en", "es")

NOMBRES = {
    "en": "English",
    "es": "Español",
}

# Clave = el texto en ingles, que es lo que esta escrito en el codigo.
# Valor = como se muestra si el usuario eligio español.
ES: dict[str, str] = {}


def set_lang(lang: str) -> str:
    """Fija el idioma global. Devuelve el que quedo, no el que se pidio.

    Un idioma desconocido cae en ingles en vez de romper: una config editada a
    mano con `language: "fr"` no puede dejar la ventana en blanco.
    """
    global _IDIOMA
    _IDIOMA = lang if lang in IDIOMAS else "en"
    return _IDIOMA


def lang() -> str:
    return _IDIOMA


def tr(texto: str) -> str:
    """Traduce un literal en ingles. Si no hay traduccion, lo devuelve igual.

    Devolver el original sin quejarse es a proposito: asi un texto nuevo
    aparece en ingles hasta que le agregan la entrada, en vez de desaparecer.
    """
    if _IDIOMA == "es":
        return ES.get(texto, texto)
    return texto


def faltantes(usados: set[str]) -> list[str]:
    """Traducciones que se usan pero no estan en la tabla ES.

    Lo usa test_i18n. Una cadena nueva sin traducir funciona (sale en ingles),
    pero es un olvido: esta lista lo vuelve visible.
    """
    return sorted(usados - set(ES))


def sobrantes(usados: set[str]) -> list[str]:
    """Entradas de la tabla que ya no usa nadie.

    Sobras por el camino no rompen nada, pero hacen que la tabla crezca sin
    que se note.
    """
    return sorted(set(ES) - usados)
