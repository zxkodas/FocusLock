"""Validación del compromiso escrito de emergencia.

No es un formulario: es una barrera de fricción. Para desbloquear tenés que
escribir de verdad, durante tiempo real, y queda guardado para releerlo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

# Anti-pegado: caracteres tecleados por pulsación. Teclear normal ronda 1.0-1.6;
# pegar un bloque de texto lleva el ratio muy por encima de 3.
MAX_CHARS_PER_KEYSTROKE = 3.0

# Una pausa de más de esto se considera que "estabas pensando", no escribiendo.
IDLE_GAP_SECONDS = 45.0

WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)

PROMPTS: list[tuple[str, str]] = [
    ("motivo", "Describe the actual situation. Is it genuinely urgent, or are you tired?"),
    ("costo", "If the real reason were getting stuck, what exactly would it be?"),
    ("plan", "A concrete plan with a time. If you cannot write it, do not unlock."),
]

# El diálogo muestra títulos legibles; la clave de transporte es estable.
# Los valores van en inglés y el diálogo los pasa por tr(); están en la tabla
# de focuslock/i18n.py.
PROMPT_LABELS: dict[str, str] = {
    "motivo": "Why you want to unlock right now",
    "costo": "What you lose if you do not",
    "plan": "What you are going to do afterwards",
}

MIN_PROMPT_WORDS = 30

# Los errores de este modulo los arma el SERVICIO, que ya sabe el idioma del
# usuario porque lo lee de la config (ver daemon.py). Por eso usan tr() y no
# cadenas fijas: si no, un usuario en ingles veria los errores en espanol.
from .i18n import tr  # noqa: E402  (al final: PROMPTS no depende de i18n)


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text or ""))


@dataclass
class EmergencySubmission:
    text: str = ""
    prompts: dict[str, str] = field(default_factory=dict)
    keystrokes: int = 0
    elapsed: float = 0.0
    longest_idle: float = 0.0
    started_at: float = 0.0


@dataclass
class EmergencyVerdict:
    ok: bool = False
    words: int = 0
    seconds: float = 0.0
    ratio: float = 0.0
    errors: list[str] = field(default_factory=list)

    def message(self) -> str:
        return "\n".join(f"• {e}" for e in self.errors)


def requirements(config: dict) -> tuple[int, int]:
    cfg = config.get("emergency", {}) if isinstance(config, dict) else {}
    try:
        words = int(cfg.get("min_words", 300))
    except (TypeError, ValueError):
        words = 300
    try:
        minutes = int(cfg.get("min_minutes", 5))
    except (TypeError, ValueError):
        minutes = 5
    return max(1, words), max(1, minutes)


def validate(submission: EmergencySubmission, config: dict) -> EmergencyVerdict:
    min_words, min_minutes = requirements(config)
    verdict = EmergencyVerdict()

    verdict.words = count_words(submission.text)
    verdict.seconds = max(0.0, submission.elapsed)
    chars = len(submission.text or "")
    verdict.ratio = chars / submission.keystrokes if submission.keystrokes > 0 else 0.0

    if verdict.words < min_words:
        faltan = min_words - verdict.words
        verdict.errors.append(
            tr("You are {n} words short (you wrote {w} of {m}).").format(
                n=faltan, w=verdict.words, m=min_words)
        )

    min_seconds = min_minutes * 60
    if verdict.seconds < min_seconds:
        faltan = int(min_seconds - verdict.seconds)
        verdict.errors.append(
            tr("{n} min {s:02d} s of real writing still to go (you have {a} min {b:02d} s).").format(
                n=faltan // 60, s=faltan % 60,
                a=int(verdict.seconds // 60), b=int(verdict.seconds % 60))
        )

    if submission.keystrokes == 0:
        verdict.errors.append(tr("No keystrokes were recorded."))
    elif verdict.ratio > MAX_CHARS_PER_KEYSTROKE:
        verdict.errors.append(
            tr("This looks pasted from the clipboard ({r:.1f} characters per "
               "keystroke). It has to be written.").format(r=verdict.ratio)
        )

    if submission.longest_idle > max(IDLE_GAP_SECONDS, verdict.seconds * 0.6):
        verdict.errors.append(
            tr("You went {n} min without writing. Waiting does not count if you "
               "are not writing.").format(n=int(submission.longest_idle // 60))
        )

    for key, _hint in PROMPTS:
        written = submission.prompts.get(key, "")
        if count_words(written) < MIN_PROMPT_WORDS:
            faltan = MIN_PROMPT_WORDS - count_words(written)
            label = tr(PROMPT_LABELS.get(key, key))
            verdict.errors.append(
                tr("Incomplete answer: '{label}' ({n} words short).").format(
                    label=label, n=faltan)
            )

    verdict.ok = not verdict.errors
    return verdict


def summarize(submission: EmergencySubmission, verdict: EmergencyVerdict) -> dict:
    """Entrada de bitácora. Guarda el texto completo para poder releerlo."""
    return {
        "at": submission.started_at,
        "words": verdict.words,
        "seconds": round(verdict.seconds),
        "keystrokes": submission.keystrokes,
        "chars_per_key": round(verdict.ratio, 2),
        "commitment": submission.text.strip(),
        "prompts": {k: (v or "").strip() for k, v in submission.prompts.items()},
    }
