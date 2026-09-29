"""Motor de la puerta: observa TickTick y concede el desbloqueo.

Regla de negocio:
  - Cuenta SOLO tareas del proyecto configurado cuyo título empieza con
    el prefijo (por defecto "Lectura").
  - Cada transición pendiente -> completada otorga 1 crédito.
  - Al llegar a `required` créditos, se desbloquea.
  - El crédito NO se otorga haciendo clic en la app: hay que completar en TickTick.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from .config import Config
from .rules import norm_key, title_matches_prefix
from .store import Store
from .ticktick import TickTickClient, TickTickError


@dataclass
class Lectura:
    id: str
    title: str
    completed: bool
    column: str = ""

    def module(self) -> str:
        return self.column or "General"


@dataclass
class GateStatus:
    required: int = 2
    credits: int = 0
    unlocked: bool = False
    unlock_reason: str = ""
    pending: list[Lectura] = field(default_factory=list)
    done: list[Lectura] = field(default_factory=list)
    modules: dict[str, int] = field(default_factory=dict)
    error: str = ""
    checked_at: float = 0.0

    def remaining(self) -> int:
        return max(0, self.required - self.credits)

    def progress_text(self) -> str:
        if self.unlocked:
            return "Desbloqueado"
        return f"{self.credits}/{self.required} Lecturas completadas"


def _is_completed(task: dict) -> bool:
    if task.get("status") == 2:
        return True
    return bool(task.get("completedTime"))


# Margen de tolerancia: TickTick y la hora local pueden diferir un poco, y un
# reloj de servidor desfasado no debe hacerte perder el credito de una Lectura
# que tachaste hace 30 segundos.
_TOLERANCE_SECONDS = 120


def _completed_at(task: dict) -> float | None:
    """Epoch de cuando se completó la tarea, o None si TickTick no lo dice.

    TickTick usa `2026-01-25T12:00:00+0000` (offset sin dos puntos) o `...Z`.
    Se prueban varios formatos porque no están documentados de forma estable.
    """
    raw = task.get("completedTime")
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()

    from datetime import datetime, timedelta, timezone

    candidates = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
    ]
    for fmt in candidates:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()

    try:
        cleaned = text.replace("Z", "+00:00")
        if "." in cleaned:
            head, _, tail = cleaned.partition(".")
            digits = "".join(c for c in tail if c.isdigit())[:6]
            offset = tail[len(digits):] if len(tail) > len(digits) else ""
            offset = offset if offset else "+00:00"
            if len(offset) == 5 and ":" not in offset:
                offset = offset[:3] + ":" + offset[3:]
            cleaned = f"{head}.{digits}{offset}"
        return datetime.fromisoformat(cleaned).timestamp()
    except (ValueError, TypeError):
        return None


class Gate:
    def __init__(self, client: TickTickClient, config: Config, store: Store) -> None:
        self._client = client
        self._config = config
        self._store = store
        self._lock = threading.RLock()
        self._status = GateStatus()
        self._project_id: str | None = None

    # -- configuración efectiva --------------------------------------------
    @property
    def required(self) -> int:
        try:
            return max(1, int(self._config.get("ticktick").get("required", 2)))
        except (TypeError, ValueError):
            return 2

    @property
    def prefix(self) -> str:
        """Deprecated: ya no se filtra por nombre de tarea.

        Se conserva por compatibilidad con configs viejas y con los tests.
        El conteo toma cualquier tarea del proyecto.
        """
        return self._config.get("ticktick").get("task_prefix", "")

    # -- estado ------------------------------------------------------------
    def status(self) -> GateStatus:
        with self._lock:
            self._status.unlocked = self.is_unlocked()
            return self._status

    def is_unlocked(self, now: float | None = None) -> bool:
        """Semantica del estado:

        - `unlock_until == 0` -> desbloqueo abierto, hasta que se llame relock()
        - `unlock_until >  0` -> ventana temporal (emergencia). Al expirar
                                 vuelve a bloquear solo, sin intervencion.
        """
        now = now or time.time()
        data = self._store.read()
        until = float(data.get("unlock_until") or 0)
        if until:
            return now < until
        return not data.get("locked", True)

    def credits(self) -> int:
        return int(self._store.get("credits", 0) or 0)

    def reason(self) -> str:
        return str(self._store.get("unlock_reason", "") or "")

    # -- acciones ----------------------------------------------------------
    def relock(self) -> None:
        self._store.reset_lock_cycle(self.required)
        with self._lock:
            self._status.credits = 0
            self._status.unlocked = False
            self._status.unlock_reason = ""

    def unlock_now(self, reason: str, minutes: int = 0) -> None:
        """Desbloquea. minutes>0 => temporal (emergencia)."""
        data = self._store.read()
        data["locked"] = False
        data["unlock_until"] = time.time() + minutes * 60 if minutes else 0.0
        data["unlock_reason"] = reason
        self._store.write()
        with self._lock:
            self._status.unlocked = True
            self._status.unlock_reason = reason

    def log_emergency(self, entry: dict) -> None:
        data = self._store.read()
        limit = int(self._config.get("emergency").get("history_limit", 50))
        data.setdefault("emergencies", []).append(entry)
        data["emergencies"] = data["emergencies"][-limit:]
        self._store.write()

    def emergencies(self) -> list[dict]:
        return list(self._store.get("emergencies", []) or [])

    def log_block(self, entry: dict) -> None:
        data = self._store.read()
        data.setdefault("block_events", []).append(entry)
        data["block_events"] = data["block_events"][-200:]
        self._store.write()

    def blocks(self) -> list[dict]:
        return list(self._store.get("block_events", []) or [])

    # -- polling -----------------------------------------------------------
    def resolve_project_id(self) -> str:
        """Resuelve el proyecto kanban por nombre, tolerando el emoji de TickTick.

        Se busca por nombre en cada consulta a proposito: si el usuario renombra
        o recrea el proyecto en TickTick, la app lo sigue sin intervencion.
        """
        cfg = self._config.get("ticktick")
        explicit = (cfg.get("project_id") or "").strip()
        name = (cfg.get("project_name") or "").strip()

        projects = self._client.projects()

        if name:
            target = norm_key(name)
            for project in projects:
                if norm_key(project.get("name", "")) == target:
                    return str(project.get("id"))
            # No se encontro por nombre: avisamos en vez de adivinar.
            available = ", ".join(
                f"{p.get('name')} ({p.get('id')})" for p in projects
            ) or "ninguno"
            raise TickTickError(
                f"No se encontró el proyecto '{name}' en tu TickTick. "
                f"Proyectos disponibles: {available}. "
                "Corregí el nombre en FocusLock → Ajustes."
            )

        if explicit:
            for project in projects:
                if project.get("id") == explicit:
                    return explicit
            raise TickTickError(
                f"El proyecto {explicit} ya no existe en TickTick. "
                "Indicá un nombre en FocusLock → Ajustes."
            )

        raise TickTickError("No configuraste ningún proyecto de TickTick.")

    def poll(self) -> GateStatus:
        """Consulta TickTick, actualiza créditos y devuelve el estado."""
        with self._lock:
            self._status.checked_at = time.time()
            self._status.required = self.required
            self._status.unlocked = self.is_unlocked()
            self._status.unlock_reason = self.reason()

            if not self._client.configured:
                self._status.error = (
                    "Sin token de TickTick. Abrí FocusLock → Ajustes y pegalo."
                )
                return self._status

            try:
                project_id = self.resolve_project_id()
                data = self._client.project_data(project_id)
            except TickTickError as exc:
                self._status.error = str(exc)
                self._store.set("last_error", str(exc))
                return self._status
            except Exception as exc:  # noqa: BLE001
                # Cualquier fallo de red o de datos tiene que verse. Un error
                # tragado acá deja el contador en 0 sin explicación.
                self._status.error = f"{type(exc).__name__}: {exc}"
                self._store.set("last_error", self._status.error)
                return self._status

            project = data.get("project") or {}
            project_name = project.get("name") or "TickTick"

            # Una respuesta vacia o sin tareas no es un estado valido para tomar
            # como linea base: siTickTick fallara, no hay que sembrar nada.
            if not data.get("tasks"):
                self._status.error = (
                    "TickTick devolvió el proyecto sin tareas. No se tomó como base."
                )
                self._store.set("last_error", self._status.error)
                return self._status

            columns = {c.get("id"): (c.get("name") or "General") for c in data.get("columns", [])}
            tasks = data.get("tasks", []) or []

            # Sin filtro de prefijo: cuenta cualquier tarea del proyecto. El
            # nombre de la tarea no importa, importa que el total de la
            # columna baje.
            items: list[Lectura] = []
            raw_by_id: dict[str, dict] = {}
            for task in tasks:
                title = task.get("title", "")
                if not title.strip():
                    continue
                task_id = str(task.get("id"))
                raw_by_id[task_id] = task
                items.append(
                    Lectura(
                        id=task_id,
                        title=title,
                        completed=_is_completed(task),
                        column=columns.get(task.get("columnId"), "General"),
                    )
                )

            # ------------------------------------------------------------------
            # Cómo se acredita el trabajo.
            #
            # Tus tareas de Lectura son recurrentes (`repeatFrom`): al tacharlas
            # TickTick las reinicia al día siguiente en vez de archivarlas. Por
            # eso `status` vuelve a 0 al instante y no existe una transición
            # "pendiente -> completada" que se pueda observar.
            #
            # Se acredita por完成任务 DOS señales, porque TickTick no da una
            # sola fiable:
            #   1. La tarea figura completada ahora (status=2 / completedTime
            #      posterior al inicio del bloqueo).
            #   2. La tareaya no está en el proyecto: una tarea recurrente que
            #      se completa y se retira desaparece de la lista. Si la
            #      teníamos registrada y ahora no está, se completó.
            #
            # (2) es lo que cubre tu caso real. Y tiene un límite: si borrás
            # una tarea a mano, también cuenta. Es el precio de que TickTick no
            # exponga el estado de una tarea recurrente completada.
            # ------------------------------------------------------------------
            started = float(self._store.get("lock_started", 0) or 0)
            gained = 0
            newly_done: list[Lectura] = []
            current: dict[str, bool] = {item.id: item.completed for item in items}
            previous: dict = dict(self._store.get("lectura_status", {}) or {})
            previous_titles: dict = dict(self._store.get("lectura_titles", {}) or {})

            credited = set(self._store.get("credited_ids", []) or [])

            for item in items:
                if item.id in credited:
                    continue
                if not item.completed:
                    continue
                stamp = _completed_at(raw_by_id.get(item.id, {}))
                if stamp is not None and started > 0:
                    if stamp >= started - _TOLERANCE_SECONDS:
                        gained += 1
                        newly_done.append(item)
                        credited.add(item.id)
                elif item.id in previous and not previous[item.id]:
                    gained += 1
                    newly_done.append(item)
                    credited.add(item.id)

            # Señal 2: tareas que estaban y ya no están (recurrentes completadas).
            if started > 0:
                for task_id, was_done in list(previous.items()):
                    if task_id in credited or task_id in current:
                        continue
                    if was_done:
                        continue
                    # Estaba pendiente y desapareció tras activarse el bloqueo.
                    gained += 1
                    credited.add(task_id)
                    newly_done.append(
                        Lectura(
                            id=task_id,
                            title=previous_titles.get(task_id, "tarea retirada"),
                            completed=True,
                            column="",
                        )
                    )

            credits = int(self._store.get("credits", 0) or 0) + gained
            required = self.required
            unlocked = self.is_unlocked()

            if gained and credits >= required and not unlocked:
                data_state = self._store.read()
                data_state["locked"] = False
                data_state["unlock_until"] = 0.0
                data_state["unlock_reason"] = (
                    f"TickTick: {credits} tareas completadas en {project_name}"
                )
                self._store.write()
                unlocked = True

            self._store.update(
                credits=credits,
                required=required,
                lectura_status=current,
                lectura_titles={i.id: i.title for i in items},
                credited_ids=sorted(credited),
                last_poll=time.time(),
                last_error="",
            )

            modules: dict[str, int] = {}
            for item in items:
                if not item.completed:
                    modules[item.module()] = modules.get(item.module(), 0) + 1

            self._status.credits = credits
            self._status.unlocked = unlocked
            self._status.unlock_reason = self.reason()
            self._status.pending = [i for i in items if not i.completed]
            self._status.done = [i for i in items if i.completed] + newly_done
            self._status.modules = dict(sorted(modules.items()))
            self._status.error = ""
            # Marca de que hubo una consulta real: la UI la usa para no
            # afirmar "no hay pendientes" cuando en realidad no preguntó.
            self._status.checked_at = time.time()
            if newly_done:
                names = ", ".join(i.title for i in newly_done[:4])
                self._status.error = ""
                self._last_gain = names
            return self._status
