# Verschmelzung mit einer Hauptanwendung

PersonIntel ist als Teilmodul gebaut. Dieses Dokument beschreibt die Schnittstellen, auf die eine
übergeordnete System-OSINT-Anwendung sich verlassen kann, und wie die Bestandteile einzeln
übernommen werden.

## 1. Paket-Schnittstelle

Stabil ist **ausschließlich** `personintel.api`. Alles andere ist Innenleben.

```python
from personintel.api import PersonIntel, AppPaths, Purpose, ActiveConfirmation, QueryKind

pi = PersonIntel(AppPaths(data_dir=Path("…/data"), config_dir=Path("…/config")))

case = pi.create_case("Recherche X")
pi.set_purpose(case.id, Purpose(category="journalism",
                                description="Verifikation einer Quelle für Artikel Y",
                                authorized_by="Redaktionsleitung",
                                active_checks_allowed=True), days_valid=30)

target = pi.add_target(case.id, QueryKind.EMAIL, "person@example.org")
rec = pi.run_query(case.id, "holehe", target.id,
                   confirmation=ActiveConfirmation(typed_target="person@example.org",
                                                   acknowledges_third_party_contact=True,
                                                   acknowledges_terms_of_service=True))
rec = pi.wait(rec.id, timeout=120)

for f in pi.findings(case.id):
    print(f.evidence.label_de, f.title, f.url)

bundle = pi.export_case(case.id)
report = pi.build_report(case.id)          # .to_markdown() / .to_html() / .to_json()
pi.close()
```

Wichtige Methoden: `adapters()`, `statuses()`, `configure_adapter()`, `unlock_credentials()`,
`cases()`, `create_case()`, `set_purpose()`, `delete_case()`, `add_target()`, `targets()`,
`remove_target()`, `run_query()`, `cancel_query()`, `wait()`, `queries()`, `findings()`,
`sources()`, `review_finding()`, `delete_finding()`, `delete_query_data()`, `timeline()`,
`export_case()`, `import_case()`, `build_report()`, `register_adapter()`, `close()`.
Dazu die Felder `graph`, `audit`, `jobs`, `settings`, `paths`, `repo`, `registry`.

Mehrere Instanzen sind möglich und voneinander unabhängig: jede bekommt ihr eigenes
`AppPaths`-Paar. Innerhalb eines Prozesses kann eine Hauptanwendung also mehrere getrennte
Datenbestände verwalten.

Es gibt **keine** festverdrahtete Bindung an eine Wirtsanwendung: keine globalen Zustände, keine
erwarteten Umgebungsvariablen (die `PERSONINTEL_*`-Variablen sind optional), keine Annahme über
das Arbeitsverzeichnis, kein Netzwerkdienst.

## 2. Versionierung

| Gegenstand | Konstante | Regel |
|---|---|---|
| Paketversion | `personintel.__version__` | semantisch |
| Ergebnis-/Austauschformat | `personintel.RESULT_SCHEMA_VERSION` (`"1.0"`) | gleiche Hauptversion ist importierbar; unbekannte Felder werden ignoriert |
| Austauschformat-Kennung | `personintel.EXCHANGE_FORMAT` (`"personintel.case"`) | – |

Zusagen für die Hauptversion 1 des Formats: vorhandene Feldnamen und Aufzählungswerte
verschwinden nicht und ändern ihre Bedeutung nicht; neue Felder dürfen hinzukommen. Ein
Lesegerät darf unbekannte Felder verwerfen.

## 3. Austauschformat

`pi.export_case(case_id)` liefert ein JSON-fähiges Dict:

```json
{
  "format": "personintel.case",
  "schema_version": "1.0",
  "exported_at": "2026-11-09T07:00:00+00:00",
  "origin": {"app": "personintel", "version": "0.1.0"},
  "case":     {"id": "case_…", "name": "…", "purpose": {…}},
  "targets":  [{"id": "tgt_…", "case_id": "case_…", "kind": "email", "value": "…"}],
  "sources":  [{"id": "src_…", "adapter_id": "holehe", "retrieved_at": "…", "tool_version": "…", "active": true}],
  "findings": [{"id": "fnd_…", "type": "account", "title": "…", "evidence": "indication",
                "status": "found", "review_state": "unreviewed", "source_id": "src_…",
                "target_id": "tgt_…", "query_id": "qry_…", "data": {…}, "tags": ["…"]}],
  "queries":  [{"id": "qry_…", "adapter_id": "holehe", "kind": "email", "mode": "active", "state": "done"}],
  "events":   [{"id": "evt_…", "type": "query.done", "summary": "…", "ts": "…"}],
  "graph":    {"nodes": [{"id": "nod_…", …}], "edges": [{"id": "edg_…", "basis_finding_ids": ["fnd_…"], …}]}
}
```

* **IDs** sind präfixiert und global eindeutig: `case_`, `tgt_`, `src_`, `fnd_`, `qry_`, `evt_`,
  `nod_`, `edg_` plus 16 Hexstellen. `personintel.core.ids.new_id(prefix)` erzeugt sie,
  `is_valid_id(value, prefix)` prüft sie.
