# ChatGPT Test 1.4 – Bedienung, Funktionen, Grenzen

## Neu: Ergebnisse wie ein Steckbrief

Die Ausgabe wird während einer laufenden Suche weiter zeilenweise angezeigt. Nach Abschluss erscheint **automatisch eine strukturierte Übersicht**:

1. **Kategorien:** Person & identity, Contact details, Profiles & accounts, Places & maps, Organizations, Network & services, Documents & sources, Other / warnings.
2. **Untergruppen:** z. B. X / Twitter, GitHub, Instagram, Telefonnummern, E-Mails, Wikidata/Wikipedia, DNS, IP/ASN.
3. **Fundstellen:** eindeutige Treffer in der gewählten Untergruppe.
4. **Details:** vollständiger ursprünglicher Fundtext, Quellabschnitt, optionaler Quellverweis, Status und Duplikatanzahl.

Ein gefundenes Profil ist nicht automatisch ein verifizierter Identitätsnachweis. Unterschiedliche Konten mit gleichem Handle werden nicht allein aufgrund des Handles zusammengeführt.

## Tastatur und Flipper-Tasten

- **B / Enter**: Öffnen (Kategorie → Untergruppe → Fund → Details)
- **X**: Zurück zur vorherigen Ebene; von der Ergebniswurzel ins Startmenü
- **Z**: Home, direkt zurück ins Startmenü, ohne die App zu schließen
- **V**: Suche wiederholen, während der Suche stoppen
- **Pfeil hoch/runter** und **Mausrad**: Auswahl verschieben / Details scrollen
- **Touch**: Kategorie, Untergruppe oder Fund direkt öffnen

Der frühere **All/Index-Umschalter entfällt**.

## Startmenü

Eine gut verständliche Eingabeliste bleibt. Technische Duplikate wie `IP: original` und `Domain: original` sowie `Vendor: name` wurden **aus dem Startmenü entfernt**. Die ursprünglichen Go-CLI-Kommandos bleiben aus Gründen der Kompatibilität im Backend erhalten.

Gewöhnliche Suchen nach Name, E-Mail, Benutzername und Telefonnummer starten **ohne Bestätigungsmodal**. Dies geschieht dadurch, dass die Standard-Suche nur die ohnehin unterstützten öffentlichen bzw. technischen Prüfungen ausführt. Automatisierte Konto-Registrierungsprüfungen bei fremden Diensten werden dabei **nicht heimlich** gestartet. Die optionalen Personenprovider bleiben über die bestehenden gesonderten, autorisierten Schnittstellen erreichbar; ihr Livebetrieb ist nicht für alle Dienste nachgewiesen.

## Bessere Recherchekette

Der bisherige begrenzte **Firma → offizieller Webauftritt → DNS → öffentliche IP-Adressen**-Weg wurde erweitert:

**Firma / Organisation → Wikidata-Webseite → DNS (max. 3 öffentliche IPs je Host) → RIPEstat ASN (max. 2 IPs je Host)**.

Der Pfad ist auf höchstens vier unterschiedliche Webseiten pro Suchlauf begrenzt. Kein automatischer Portscan dieser neu gewonnenen IPs, keine personenbezogene Rekursion, keine unbegrenzten API-Aufrufe.

Die bestehende zentrale Store-Implementierung führt gleiche normalisierte Werte zusammen, erhält unabhängige Quellen und verhindert doppelte Graphkanten. Zusätzlich entfernt der neue Ergebnisbrowser exakte Trefferduplikate anhand stabiler Objekt-URLs bzw. normalisierter Texte, ohne verschiedene Konten nur nach Handle zusammenzulegen.

## Tests und ehrliche Einschränkungen

- `go test ./...` für Backend/Provider-/Pivottests
- `osint-ui --selftest` für Navigation, Bildschirmzustände und Doppelbefunde
- Native ARM64-AppImage-Paketierung und SHA-256 im GitHub-Actions-Workflow
- **Noch nicht bestätigt:** Start auf deinem konkreten Flipper-One-Emulator, echte Ergebnisse jedes externen Providers und Python-Laufzeit für PersonIntel
- **Nicht enthalten:** Vollautomatische Identitäts- oder Privatdaten-Aggregation, heimliche Registrierungstests, vollständige proprietäre Dienste oder eine fest eingebundene Python Runtime

Das AppImage ist als **Entwicklungs-/Testversion** zu betrachten, bis die Bedienung im echten Flipper-One-Emulator nachgewiesen wurde.
