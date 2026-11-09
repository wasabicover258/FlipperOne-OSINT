# Aufbau

## Schichten

```
personintel/
  core/        Modelle, Validierung, Einstellungen, Engine, Jobs, Plugin-Registry
  adapters/    die zehn Connectoren + gemeinsame Basis (Prozess, HTTP, Normalisierung)
  security/    Autorisierung, Audit-Protokoll, Verschlüsselung, Zugangsdaten
  storage/     SQLite-Repository und Migrationen
  graph/       Knoten, Kanten, Layout
  reports/     Berichtsgenerator (Markdown, HTML, JSON)
  exchange/    versioniertes JSON-Austauschformat
  ui/          PySide6-Oberfläche (Seiten einzeln austauschbar)
  api.py       stabile Schnittstelle für die Einbindung
  cli.py       headless-Kommandozeile
```

Abhängigkeiten laufen nur nach innen: `ui` → `api`/`core` → `adapters`/`storage`/`security`.
Die Oberfläche spricht **nie** direkt mit einem Adapter, die Adapter **nie** mit der Datenbank.

## Die Engine als einzige Fassade

`personintel.core.engine.Engine` (exportiert als `personintel.api.PersonIntel`) hält Repository,
Audit-Protokoll, Autorisierung, Jobverwaltung, Graph und Adapter zusammen. Oberfläche, CLI und
eine spätere Hauptanwendung nutzen ausschließlich diese Klasse.

## Ablauf einer Abfrage

```
Oberfläche
   │ engine.run_query(case, adapter, target, confirmation, options)
   ▼
AuthorizationGate.authorize()         ← prüft Zweck, Fallumfang, Art, Modus, Budget, Bestätigung
   │ AuthorizedQuery (HMAC-signiert, unveränderlich)
   ▼
JobManager.submit()                   → Threadpool, Abfrage-Datensatz, Ereignis, Protokoll
   │
   ▼
Adapter.execute_authorized_query()    ← require_valid() lehnt alles ohne gültige Signatur ab
   │ RawResult (nur im Speicher)
   ▼
Adapter.normalize_results()           → Source + Finding (mit Belegstufe)
   │
   ▼
Repository                            → speichert nur normalisierte Befunde
```

Jeder Schritt ist einzeln abweisbar, und jede Ablehnung wird protokolliert. Weil die
Autorisierung signiert und `frozen` ist, kann ein Adapter nicht versehentlich – oder durch
fehlerhaften Fremdcode – mit einer selbstgebauten Abfrage aufgerufen werden: `require_valid`
prüft die Signatur über alle Felder einschließlich Kennung und Modus. Der Schlüssel ist
prozesslokal und zufällig (`os.urandom`), gilt also nur für die laufende Sitzung.

## Recherchekontrolle im Einzelnen

Die Regeln stehen in `security/authorization.py` und sind durch Tests abgedeckt:

1. **Zweck** – Kategorie, Beschreibung (≥ 20 Zeichen), verantwortliche Person, befristet
   (höchstens 90 Tage). Ohne gültigen Zweck wird jede Abfrage abgelehnt.
2. **Fallumfang** – die Kennung muss im Fall registriert sein; höchstens zehn Kennungen pro Fall.
   Für eine weitere Person ist ein eigener Fall mit eigenem Zweck nötig.
3. **Kennungsart** – muss vom Zweck erlaubt sein und zur registrierten Kennung passen.
4. **Einzelkennung** – `core/validation.py` weist Listen, Zeilenumbrüche, Platzhalter und
   Mustersuchen ab und normalisiert (E-Mail klein, Telefon E.164 mit `phonenumbers`).
5. **Aktive Prüfungen** – nur wenn der Zweck sie erlaubt, nur mit erneuter Eingabe der Kennung
   und zwei Bestätigungen (Drittkontakt, Nutzungsbedingungen), begrenzt durch Tagesbudget
   (25 pro Fall) und Mindestabstand (5 s pro Modul).
