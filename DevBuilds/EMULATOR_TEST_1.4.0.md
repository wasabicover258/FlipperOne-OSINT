# Emulator-Testverfahren – FlipperOne-OSINT 1.4.1 (Fusion)

**Wichtig vorab:** Ich konnte diesen Test **nicht selbst durchführen**. Dein Rechner
`justusdesktop` ist zwar mit der Sitzung verbunden, aber der Zugriff auf einen Ordner wurde vom
Sicherheitsfilter dieser Sitzung blockiert, bevor eine Anfrage bei dir ankam. Damit kann ich
weder das AppImage auf deinem PC ablegen noch den File Manager oder die Emulatoroberfläche
bedienen. Unten steht deshalb ein Verfahren, das du Schritt für Schritt abarbeiten kannst, und
darunter genau die Ausgaben, die ich für eine belastbare Auswertung brauche.

Was in diesem Dokument steht, ist **nicht** als Testergebnis zu lesen. Es ist der Testplan.

---

## 0. Voraussetzungen

| | |
|---|---|
| Emulator | FlipperEmulator 11.5 (oder neuer), Modus **Flipper OS + File Manager** |
| AppImage | `DevBuilds/FlipperOne-OSINT-1.4.1-aarch64.AppImage` aus dem Branch `fusion/flipper-personintel` |
| Prüfsumme | siehe `DevBuilds/FlipperOne-OSINT-1.4.1-aarch64.AppImage.sha256` |
| Dauer | 20–40 Minuten; der erste App-Start kann unter Software-Emulation mehrere Minuten dauern |

Vor dem Hochladen die Prüfsumme vergleichen (PowerShell):

```powershell
Get-FileHash .\FlipperOne-OSINT-1.4.1-aarch64.AppImage -Algorithm SHA256
```

## 1. Installation im Emulator

1. Emulator starten, Modus **Flipper OS + File Manager** wählen. Zwei Browser-Tabs öffnen sich.
2. Im File-Manager-Tab (`http://127.0.0.1:8898/`) das AppImage hochladen oder auf die Seite ziehen.
3. **Install** neben der Datei wählen und bestätigen. Erwartet: Badge **Installed**.
4. Im Flipper-OS-Tab **Apps** öffnen. Erwartet: Eintrag **OSINT 1.4.0**.

**Festhalten:** Nimmt der Shelf die Datei an? Wenn nicht, die genaue Meldung notieren
(der Shelf prüft ELF-Header, ARM64 und `app.toml` im squashfs-Root).

## 2. Start und Grundzustand

5. **OSINT 1.4.0** starten. Erwartet: das orange Menü mit der Kopfzeile `OSINT` und `1/14`.
6. Startlog sichern: `/tmp/flipperone-osint.log` im Gast (über den File Manager erreichbar).

**Festhalten:** Zeit vom Antippen bis zum ersten Bild. Welcher SDL-Treiber steht im Log?

## 3. Bestehende Funktionen (dürfen sich nicht verändert haben)

7. **Phone number** → `0171 1234567` → **Start**. Erwartet: E.164, Land, Längenprüfung, Typ;
   ausdrücklich **kein** Inhaberabgleich. Reine Offline-Prüfung, muss sofort kommen.
8. **Domain / recon** → `example.com` → **Start**. Erwartet: Übersicht mit mehreren Kategorien,
   Statuspunkten und Trefferzahlen; `X` wechselt zwischen Index und Gesamtliste.
9. **IP address** → `8.8.8.8` → **Start**.
10. **Username** → ein öffentlicher Handle → **Start**.
11. **Email address** → eine Adresse → **Start**.

**Festhalten:** Laufzeit je Modul, ob die Übersicht erscheint, ob Scrollen und Rückschritt
funktionieren. Jede Abweichung gegenüber 1.3.0 ist ein Fehler.

## 4. Navigation im erweiterten Menü

12. Mit dem D-Pad durch alle 14 Einträge gehen. Erwartet: die Liste scrollt, die Auswahl bleibt
    sichtbar, der Zähler oben rechts zählt `1/14` … `14/14`, rechts ist ein Scrollbalken.
13. Erwartet: bei den Einträgen **Person: username**, **Person: email**, **Person: phone**,
    **Person: name** steht ein `!` am rechten Rand (sie kontaktieren Dritte).

## 5. Personenmodule – Status

14. **Person modules** öffnen (startet ohne Eingabe).

Erwartet, wenn im Gast ein `python3` ≥ 3.10 vorhanden ist:

```
# Person modules (PersonIntel)
i PersonIntel 0.1.0 (protocol 1) via <pfad> + bundled PersonIntel
i Data: /home/user/.local/share/personintel
i No encrypted credential store on this device (the bundle is pure Python).
i Pass vendor keys as PERSONINTEL_<MODULE>_<FIELD>, e.g. PERSONINTEL_PIPL_API_KEY.
! Holehe: Nicht installiert
i     needs: Installation: pipx install holehe ...
... (alle zehn Module)
# Summary
! 0 of 10 person modules ready
```

Erwartet, wenn **kein** `python3` im Gast ist:

```
# Person modules (PersonIntel)
! PersonIntel bridge not available: PersonIntel not found
i The bundle carries PersonIntel, but no python3 was found on the device. ...
i The infrastructure modules keep working without it.
```

