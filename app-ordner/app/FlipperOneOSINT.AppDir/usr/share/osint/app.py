#!/usr/bin/env python3
"""FlipperOne-OSINT - Grundgerüst (v0.1.0)

Lokale Web-UI (nur 127.0.0.1). Eingabetyp wählen, Wert eingeben, Module laufen.
Neue Module: Funktion schreiben und mit @module(...) registrieren.
"""
import json
import re
import socket
import threading
import urllib.request
import urllib.error
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "0.1.1"
INPUT_TYPES = {
    "username": "Username",
    "realname": "Echter Name",
    "email": "E-Mail-Adresse",
    "phone": "Telefonnummer",
    "domain": "Domain",
}
MODULES = {}


def module(input_type, name):
    def deco(fn):
        MODULES.setdefault(input_type, []).append((name, fn))
        return fn
    return deco


# ---------- Module ----------

@module("email", "Syntax-Prüfung")
def email_syntax(value):
    ok = re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", value) is not None
    return {"gueltige_syntax": ok}


@module("email", "Domain erreichbar (DNS)")
def email_domain(value):
    if "@" not in value:
        return {"fehler": "Kein @ gefunden"}
    domain = value.split("@", 1)[1]
    try:
        ips = sorted({r[4][0] for r in socket.getaddrinfo(domain, None)})
        return {"domain": domain, "aufloesbar": True, "ips": ips[:5]}
    except socket.gaierror:
        return {"domain": domain, "aufloesbar": False}


@module("domain", "DNS-Auflösung")
def domain_dns(value):
    try:
        ips = sorted({r[4][0] for r in socket.getaddrinfo(value, None)})
        return {"aufloesbar": True, "ips": ips[:10]}
    except socket.gaierror:
        return {"aufloesbar": False}


COUNTRY_CODES = {"+49": "Deutschland", "+43": "Österreich", "+41": "Schweiz",
                 "+44": "Vereinigtes Königreich", "+33": "Frankreich", "+39": "Italien",
                 "+34": "Spanien", "+31": "Niederlande", "+48": "Polen", "+1": "USA/Kanada"}


@module("phone", "Format & Ländervorwahl")
def phone_format(value):
    num = re.sub(r"[^\d+]", "", value)
    if num.startswith("00"):
        num = "+" + num[2:]
    if not num.startswith("+"):
        return {"hinweis": "Bitte mit Ländervorwahl angeben, z. B. +49...", "bereinigt": num}
    country = next((n for c, n in COUNTRY_CODES.items() if num.startswith(c)), "unbekannt")
    digits = len(num) - 1
    return {"bereinigt": num, "land": country, "ziffern": digits,
            "plausible_laenge": 7 <= digits <= 15}


USERNAME_SITES = {
    "GitHub": "https://github.com/{}",
    "GitLab": "https://gitlab.com/{}",
    "Codeberg": "https://codeberg.org/{}",
}


@module("username", "Format-Prüfung")
def username_format(value):
    return {"laenge": len(value), "nur_zulaessige_zeichen": re.fullmatch(r"[\w.\-]{2,40}", value) is not None}


@module("username", "Profil-Check (GitHub, GitLab, Codeberg)")
def username_sites(value):
    if not re.fullmatch(r"[\w.\-]{2,40}", value):
        return {"fehler": "Ungültiger Username"}
    out = {}
    for site, tpl in USERNAME_SITES.items():
        url = tpl.format(value)
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "FlipperOne-OSINT/" + VERSION})
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                out[site] = {"status": r.status, "url": url, "gefunden": r.status == 200}
        except urllib.error.HTTPError as e:
            out[site] = {"status": e.code, "gefunden": False}
        except Exception as e:
            out[site] = {"fehler": str(e)[:80]}
    return out


@module("realname", "Username-Varianten (lokal)")
def name_variants(value):
    parts = [p.lower() for p in re.split(r"\s+", value.strip()) if p]
    if len(parts) < 2:
        return {"hinweis": "Bitte Vor- und Nachname angeben"}
    f, l = parts[0], parts[-1]
    return {"varianten": sorted({f + l, f + "." + l, f + "_" + l, f[0] + l, l + f, f + l[0]})}


# ---------- Server ----------

PAGE = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<title>FlipperOne-OSINT</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:system-ui,sans-serif;background:#0d1117;color:#e6edf3;max-width:820px;margin:2rem auto;padding:0 1rem}
h1{font-size:1.4rem}small{color:#8b949e}
.row{display:flex;gap:.5rem;margin:1rem 0}
select,input,button{background:#161b22;color:#e6edf3;border:1px solid #30363d;border-radius:6px;padding:.6rem;font-size:1rem}
input{flex:1}button{background:#238636;border-color:#238636;cursor:pointer}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:1rem;margin:.8rem 0}
.card h3{margin:.0 0 .5rem;font-size:1rem;color:#58a6ff}pre{margin:0;white-space:pre-wrap;word-break:break-word}
</style></head><body>
<h1>FlipperOne-OSINT <small>v__VERSION__</small></h1>
<small>Wähle, was du hast, und gib den Wert ein. Nur für Recherche zu eigenen Daten, Test-Accounts oder mit Einwilligung der Betroffenen.</small>
<div class="row"><select id="t"></select><input id="v" placeholder="Wert eingeben" autofocus><button id="go">Start</button></div>
<div id="out"></div>
<script>
const t=document.getElementById('t'),v=document.getElementById('v'),out=document.getElementById('out');
fetch('/api/types').then(r=>r.json()).then(d=>{for(const[k,n]of Object.entries(d)){t.add(new Option(n,k))}});
async function run(){
  out.innerHTML='<div class="card">Läuft…</div>';
  const r=await fetch('/api/run',{method:'POST',body:JSON.stringify({type:t.value,value:v.value.trim()})});
  const d=await r.json();out.innerHTML='';
  for(const m of d.results){const c=document.createElement('div');c.className='card';
    const h=document.createElement('h3');h.textContent=m.module;const p=document.createElement('pre');
    p.textContent=JSON.stringify(m.data,null,2);c.append(h,p);out.append(c)}
}
document.getElementById('go').onclick=run;v.addEventListener('keydown',e=>{if(e.key==='Enter')run()});
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            self._send(200, PAGE.replace("__VERSION__", VERSION), "text/html")
        elif self.path == "/api/types":
            self._send(200, json.dumps(INPUT_TYPES))
        else:
            self._send(404, "{}")

    def do_POST(self):
        if self.path != "/api/run":
            return self._send(404, "{}")
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        itype, value = body.get("type"), (body.get("value") or "")[:200]
        results = []
        for name, fn in MODULES.get(itype, []):
            try:
                results.append({"module": name, "data": fn(value)})
            except Exception as e:
                results.append({"module": name, "data": {"fehler": str(e)}})
        self._send(200, json.dumps({"results": results}))


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="FlipperOne-OSINT")
    ap.add_argument("--port", type=int, default=0, help="Fester Port (Standard: zufällig)")
    ap.add_argument("--no-browser", action="store_true", help="Browser nicht automatisch öffnen")
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = "http://127.0.0.1:%d/" % srv.server_address[1]
    print("FlipperOne-OSINT %s läuft auf %s (Strg+C zum Beenden)" % (VERSION, url))
    if not args.no_browser:
        def _open():
            if not webbrowser.open(url):
                print("Kein Browser gefunden. Öffne diese Adresse manuell:", url)
        threading.Timer(0.5, _open).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