6. **Keine Stapelverarbeitung** – eine Autorisierung gilt für genau eine Kennung und genau ein
   Modul.

## Belegstufen

`Evidence` kennt drei Stufen, die in jeder Ansicht und im Bericht mitlaufen:

| Stufe | Bedeutung | Wer setzt sie |
|---|---|---|
| **unmittelbar belegt** | Die Quelle selbst belegt die Aussage. | Nur der Bearbeiter, und nur mit Begründung. |
| **Indiz** | Ein Hinweis aus einer nachvollziehbaren Quelle, kein Beweis. | Adapter (z. B. ein von Holehe gemeldetes Konto), Bearbeiter. |
| **unbestätigt** | Rohhinweis, Suchvorschlag, Angabe eines Anbieterdatensatzes. | Adapter, Bearbeiter. |

Adapter geben **nie** „unmittelbar belegt“ aus. Ein Werkzeugtreffer ist höchstens ein Indiz;
Module mit bekanntem Rate-Limit-Problem liefern „möglicher Treffer“ und „unbestätigt“.

## Protokoll

`security/audit.py` schreibt eine `append-only`-Tabelle mit SHA-256-Hash-Kette: jeder Eintrag
bindet den Hash des Vorgängers ein, `verify()` findet den ersten Bruch. Protokolliert werden
Freigaben, Ablehnungen (mit Grund), Abfrageergebnisse, Prüfvermerke, Konfigurationsänderungen,
Export und Import.

Kennungen stehen **nie** im Klartext im Protokoll, sondern als HMAC-Pseudonym (`target_ref`,
lokaler Zufallsschlüssel in `meta`). Damit bleibt nachvollziehbar, *dass* und *wie oft* eine
Kennung abgefragt wurde, ohne sie offenzulegen. Schlüssel- und tokenartige Felder werden vor dem
Schreiben entfernt.

## Speicher

SQLite mit `PRAGMA user_version`-Migrationen (`storage/migrations.py`, nur anhängen).
Tabellen: `meta`, `cases`, `records` (`target|source|finding|query|event|node|edge`), `audit`.
Die Nutzlast liegt als JSON; bei aktivierter Verschlüsselung Fernet-verschlüsselt mit Präfix
`enc1:`. IDs, Zeitstempel und Datensatzart bleiben im Klartext, damit Indizes und gezieltes
Löschen funktionieren.

## Adapter

Jeder Connector erbt von `adapters/base.Adapter` und implementiert:

```python
detect_installation()        -> InstallInfo        # ist das Werkzeug wirklich da?
get_capabilities()           -> list[Capability]   # welche Eingabe, passiv/aktiv, verfügbar?
validate_configuration()     -> ConfigValidation
execute_authorized_query(aq) -> RawResult          # beginnt mit self._authorize(aq)
cancel_query(query_id)       -> bool
normalize_results(raw)       -> NormalizedBatch    # Source + Finding mit Belegstufe
get_status()                 -> AdapterStatus      # für das Dashboard
```

Gemeinsame Hilfen: `_process.py` (eigene Prozessgruppe, abbrechbar, Zeit- und Ausgabegrenze,
bereinigte Umgebung, Flags nur wenn `--help` sie kennt), `_http.py` (Standardbibliothek,
HTTPS erzwungen außer Loopback, Geheimnisse werden aus Fehlermeldungen entfernt), `_norm.py`
(Quellen und Befunde erzeugen, geheimnisartige Felder entfernen), `_local.py` (lokale Werkzeuge),
`_commercial.py` (Cloud-APIs samt Verbindungs- und Lizenzstand), `_vendor_contract.py` (Anbieter
ohne öffentliche Dokumentation).

### Neuen Anbieter anbinden

Für einen Anbieter, dessen Dokumentation noch fehlt, genügt die Unterklasse von
`VendorContractAdapter` (so arbeiten ShadowDragon und Babel Street): Konfigurationsfelder,
Statusanzeige und eine klare Voraussetzung sind damit vorhanden, die Recherche bleibt
ausdrücklich „nicht verfügbar“.

