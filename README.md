# FlipperOne-OSINT

A technical OSINT / reconnaissance application for the Flipper One OS (AppImage, ARM64).
Give it a domain, an IP address, an email address or a public handle and it maps the
**infrastructure and public footprint** of that target.

Since 1.4.0 it also does **person research**, through the bundled
[PersonIntel](PersonIntel/) module: with a documented purpose, a separate confirmation for
every check that contacts third parties, and an evidence level on every finding. It still
does **not** do owner lookup for a phone number and does not assemble a profile of a
private individual on its own — see [Person research](#person-research-since-140).

## Modules

| Module | What it does |
|--------|--------------|
| Domain | Full recon: DNS (A/AAAA/MX/NS/TXT/SOA/CAA via DNS-over-HTTPS), DNSSEC, zone-transfer (AXFR) check, mail-security grade (SPF lookup budget, DMARC policy, DKIM selectors, MTA-STS), RDAP registration, web server, tech fingerprint, security-header grade, TLS certificate, multi-source subdomain discovery (crt.sh + certspotter + HackerTarget + DNS sweep), and a chained **infrastructure tree**: every host grouped by IP, each IP enriched with operator/ASN, a **live port scan + service banners**, Shodan data and known CVEs |
| IP | rDNS, ASN and operator (ipinfo.io), RDAP netblock range + abuse contact, a **live TCP port scan with service banners**, plus Shodan InternetDB (ports, software/CPE, known CVEs) |
| Email | Syntax, role/disposable/free provider, MX and mail provider, plus the full domain mail-security grade (SPF, DMARC, DKIM, MTA-STS), Gravatar, domain registration |
| Username | Checks 70+ public platforms (grouped: developer, security, social, creative, music, gaming, ...) whether the handle is taken, with a direct link to each profile |
| Phone | Country, E.164/international format, plausible length, line type (fully offline) |

### Techniques

The tool reimplements the information-gathering techniques of several Kali tools
as one static binary (nothing is shelled out): certificate-transparency and
passive-DNS subdomain discovery (crt.sh, certspotter, HackerTarget — theHarvester
style), DNS enumeration and an AXFR zone-transfer check (DNSrecon style), WHOIS/RDAP,
TLS and HTTP fingerprinting (WhatWeb style), a live TCP connect port scan with
banner grabbing (nmap style), and Shodan InternetDB for CVEs. It stays on
read/reconnaissance techniques and does not include active attack or brute-force
tooling (no sqlmap, wpscan brute, dir brute-forcing, etc.).

### The infrastructure tree (domain module)

Starting from one domain the tool expands outward: it collects subdomains from
certificate-transparency logs (crt.sh + certspotter), HackerTarget and a DNS sweep
of common labels, resolves them, groups every host by the IP address behind it, and
enriches the busiest addresses with their operator/ASN, a live TCP port scan with
service banners, and known vulnerabilities. The result is a single map of the
target's whole reachable surface, built from one starting point.

### Techniques (and the Kali tools they mirror)

Every technique is re-implemented natively in Go, so the app needs no external
binaries and runs entirely on the Flipper:

| Technique in the app | Kali equivalent |
|----------------------|-----------------|
| DNS enumeration incl. SOA/CAA/DNSSEC over DNS-over-HTTPS | dnsrecon, dig |
| Zone-transfer (AXFR) check over raw TCP DNS | dnsrecon -t axfr |
| Subdomains from CT logs, HackerTarget and a DNS sweep | theHarvester, Sublist3r |
| Registration / netblock / abuse contact (RDAP) | whois |
| Operator, ASN, geolocation | ipinfo.io |
| Live TCP connect port scan + service/version banners | nmap -sT / -sV |
| Open ports, software (CPE) and known CVEs from a cached index | Shodan |
| Web tech / stack fingerprint | WhatWeb |
| Security-header and TLS grade | testssl.sh, securityheaders |
| Sensitive-path / directory-listing / HTTP-method exposure check | dirb, Nikto |
| Mail-security grade (SPF, DMARC, DKIM, MTA-STS) | dmarc/spf auditors |

### Correlation and entity graph (SpiderFoot / Recon-ng / Maltego idea)

After the infrastructure tree is built, the tool cross-references the discovered
entities instead of just listing them:

- **Operator / ASN spread** - how many providers the estate is split across.
- **Shared hosting** - IPs that serve several subdomains.
- **Netblock grouping** - mapped IPs that sit in the same /24.
- **Common services** - which ports recur across the hosts.
- **Vulnerable-host rollup** - which addresses carry known CVEs.
- **Pivot candidates** - reverse-DNS names pointing outside the target domain,
  i.e. related infrastructure worth a follow-up lookup (the Maltego "transform
  into a new entity" idea, applied to domains and hosts).

It then draws a text **entity graph**: `domain -> operator/ASN -> IP -> hosts`.
This brings the module/workspace/graph structure of SpiderFoot, Recon-ng and
Maltego to the app, applied to systems.

## Person research (since 1.4.0)

Up to 1.3.0 this was an infrastructure-only tool and person-focused OSINT was
deliberately left out. Since 1.4.0 the app also carries **person research**, but not as
a free-for-all: it runs through [PersonIntel](PersonIntel/), which enforces a documented
purpose, separates passive from active checks and attaches an evidence level to every
finding. The infrastructure modules are unchanged and keep working on their own.

| Person module | Input | Check | Needs |
|---|---|---|---|
| Holehe | email | active | `pipx install holehe` |
| Mosint | email | active | `mosint` + its own config file |
| Sherlock | username | active | `pipx install sherlock-project` |
| PhoneInfoga | phone | passive | `phoneinfoga` binary |
| Ignorant | phone | active | `pipx install ignorant` |
| Mr.Holmes | report file | passive | an existing report (import only) |
| Pipl | email, phone, username, name | active | vendor contract + API key |
| Spokeo | email, phone (US), username | active | vendor contract + API key |
| ShadowDragon | — | — | **not available**: no public API documentation |
| Babel Street | — | — | **not available**: the documented API is text analytics, not people search |

Nothing is simulated. A module that is not installed, not configured or not released by
its vendor says so on the **Person modules** screen, names the exact prerequisite, and is
skipped during a query — the other modules still run.

### What the app refuses to do

- **No query without a documented purpose.** `Case & purpose` asks why you are
  researching; without a valid purpose every person query is blocked.
- **No silent third-party contact.** An active check shows a confirmation screen with the
  identifier and two statements to tick. Only then does the backend receive the word
  `confirm`; without it PersonIntel refuses the query.
- **No mass lookups.** One identifier per query, at most ten per case, a daily budget and a
  minimum interval between active checks.
- **No identity claims.** A hit is a lead. `=` proven, `~` indication, `?` unconfirmed —
  and `=` is only ever set by a person reviewing a finding, never by a module. The same
  handle on two platforms is a hint, not a link.
- **No leaked credentials.** Breach sections are reduced to source name and date; passwords
  and hashes are discarded.
- **No circumvention.** Rate limits end a query instead of being worked around.

### Shared result model

Infrastructure and person findings land in one store. A finding that several sources
report becomes one entry with several sources (an account is identified by its profile
URL, so the same handle on two platforms stays two accounts). Links carry the evidence
level of their weakest end, and derived identifiers are only ever listed as *possible
follow-up queries* — nothing is queried automatically, and the case scope limits how many
identifiers a case may hold.

The combined modes (`Person: username`, `Person: email`, `Person: phone`) run the
infrastructure module and the person modules in one pass so the merge can happen.

### How it is wired

PersonIntel is Python; this app is C/SDL2 plus a static Go binary. Instead of shipping a
Qt interface (~250 MB, software-rendered on the device), the bundle carries PersonIntel as
540 KB of pure Python and talks to it over a line-based JSON protocol on stdin/stdout. The
process is started only when a person module is used and ends with the query — no service
stays behind. If the device has no Python 3.10+, the person modules say so and everything
else keeps working.

Because the bundle is pure Python, it has no `cryptography`: on the device there is no
at-rest encryption and no encrypted credential store, and vendor keys are passed as
`PERSONINTEL_<MODULE>_<FIELD>` environment variables. On a desktop install
(`pip install personintel`) both are available.

### What is still deliberately left out

The app borrows the *framework structure* of SpiderFoot, Recon-ng and Maltego (modules,
correlation, an entity graph). It does not assemble a profile from fragments: it does not
link identities on its own, does not rank people, and does not store raw vendor payloads.
Addresses, dates of birth and relatives are dropped from vendor records.

## Results view

When a search finishes the app shows an **Overview**: one row per result category
(DNS, Email security, Web exposure, Subdomains, Infrastructure, Correlations,
Entity graph, ...) with a status dot and a finding count. The d-pad moves between
categories, **OK** opens one full-screen, **X** switches between this index and the
full continuous list, and the step-back button returns to the index. This keeps the
whole result set available but tidy and navigable on the small screen.

## Controls

The five buttons below the screen reach the app as the keys `Z X C V B`.

| Button | Menu | Input screen | Confirmation | Results |
|--------|------|--------------|--------------|---------|
| ✕ (Z) | Exit | Cursor left | Tick statement 1 | Exit |
| ☰ (X) | - | Cursor right | Tick statement 2 | Jump to top |
| [ ] (V) | - | Back to the menu | Cancel | Refresh / Stop |
| ✓ (B) | Open | Start | Start (both ticked) | New search |

The menu scrolls: the d-pad reaches all entries, and `!` marks a mode that contacts third
parties. Modes without an input field (module status, links, report) start straight away.

The d-pad moves the keyboard focus, Enter presses the focused key, `<` deletes
and `clr` empties the field. `abc`/`ABC` toggles upper case.

The physical **Bksp** key cannot be used by the app: Flipper OS treats it as the
system back key and closes the running app (this applies to every app, not just
this one). That is why the step back inside the app sits on the [ ] button.

## Layout

- `app-ordner/src/ui/` - SDL2 user interface (C), touch + on-screen keyboard + Flipper buttons
  - `osint-ui --selftest` checks the state machine without a display
  - `osint-ui --screenshot <dir>` renders every screen offscreen for a layout review
- `app-ordner/src/cli/` - backend `osint-cli` (Go, static)
  - `findings.go` - shared result and graph model (sources, evidence levels, deduplication)
  - `personintel.go` - bridge to the person modules; `go test ./...` covers both
- `app-ordner/app/FlipperOneOSINT.AppDir/` - AppImage template (`AppRun`, `app.toml`, icon)
- `app-ordner/VERSION` - version of the next build
- `PersonIntel/` - the person-research module (Python); `python -m pytest -q` in that folder

## Releases

1. Change `app-ordner/VERSION` and push. GitHub Actions builds the AppImage into `DevBuilds/`.
   `build-appimage.yml` builds from `main`; `build-appimage-fusion.yml` builds from a
   `fusion/**` branch, commits only to that branch and refuses to write to `main`.
2. Test a build; copy the chosen file to `Public Releases/`.
3. A second workflow places the newest public release into `AppCatalogue/OSINT/` of the Flipper-Emulator repo.

Neither workflow ever replaces an existing AppImage: the file name carries the version and
the job fails if that file is already there.

The version history is in [DevBuilds/VERSIONS.md](DevBuilds/VERSIONS.md).
