# FlipperOne-OSINT · ChatGPT Test 2.0

## Zweck und Lieferumfang

2.0 ergänzt **eine benutzbare Web-/Dokumentenrecherche und eine quellengebundene Kurz-Zusammenfassung**. Die vorhandene 1.6.1-Architektur (SDL2-Oberfläche + statisches Go-Backend + optionales PersonIntel) bleibt erhalten.

### Was ohne zusätzliche Konfiguration funktioniert

- Menüeintrag **AI web & PDFs**: freie Suche über die öffentlichen Suchschnittstellen von **Wikipedia** und **OpenAlex**. Diese sind keine vollständige Websuchmaschine.
- Nach jedem normalen Suchlauf zeigt die App unter **AI key findings** bis zu fünf **anklickbare Kernpunkte**. Ein lokaler, extraktiver NLP-Ranker gewichtet vorhandene Befunde nach Suchbezug, Quellenqualität und inhaltlicher Abwechslung und entfernt Wiederholungen.
- Jeder Kernpunkt öffnet eine Detailansicht mit erhaltenem Originalbefund, soweit vorhanden einem konkreten Textauszug und dem Quellenlink. Unbestätigte Identitätskandidaten bleiben ausdrücklich unbestätigt.
- Alte technische und geografische Recherchemodule sind weiterhin nutzbar.

### Mit Brave Search API-Schlüssel

Bei **AI web & PDFs** führt die App zusätzlich zwei begrenzte Anfragen durch:

1. Exakte Suche nach der eingegebenen Formulierung.
2. Eine unabhängige Suche mit `filetype:pdf` nach öffentlichen PDF-Dokumenten.

Treffer werden nach normalisierter URL dedupliziert. Maximal zwei kleine, öffentlich zugängliche textbasierte PDFs werden vollständig heruntergeladen (je maximal 3 MiB, bis zu 12 Seiten werden geprüft). Bei einer tatsächlichen Textübereinstimmung zeigt das Programm einen Auszug **mit Seitenzahl**. Bei gescannten PDFs ohne Textebene ist eine OCR-Erweiterung erforderlich.

Das ist der Weg, mit dem beispielsweise eine **öffentliche PDF aus 2011** entdeckt und ein vorhandener Name im Text geprüft werden kann. Kein Treffer ist garantiert; Suchindizes und Archivabdeckung sind unvollständig.

### Mit einem kleinen Sprachmodell

Der lokale NLP-Ranker ist jederzeit verfügbar und benötigt **kein Sprachmodell**. Für generative, freier formulierte Zusammenfassungen lässt sich **optional** ein kleines Modell über eine OpenAI-kompatible Chat-API anbinden. Beispielsweise kann ein lokaler llama.cpp-Server auf dem Flipper One oder ein HTTPS-Anbieter verwendet werden.

**Das generative GGUF-Sprachmodell selbst ist nicht in der 2.0-AppImage enthalten.** Es ist auch kein einsatzbereiter llama.cpp-Server vorinstalliert. Ohne eine explizit konfigurierte Modell-Laufzeit ist die Zusammenfassung extraktiv, nicht generativ. Das ist eine bewusst klare Unterscheidung.

Ein LLM darf nur vom Programm vorgegebene kurze Quellenauszüge umformulieren. Es kann keinen neuen Quellenlink erfinden; die Links werden aus den tatsächlich gefundenen Datensätzen übertragen. Trotzdem müssen die KI-Formulierungen anhand der Originalquelle kontrolliert werden.

## Einrichtung

Die Beispielkonfiguration liegt in der AppImage unter:

`usr/share/flipperone-osint/ai.env.example`

Lege auf dem Flipper-One-Linux-System folgende Datei an:

`~/.config/flipperone-osint/ai.env`

Inhalt (Beispiel):

```ini
BRAVE_SEARCH_API_KEY=DEIN_EIGENER_BRAVE_SEARCH_API_KEY
AI_CHAT_URL=http://127.0.0.1:8080/v1/chat/completions
AI_CHAT_MODEL=dein-geladenes-kleines-sprachmodell
AI_CHAT_API_KEY=
```

Für ein Cloud-Modell verwende einen HTTPS-Endpunkt sowie den nötigen eigenen API-Schlüssel. Lasse die drei `AI_CHAT_*`-Zeilen weg, wenn du nur die lokale, immer verfügbare NLP-Auswertung verwenden willst. **Keine echten Zugangsdaten in das GitHub-Repository oder öffentlich geteilte Screenshots schreiben.**

Die App liest nur die vier ausdrücklich erlaubten Variablen und führt die Konfigurationsdatei nicht als Shell-Skript aus.

Im Hauptmenü zeigt **AI search setup**, welche Bestandteile konfiguriert sind. Zugangsdaten werden dort nicht angezeigt.

## Oberfläche

- Die Kategorie **AI key findings** erscheint vor den bisherigen Ergebnisgruppen.
- Maximal fünf Befunde, jeweils anklickbar.
- **B/Enter:** Öffnen und bis zur Quelle/Detailansicht navigieren.
- **X:** eine Ebene zurück.
- **Z:** Home, direkt ins Startmenü.
- Alte Kategorien, Primärdaten und technische Detailberichte bleiben verfügbar.

## Grenzen und Sicherheit

- Namensgleichheit beweist keine Personenidentität.
- Keine unbegrenzte personenbezogene Datenverkettung oder automatischer Rückschluss auf private Kontaktadressen.
- Automatisierte Websuche ist mit eigenem Brave-Schlüssel nutzbar; ohne Schlüssel nur eingeschränkte offene Katalogquellen.
- Externe AI-API-Konfiguration kann zur Übermittlung der Ausschnitte an einen Dritten führen; dafür gelten die Bedingungen des gewählten Betreibers.
- PDFs werden nur über HTTPS von öffentlichen Hosts heruntergeladen. Private IP-Ziele und interne Hosts werden gesperrt, Dateigröße und Seitenzahl sind begrenzt. Textbasierte PDF-Auswertung ist nicht OCR.
- Alle KI- und Webfunktionen benötigen funktionierende DNS/TLS/Netzwerkunterstützung auf der tatsächlichen Flipper-Linux-Laufzeit.

## Abnahmetests

- `go test ./...` inkl. URL-Schutz, Brave-JSON, PDF-Kandidaten, NLP-Quellen und Duplikaten.
- UI-Selbsttests inkl. **AI key findings**, Detailanzeige, Quellen und Navigation.
- ARM64-AppImage-Build und SHA-256-Prüfung im GitHub-Workflow.
- Ein grüner CI-Workflow **beweist keinen erfolgreichen Emulatorstart**. Die Installation in deinem Flipper-One-Emulator und eine reale PDF-Fundstelle sollten anschließend separat geprüft werden.

## Externe Quellen

- Brave API: https://api-dashboard.search.brave.com/documentation/services/web-search
- MediaWiki Search: https://www.mediawiki.org/wiki/API:Search
- OpenAlex: https://docs.openalex.org/api-entities/works/search-works
- Go PDF Reader: https://github.com/rsc/pdf (BSD-3-Clause)
- llama.cpp: https://github.com/ggml-org/llama.cpp
