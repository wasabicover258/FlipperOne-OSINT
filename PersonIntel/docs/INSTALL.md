# Installation und Betrieb

## 1. PersonIntel selbst

Voraussetzung: Linux, Python ≥ 3.10.

```bash
git clone <dieses Repository>
cd PersonIntel
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[ui]'          # mit Oberfläche
# pip install -e '.'            # nur Kern + Kommandozeile (headless/Server)
```

Start:

```bash
personintel                     # Oberfläche
personintel --data-dir ~/recherche-A   # eigenes Daten-/Konfigurationsverzeichnis
personintel-cli status          # Betriebsstatus aller Module, ohne Oberfläche
personintel-cli --help
```

Ohne weitere Angabe liegen die Daten nach XDG-Konvention in
`~/.local/share/personintel/` (Datenbank) und `~/.config/personintel/`
(Einstellungen, Zugangsdaten). Mit `PERSONINTEL_HOME=/pfad` lässt sich beides verlegen;
Verzeichnisse werden mit `0700`, Dateien mit `0600` angelegt.

### AppImage

```bash
pip install python-appimage
sudo apt-get install -y file            # von appimagetool benötigt
packaging/build_appimage.sh             # baut für die Architektur des Rechners
packaging/build_appimage.sh --help
```

Ergebnis: `DevBuilds/PersonIntel-<Version>-<Arch>.AppImage` (im Git-Repo), sonst `dist/`.
Bestehende Dateien werden nie überschrieben; für einen weiteren Build derselben Version dient
`--suffix`.

**Architektur:** python-appimage benennt das Ergebnis nach der Architektur des bauenden
Rechners und installiert die Abhängigkeiten (PySide6) mit `pip` in dessen Laufzeit. Ein
ARM64-AppImage entsteht deshalb nur in einer ARM64-Umgebung. x86_64 und ARM64 werden getrennt
gebaut:

```bash
# auf x86_64
packaging/build_appimage.sh                     # -> PersonIntel-<Version>-x86_64.AppImage

# auf ARM64-Hardware oder in einer ARM64-Umgebung
packaging/build_appimage.sh                     # -> PersonIntel-<Version>-aarch64.AppImage

# ARM64 auf einem x86_64-Rechner, über qemu-user-static:
docker run --rm --privileged tonistiigi/binfmt --install arm64
docker run --rm --platform linux/arm64 -v "$PWD":/src -w /src python:3.12-slim bash -c \
  "apt-get update && apt-get install -y --no-install-recommends file binutils zsync && \
   pip install python-appimage && packaging/build_appimage.sh"
```

Das Skript bricht ab, wenn `--arch` nicht zur Architektur des Rechners passt, statt eine falsch
benannte Datei zu erzeugen. Die zehn Recherchewerkzeuge sind **nicht** im AppImage enthalten
(siehe unten); sie werden zur Laufzeit im `PATH` bzw. an den in den Einstellungen angegebenen
Pfaden gesucht.

## 2. Die zehn Module

PersonIntel bringt keine Werkzeuge mit und lädt nichts im Hintergrund nach. Jedes Modul ist
einzeln aktivierbar; was fehlt, erscheint im Dashboard als „Nicht installiert“ mit dem
Installationsbefehl. Alle übrigen Module bleiben nutzbar.

### Lokale Werkzeuge

