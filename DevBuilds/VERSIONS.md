# FlipperOne-OSINT: versions (newest first)

| Version | File | Change |
|---------|------|--------|
| 0.2.8 | `DevBuilds/FlipperOne-OSINT-0.2.8-aarch64.AppImage` | Step back moved to the [ ] button (measured on the device: Flipper OS itself closes the running app on Bksp, for every app, so no app can use that key); Clear moved onto the on-screen keyboard |
| 0.2.7 | `DevBuilds/FlipperOne-OSINT-0.2.7-aarch64.AppImage` | Physical Bksp key (arrives as a close request from the system) now only steps back; the app can only be closed with Z (Exit) |
| 0.2.6 | `DevBuilds/FlipperOne-OSINT-0.2.6-aarch64.AppImage` | Backspace can no longer close the app (Esc in the menu removed, held Backspace stops at the empty field instead of running on into the menu) |
| 0.2.5 | `DevBuilds/FlipperOne-OSINT-0.2.5-aarch64.AppImage` | Cleaner flat UI; keyboard is lowercase by default with a Shift toggle; Name/Help/Key test removed; results tabs Refresh + Again; Backspace only steps back and never closes the app |
| 0.2.4 | `DevBuilds/FlipperOne-OSINT-0.2.4-aarch64.AppImage` | Text cursor: Z/X move left/right inside the typed text, V clears, Backspace deletes at the cursor; consent notices removed |
| 0.2.3 | `DevBuilds/FlipperOne-OSINT-0.2.3-aarch64.AppImage` | Keyboard focus with arrow keys + Enter (like the browser keyboard); Z button closes the app, Backspace/V goes one step back; exact Flipper One orange |
| 0.2.2 | `DevBuilds/FlipperOne-OSINT-0.2.2-aarch64.AppImage` | On-screen touch keyboard; the Flipper buttons (keys Z X C V B) now control the app instead of typing letters; tab bar matches the five buttons; whole project switched to English |
| 0.2.1 | `DevBuilds/FlipperOne-OSINT-0.2.1-aarch64.AppImage` | Orange Flipper-style design, key test screen, touch scrolling, start log `/tmp/flipperone-osint.log`, version in the app name |
| 0.2.0 | `DevBuilds/FlipperOne-OSINT-0.2.0-aarch64.AppImage` | New: native SDL2 window + Go backend. Modules: username (33 platforms), email, phone, domain, IP, name -> username variants |
| 0.1.2 | `DevBuilds/FlipperOne-OSINT-0.1.2-aarch64.AppImage` | App shelf entry (`app.toml`, 14x14 icon), start like real Flipper apps (`flipctl`), start log |
| 0.1.1 | `DevBuilds/FlipperOne-OSINT-0.1.1-aarch64.AppImage` | ARM64 build (Flipper OS); new start options `--port` and `--no-browser` |
| 0.1.0 | `Public Releases/FlipperOne-OSINT-0.1.0-x86_64.AppImage` | First skeleton (x86_64) |
