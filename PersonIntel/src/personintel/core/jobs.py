"""Hintergrundausfuehrung autorisierter Abfragen.

Der JobManager fuehrt ausschliesslich :class:`AuthorizedQuery`-Objekte aus, speichert nur
*normalisierte* Befunde und Quellen (nie Rohdaten) und haelt den Ablauf nachvollziehbar
(Abfrage-Datensatz, Ereignis, Audit-Eintrag).
"""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Optional

from ..adapters.base import Adapter
from ..core.errors import AdapterError, AdapterNotAvailable, QueryCancelled, UnauthorizedQueryError
from ..core.ids import new_id, now_iso
from ..core.models import Event, FindingStatus, QueryMode, QueryRecord, QueryState
from ..security.audit import AuditLog
from ..security.authorization import AuthorizedQuery, require_valid
from ..storage.repository import Repository

Listener = Callable[[QueryRecord], None]


class JobManager:
    def __init__(self, repo: Repository, audit: AuditLog, max_workers: int = 3):
        self.repo = repo
        self.audit = audit
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="personintel-job")
        self._futures: dict[str, Future] = {}
        self._adapters: dict[str, Adapter] = {}
        self._cancelled: set[str] = set()
        self._listeners: list[Listener] = []
        self._lock = threading.Lock()

    # ----------------------------------------------------------- Listener
    def add_listener(self, fn: Listener) -> None:
        self._listeners.append(fn)

    def _emit(self, record: QueryRecord) -> None:
        for fn in list(self._listeners):
            try:
                fn(record)
            except Exception:  # Listener duerfen den Job nie beeinflussen
                pass

    # -------------------------------------------------------------- Submit
    def submit(self, aq: AuthorizedQuery, adapter: Adapter) -> QueryRecord:
        aq = require_valid(aq)
        if aq.adapter_id != adapter.id:
            raise UnauthorizedQueryError("Autorisierung gehoert zu einem anderen Modul.")
        record = QueryRecord(id=aq.query_id, case_id=aq.case_id, adapter_id=adapter.id, target_id=aq.target_id,
                             kind=aq.kind, mode=aq.mode, state=QueryState.QUEUED)
        self.repo.put("query", record, ts=record.created_at)
        with self._lock:
            self._adapters[aq.query_id] = adapter
            self._futures[aq.query_id] = self._pool.submit(self._run, aq, adapter, record)
        self._emit(record)
        return record

    # ------------------------------------------------------------- Worker
    def _update(self, record: QueryRecord, **changes) -> None:
        for k, v in changes.items():
            setattr(record, k, v)
        self.repo.put("query", record, ts=record.created_at)
        self._emit(record)

    def _run(self, aq: AuthorizedQuery, adapter: Adapter, record: QueryRecord) -> QueryRecord:
        if aq.query_id in self._cancelled:
            self._finish(record, QueryState.CANCELLED, "Vor dem Start abgebrochen.", 0)
            return record
        self._update(record, state=QueryState.RUNNING, started_at=now_iso())
        try:
            raw = adapter.execute_authorized_query(aq)
            batch = adapter.normalize_results(raw)
            sources = {s.id: s for s in batch.sources}
            for s in batch.sources:
                s.case_id, s.query_id = aq.case_id, aq.query_id
                s.adapter_id = adapter.id
                s.active = aq.mode is QueryMode.ACTIVE
                if not s.tool_version:
                    s.tool_version = raw.tool_version
                self.repo.put("source", s, ts=s.retrieved_at)
            only_source = next(iter(sources)) if len(sources) == 1 else ""
            for f in batch.findings:
                f.case_id, f.query_id, f.target_id = aq.case_id, aq.query_id, aq.target_id
                f.adapter_id = adapter.id
                if not f.source_id:
                    f.source_id = only_source
                self.repo.put("finding", f, ts=f.observed_at)
            hits = sum(1 for f in batch.findings if f.status in (FindingStatus.FOUND, FindingStatus.POSSIBLE))
            problems = list(raw.errors) + list(batch.notes)
            msg = f"{len(batch.findings)} Einträge, davon {hits} Treffer."
            if problems:
                msg += " Hinweise: " + "; ".join(problems[:5])
            state = QueryState.CANCELLED if aq.query_id in self._cancelled else QueryState.DONE
            self._finish(record, state, msg, len(batch.findings))
        except QueryCancelled:
            self._finish(record, QueryState.CANCELLED, "Abfrage abgebrochen.", 0)
        except (AdapterNotAvailable, AdapterError, UnauthorizedQueryError) as exc:
            self._finish(record, QueryState.FAILED, str(exc), 0)
        except Exception as exc:  # unerwartet: sichtbar machen, nicht verschlucken
            self._finish(record, QueryState.FAILED, f"Unerwarteter Fehler ({type(exc).__name__}): {exc}", 0)
        finally:
            with self._lock:
                self._adapters.pop(aq.query_id, None)
                self._cancelled.discard(aq.query_id)
        return record

    def _finish(self, record: QueryRecord, state: QueryState, message: str, count: int) -> None:
        self._update(record, state=state, message=message, finding_count=count, finished_at=now_iso())
        ev = Event(id=new_id("evt"), case_id=record.case_id, type=f"query.{state.value}",
                   summary=f"{record.adapter_id}: {record.kind.label_de} – {state.value} ({count} Einträge)",
                   ref_id=record.id, ts=record.finished_at)
        self.repo.put("event", ev, ts=ev.ts)
        self.audit.record(f"query.{state.value}", case_id=record.case_id, adapter_id=record.adapter_id,
                          detail={"query_id": record.id, "findings": count, "mode": record.mode.value})

    # ------------------------------------------------------- Steuerung
    def cancel(self, query_id: str) -> bool:
        with self._lock:
            adapter = self._adapters.get(query_id)
            running = query_id in self._futures
            if running:
                self._cancelled.add(query_id)
        if adapter is None:
            return False
        try:
            adapter.cancel_query(query_id)
        except Exception:
            pass
        self.audit.record("query.cancel_requested", adapter_id=adapter.id, detail={"query_id": query_id})
        return True

    def wait(self, query_id: str, timeout: Optional[float] = None) -> QueryRecord:
        with self._lock:
            fut = self._futures.get(query_id)
        if fut is None:
            rec = self.repo.get("query", query_id)
            if rec is None:
                raise KeyError(query_id)
            return rec
        return fut.result(timeout)

    def shutdown(self, wait: bool = True) -> None:
        self._pool.shutdown(wait=wait, cancel_futures=not wait)
