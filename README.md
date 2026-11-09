# FlipperOne-OSINT

**OSINT-Recherche für den Flipper One – mit übersichtlicher Bedienoberfläche, öffentlichen Datenquellen, Dokumentensuche und quellenbezogenen Ergebnissen.**

FlipperOne-OSINT ist eine für **Linux ARM64 (aarch64)** entwickelte Open-Source-Intelligence-Anwendung. Sie kombiniert verschiedene Recherchemethoden in einer App, statt für jede Informationsart ein separates Werkzeug vorauszusetzen. Die Ergebnisse werden in Kategorien gegliedert; relevante Funde können mit ihren Quellen im Detail betrachtet werden.

> **Aktuelle öffentliche Version: 2.0.5**  
> Das App-Shelf zeigt die Anwendung als **OSINT** mit einem kleinen Lupen-Icon. Die AppImage ist für den **Flipper One**, nicht für x86-64-PCs.

## Download und Installation

**[FlipperOne-OSINT-2.0.5-aarch64.AppImage herunterladen](https://github.com/wasabicover258/FlipperOne-OSINT/raw/refs/heads/main/Public%20Releases/FlipperOne-OSINT-2.0.5-aarch64.AppImage)**

**[Public Releases öffnen](https://github.com/wasabicover258/FlipperOne-OSINT/tree/main/Public%20Releases)** · **[Flipper-Emulator-AppCatalogue öffnen](https://github.com/wasabicover258/Flipper-Emulator/tree/main/AppCatalogue/OSINT)**

1. Lade die Datei **`FlipperOne-OSINT-2.0.5-aarch64.AppImage`** herunter.
2. Importiere sie über den App-Store beziehungsweise den Dateimanager deiner Flipper-One-Umgebung.
3. Öffne die Anwendung **OSINT** über das App-Shelf.
4. Wähle eine Suchart, gib einen Suchwert ein und starte die Recherche.

Wenn nach der Aktualisierung noch eine frühere Darstellung oder ein schwarzes Icon-Quadrat erscheint, entferne gegebenenfalls den alten App-Eintrag und lade das App-Shelf beziehungsweise den Emulator neu. Die 2.0.5 enthält ein **14 × 14 Pixel großes RGBA-Lupen-Icon** mit transparentem Hintergrund; das Flipper-Shelf verwendet dessen Alpha-Kanal als Maske.

**Verifikation des veröffentlichten Pakets:**

| Eigenschaft | Wert |
|---|---|
| Version | **2.0.5** |
| Architektur | **AArch64 / ARM64** |
| Dateiname | `FlipperOne-OSINT-2.0.5-aarch64.AppImage` |
| Größe | 4.135.432 Byte |
| SHA-256 | `5d1568fb1170bc491c02f4d4d36ade7eec426e46c7e83352c1b0945702f3bbc1` |

Die ARM64-Binärdatei, die Metadaten, das Icon im entpackten AppImage und **343 UI-Selbstprüfungen** wurden im [Build von Version 2.0.5](https://github.com/wasabicover258/FlipperOne-OSINT/actions/runs/42683024791) erfolgreich geprüft. Der erste echte Sichttest der neuen Icon-Darstellung auf deinem Emulator ist davon zu unterscheiden.

## Funktionen

Die App unterstützt mehrere Ausgangspunkte für eine Recherche:

| Eingabe | Beispiele für recherchierte Informationen |
|---|---|
| **Domain / Website** | DNS, TLS, öffentliche Subdomains, Webtechnik, HTTP-Header, historische Website-Snapshots |
| **IPv4 / IPv6** | RDAP, Reverse-DNS, Netzbetreiber, ASN, öffentliche technische Hinweise und ein zweiter IP-Datenanbieter |
| **Benutzername** | Öffentliche Profilseiten und GitHub-Accountdaten; Namensgleichheit bedeutet keine bestätigte Identität |
| **Vollständiger Name** | Öffentliche Kandidateneinträge in Wikidata, Wikipedia und OpenAlex, etwa wissenschaftliche Veröffentlichungen |
| **E-Mail-Adresse** | Format und Domain, Mailserver, SPF/DMARC und weitere öffentlich prüfbare Mail-Sicherheitsinformationen |
| **Telefonnummer** | Nummernformat, Land und begrenzte Nummernplan-Informationen, **keine** private Inhaberermittlung |
| **GPS-Koordinaten** | Öffentliche Einrichtungen und Betriebe im Umkreis über OpenStreetMap/Overpass sowie passende Karteninformationen |
| **Adresse / Ort** | Ortsauflösung, nahegelegene öffentliche Einträge und zusätzliche geografische Wikipedia-Hinweise |
| **Firma / Organisation** | Öffentliche Organisationsdaten, Websites, DNS-Bezüge und gegebenenfalls GLEIF-/LEI-Registereinträge |
| **Registernummer / VIN / Kennzeichen** | Je nach Eingabe zugängliche öffentliche Register-, Hersteller- oder Formatdaten |
| **Bitcoin-Adresse / ASN** | Öffentlich zugängliche Blockchain- beziehungsweise BGP-/Routingdaten |

Welche Daten tatsächlich erscheinen, hängt von der jeweiligen öffentlichen Quelle, deren Abdeckung und ihrer Erreichbarkeit ab.

### Orts- und Umgebungssuche

Beispiel für eine GPS-Eingabe:

```text
48.086056, 11.556722
```

Die App sucht nach öffentlich erfassten Einrichtungen in einem **500-Meter-Umkreis** und ordnet die Ergebnisse **aufsteigend nach Entfernung** – der nächste Treffer zuerst, unabhängig davon, ob es sich um ein Restaurant, eine Klinik oder einen anderen Eintrag handelt.

Bei entsprechend gepflegten OpenStreetMap-Einträgen können **Name, Art des Betriebs, Entfernung, Geschäftsadresse, Website, Telefonnummer und E-Mail-Adresse** erscheinen. Fehlen Angaben in der Quelle, kann die App sie nicht zuverlässig ergänzen. Die Auswahl ist außerdem begrenzt; sie stellt kein vollständiges Verzeichnis aller Einrichtungen dar.

### KI-Web- und PDF-Recherche

Unter **AI web & PDFs** lässt sich eine öffentliche Recherche nach einem Namen oder einem Thema starten.

- Ohne zusätzliche Zugangsdaten durchsucht die App **Wikipedia** und **OpenAlex**.
- Mit eigenem **Brave Search API-Schlüssel** kommen allgemeine Websuchen und gezielte **PDF-Suchen** hinzu.
- Kleine, textbasierte öffentliche PDF-Dokumente können auf die Suchformulierung geprüft werden. Bei einem tatsächlichen Treffer zeigt die App möglichst einen **Textauszug und die betreffende Seite**.
- Anschließend zeigt die Ergebnisansicht unter **AI key findings** bis zu **fünf anklickbare Kernergebnisse**. Die Quellen und vorhandenen Textauszüge bleiben einsehbar.

Die standardmäßig integrierte Zusammenfassung nutzt einen **lokalen NLP-Relevanzalgorithmus**: Er wählt relevante, möglichst unterschiedliche Funde aus. Ein generatives Sprachmodell ist **nicht** in der AppImage enthalten. Für natürlich formulierte KI-Zusammenfassungen kann optional ein lokaler oder ein kompatibler Online-Modellendpunkt konfiguriert werden.

Ein gescannter PDF-Bildinhalt ohne durchsuchbare Textebene wird derzeit nicht automatisch per OCR gelesen.

## Optionale KI- und Websuche einrichten

Für die zusätzlichen Dienste kann unter Flipper Linux diese Datei angelegt werden:

```text
~/.config/flipperone-osint/ai.env
```

Beispiel:

```ini
# Optional: allgemeine Web- und PDF-Suche
BRAVE_SEARCH_API_KEY=

# Optional: generatives Modell, z. B. ein eigener llama.cpp-Server
AI_CHAT_URL=http://127.0.0.1:8080/v1/chat/completions
AI_CHAT_MODEL=
AI_CHAT_API_KEY=
```

Der Modellendpunkt muss einen **OpenAI-kompatiblen Chat-Endpunkt** bereitstellen. Für externe Modellanbieter ist HTTPS vorgesehen. Das Modell selbst muss separat installiert oder bereitgestellt werden. Die App zeigt unter **AI search setup**, ob die optionalen Komponenten konfiguriert sind; Zugangsdaten gehören **nicht** ins Repository.

**Ohne Brave-Schlüssel bleibt die allgemeine Websuche eingeschränkt. Ohne Modellendpunkt funktioniert die lokale Ergebnisgewichtung weiterhin.** Eine Cloud-KI kann übermittelte Quellenauszüge beim gewählten Anbieter verarbeiten – beachte dessen Datenschutzbedingungen.

## Bedienung

Die Anwendung ist für das kleine Flipper-One-Display ausgelegt:

- **Steuerkreuz:** Menüpunkt, Bildschirmtastatur oder Ergebnis auswählen.
- **Enter / Bestätigen:** Auswahl öffnen beziehungsweise Suche starten.
- **B (Bestätigen):** In Ergebnislisten einen Stichpunkt, eine Kategorie oder eine Detailansicht öffnen.
- **X:** Innerhalb der Ergebnisansichten eine Ebene zurück.
- **Z:** Aus der Recherche zurück zur Startansicht.
- **Bildschirmtastatur:** `<` für Löschen, `clr` zum Leeren, `abc/ABC` für Groß- und Kleinschreibung.

Die Ergebnisse werden zunächst in **Kategorien und Untergruppen** sortiert. Ein Eintrag führt zu seiner Detailansicht und – soweit vorhanden – zum Quellenverweis. Die Oberfläche zeichnet einen **rein weißen Hintergrund**, schwarze Beschriftung und abgerundete Buttons; der Flipper-Emulator färbt diese Graustufen anschließend orange ein.

## Technischer Aufbau

| Bereich | Technologie |
|---|---|
| Bedienoberfläche | **C / SDL2**, optimiert für 256 × 144 Pixel |
| Recherche-Backend | **Go**, auf ARM64 als ausführbares Programm gepackt |
| Paket | **AppImage** für AArch64 |
| Zusätzliche Datenquellen | Unter anderem OpenStreetMap, Wikipedia, OpenAlex, GitHub, GLEIF, RIPEstat und Internet Archive |
| Optionale Sprachmodell-Auswertung | OpenAI-kompatibler API-Endpunkt; beispielsweise ein separat gestartetes llama.cpp-Modell |
| Flipper-Shelf | `app.toml` und transparentes **14×14-PNG** in der SquashFS-Wurzel |

**Wichtige Verzeichnisse:**

```text
app-ordner/
  src/ui/                         # SDL2-Oberfläche
  src/cli/                        # Go-Recherchemodule
  app/FlipperOneOSINT.AppDir/     # AppRun, app.toml, Icon
IntegrationTests/OSINT-ARM64/     # ARM64-Build und Icon-Prüfung
Public Releases/                  # Nur die aktuelle öffentliche AppImage
ChatGPT Test/                     # Ältere Test-Builds
DevBuilds/                        # Entwicklungs- und ältere PC-Pakete
```

Der **aktuelle Quellstand für das veröffentlichte 2.0.5-Paket** liegt im Entwicklungsbranch **[`experiment/chatgpt-v2.0.5-alpha-icon`](https://github.com/wasabicover258/FlipperOne-OSINT/tree/experiment/chatgpt-v2.0.5-alpha-icon)**. `main` enthält die Veröffentlichung und weitere bestehende Projektdateien; deren Quellstand muss nicht vollständig dem zuletzt veröffentlichten AppImage entsprechen.

### ARM64-Build

Der [Build-Workflow](https://github.com/wasabicover258/FlipperOne-OSINT/blob/experiment/chatgpt-v2.0.5-alpha-icon/.github/workflows/experiment-publish-osint-v2.0.5.yml) verwendet einen nativen ARM64-GitHub-Runner. Das [Build-Skript](https://github.com/wasabicover258/FlipperOne-OSINT/blob/experiment/chatgpt-v2.0.5-alpha-icon/IntegrationTests/OSINT-ARM64/build_arm64.sh) prüft unter anderem Go-Tests, UI-Selbsttests, AArch64-Architektur und das Shelf-Icon. Anschließend wird das fertige AppImage erneut entpackt und dessen Root-Icon kontrolliert.

**Neue Veröffentlichungen** sollen immer den Dateinamen

```text
FlipperOne-OSINT-<version>-aarch64.AppImage
```

erhalten. `Public Releases` soll ausschließlich **eine aktuelle, geprüfte ARM64-AppImage** enthalten. Historische Dateien bleiben außerhalb dieses Ordners erhalten.

## Grenzen und verantwortungsvolle Nutzung

OSINT bezeichnet die Auswertung **öffentlich zugänglicher Informationen**. Die App ist kein Beweisverfahren für persönliche Identitäten:

- Ein identischer Name oder Benutzername reicht nicht aus, um ein Profil sicher einer Person zuzuordnen.
- E-Mail-Adressen, Telefonnummern, Standortangaben und Unternehmensdaten sind nur so belastbar wie ihre jeweilige Quelle.
- Es gibt keine Garantie für vollständige oder stets aktuelle Ergebnisse.
- Einige Recherchewege nutzen externe Dienste, die zeitweise ausfallen oder Anfragen begrenzen können.
- Weitergehende aktive Netzwerkprüfungen sollten ausschließlich an eigenen oder ausdrücklich freigegebenen Systemen durchgeführt werden.

**Hinweis:** Ein erfolgreicher ARM64-Build und automatisierte Tests ersetzen keinen vollständigen Funktionstest im Flipper-One-Emulator oder auf dem realen Gerät.

---

**Projekt:** [wasabicover258/FlipperOne-OSINT](https://github.com/wasabicover258/FlipperOne-OSINT) · **Aktueller Download:** [OSINT 2.0.5 (ARM64)](https://github.com/wasabicover258/FlipperOne-OSINT/raw/refs/heads/main/Public%20Releases/FlipperOne-OSINT-2.0.5-aarch64.AppImage)
