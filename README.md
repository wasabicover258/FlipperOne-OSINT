# FlipperOne-OSINT

A technical OSINT / reconnaissance application for the Flipper One OS (AppImage, ARM64).
Give it a domain, an IP address, an email address or a public handle and it maps the
**infrastructure and public footprint** of that target.

This is an infrastructure-recon tool. It investigates domains, hosts, networks and
deliberately-public accounts. It does **not** do people search, owner lookup for a
phone number, or automated profiling of a private individual.

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

### What is deliberately left out

This is an infrastructure-recon tool. The person-focused OSINT tools from the same
Kali toolbox — Holehe and Mosint (email to a person's accounts and breaches),
Sherlock used as an automatic pivot, PhoneInfoga owner lookup, Ignorant, Mr.Holmes —
and commercial people-search / identity-linking platforms such as Pipl, Spokeo,
ShadowDragon and Babel Street — are intentionally **not** emulated. The tool borrows
the *framework structure* of SpiderFoot, Recon-ng and Maltego (modules, correlation,
an entity graph) but applies it to **systems, not people**: it does not take one
fragment about a person and assemble a profile of them.

## Controls

The five buttons below the screen reach the app as the keys `Z X C V B`.

| Button | Menu | Input screen | Results |
|--------|------|--------------|---------|
| ✕ (Z) | Exit | Cursor left | Exit |
| ☰ (X) | - | Cursor right | Jump to top |
| [ ] (V) | - | Back to the menu | Refresh / Stop |
| ✓ (B) | Open | Start | New search |

The d-pad moves the keyboard focus, Enter presses the focused key, `<` deletes
and `clr` empties the field. `abc`/`ABC` toggles upper case.

The physical **Bksp** key cannot be used by the app: Flipper OS treats it as the
system back key and closes the running app (this applies to every app, not just
this one). That is why the step back inside the app sits on the [ ] button.

## Layout

- `app-ordner/src/ui/` - SDL2 user interface (C), touch + on-screen keyboard + Flipper buttons
- `app-ordner/src/cli/` - backend `osint-cli` (Go, static)
- `app-ordner/app/FlipperOneOSINT.AppDir/` - AppImage template (`AppRun`, `app.toml`, icon)
- `app-ordner/VERSION` - version of the next build

## Releases

1. Change `app-ordner/VERSION` and push. GitHub Actions builds the AppImage into `DevBuilds/`.
2. Test a build; copy the chosen file to `Public Releases/`.
3. A second workflow places the newest public release into `AppCatalogue/OSINT/` of the Flipper-Emulator repo.

The version history is in [DevBuilds/VERSIONS.md](DevBuilds/VERSIONS.md).
