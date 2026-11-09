"""Dashboard: tatsaechlicher Betriebsstatus aller Module - ohne Beschoenigung."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout)

from ...adapters.base import AdapterState
from ..widgets import Page, Table, cell, state_item, warn_label


class DashboardPage(Page):
    id = "dashboard"
    title = "Übersicht"
    hint = ("Betriebsstatus der angebundenen Module. Angezeigt wird, was tatsächlich vorhanden ist: "
            "lokal installierte Werkzeuge, hinterlegte Zugangsdaten und – wo eine Funktion nicht verfügbar ist – "
            "die konkrete Voraussetzung.")

    def build(self) -> None:
        self.summary = QLabel("Status wird geprüft …")
        self.summary.setObjectName("CaseBanner")
        self.body.addWidget(self.summary)

        self.table = Table(["", "Modul", "Kategorie", "Status", "Version", "Voraussetzung / Meldung"], stretch=5)
        self.table.itemSelectionChanged.connect(self._selection)
        self.body.addWidget(self.table, 1)

        box = QGroupBox("Hinweise zur Recherchekontrolle")
        lay = QVBoxLayout(box)
        lay.addWidget(QLabel(
            "• Abfragen sind nur in einem Fall mit dokumentiertem Zweck möglich.\n"
            "• Aktive Prüfungen kontaktieren fremde Dienste und müssen pro Abfrage einzeln bestätigt werden.\n"
            "• Es werden keine Leak-Datenbanken mit Zugangsdaten genutzt, keine Konten übernommen und keine "
            "Zugangsbeschränkungen umgangen.\n"
            "• Befunde tragen immer eine Belegstufe: unmittelbar belegt, Indiz oder unbestätigt."))
        self.body.addWidget(box)

        buttons = QHBoxLayout()
        self.btn_refresh = QPushButton("Status neu prüfen")
        self.btn_refresh.setObjectName("Primary")
        self.btn_refresh.clicked.connect(self._refresh_clicked)
        self.btn_toggle = QPushButton("Modul deaktivieren")
        self.btn_toggle.clicked.connect(self._toggle)
        self.btn_toggle.setEnabled(False)
        self.btn_config = QPushButton("Konfigurieren …")
        self.btn_config.clicked.connect(self._configure)
        self.btn_config.setEnabled(False)
        buttons.addWidget(self.btn_refresh)
        buttons.addWidget(self.btn_toggle)
        buttons.addWidget(self.btn_config)
        buttons.addStretch(1)
        self.body.addLayout(buttons)

        self.ctx.statuses_changed.connect(self._render)

    # ------------------------------------------------------------------
    def _refresh_clicked(self) -> None:
        self.btn_refresh.setEnabled(False)
        self.summary.setText("Status wird geprüft …")
        self.ctx.refresh_statuses()

    def refresh(self) -> None:
        if not self.ctx.statuses:
            self.ctx.refresh_statuses()
        else:
            self._render()

    def _render(self) -> None:
        self.btn_refresh.setEnabled(True)
        statuses = {s.adapter_id: s for s in self.ctx.statuses}
        rows = []
        counts = {"ready": 0, "blocked": 0}
        for ad in self.engine.adapters():
            st = statuses.get(ad.id)
            if st is None:
                continue
            if st.state is AdapterState.AVAILABLE:
                counts["ready"] += 1
            else:
                counts["blocked"] += 1
            msg = st.requirement or st.message
            rows.append([cell("", data=ad.id), cell(ad.name, tooltip=ad.description),
                         cell(ad.category), state_item(st.state), cell(st.version or "–"),
                         cell(msg, tooltip=f"{st.message}\n\nLizenz: {st.license_status}\n"
                                           f"Verbindung: {st.connection_status}\nGeprüft: {st.checked_at}")])
        self.table.fill(rows)
        total = counts["ready"] + counts["blocked"]
        self.summary.setText(f"<b>{counts['ready']} von {total} Modulen betriebsbereit.</b> "
                             f"{counts['blocked']} Modul(e) benötigen eine Voraussetzung (Spalte rechts).")

    def _selection(self) -> None:
        aid = self.table.selected_data(0)
        self.btn_toggle.setEnabled(bool(aid))
        self.btn_config.setEnabled(bool(aid))
        if aid:
            enabled = self.engine.settings.is_enabled(aid)
            self.btn_toggle.setText("Modul deaktivieren" if enabled else "Modul aktivieren")

    def _toggle(self) -> None:
        aid = self.table.selected_data(0)
        if not aid:
            return
        new = not self.engine.settings.is_enabled(aid)
        self.engine.configure_adapter(aid, enabled=new)
        self.ctx.notify(f"{self.ctx.adapter_name(aid)}: {'aktiviert' if new else 'deaktiviert'}.", data=False)
        self._refresh_clicked()

    def _configure(self) -> None:
        aid = self.table.selected_data(0)
        if aid:
            self.ctx.message.emit(f"Einstellungen für {self.ctx.adapter_name(aid)} geöffnet.", False)
            win = self.window()
            if hasattr(win, "show_page"):
                win.show_page("settings", adapter_id=aid)
