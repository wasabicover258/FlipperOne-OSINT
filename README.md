# FlipperOne-OSINT

An all-in-one OSINT application for the Flipper One OS (AppImage, ARM64).
Pick what you have (username, email, phone number, domain, IP address, name) and the
app gathers publicly available information about it.

There is no people search and no phone-owner lookup by design.

## Modules

| Module | What it does |
|--------|--------------|
| Username | Checks 33 public platforms (GitHub, GitLab, Reddit, Steam, ...) whether the name is taken |
| Email | Syntax, role/disposable/free provider, MX, mail provider, SPF/DMARC, Gravatar, domain registration |
| Phone | Country, E.164/international format, plausible length, line type (offline) |
| Domain | DNS records, RDAP registration, web server and security headers, TLS certificate, subdomains (crt.sh) |
| IP | rDNS, operator/country (ipinfo.io), open ports and known CVEs (Shodan InternetDB) |

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
