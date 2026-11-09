"""Bindeglied zwischen Engine und Qt: gemeinsamer Zustand, Signale, Hintergrundaufrufe."""

from __future__ import annotations

import traceback
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from ..core.engine import Engine
from ..core.models import QueryRecord


class _WorkerSignals(QObject):
    done = Signal(object)
    failed = Signal(str, object)


class _Worker(QRunnable):
    """Einmalige Aufgabe im Threadpool.

    Wichtig: ``signals`` wird vom :class:`AppContext` referenziert, bis die Rueckmeldung im
    GUI-Thread angekommen ist. Der Threadpool loescht den QRunnable direkt nach ``run``; ohne
    eigene Referenz wuerde das Signalobjekt mit ihm verschwinden und die bereits eingereihte
    Rueckmeldung ins Leere laufen (verlorene Ergebnisse bzw. Absturz).
    """

    def __init__(self, fn: Callable[[], Any], signals: "_WorkerSignals"):
        super().__init__()
        self.fn = fn
        self.signals = signals

    @Slot()
    def run(self) -> None:  # pragma: no cover - Thread
        try:
            result = self.fn()
        except Exception as exc:
            traceback.print_exc()
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}", exc)
        else:
            self.signals.done.emit(result)


class AppContext(QObject):
    """Haelt Engine und aktuellen Fall; verteilt Aenderungen an alle Seiten."""

    case_changed = Signal(str)        # Fall gewechselt (ID oder "")
    data_changed = Signal()           # Daten des aktuellen Falls haben sich geaendert
    cases_changed = Signal()          # Fallliste hat sich geaendert
    query_updated = Signal(object)    # QueryRecord (aus einem Arbeitsthread)
    statuses_changed = Signal()       # Modulstatus wurde neu geprueft
    message = Signal(str, bool)       # Text, is_error -> Statusleiste

    def __init__(self, engine: Engine):
        super().__init__()
        self.engine = engine
        self._case_id: str = ""
        self.pool = QThreadPool.globalInstance()
        self._statuses: list = []
        self._pending: set[_WorkerSignals] = set()
        self._closing = False
        engine.jobs.add_listener(self._on_job)

    # ---------------------------------------------------------------- Faelle
    @property
    def case_id(self) -> str:
        return self._case_id

    @property
    def case(self):
        return self.engine.case(self._case_id) if self._case_id else None

    def set_case(self, case_id: str) -> None:
        if case_id != self._case_id:
            self._case_id = case_id
            self.case_changed.emit(case_id)

    def has_case(self) -> bool:
        return bool(self._case_id)

    # ------------------------------------------------------------- Signale
    def _on_job(self, record: QueryRecord) -> None:
        """Wird im Arbeitsthread aufgerufen; Qt stellt das Signal in den GUI-Thread um."""
        if not self._closing:
            self.query_updated.emit(record)

    def notify(self, text: str = "", *, error: bool = False, data: bool = True) -> None:
        if text:
            self.message.emit(text, error)
        if data:
            self.data_changed.emit()

    # -------------------------------------------------------- Hintergrund
    def run_async(self, fn: Callable[[], Any], on_done: Callable[[Any], None],
                  on_error: Optional[Callable[[str], None]] = None) -> None:
        """Fuehrt ``fn`` im Threadpool aus; Rueckmeldung im GUI-Thread."""
        signals = _WorkerSignals()
        self._pending.add(signals)

        def finished(result: Any) -> None:
            self._pending.discard(signals)
            on_done(result)

        def failed(msg: str, _exc: Any) -> None:
            self._pending.discard(signals)
            (on_error or self._default_error)(msg)

        signals.done.connect(finished)
        signals.failed.connect(failed)
        self.pool.start(_Worker(fn, signals))

    def _default_error(self, msg: str) -> None:
        self.message.emit(msg, True)

    def shutdown(self) -> None:
        """Keine Rueckmeldungen mehr annehmen und auf laufende Hintergrundaufgaben warten."""
        self._closing = True
        self.engine.jobs.remove_listener(self._on_job)
        self.pool.waitForDone(5000)
        self._pending.clear()

    # -------------------------------------------------------- Modulstatus
    @property
    def statuses(self) -> list:
        return list(self._statuses)

    def refresh_statuses(self) -> None:
        """Prueft alle Module im Hintergrund (ruft lokale Programme auf, kann dauern)."""
        def done(result):
            self._statuses = result
            self.statuses_changed.emit()
        self.run_async(self.engine.statuses, done)

    def adapter_name(self, adapter_id: str) -> str:
        try:
            return self.engine.adapter(adapter_id).name
        except Exception:
            return adapter_id
