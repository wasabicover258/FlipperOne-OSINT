# FlipperOne-OSINT

**Technical OSINT on a handheld: infrastructure, web, network, threat intel, organisations, places and blockchain, on the Flipper One (Linux ARM64).**

Desktop tools like SpiderFoot have more modules. FlipperOne-OSINT aims to win where they cannot: it is **mobile**, works **offline** where possible, and can **watch targets over time**. Person profiling (dossiers, linking names, numbers and accounts) is deliberately out of scope.

> **Current development version: 2.2.0** (entity engine). Last public AppImage: 2.0.5.
> Builds are for **AArch64 / ARM64** (Flipper One), not for x86-64 PCs.

## Download

New versions are published as **[GitHub Releases](https://github.com/wasabicover258/FlipperOne-OSINT/releases)**: normal releases are public builds, pre-releases are DevBuilds. Each AppImage is built by CI from one Git tag and comes with a `.sha256` file.

Until the binary migration is done, the last public build is still available at
[`Public Releases/FlipperOne-OSINT-2.0.5-aarch64.AppImage`](https://github.com/wasabicover258/FlipperOne-OSINT/raw/refs/heads/main/Public%20Releases/FlipperOne-OSINT-2.0.5-aarch64.AppImage).

1. Download `FlipperOne-OSINT-<version>-aarch64.AppImage`.
2. Import it through the app store or file manager of your Flipper One.
3. Open **OSINT** from the app shelf.

The public release is synced to the [Flipper Emulator AppCatalogue](https://github.com/wasabicover258/Flipper-Emulator/tree/main/AppCatalogue/OSINT) automatically.

## What it does

### Deep scan (entity engine)

Enter a **domain, hostname, IPv4/IPv6 address, ASN (`AS15169`), CVE, LEI or coordinate**. The engine works like SpiderFoot/Maltego: every module declares what it consumes and what it produces, and every new finding automatically runs through all matching modules, within a scope (the target's registrable domain) and a depth limit.

```text
domain ──> subdomains ──> IPs ──> ports / software / CVEs ──> KEV + EPSS priority
   │            │           └──> ASN ──> prefixes, upstreams, peers
   │            ├──> CNAME ──> subdomain takeover check
   │            └──> TLS certificate ──> expiry, trust, new SAN hostnames
   └──> lookalike domains (typos, homoglyphs, other TLDs) ──> registered? MX? website?
```

| Area | Modules (free unless noted) |
|---|---|
| Subdomains | crt.sh, Cert Spotter, Wayback CDX, AlienVault OTX, urlscan, HackerTarget, prefix permutations (`dev-`, `staging-` ...), wildcard detection; with key: VirusTotal, SecurityTrails |
| Takeover | Dangling CNAMEs to 43 services (GitHub Pages, S3, Azure, Heroku, Shopify, Fastly ...): NXDOMAIN and "not found" fingerprints |
| Brand protection | dnstwist-style lookalikes: omission, repetition, transposition, keyboard typos, homoglyphs incl. IDN/punycode, bitsquatting, hyphenation, TLD swap; checked for NS, website and **mail server** |
| Web / TLS | Certificate expiry and trust, SAN hostnames, legacy TLS 1.0/1.1, exposed `.git` / `.env` / `.svn` / `server-status`, `security.txt` |
| Network | Shodan InternetDB (ports, CPEs, CVEs without scanning), RIPEstat IP -> ASN/prefix, ASN -> holder, all v4/v6 prefixes, upstreams, peers, size; reverse DNS (in-addr.arpa and ip6.arpa); ipwho.is location/ISP estimate; with key: Shodan host API |
| IPv6 | Canonical form, private/reserved ranges skipped, embedded IPv4 of 6to4 / Teredo / NAT64 addresses followed, EUI-64 (MAC-derived) interface IDs flagged |
| History | Wayback Machine: historic hostnames (CDX), first and latest archived snapshot |
| Vulnerabilities | CVEs prioritised with **CISA KEV** (known exploited -> critical) and **EPSS** probability instead of a CVE wall |

### Organisation / LEI

Enter a company name (`org:Siemens AG` on the command line) or a 20-character **LEI**. GLEIF returns the legal entity (legal name, status, jurisdiction, legal and HQ address, BIC) and its **direct and ultimate parent**; Wikidata adds the **official website domains** (by LEI where possible, otherwise by name as a lower-confidence candidate). Domains and parent companies are reported with a "deep ..." pivot suggestion but not scanned automatically. Legal entities only: no officers, employees or owners.

### GPS / place

Enter `lat,lon` (decimal degrees) or a place name / address. You get map links (OpenStreetMap, Google, Bing, `geo:` URI), DMS notation, **elevation** and **time zone / UTC offset** (Open-Meteo), the nearest mapped address (Nominatim), **public facilities within 500 m** - hospitals, clinics, pharmacies, restaurants, shops, offices, schools - strictly nearest first with their public address, phone and website (OSM Overpass, two servers), and nearby Wikipedia articles. Public map features only: no residents, owners or visitors.

The result starts with an **attack-surface summary** (grade A-F, findings by severity), **pivot suggestions** ("this IP links to 29 entities - deep 1.2.3.4"), then all entities by category. Every finding has a type, value, source, timestamp, confidence and severity.

### Watch / diff

**Watch / diff** rescans a target and shows what changed since the last run: new subdomains, new open ports, certificates about to expire, newly registered lookalike domains, new issues. Every target scanned there is added to the watch list; `osint-cli watch run` rescans all of them (for a timer, see below).

### Classic reports

| Input | What you get |
|---|---|
| **Domain / recon** | DNS incl. CAA/DNSSEC/SOA, mail security grade (SPF, DMARC, DKIM, MTA-STS), RDAP, web server and tech fingerprint, TLS, web exposure, AXFR, subdomain infrastructure tree with ports/CVEs and correlations |
| **IP address** | rDNS, ASN, RDAP netblock + abuse contact, live TCP port scan with banners, software and known CVEs |
| **Email address** | Provider, mail servers, SPF/DMARC/DKIM grade |
| **Phone number** | Country, format, line type (offline). No owner lookup. |
| **Username** | 70+ public platforms. Every hit is re-checked with a random control name; platforms that "find" anything are marked unreliable. A hit means the name is taken, not that it is the same person. |

## Controls

- **D-pad:** select menu entry, keyboard key or result category
- **Enter / OK:** open, start the search
- **Z:** exit · **X:** toggle overview / full list · **[ ]:** one step back
- On-screen keyboard: `<` delete, `clr` clear, `abc/ABC` shift

## Command line

The backend also runs without the UI: `FlipperOne-OSINT-<version>-aarch64.AppImage cli <command>` (or `osint-cli` from an extracted AppImage):

```text
osint-cli deep <domain|host|ip|ASN|CVE|LEI|lat,lon|org:name|place:name>
              [--depth 4] [--deadline 240] [--json] [--modules a,b] [--exclude a,b] [--fresh]
osint-cli org <name|LEI>                        # = deep org:<name>
osint-cli geo <lat,lon|place>                   # = deep <lat,lon> / place:<name>
osint-cli watch add|rm|list|scan|run [target]   # run: exit code 3 = alerts
osint-cli cases                                 # saved cases
osint-cli export <case> json|md|graphml|csv [file]
osint-cli modules                               # modules, inputs/outputs, unlocked keys
osint-cli update-data                           # refresh offline data packs
osint-cli <username|email|phone|domain|ip> <value>   # classic reports
```

GraphML opens in Gephi or yEd and can be imported into Maltego.

### API keys (optional)

Everything free runs without any key. Keys unlock extra modules; put them in `~/.config/flipperone-osint/keys.env` (environment variables override):

```ini
VIRUSTOTAL_API_KEY=
SECURITYTRAILS_API_KEY=
SHODAN_API_KEY=
```

`osint-cli modules` shows which modules are unlocked. Never commit keys to the repository.

### Storage and offline data

| Path | Content |
|---|---|
| `~/.local/share/flipperone-osint/cases/` | one JSON file per target with the last 10 runs (used for diff/watch and export) |
| `~/.local/share/flipperone-osint/watch.json` | watch list |
| `~/.local/share/flipperone-osint/data/` | offline packs: Public Suffix List, CISA KEV catalog, takeover patterns (editable) |
| `~/.cache/flipperone-osint/http/` | response cache, protects free APIs from rate limits |

Storage is plain JSON instead of SQLite: Go's standard library has no SQLite driver and a pure-Go one would roughly triple the binary on the device.

### Scheduled watching

A systemd user timer that rescans all watched targets every 6 hours:

```ini
# ~/.config/systemd/user/osint-watch.service
[Service]
Type=oneshot
ExecStart=%h/Applications/FlipperOne-OSINT-2.2.0-aarch64.AppImage cli watch run

# ~/.config/systemd/user/osint-watch.timer
[Timer]
OnBootSec=10min
OnUnitActiveSec=6h
[Install]
WantedBy=timers.target
```

## Build and release

| Part | Technology |
|---|---|
| UI | C / SDL2, 256 x 144 pixels |
| Backend | Go, static, no external dependencies |
| Package | AppImage for AArch64 |

```text
app-ordner/
  VERSION                      # version of the next release
  src/ui/osint-ui.c            # SDL2 interface
  src/cli/                     # Go backend: engine (engine.go, finding.go),
                               # modules (mod_*.go), storage, reports, tests
  app/FlipperOneOSINT.AppDir/  # AppRun, app.toml, shelf icon
tools/migrate-binaries-to-releases.sh   # one-time move of old AppImages to Releases
```

**Release flow:** set `app-ordner/VERSION`, commit, then tag. CI (`.github/workflows/build-appimage.yml`) runs `go vet` and the fixture-based tests, builds natively on ARM64, checks architecture and glibc level, packs the AppImage and creates the GitHub Release. A public release is then synced to the emulator.

```bash
git tag v2.2.0 && git push origin v2.2.0          # public release
git tag v2.2.0-dev.1 && git push origin v2.2.0-dev.1   # DevBuild (pre-release)
```

Tests run without network access, using recorded responses:

```bash
cd app-ordner/src/cli && go test ./...
```

Version history: [`DevBuilds/VERSIONS.md`](DevBuilds/VERSIONS.md).

## Responsible use

OSINT means evaluating **publicly available** information.

- Results are only as reliable as their sources; free services can be down or rate-limited.
- CVEs from InternetDB are version-based and unverified; confirm before acting.
- Active checks (port scans, AXFR) belong only on systems you own or are explicitly allowed to test.
- A matching username or name never proves identity.
