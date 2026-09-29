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
    ("motivo", "Describí la situación concreta. ¿Es urgente de verdad o es cansancio?"),
    ("costo", "Si el motivo real fuera quedar varado, ¿cuál es exactamente?"),
    ("plan", "Un plan concreto y con horario. Si no podés escribirlo, no desbloquees."),
]

# El diálogo muestra títulos legibles; la clave de transporte es estable.
PROMPT_LABELS: dict[str, str] = {
    "motivo": "Por qué querés desbloquear ahora",
    "costo": "Qué perdés si no lo hacés",
    "plan": "Qué vas a hacer después",
}

MIN_PROMPT_WORDS = 30


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
            f"Te faltan {faltan} palabras (escribiste {verdict.words} de {min_words})."
        )

    min_seconds = min_minutes * 60
    if verdict.seconds < min_seconds:
        faltan = int(min_seconds - verdict.seconds)
        verdict.errors.append(
            f"Faltan {faltan // 60} min {faltan % 60:02d} s de escritura real "
            f"(llevás {int(verdict.seconds // 60)} min {int(verdict.seconds % 60):02d} s)."
        )

    if submission.keystrokes == 0:
        verdict.errors.append("No se registró ninguna pulsación.")
    elif verdict.ratio > MAX_CHARS_PER_KEYSTROKE:
        verdict.errors.append(
            f"El texto parece pegado desde el portapapeles "
            f"({verdict.ratio:.1f} caracteres por pulsación). Hay que escribirlo."
        )

    if submission.longest_idle > max(IDLE_GAP_SECONDS, verdict.seconds * 0.6):
        verdict.errors.append(
            f"Pasaste {int(submission.longest_idle // 60)} min sin escribir nada. "
            "El tiempo de espera no cuenta si no estás escribiendo."
        )

    for key, _hint in PROMPTS:
        written = submission.prompts.get(key, "")
        if count_words(written) < MIN_PROMPT_WORDS:
            faltan = MIN_PROMPT_WORDS - count_words(written)
            label = PROMPT_LABELS.get(key, key)
            verdict.errors.append(f"Respuesta incompleta: '{label}' (faltan {faltan} palabras).")

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
