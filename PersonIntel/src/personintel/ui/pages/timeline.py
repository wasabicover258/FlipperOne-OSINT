"""Chronologische Ansicht aller Vorgaenge und Treffer eines Falls."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel

from ..widgets import Page, Table, cell


class TimelinePage(Page):
    id = "timeline"
    title = "Chronologie"
    hint = ("Zeitlicher Ablauf der Recherche: Zweckdokumentation, registrierte Kennungen, Abfragen und Treffer. "
            "Die Zeitstempel sind die Beobachtungszeitpunkte (UTC).")

    def build(self) -> None:
        self.table = Table(["Zeitpunkt (UTC)", "Art", "Vorgang", "Belegstufe"], stretch=2)
        self.body.addWidget(self.table, 1)
        self.info = QLabel("")
        self.body.addWidget(self.info)

    def refresh(self) -> None:
        if not self.ctx.has_case():
            self.table.fill([])
            self.info.setText("Kein Fall ausgewählt.")
            return
        entries = self.engine.timeline(self.ctx.case_id)
        self.table.fill([[cell(e.ts.replace("T", " ")), cell("Treffer" if e.kind == "finding" else "Vorgang"),
                          cell(e.summary, tooltip=e.summary), cell(e.evidence or "–")] for e in entries])
        self.info.setText(f"{len(entries)} Einträge. Verworfene Befunde erscheinen nicht in der Chronologie.")