Sobald die Dokumentation vorliegt:

```python
class MeinAnbieterAdapter(CommercialAdapter):
    id, name, vendor, category, description, homepage = ...

    def get_capabilities(self):
        ok = self.has_key()
        return [Capability(QueryKind.EMAIL, QueryMode.ACTIVE, "Suche nach E-Mail",
                           "Übermittelt die Adresse an …", available=ok,
                           reason="" if ok else self.missing_requirement(),
                           cost_note=self.cost_note)]

    def execute_authorized_query(self, query):
        aq = self._authorize(query)                      # Pflicht
        key = self.api_key()
        started = now_iso()
        self._check_cancel(aq.query_id)
        resp = _http.request("GET", f"{self._base()}/suche",
                             params={"email": aq.value},
                             headers={"Authorization": f"Bearer {key}"},
                             timeout=45, secrets=(key,))
        if resp.status != 200:
            raise self._http_error(resp.status)           # 401/403/429 werden übersetzt
        self._set_conn("ok")
        return self._raw(aq, started, {"response": resp.json})

    def normalize_results(self, raw):
        batch = NormalizedBatch()
        src = make_source(raw, "Anbieter-API", kind="api", active=True)
        batch.sources.append(src)
        ...                                               # Belegstufe höchstens INDICATION
        return batch
```

Registrieren über `BUILTIN_ADAPTERS` (im Projekt) oder zur Laufzeit über
`engine.register_adapter(cls)` bzw. einen Entry-Point (siehe [FUSION.md](FUSION.md)).

Beim Normalisieren gelten drei Regeln: Rohantworten nicht speichern; Wohnadressen, Geburtsdaten
und Verwandte nicht übernehmen; Anbieterdatensätze sind höchstens ein **Indiz** und werden mit
`tags=["vendor-record"]` sowie einem Hinweis im Feld `data` gekennzeichnet.

## Graph

Knoten und Kanten entstehen ausschließlich durch eine Aktion des Bearbeiters
(`created_by="analyst"`). Jede Kante nennt mindestens einen Basisbefund desselben Falls; ihre
Belegstufe ist durch die beste Belegstufe dieser Befunde gedeckelt. Verworfene Befunde können
nicht als Beleg dienen. Die Gleichsetzung zweier Identitäten (`same_person`) verlangt zusätzlich
eine Begründung, mindestens die Stufe „Indiz“ und mindestens einen Beleg, der **nicht** allein
auf einem identischen Benutzernamen beruht. `suggest_links()` liefert nur unverbindliche
Hinweise und speichert nichts.

## Nebenläufigkeit

`core/jobs.py` nutzt einen Threadpool (Standard: drei gleichzeitige Abfragen). Jeder Job
schreibt Zustandsänderungen in den Abfrage-Datensatz und meldet sie an registrierte Beobachter.
Die Oberfläche setzt darauf einen Qt-Signalbrücke (`ui/context.py`), damit Rückmeldungen aus
Arbeitsthreads im GUI-Thread ankommen. Abbrechen erreicht die laufende Abfrage über
`Adapter.cancel_query` (bei Prozessen per Prozessgruppen-Signal).

## Grenzen des Entwurfs

* Rate-Limits und Zugangsbeschränkungen werden nicht umgangen, sondern als Ergebnis gemeldet.
  Eine Abfrage, die am Limit scheitert, gilt als fehlgeschlagen und macht die Ergebnislage
  ausdrücklich unvollständig.
* Der Prozessschlüssel der Autorisierung schützt gegen Programmierfehler und Fremdcode im
  gleichen Prozess, nicht gegen einen Angreifer mit Schreibrechten auf dem Rechner.
* Verschlüsselung schützt ruhende Daten. Läuft das Programm mit entsperrter Datenbank, sind die
  Inhalte im Speicher lesbar.