* **Zeitstempel** sind UTC nach ISO 8601, auf Sekunden gerundet.
* **Aufzählungen** werden als Zeichenkette geschrieben: `evidence` = `confirmed|indication|unconfirmed`,
  `status` = `found|possible|not_found|failed|info`, `review_state` = `unreviewed|reviewed|rejected`,
  `kind` = `email|username|phone|name|report_file`, `mode` = `passive|active`.
* **Import:** `pi.import_case(bundle)` prüft Format, Hauptversion und Struktur
  (`validate_bundle` wirft `ExchangeError` mit verständlicher Meldung). Kollidieren IDs mit dem
  Zielbestand, werden **alle** IDs des Bündels konsistent neu vergeben – Querverweise
  (`source_id`, `target_id`, `basis_finding_ids` …) bleiben erhalten; der Fallname erhält den
  Zusatz „(Import)“.
* Das **Protokoll** wird nicht exportiert: es ist lokal, enthält keine Rechercheinhalte und seine
  Hash-Kette gilt nur für die eigene Datenbank.

## 4. Module einzeln einbinden

Adapter sind unabhängig von Oberfläche und Engine nutzbar, solange die Autorisierung aus dem
Gate kommt:

```python
from personintel.adapters import BUILTIN_ADAPTERS, HoleheAdapter

ad = HoleheAdapter()
ad.bind(config={}, secrets=my_secret_reader, enabled=True)
print(ad.get_status().state.label_de, ad.get_capabilities())
```

`bind()` erwartet ein Dict, ein Objekt mit `get(field)`/`has(field)` und ein Flag — eine
Hauptanwendung kann ihre eigene Konfigurations- und Geheimnisverwaltung durchreichen, ohne den
Credential-Store von PersonIntel zu übernehmen.

Eigene Module zur Laufzeit registrieren:

```python
pi.register_adapter(MeinAdapter)                      # sofort im Dashboard und in der Recherche
```

Oder über Entry-Points eines eigenen Pakets:

```toml
[project.entry-points."personintel.adapters"]
meinmodul = "meinpaket.adapter:MeinAdapter"

[project.entry-points."personintel.ui_pages"]
meineseite = "meinpaket.ui:page_spec"        # PageSpec oder Fabrik, die eine liefert
```

Geladen wird mit `Engine(..., load_plugins=True)`; fehlerhafte Plugins werden in
`engine.plugin_problems` gemeldet und verhindern den Start nicht.

## 5. Oberfläche einbinden oder ersetzen

Die Seiten sind eigenständige `QWidget`-Klassen, die nur einen `AppContext` brauchen:

```python
from personintel.ui.context import AppContext
from personintel.ui.pages.dashboard import DashboardPage
from personintel.ui.pages.results import ResultsPage

ctx = AppContext(pi)                       # pi = PersonIntel-Instanz
host_tabs.addTab(DashboardPage(ctx), "OSINT-Module")
host_tabs.addTab(ResultsPage(ctx), "Befunde")
```

`AppContext` liefert die Signale `case_changed`, `data_changed`, `cases_changed`,
`query_updated`, `statuses_changed` und `message` sowie `run_async()` für Hintergrundarbeit.
`ctx.set_case(case_id)` schaltet alle angeschlossenen Seiten um; `ctx.shutdown()` beendet die
Beobachtung sauber.

Eine Hauptanwendung kann auch nur einzelne Seiten übernehmen, eigene Seiten per
`registry.register_page(PageSpec(...))` ergänzen oder die Oberfläche vollständig ersetzen und nur
`personintel.api` nutzen. Für eine Einbettung ohne eigenes Fenster ist `MainWindow` nicht nötig.

## 6. Headless-Betrieb

`personintel-cli` deckt Status, Fallliste, Export, Import, Bericht und Protokollprüfung ab –
bewusst **ohne** Recherchebefehle, weil aktive Prüfungen eine Bestätigung pro Abfrage verlangen.
Eine Hauptanwendung, die automatisiert abfragen will, benutzt `personintel.api` und muss die
Bestätigung selbst von einem Menschen einholen; `ActiveConfirmation` lässt sich nicht umgehen,
und die Protokollierung vermerkt die mitgegebene Notiz.

## 7. Checkliste für die Verschmelzung

1. `pip install personintel` (oder als Teilbaum übernehmen) und `AppPaths` auf die Verzeichnisse
   der Hauptanwendung zeigen lassen.
2. Zugangsdaten entweder PersonIntel verwalten lassen (`unlock_credentials`) oder beim
   `bind()` der Adapter durchreichen.
3. Fälle der Hauptanwendung auf PersonIntel-Fälle abbilden – oder Fälle über das
   Austauschformat ein- und ausspielen.
4. Oberfläche: Seiten einzeln einhängen oder ersetzen.
5. Eigene Module als Entry-Point-Plugins statt als Änderung im Paket.
6. Protokoll und Berichte unverändert übernehmen; sie sind Teil der Nachweiskette.
