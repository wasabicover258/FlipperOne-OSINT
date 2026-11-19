# FlipperOne-OSINT: versions (newest first)

Only the current build is kept in `Public Releases/` (synced to the Flipper
Emulator). Older AppImages were removed from the repository in 2.2.0; they
remain reachable through the Git history and the experiment branches.

| Version | Line | Change |
|---------|------|--------|
| 2.2.0 | main | `FlipperOne-OSINT-2.2.0-aarch64.AppImage`, SHA-256 `afac6097c6b4a4431187e8d06361fe3f7f745d01b6e5531a8205325ed279f9b0`. **Entity engine** (roadmap phases 0 + 1, plus first items of 2-5). Every module declares input -> output kinds (domain -> hostname/IP/cert/MX ...); new findings flow automatically through matching modules with adjustable depth and scope. Unified finding format (type, value, source, time, confidence, severity). Per-module timeout, rate limit, retries; a slow service no longer blocks the run. Local case store with run history and diff, response cache, API keys in `~/.config/flipperone-osint/keys.env` (`osint-cli modules` shows what is unlocked). Export JSON / Markdown / GraphML / CSV. New modules: subdomain sources (crt.sh, Cert Spotter, Wayback CDX, AlienVault OTX, urlscan, HackerTarget; VirusTotal and SecurityTrails with key), wildcard detection, prefix permutations, **subdomain takeover check** (43 services), **lookalike/typosquatting** detection (dnstwist style, incl. IDN homoglyphs), TLS expiry/trust/legacy-protocol, exposed `.git`/`.env`, Shodan InternetDB, RIPEstat ASN/prefixes/neighbours, **CVE prioritisation with CISA KEV + EPSS**. Attack-surface grade, pivot suggestions, **watch mode** (rescan + changes). UI: new "Deep scan" and "Watch / diff" modes, scrolling menu. Fixes: Exploit.in entry queried GitLab (removed), global 150 s kill replaced by a configurable limit, wrong watchdog comment. Username check now re-tests every hit with a random control name and hides platforms that answer "found" for anything. Go tests with recorded fixtures. |
| 2.0.5 | experiment (ChatGPT) | Alpha-mask shelf icon fix. Source: branch `experiment/chatgpt-v2.0.5-alpha-icon`. Public release at the time. |
| 2.0.4 | experiment (ChatGPT) | Shelf icon. Branch `experiment/chatgpt-v2.0.4-shelf-icon`. |
| 2.0.3 | experiment (ChatGPT) | List buttons. Branch `experiment/chatgpt-v2.0.3-list-buttons`. |
| 2.0.2 | experiment (ChatGPT) | Grayscale display palette. Branch `experiment/chatgpt-v2.0.2-grayscale`. |
| 2.0.1 | experiment (ChatGPT) | PDF search. Branch `experiment/chatgpt-v2.0.1-pdf`. |
| 2.0 | experiment (ChatGPT) | AI web research (Wikipedia, OpenAlex, optional Brave + LLM endpoint). Branch `experiment/chatgpt-v2.0-ai-research`. |
| 1.6.1 | experiment (ChatGPT) | Reliability fixes. Branch `experiment/chatgpt-v1.6.1-reliability`. |
| 1.6 | experiment (ChatGPT) | Enrichment (IPv6, ASN, Wayback, GLEIF). Branch `experiment/chatgpt-v1.6-enrichment`. |
| 1.5 | experiment (ChatGPT) | GPS / points of interest. Branch `experiment/chatgpt-v1.5-poi`. |
| 1.4 | experiment (ChatGPT) | UI rework. Branch `experiment/chatgpt-v1.4-ui`. |
| 1.0 - 1.3.1 | experiment (ChatGPT) | Early test builds `ChatGPT Test/ChatGPT-Test-*.AppImage` (separate numbering from the main line). |
| 1.3.0 | main | Results are presented as a navigable **Overview**: every result category with a status dot and a finding count; d-pad selects, OK opens full-screen, X toggles index / full list. |
| 1.2.0 | main | Correlation engine + entity graph on infrastructure entities: operator/ASN spread, shared-hosting IPs, netblock groups, common services, vulnerable-host rollup, rDNS pivot candidates; text graph domain -> operator -> IP -> hosts. Person-linking services deliberately not emulated. |
| 1.1.1 | main | Native raw-TCP AXFR probe; web-exposure check (.git, .env, backups, server-status, phpinfo), directory listing, risky HTTP methods. |
| 1.1.0 | main | Live TCP connect port scan + banner grab; multi-source subdomains (crt.sh, Cert Spotter, HackerTarget); AXFR check. Watchdog raised to 150 s. |
| 1.0.0 | main | Full domain recon with DNS-over-HTTPS (CAA, DNSSEC, SOA), mail-security grade (SPF, DMARC, DKIM, MTA-STS), tech fingerprint, infrastructure tree. IP: RDAP netblock + abuse contact, CPEs. Username: 70+ platforms. |
| 0.2.8 | main | Step back moved to the [ ] button (Flipper OS closes apps on Bksp); Clear moved onto the on-screen keyboard. |
| 0.2.7 | main | Physical Bksp only steps back; the app closes only with Z (Exit). |
| 0.2.6 | main | Backspace can no longer close the app. |
| 0.2.5 | main | Flat UI; lowercase keyboard with Shift; results tabs Refresh + Again. |
| 0.2.4 | main | Text cursor (Z/X move, V clears). |
| 0.2.3 | main | Keyboard focus with arrows + Enter; Z closes the app; Flipper One orange. |
| 0.2.2 | main | On-screen touch keyboard; Flipper buttons Z X C V B control the app; project switched to English. |
| 0.2.1 | main | Orange design, key test screen, touch scrolling, start log. |
| 0.2.0 | main | Native SDL2 window + Go backend: username, email, phone, domain, IP, name -> username variants. |
| 0.1.2 | main | App shelf entry (`app.toml`, 14x14 icon), start via `flipctl`. |
| 0.1.1 | main | First ARM64 build; `--port` and `--no-browser`. |
| 0.1.0 | main | First skeleton (x86_64). |
