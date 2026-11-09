"""Einstellungen: Modulkonfiguration, Zugangsdaten, Grenzen der Recherchekontrolle, Verschluesselung."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QSpinBox,
                               QSplitter, QVBoxLayout, QWidget)

from ...core.errors import PersonIntelError
from ..dialogs import PassphraseDialog
from ..widgets import Page, warn_label


class SettingsPage(Page):
    id = "settings"
    title = "Einstellungen"
    hint = ("Je Modul werden hier Pfade, Optionen und Zugangsdaten hinterlegt. Geheimnisse liegen verschlüsselt im "
            "lokalen Zugangsdatenspeicher und werden nie in die Einstellungsdatei, das Protokoll oder einen Export "
            "geschrieben.")

    def build(self) -> None:
        split = QSplitter(Qt.Horizontal)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(lambda _: self._show_adapter())
        split.addWidget(self.list)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)

        self.cred_box = QGroupBox("Zugangsdatenspeicher")
        cl = QHBoxLayout(self.cred_box)
        self.cred_state = QLabel("")
        cl.addWidget(self.cred_state, 1)
        self.b_unlock = QPushButton("Entsperren / anlegen …")
        self.b_unlock.clicked.connect(self._unlock)
        cl.addWidget(self.b_unlock)
        rl.addWidget(self.cred_box)

        self.form_box = QGroupBox("Modul")
        self.form_area = QScrollArea()
        self.form_area.setWidgetResizable(True)
        fl = QVBoxLayout(self.form_box)
        fl.addWidget(self.form_area)
        rl.addWidget(self.form_box, 1)

        limits = QGroupBox("Grenzen der Recherchekontrolle")
        lf = QFormLayout(limits)
        self.max_targets = QSpinBox()
        self.max_targets.setRange(1, 50)
        self.max_daily = QSpinBox()
        self.max_daily.setRange(1, 500)
        self.min_interval = QSpinBox()
        self.min_interval.setRange(0, 3600)
        self.min_interval.setSuffix(" s")
        self.timeout = QSpinBox()
        self.timeout.setRange(10, 3600)
        self.timeout.setSuffix(" s")
        lf.addRow("Kennungen je Fall (höchstens):", self.max_targets)
        lf.addRow("Aktive Prüfungen je Fall und Tag:", self.max_daily)
        lf.addRow("Mindestabstand aktiver Abfragen:", self.min_interval)
        lf.addRow("Zeitgrenze je Abfrage:", self.timeout)
        self.backend = QComboBox()
        self.backend.addItem("verschlüsselte Datei (Standard)", "file")
        self.backend.addItem("System-Schlüsselbund (Paket „keyring“)", "keyring")
        lf.addRow("Zugangsdaten speichern in:", self.backend)
        b_save = QPushButton("Grenzen speichern")
        b_save.setObjectName("Primary")
        b_save.clicked.connect(self._save_limits)
        lf.addRow("", b_save)
        rl.addWidget(limits)

        enc = QGroupBox("Datenhaltung")
        el = QVBoxLayout(enc)
        self.enc_state = QLabel("")
        self.enc_state.setWordWrap(True)
        el.addWidget(self.enc_state)
        eb = QHBoxLayout()
        self.b_encrypt = QPushButton("Datenbank verschlüsseln …")
        self.b_encrypt.clicked.connect(self._encrypt)
        eb.addWidget(self.b_encrypt)
        eb.addStretch(1)
        el.addLayout(eb)
        el.addWidget(QLabel("Alle Daten bleiben lokal. Es werden keine Rohdaten der Werkzeuge gespeichert, "
                            "sondern nur normalisierte Befunde mit Herkunftsnachweis."))
        rl.addWidget(enc)

        split.addWidget(right)
        split.setSizes([260, 760])
        self.body.addWidget(split, 1)
        self._widgets: dict[str, QWidget] = {}
        self._current: Optional[str] = None
        self._fill_list()

    # ------------------------------------------------------------------
    def _fill_list(self) -> None:
        self.list.clear()
        for ad in self.engine.adapters():
            it = QListWidgetItem(ad.name)
            it.setData(Qt.UserRole, ad.id)
            self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)

    def select_adapter(self, adapter_id: str) -> None:
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == adapter_id:
                self.list.setCurrentRow(i)
                return

    def refresh(self) -> None:
        lim = self.engine.settings.limits
        self.max_targets.setValue(lim.max_targets_per_case)
        self.max_daily.setValue(lim.max_active_queries_per_case_per_day)
        self.min_interval.setValue(int(lim.min_active_interval_seconds))
        self.timeout.setValue(lim.query_timeout_seconds)
        i = self.backend.findData(self.engine.settings.credential_backend)
        self.backend.setCurrentIndex(max(0, i))
        locked = self.engine.credentials.locked
        self.cred_state.setText("<b style='color:#a62121'>gesperrt</b> – geheime Felder können nicht gelesen oder "
                                "gespeichert werden." if locked
                                else "<b style='color:#1b7f3a'>entsperrt</b> – geheime Felder sind verfügbar.")
        encrypted = self.engine.repo.is_encrypted
        self.enc_state.setText(
            "Datenbank: <b style='color:#1b7f3a'>verschlüsselt</b> (Fernet, Schlüssel aus Passphrase)."
            if encrypted else
            "Datenbank: <b>unverschlüsselt</b>. Die Inhalte können nachträglich verschlüsselt werden; "
            "danach ist beim Start eine Passphrase nötig.")
        self.b_encrypt.setEnabled(not encrypted)
        self._show_adapter()

    def _show_adapter(self) -> None:
        it = self.list.currentItem()
        if it is None:
            return
        aid = it.data(Qt.UserRole)
        self._current = aid
        ad = self.engine.adapter(aid)
        st = ad.get_status()
        panel = QWidget()
        lay = QVBoxLayout(panel)
        self.form_box.setTitle(f"{ad.name} – {ad.category}")
        head = QLabel(f"<b>{ad.description}</b><br>Status: {st.state.label_de}"
                      + (f"<br>Voraussetzung: {st.requirement}" if st.requirement else "")
                      + (f"<br>{st.message}" if st.message else "")
                      + (f"<br>Lizenz: {st.license_status} · Verbindung: {st.connection_status}"
                         if st.license_status != "n/a" else "")
                      + (f"<br>Projektseite: {ad.homepage}" if ad.homepage else ""))
        head.setWordWrap(True)
        lay.addWidget(head)

        self.enabled_cb = QCheckBox("Modul aktiv")
        self.enabled_cb.setChecked(self.engine.settings.is_enabled(aid))
        lay.addWidget(self.enabled_cb)

        caps = QLabel("<b>Funktionen:</b><br>" + "<br>".join(
            f"• {c.label} – {'verfügbar' if c.available else 'nicht verfügbar'}"
            f" ({'aktive Prüfung' if c.mode.value == 'active' else 'passiv'})"
            + (f"<br>&nbsp;&nbsp;{c.reason}" if not c.available and c.reason else "")
            for c in ad.get_capabilities()))
        caps.setWordWrap(True)
        lay.addWidget(caps)

        form = QFormLayout()
        self._widgets = {}
        for field in ad.config_fields:
            w = QLineEdit()
            if field.secret:
                w.setEchoMode(QLineEdit.Password)
                w.setPlaceholderText("gespeichert – zum Ändern neuen Wert eingeben"
                                     if ad.secrets.has(field.key) else "noch nicht hinterlegt")
            else:
                w.setText(str(self.engine.settings.adapter_config.get(aid, {}).get(field.key, field.default or "")))
            if field.help:
                w.setToolTip(field.help)
            label = field.label + (" *" if field.required else "")
            form.addRow(label + ":", w)
            if field.help:
                hint = QLabel(field.help)
                hint.setWordWrap(True)
                hint.setStyleSheet("color:#4b5a68; font-size:11px")
                form.addRow("", hint)
            self._widgets[field.key] = w
        if not ad.config_fields:
            form.addRow(QLabel("Dieses Modul braucht keine Konfiguration."))
        lay.addLayout(form)

        btns = QHBoxLayout()
        b_save = QPushButton("Speichern")
        b_save.setObjectName("Primary")
        b_save.clicked.connect(self._save_adapter)
        btns.addWidget(b_save)
        if hasattr(ad, "test_connection"):
            b_test = QPushButton("Zugang testen")
            b_test.clicked.connect(self._test_connection)
            btns.addWidget(b_test)
        secret_keys = [f.key for f in ad.config_fields if f.secret and ad.secrets.has(f.key)]
        if secret_keys:
            b_clear = QPushButton("Zugangsdaten löschen")
            b_clear.setObjectName("Danger")
            b_clear.clicked.connect(self._clear_secrets)
            btns.addWidget(b_clear)
        btns.addStretch(1)
        lay.addLayout(btns)
        lay.addWidget(warn_label(
            "Zugangsdaten können auch über Umgebungsvariablen bereitgestellt werden "
            f"(z. B. PERSONINTEL_{aid.upper()}_API_KEY) – dann werden sie nicht gespeichert."))
        lay.addStretch(1)
        self.form_area.setWidget(panel)

    # ----------------------------------------------------------- Aktionen
    def _save_adapter(self) -> None:
        aid = self._current
        if not aid:
            return
        ad = self.engine.adapter(aid)
        config, secrets = {}, {}
        for field in ad.config_fields:
            text = self._widgets[field.key].text().strip()
            if field.secret:
                if text:
                    secrets[field.key] = text
            else:
                config[field.key] = text
        if secrets and self.engine.credentials.locked:
            QMessageBox.warning(self, "Zugangsdaten", "Der Zugangsdatenspeicher ist gesperrt. Bitte zuerst "
                                                      "entsperren oder anlegen.")
            return
        try:
            st = self.engine.configure_adapter(aid, config=config, secrets=secrets,
                                               enabled=self.enabled_cb.isChecked())
        except PersonIntelError as exc:
            QMessageBox.warning(self, "Einstellungen", str(exc))
            return
        self.ctx.message.emit(f"{ad.name}: gespeichert – {st.state.label_de}", False)
        self.ctx.refresh_statuses()
        self.refresh()

    def _clear_secrets(self) -> None:
        aid = self._current
        ad = self.engine.adapter(aid)
        keys = [f.key for f in ad.config_fields if f.secret]
        self.engine.configure_adapter(aid, clear_secrets=keys)
        self.ctx.message.emit(f"{ad.name}: Zugangsdaten gelöscht.", False)
        self.ctx.refresh_statuses()
        self.refresh()

    def _test_connection(self) -> None:
        aid = self._current
        ad = self.engine.adapter(aid)

        def done(result):
            ok, msg = result
            QMessageBox.information(self, "Zugang testen", msg)
            self.ctx.refresh_statuses()
            self.refresh()

        def failed(msg):
            QMessageBox.warning(self, "Zugang testen", msg)
        self.ctx.message.emit(f"{ad.name}: Zugang wird getestet …", False)
        self.ctx.run_async(ad.test_connection, done, failed)

    def _unlock(self) -> None:
        from ...security.credentials import EncryptedFileBackend
        backend = self.engine.credentials.backend
        if not isinstance(backend, EncryptedFileBackend):
            QMessageBox.information(self, "Zugangsdaten", "Es wird der System-Schlüsselbund verwendet; eine "
                                                          "Passphrase ist nicht nötig.")
            return
        exists = backend.exists
        dlg = PassphraseDialog(
            "Zugangsdatenspeicher " + ("entsperren" if exists else "anlegen"),
            "Passphrase des verschlüsselten Zugangsdatenspeichers." if exists else
            "Es wird ein neuer, verschlüsselter Zugangsdatenspeicher angelegt. Die Passphrase kann nicht "
            "zurückgesetzt werden.", confirm=not exists, parent=self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        try:
            self.engine.unlock_credentials(dlg.passphrase)
        except PersonIntelError as exc:
            QMessageBox.warning(self, "Zugangsdaten", str(exc))
            return
        self.ctx.message.emit("Zugangsdatenspeicher entsperrt.", False)
        self.refresh()

    def _encrypt(self) -> None:
        dlg = PassphraseDialog("Datenbank verschlüsseln",
                               "Alle vorhandenen Inhalte werden verschlüsselt. Ohne diese Passphrase sind die "
                               "Daten danach nicht mehr lesbar – sie kann nicht zurückgesetzt werden.",
                               confirm=True, parent=self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        try:
            self.engine.repo.encrypt_existing(dlg.passphrase)
        except PersonIntelError as exc:
            QMessageBox.warning(self, "Verschlüsselung", str(exc))
            return
        self.engine.audit.record("storage.encrypted")
        QMessageBox.information(self, "Verschlüsselung",
                                "Die Datenbank ist jetzt verschlüsselt. Beim nächsten Start wird die Passphrase "
                                "abgefragt.")
        self.refresh()

    def _save_limits(self) -> None:
        s = self.engine.settings
        s.limits.max_targets_per_case = self.max_targets.value()
        s.limits.max_active_queries_per_case_per_day = self.max_daily.value()
        s.limits.min_active_interval_seconds = float(self.min_interval.value())
        s.limits.query_timeout_seconds = self.timeout.value()
        s.credential_backend = self.backend.currentData()
        s.save(self.engine.paths.settings_path)
        self.engine.gate.limits = s.limits
        self.engine.audit.record("settings.limits", detail={
            "max_targets": s.limits.max_targets_per_case,
            "max_active_per_day": s.limits.max_active_queries_per_case_per_day,
            "min_interval": s.limits.min_active_interval_seconds})
        self.ctx.message.emit("Grenzen gespeichert. Der Speicherort der Zugangsdaten wirkt beim nächsten Start.",
                              False)
