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
| Domain | Full recon: DNS (A/AAAA/MX/NS/TXT/SOA/CAA via DNS-over-HTTPS), DNSSEC, mail-security grade (SPF lookup budget, DMARC policy, DKIM selectors, MTA-STS), RDAP registration, web server, tech fingerprint, security-header grade, TLS certificate, subdomain discovery (crt.sh + DNS sweep), and a chained **infrastructure tree**: every host grouped by IP, each IP enriched with operator/ASN, open ports and known CVEs |
| IP | rDNS, ASN and operator (ipinfo.io), RDAP netblock range + abuse contact, open ports with named services, detected software (CPE) and known CVEs (Shodan InternetDB) |
| Email | Syntax, role/disposable/free provider, MX and mail provider, plus the full domain mail-security grade (SPF, DMARC, DKIM, MTA-STS), Gravatar, domain registration |
| Username | Checks 70+ public platforms (grouped: developer, security, social, creative, music, gaming, ...) whether the handle is taken, with a direct link to each profile |
| Phone | Country, E.164/international format, plausible length, line type (fully offline) |

### The infrastructure tree (domain module)

Starting from one domain the tool expands outward: it collects subdomains from
certificate-transparency logs and a DNS sweep of common labels, resolves them,
groups every host by the IP address behind it, and enriches the busiest addresses
with their operator/ASN, open ports and known vulnerabilities. The result is a
single map of the target's whole reachable surface, built from one starting point.

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
