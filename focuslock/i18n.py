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
ES: dict[str, str] = {
    # -- diálogo de emergencia ---------------------------------------------
    "Emergency unlock": "Desbloqueo de emergencia",
    (
        "Heads up: this is an emergency exit, not a shortcut. It unlocks "
        "for {n} minutes and it is logged with a date and the text you "
        "wrote. Read it back next time."
    ): (
        "Atent@: esto es una salida de emergencia, no un atajo. Desbloquea "
        "{n} minutos y queda registrado con fecha y texto. Releelo la "
        "próxima vez."
    ),
    "Requirements": "Requisitos",
    "Words": "Palabras",
    "Writing time": "Tiempo de escritura",
    "Keystrokes": "Pulsaciones",
    "1. Why do you need to unlock right now?": "1. ¿Por qué necesitás desbloquear ahora?",
    "At least {n} words.": "Mínimo {n} palabras.",
    "Summary": "Resumen",
    "One-line summary (it goes into the log)": "Resumen en una línea (queda en la bitácora)",
    "Keep studying": "Seguir estudiando",
    "Verify and unlock": "Verificar y desbloquear",
    "Verifying…": "Verificando…",
    "Not yet:\n": "Todavía no:\n",
    "Unknown error": "Error desconocido",
    "Could not reach the service: {err}": "No se pudo contactar al servicio: {err}",
    "{n} words left.": "Faltan {n} palabras.",
    "Keep writing until the time is up.": "Seguí escribiendo hasta completar el tiempo.",
    "Answer all three questions.": "Completá las tres preguntas.",
    "You can verify. The service will confirm.": "Podés verificar. El servicio va a confirmar.",
    # -- preguntas del diálogo ---------------------------------------------
    "Describe the actual situation. Is it genuinely urgent, or are you tired?": (
        "Describí la situación concreta. ¿Es urgente de verdad o es cansancio?"
    ),
    "If the real reason were getting stuck, what exactly would it be?": (
        "Si el motivo real fuera quedar varado, ¿cuál es exactamente?"
    ),
    "A concrete plan with a time. If you cannot write it, do not unlock.": (
        "Un plan concreto y con horario. Si no podés escribirlo, no desbloquees."
    ),
    "Why you want to unlock right now": "Por qué querés desbloquear ahora",
    "What you lose if you do not": "Qué perdés si no lo hacés",
    "What you are going to do afterwards": "Qué vas a hacer después",
    # -- errores que arma el servicio --------------------------------------
    # Los produce emergency.py, que corre dentro del servicio. El servicio
    # fija el idioma desde la config antes de validar, asi que el error le
    # llega al usuario en el idioma que eligio.
    "You are {n} words short (you wrote {w} of {m}).": (
        "Te faltan {n} palabras (escribiste {w} de {m})."
    ),
    "{n} min {s:02d} s of real writing still to go (you have {a} min {b:02d} s).": (
        "Faltan {n} min {s:02d} s de escritura real (llevás {a} min {b:02d} s)."
    ),
    "No keystrokes were recorded.": "No se registró ninguna pulsación.",
    "This looks pasted from the clipboard ({r:.1f} characters per keystroke). It has to be written.": (
        "El texto parece pegado desde el portapapeles ({r:.1f} caracteres por "
        "pulsación). Hay que escribirlo."
    ),
    "You went {n} min without writing. Waiting does not count if you are not writing.": (
        "Pasaste {n} min sin escribir nada. El tiempo de espera no cuenta si no "
        "estás escribiendo."
    ),
    "Incomplete answer: '{label}' ({n} words short).": (
        "Respuesta incompleta: '{label}' (faltan {n} palabras)."
    ),
    "Emergency: written commitment ({w} words, {m} min)": (
        "Emergencia: compromiso escrito ({w} palabras, {m} min)"
    ),
}


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
