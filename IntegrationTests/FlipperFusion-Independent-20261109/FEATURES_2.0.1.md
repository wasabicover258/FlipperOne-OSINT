# ChatGPT Test 2.0.1 – AI-Webrecherche und bestätigte PDF-Auswertung

## Status

Die ARM64-AppImage ist auf `main` im unveränderten Ordner `ChatGPT Test` veröffentlicht:

`ChatGPT-Test-2.0.1-aarch64.AppImage`

**SHA-256**: `b7ade7adcf060733dceea51674f535bee5376481d632473a36299bb5228a886d`

Die ursprüngliche 2.0 und alle Vorgängerversionen bleiben erhalten.

## Warum 2.0.1 statt 2.0?

Der erste echte Live-Test auf ARM64 zeigte, dass die beiden Webquellen Wikipedia und OpenAlex erreichbar waren, der ältere PDF-Parser aber einen konkreten Satz in einem bekannten öffentlichen Beispiel-PDF nicht korrekt extrahierte.

2.0.1 ersetzt die PDF-Textauswertung durch `github.com/giraffesyo/pdf`, einen quelloffenen, reinen Go-Parser (v0.8.0), mit begrenzten HTTP-Downloads und abgebrochener Verarbeitung bei Zeitüberschreitung.

**Wiederholung genau desselben Live-Tests am 9. November 2026:**

- Wikipedia-Such-API: 5 verwertbare Treffer
- OpenAlex: 5 verwertbare Veröffentlichungen
- Öffentliche W3C-Test-PDF: gesuchte Formulierung auf **Seite 1** erfolgreich extrahiert
- Go-Tests erfolgreich
- 323 UI-Selbstprüfungen ohne Fehler
- Native ARM64-AppImage aufgebaut, Prüfsumme erzeugt

Build: https://github.com/wasabicover258/FlipperOne-OSINT/actions/runs/42662299980

Live-Prüfung: https://github.com/wasabicover258/FlipperOne-OSINT/actions/runs/42662494812

## Was ohne Einrichtung funktioniert

- Ein eigener Menüpunkt **AI web & PDFs** durchsucht die öffentlichen Wikipedia- und OpenAlex-Kataloge.
- Nach allen Recherchemodulen wird aus den tatsächlich ausgegebenen Funden eine **lokale extraktive 3–5-Punkte-Zusammenfassung** erzeugt.
- Die Kategorie **AI key findings** erscheint oben; jeder Punkt ist anwählbar und öffnet den ursprünglichen Fund, Textauszug und Quelleninformation, sofern vorhanden.
- Die alten Suchmodule und die bestehenden Flipper-Tastenpfade bleiben erhalten.

## Was für die volle Web-/KI-Suche erforderlich ist

**Brave Search API** für allgemeine Websuchergebnisse, inklusive gezielter `filetype:pdf`-Recherche. Ohne API-Schlüssel können die kostenlosen Wikipedia-/OpenAlex-Kataloge eine beliebige PDF aus 2011 außerhalb dieser Kataloge nicht zuverlässig finden.

**Optionales generatives Sprachmodell** für natürlich formulierte Zusammenfassungen über eine OpenAI-kompatible API, z. B. eine selbst betriebene `llama.cpp`-Serverinstanz auf dem Flipper oder einen HTTPS-Cloudanbieter. Das Sprachmodell und sein Server sind **nicht in der AppImage vorinstalliert**. Ohne diesen Endpunkt verwendet die App den bereits funktionsfähigen lokalen NLP-Ranker.

Die eigenen Zugangsdaten gehören auf dem Flipper nach:

`~/.config/flipperone-osint/ai.env`

Eine Vorlage befindet sich in der AppImage unter:

`usr/share/flipperone-osint/ai.env.example`

Die App liest nur erlaubte Konfigurationsschlüssel ein, zeigt niemals den Wert von API-Schlüsseln im Statusmenü und schreibt keine Keys ins GitHub-Repository.

## Bekannte Grenzen

- **Kein Emulatorstart von 2.0.1 selbst bestätigt.** Ein erfolgreicher ARM64-CI-Build ersetzt die Prüfung im Flipper-One-Gast.
- KI-Aussagen werden als Kandidaten behandelt. Namen allein sind kein Beweis, dass ein Profil, Dokument oder Account zu einer bestimmten Person gehört.
- Der öffentliche PDF-Reader verarbeitet nur textbasierte PDFs, keine Bildscans ohne OCR; er beschränkt sich auf die ersten 12 Textseiten kleiner Dokumente (maximal 3 MiB pro Datei).
- Pro Websuchlauf werden höchstens zwei PDFs zur Inhaltsprüfung heruntergeladen, keine unbegrenzten Crawls.
- Die kostenlose Recherchequalität hängt von Quellen, Netzwerkzugang und Suchabdeckung ab.
- Keine automatische Ermittlung privater Kontaktdaten aus bloßer Namensgleichheit.

## Einfacher Test im Flipper-Emulator

1. `ChatGPT-Test-2.0.1-aarch64.AppImage` in den File Manager ziehen und installieren.
2. Bei Bedarf nur das emulierte Flipper OS normal neu starten.
3. Im Startmenü **AI web & PDFs** öffnen und `Ada Lovelace` oder ein öffentlich bekanntes Forschungsthema eingeben.
4. Nach dem Suchlauf die Kategorie **AI key findings** öffnen. Bis zu fünf Stichpunkte sollten anklickbar sein.
5. Die Quellen- und Auszugsansicht aufrufen.
6. Ohne Brave-Schlüssel wird auf der Ergebnisansicht ausdrücklich darauf hingewiesen, dass allgemeine Web/PDF-Suche nicht eingerichtet ist.
7. Andere normale OSINT-Module sollten ebenfalls eine AI-Kurz-Zusammenfassung erhalten, sofern sie mindestens einen geeigneten Treffer liefern.

Weitere Konfiguration: `ChatGPT Test/README_2.0.md` im Entwicklungsbranch.
