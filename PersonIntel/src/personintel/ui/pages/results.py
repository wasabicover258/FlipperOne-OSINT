"""Ergebnisse: Befunde mit Quelle, Zeitstempel und Belegstufe; Pruefvermerke des Bearbeiters."""

from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSplitter,
                               QTextBrowser, QVBoxLayout, QWidget)

from ...core.errors import PersonIntelError
from ...core.models import Evidence, FindingStatus, ReviewState
from ..dialogs import ReviewDialog
from ..style import FINDING_STATUS_LABEL, REVIEW_LABEL
from ..widgets import Page, Table, cell, evidence_item


class ResultsPage(Page):
    id = "results"
    title = "Ergebnisse"
    hint = ("Jeder Befund nennt Quelle, Zeitpunkt und Belegstufe. Die Belegstufe beschreibt, wie gut ein Befund "
            "belegt ist – nicht, dass eine Zuordnung zu einer Person bewiesen wäre.")

    def build(self) -> None:
        filt = QHBoxLayout()
        self.f_evidence = QComboBox()
        self.f_evidence.addItem("alle Belegstufen", None)
        for ev in Evidence:
            self.f_evidence.addItem(ev.label_de, ev.value)
        self.f_adapter = QComboBox()
        self.f_adapter.addItem("alle Module", None)
        self.f_status = QComboBox()
        self.f_status.addItem("alle Status", None)
        for s in FindingStatus:
            self.f_status.addItem(FINDING_STATUS_LABEL[s], s.value)
        self.f_review = QComboBox()
        self.f_review.addItem("alle Prüfstände", None)
        for r in ReviewState:
            self.f_review.addItem(REVIEW_LABEL[r], r.value)
        for w in (self.f_evidence, self.f_adapter, self.f_status, self.f_review):
            w.currentIndexChanged.connect(self.refresh)
            filt.addWidget(w)
        filt.addStretch(1)
        self.count = QLabel("")
        filt.addWidget(self.count)
        self.body.addLayout(filt)

        split = QSplitter(Qt.Vertical)
        self.table = Table(["Befund", "Wert / URL", "Belegstufe", "Status", "Prüfung", "Modul", "Zeitpunkt"],
                           stretch=0)
        self.table.itemSelectionChanged.connect(self._show_detail)
        split.addWidget(self.table)

        detail = QWidget()
        dl = QVBoxLayout(detail)
        dl.setContentsMargins(0, 0, 0, 0)
        box = QGroupBox("Einzelheiten und Herkunft")
        bl = QVBoxLayout(box)
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(False)
        bl.addWidget(self.detail)
        dl.addWidget(box, 1)
        btns = QHBoxLayout()
        self.b_review = QPushButton("Befund prüfen …")
        self.b_review.setObjectName("Primary")
        self.b_review.clicked.connect(self._review)
        self.b_reject = QPushButton("Verwerfen")
        self.b_reject.clicked.connect(self._reject)
        self.b_delete = QPushButton("Befund löschen")
        self.b_delete.setObjectName("Danger")
        self.b_delete.clicked.connect(self._delete)
        for b in (self.b_review, self.b_reject, self.b_delete):
            b.setEnabled(False)
            btns.addWidget(b)
        btns.addStretch(1)
        dl.addLayout(btns)
        split.addWidget(detail)
        split.setSizes([420, 300])
        self.body.addWidget(split, 1)

    # ------------------------------------------------------------------
    def _findings(self) -> list:
        if not self.ctx.has_case():
            return []
        out = self.engine.findings(self.ctx.case_id)
        ev, aid, st, rv = (self.f_evidence.currentData(), self.f_adapter.currentData(),
                           self.f_status.currentData(), self.f_review.currentData())
        if ev:
            out = [f for f in out if f.evidence.value == ev]
        if aid:
            out = [f for f in out if f.adapter_id == aid]
        if st:
            out = [f for f in out if f.status.value == st]
        if rv:
            out = [f for f in out if f.review_state.value == rv]
        return sorted(out, key=lambda f: (-f.evidence.rank, f.adapter_id, f.observed_at))

    def refresh(self) -> None:
        if not self.ctx.has_case():
            self.table.fill([])
            self.detail.clear()
            self.count.setText("")
            return
        all_f = self.engine.findings(self.ctx.case_id)
        current = self.f_adapter.currentData()
        self.f_adapter.blockSignals(True)
        self.f_adapter.clear()
        self.f_adapter.addItem("alle Module", None)
        for aid in sorted({f.adapter_id for f in all_f}):
            self.f_adapter.addItem(self.ctx.adapter_name(aid), aid)
        i = self.f_adapter.findData(current)
        self.f_adapter.setCurrentIndex(max(0, i))
        self.f_adapter.blockSignals(False)

        rows = []
        for f in self._findings():
            rows.append([cell(f.title, data=f.id, tooltip=f.title), cell(f.value or f.url or "–", tooltip=f.url),
                         evidence_item(f.evidence), cell(FINDING_STATUS_LABEL[f.status]),
                         cell(REVIEW_LABEL[f.review_state], tooltip=f.reviewer_note),
                         cell(self.ctx.adapter_name(f.adapter_id)),
                         cell(f.observed_at[:19].replace("T", " "))])
        self.table.fill(rows)
        n_conf = sum(1 for f in all_f if f.evidence is Evidence.CONFIRMED)
        n_ind = sum(1 for f in all_f if f.evidence is Evidence.INDICATION)
        n_unc = sum(1 for f in all_f if f.evidence is Evidence.UNCONFIRMED)
        self.count.setText(f"{len(rows)} von {len(all_f)} Befunden · belegt {n_conf} · Indiz {n_ind} · "
                           f"unbestätigt {n_unc}")
        self._show_detail()

    def _selected(self):
        fid = self.table.selected_data(0)
        return self.engine.repo.get("finding", fid) if fid else None

    def _show_detail(self) -> None:
        f = self._selected()
        for b in (self.b_review, self.b_reject, self.b_delete):
            b.setEnabled(f is not None)
        if f is None:
            self.detail.setHtml("<i>Keinen Befund ausgewählt.</i>")
            return
        src = self.engine.repo.get("source", f.source_id) if f.source_id else None
        q = self.engine.repo.get("query", f.query_id) if f.query_id else None
        esc = lambda s: (str(s) if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        parts = [f"<h3>{esc(f.title)}</h3>",
                 f"<p><b>Belegstufe:</b> {f.evidence.label_de} &nbsp; <b>Status:</b> "
                 f"{FINDING_STATUS_LABEL[f.status]} &nbsp; <b>Prüfung:</b> {REVIEW_LABEL[f.review_state]}</p>"]
        if f.value:
            parts.append(f"<p><b>Wert:</b> {esc(f.value)}</p>")
        if f.url:
            parts.append(f"<p><b>URL:</b> {esc(f.url)}</p>")
        parts.append(f"<p><b>Modul:</b> {esc(self.ctx.adapter_name(f.adapter_id))} &nbsp; "
                     f"<b>beobachtet:</b> {esc(f.observed_at)}</p>")
        if src:
            parts.append(f"<p><b>Quelle:</b> {esc(src.description)}<br>"
                         f"<b>Art:</b> {esc(src.kind)} &nbsp; <b>abgerufen:</b> {esc(src.retrieved_at)}<br>"
                         f"<b>Werkzeug/Version:</b> {esc(src.tool_version or '–')}<br>"
                         f"<b>Abfrage:</b> {'aktiv (Drittkontakt)' if src.active else 'passiv'}"
                         + (f"<br><b>Quell-URL:</b> {esc(src.url)}" if src.url else "") + "</p>")
        if q:
            parts.append(f"<p><b>Abfrage-ID:</b> {esc(q.id)} &nbsp; <b>Meldung:</b> {esc(q.message)}</p>")
        if f.reviewer_note:
            parts.append(f"<p><b>Prüfvermerk:</b> {esc(f.reviewer_note)} ({esc(f.reviewed_at)})</p>")
        if f.tags:
            parts.append(f"<p><b>Merkmale:</b> {esc(', '.join(f.tags))}</p>")
        if f.data:
            parts.append("<p><b>Normalisierte Angaben:</b></p><pre>"
                         + esc(json.dumps(f.data, ensure_ascii=False, indent=2)) + "</pre>")
        self.detail.setHtml("".join(parts))

    def _review(self) -> None:
        f = self._selected()
        if f is None:
            return
        dlg = ReviewDialog(f, parent=self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        v = dlg.values()
        try:
            self.engine.review_finding(f.id, v["state"], v["note"], v["evidence"])
        except PersonIntelError as exc:
            QMessageBox.warning(self, "Prüfung", str(exc))
            return
        self.ctx.notify("Prüfvermerk gespeichert.")

    def _reject(self) -> None:
        f = self._selected()
        if f is None:
            return
        self.engine.review_finding(f.id, ReviewState.REJECTED, f.reviewer_note or "verworfen")
        self.ctx.notify("Befund verworfen.")

    def _delete(self) -> None:
        f = self._selected()
        if f is None:
            return
        ans = QMessageBox.question(self, "Befund löschen", "Diesen Befund unwiderruflich löschen?",
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ans == QMessageBox.Yes:
            self.engine.delete_finding(f.id)
            self.ctx.notify("Befund gelöscht.")