| Modul | Installation | Hinweise |
|---|---|---|
| Holehe | `pipx install holehe` | Erwartet die CSV-Ausgabe (`--csv`). Die Option `--no-password-recovery` wird gesetzt, falls die Installation sie kennt. |
| Mosint | `go install -v github.com/alpkeskin/mosint/v3/cmd/mosint@latest` | Braucht zusätzlich eine eigene Konfigurationsdatei (Vorlage `example-config.yaml` des Projekts, üblich `~/.mosint.yaml`). Pfad in den Einstellungen eintragen. API-Schlüssel für Drittdienste gehören in diese Datei, nicht in PersonIntel. |
| Sherlock | `pipx install sherlock-project` | Erwartet die CSV-Ausgabe. |
| PhoneInfoga | Binary aus den [Releases](https://github.com/sundowndev/phoneinfoga/releases) in den `PATH` legen | PersonIntel startet bei Bedarf `phoneinfoga serve` **nur auf 127.0.0.1** mit einem freien Port und beendet es wieder; kennt die Installation kein `--host`, wird die CLI-Ausgabe gelesen. Die Suchmaschinen-Scanner benötigen eigene Schlüssel im PhoneInfoga-Setup. |
| Ignorant | `pipx install ignorant` | Wird über den Python-Interpreter der eigenen Installation ausgeführt (benötigt dort `httpx` und `trio`). Abfragen laufen seriell und brechen beim ersten Rate-Limit ab. |
| Mr.Holmes | `git clone https://github.com/Lucksi/Mr.Holmes && cd Mr.Holmes && sudo bash install.sh` | Mr.Holmes hat keine automatisierbare Schnittstelle und wird **nicht** ferngesteuert. PersonIntel erkennt die Installation und importiert vorhandene Berichtsdateien; der Import funktioniert auch ohne Installation. |

Weicht ein Pfad ab, lässt er sich je Modul in den Einstellungen eintragen
(Feld „Pfad zum Programm“). Alternativ gilt `PERSONINTEL_<MODUL>_<FELD>` als Umgebungsvariable,
z. B. `PERSONINTEL_HOLEHE_EXECUTABLE=/opt/holehe/bin/holehe`.

### Kommerzielle Anbieter

| Modul | Voraussetzung | Stand |
|---|---|---|
| Pipl | Pipl-Vertrag und API-Schlüssel ([docs.pipl.com](https://docs.pipl.com)) | Betriebsbereit. „Zugang testen“ nutzt den vom Anbieter dokumentierten kostenlosen Testaufruf. |
| Spokeo | Spokeo-API-Vertrag, Einrichtung über `apisupport@spokeo.com` ([docs.spokeo.com](https://docs.spokeo.com)) | Betriebsbereit. Es gibt keinen kostenlosen Testendpunkt; der Lizenzstand gilt erst nach der ersten erfolgreichen Abfrage als bestätigt. Die Telefonsuche ist laut Dokumentation auf 10-stellige US-Nummern begrenzt. |
| ShadowDragon | SocialNet-/ShadowDragon-Vertrag, **Anbieterdokumentation** (Basis-URL, Authentifizierung, Antwortschema) und Zugangsdaten | **Recherche nicht verfügbar.** Es existiert keine öffentliche API-Dokumentation. Konfiguration, Statusanzeige und Adaptervertrag sind vorhanden; sobald die Dokumentation vorliegt, ist nur `execute_authorized_query` und `normalize_results` zu füllen (siehe [ARCHITECTURE.md](ARCHITECTURE.md), „Neuen Anbieter anbinden“). |
| Babel Street | Zugang zur Identity-/Insight-API samt Dokumentation | **Recherche nicht verfügbar.** Die öffentlich dokumentierte Babel-Street-API (Text Analytics) ist keine Personensuche und wäre der falsche Endpunkt. |

Schlüssel werden in den Einstellungen hinterlegt und landen im verschlüsselten
Zugangsdatenspeicher (`~/.config/personintel/credentials.enc`, Fernet, Schlüssel per scrypt aus
einer Passphrase) oder, auf Wunsch, im System-Schlüsselbund (`pip install 'personintel[keyring]'`).
Für den unbeaufsichtigten Betrieb können sie stattdessen als Umgebungsvariable übergeben werden
(z. B. `PERSONINTEL_PIPL_API_KEY`); dann werden sie nicht gespeichert.

## 3. Erster Fall

1. **Fälle → Neuer Fall**, Bezeichnung eingeben.
2. Im Dialog **Zweck dokumentieren**: Kategorie, konkreter Zweck (mindestens 20 Zeichen),
   verantwortliche Person, Gültigkeitsdauer, erlaubte Kennungsarten. Aktive Prüfungen –
   Abfragen, die fremde Dienste kontaktieren – müssen hier ausdrücklich freigegeben werden.
3. **Kennungen** registrieren: genau eine pro Eintrag, höchstens zehn pro Fall.
4. **Recherche**: Kennung und Modul wählen. Die Seite zeigt, ob die Prüfung passiv oder aktiv
   ist, und nennt jede fehlende Voraussetzung. Aktive Prüfungen verlangen die erneute Eingabe der
   Kennung und zwei Bestätigungen.
5. **Ergebnisse** prüfen: jeder Befund trägt Quelle, Zeitstempel und Belegstufe. Die Belegstufe
   lässt sich nur mit Begründung auf „unmittelbar belegt“ setzen.
6. **Verbindungen** nur manuell übernehmen, mit Basisbefund und Begründung.
7. **Bericht** erzeugen (Markdown, HTML, JSON, PDF).

## 4. Datenhaltung, Verschlüsselung, Löschen

* Alles bleibt lokal: SQLite-Datenbank, Einstellungen, Zugangsdaten. Es gibt keinen
  Netzwerkdienst und keine Telemetrie.
* **Verschlüsselung:** `Einstellungen → Datenhaltung → Datenbank verschlüsseln` verschlüsselt alle
  Inhalte nachträglich (Fallnamen, Kennungen, Befunde). Danach fragt der Start nach der
  Passphrase; headless geht `PERSONINTEL_DB_PASSPHRASE`. IDs, Zeitstempel und Datensatzart
  bleiben als Index im Klartext. **Die Passphrase kann nicht zurückgesetzt werden.**
* **Löschen:** einzelne Befunde, eine Abfrage samt Daten, eine Kennung samt Daten oder der ganze
  Fall. Gelöscht wird mit `secure_delete` und anschließendem `VACUUM`. Das Protokoll enthält keine
  Rechercheinhalte und bleibt standardmäßig erhalten; es kann beim Löschen des Falls ausdrücklich
  mitgelöscht werden (die Hash-Kette wird dann sichtbar neu aufgebaut).
* **Rohdaten** der Werkzeuge werden nie gespeichert, nur normalisierte Befunde mit
  Herkunftsnachweis. Aus Anbieterdatensätzen werden Wohnadressen, Geburtsdaten und Verwandte nicht
  übernommen; Telefon und E-Mail nur, wenn das je Modul ausdrücklich eingeschaltet wird.

## 5. Was geprüft ist und was nicht

Ehrlicher Stand, damit niemand Zusagen übernimmt, die nicht belegt sind:

**Automatisch geprüft** (`python -m pytest -q`):

* Zweck- und Berechtigungsprüfung, auch gegen gefälschte und nachträglich veränderte
  Autorisierungen, Tagesbudget, Mindestabstand, Fallumfang, Einzelkennung.
* Manipulationserkennung des Protokolls, Verschlüsselung ruhender Daten, nachträgliche
  Verschlüsselung, gezieltes Löschen, Zugangsdatenspeicher.
* Die Prozess-, Datei- und Parsing-Pfade aller lokalen Adapter – gegen **ausführbare Attrappen**,
  die die dokumentierten Ausgabeformate erzeugen (Holehe-CSV, Sherlock-CSV, Mosint-JSON,
  PhoneInfoga-CLI und -REST).
* Pipl und Spokeo gegen einen **lokalen HTTP-Server** mit dem dokumentierten Antwortformat,
  einschließlich Datensparsamkeit, abgelehnter Schlüssel und Rate-Limit.
* Graph-, Berichts- und Austauschregeln; die Oberfläche offscreen.
* Rezept und Schutzmechanismen des AppImage-Skripts.
* Das Paket installiert sich in eine frische Umgebung, beide Startbefehle laufen, die
  Icon-Ressource wird mitinstalliert.

**Nicht geprüft** (fehlende Voraussetzungen, nicht fehlende Umsetzung):

* Ein Lauf gegen die **echten** Werkzeuge: holehe, mosint, sherlock, phoneinfoga und ignorant
  waren in der Entwicklungsumgebung nicht installiert. Die Adapter folgen den dokumentierten
  Formaten; bei Abweichungen einzelner Versionen ist das Parsen anzupassen. Besonders zu prüfen
  sind das JSON-Schema von Mosint und die Textausgabe der PhoneInfoga-CLI – beide sind nicht
  formal spezifiziert.
* Abfragen bei den **echten** Anbietern Pipl und Spokeo (kostenpflichtig, Vertrag nötig).
* Der **AppImage-Bau selbst**: er lädt ein Python-Basisimage von GitHub; in der
  Entwicklungsumgebung war dieser Zugriff gesperrt. Geprüft sind Rezept, Platzhalter,
  Architekturabbruch und das Überschreibverbot.
* Mr.Holmes-Berichte echter Installationen: der Import ist gegen die Textstruktur geprüft, nicht
  gegen alle Berichtsvarianten des Projekts.