**Beides ist ein gültiges Ergebnis.** Entscheidend ist, dass alle zehn Module genannt werden
bzw. die fehlende Voraussetzung klar dasteht – und dass Schritt 3 danach unverändert
funktioniert.

**Festhalten:** Welcher der beiden Fälle eintritt, und die vollständige Ausgabe
(`X` für die Gesamtliste, dann abfotografieren oder aus dem Log kopieren).

## 6. Zweckbindung – der wichtigste Test

15. **Person: username** öffnen, einen Handle eingeben, **Start** drücken.
    Erwartet: **Bestätigungsschirm**, nicht sofortiger Start.
16. Ohne Haken **B** drücken. Erwartet: **nichts passiert**.
17. Nur `Z` drücken (ein Haken), dann **B**. Erwartet: **nichts passiert**.
18. `V` (Cancel). Erwartet: zurück zum Eingabefeld, nichts wurde gesendet.
19. Erneut **Start**, beide Haken (`Z` und `X`), dann **B**.
    Erwartet: Lauf startet und meldet
    `! No valid research purpose - person queries are blocked`, weil noch kein Zweck
    dokumentiert ist.
20. **Case & purpose** öffnen, einen konkreten Zweck eintippen (mindestens 20 Zeichen, z. B.
    `Verifikation einer Quelle fuer einen Artikel`), **Start**.
    Erwartet: `+ Purpose documented, valid until <morgen>` und die Falldaten.
21. Schritt 19 wiederholen. Erwartet: die Abfrage läuft jetzt; nicht installierte Module werden
    mit ihrer Voraussetzung übersprungen, vorhandene liefern Befunde mit Belegstufe.

**Festhalten:** Verhält sich jeder Schritt wie beschrieben? Ein Start ohne Bestätigung oder
ohne Zweck wäre ein schwerer Fehler.

## 7. Darstellung der Befunde

22. In einem Lauf mit Treffern prüfen: Zeilen mit `=` (belegt) sind fett und grün, `~` (Indiz)
    dunkler, `?` (unbestätigt) blass. Die Übersicht zählt sie als Treffer.
23. **Links & hints** öffnen. Erwartet ohne übernommene Verbindungen:
    `No links taken over yet.` plus die Erklärung, dass Verbindungen nie automatisch entstehen.
24. **Report** öffnen. Erwartet: Zweck, Methodik, Befunde nach Belegstufe, Einschränkungen.

## 8. Bedienung

25. Touch: im Menü auf einen Eintrag tippen, in der Ergebnisliste wischen, auf die untere
    Tastenleiste tippen.
26. Tasten: `Z X C V B` in jedem Schirm. Erwartet: `C` (Power) bleibt ohne Wirkung, die
    physische Bksp-Taste schließt die App (Verhalten von Flipper OS, unverändert).
27. Bildschirmtastatur: Groß-/Kleinschreibung, `<`, `clr`, `space`.

## 9. Stabilität

28. Einen langen Lauf (`Domain / recon`) mit `V` (Stop) abbrechen. Erwartet: `i Stopped`,
    kein Absturz, kein Zombie-Prozess.
29. App schließen und erneut starten. Erwartet: der dokumentierte Zweck ist noch gültig
    (er liegt in `/home/user/.local/share/personintel`).
30. Nach einem Personenlauf prüfen, dass **kein** Python-Prozess im Gast zurückbleibt:
    `ps aux | grep -c personintel` sollte nur den `grep` selbst zählen.

---

## Was ich für die Auswertung brauche

Bitte schicke mir:

1. **`/tmp/flipperone-osint.log`** aus dem Gast (vollständig).
2. Die **Gesamtliste** (`X`) von **Person modules** – abfotografiert oder als Text.
3. Das Ergebnis von **Schritt 6** (Zweckbindung), Schritt für Schritt: was passierte bei 16, 17,
   19, 20, 21.
4. Ein Foto oder Screenshot des **Bestätigungsschirms** und der **Ergebnisliste mit
   Belegstufen**.
5. Die Ausgabe von `python3 --version` im Gast (über das Terminal des Emulators oder den
   File Manager), damit klar ist, welcher der beiden Fälle aus Schritt 5 gilt.
6. Laufzeiten: Start der App, und je ein Lauf von `phone`, `domain`, `Person modules`.
7. Jede Fehlermeldung im Wortlaut.

Mit diesen Angaben kann ich sagen, was auf dem Gerät tatsächlich funktioniert – und was nicht.
Ohne sie bleibt der Emulatorteil dieses Projekts **ungetestet**, und ich werde ihn auch so
bezeichnen.

## Referenzergebnisse zum Vergleich (x86_64-Host, nicht das Gerät)

Diese Werte habe ich gemessen, sie gelten **nicht** für den Emulator, sondern als Anhaltspunkt:

| | 1.3.0 | 1.4.0 |
|---|---|---|
| Start der Oberfläche | 4,5 ms | 4,4 ms |
| RAM im Leerlauf | 7,7 MiB | 7,8 MiB |
| CPU im Leerlauf | 0,8 % | 0,8 % |
| `phone`-Lauf | 3 ms | 2 ms, zeichengleiche Ausgabe |
| Personenmodul mit Brücke | – | 146 ms, 34 MiB, danach beendet |
| Personenmodul ohne PersonIntel | – | 51 ms, meldet die Voraussetzung |

Unter QEMU mit Software-Emulation ist mit einem Vielfachen dieser Zeiten zu rechnen.
