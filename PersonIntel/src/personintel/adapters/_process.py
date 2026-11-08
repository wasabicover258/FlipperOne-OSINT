"""Hilfen fuer lokale CLI-Tools: Auffinden, Versionsabfrage, abbrechbarer Prozesslauf."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

MAX_OUTPUT_BYTES = 2_000_000

_EXTRA_DIRS = [
    "~/.local/bin", "~/go/bin", "/usr/local/go/bin", "/usr/local/bin", "/opt/phoneinfoga",
    "~/.cargo/bin",
]
_PASS_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy",
             "https_proxy", "no_proxy", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "XDG_CONFIG_HOME", "XDG_DATA_HOME")


def find_executable(name: str, override: str = "") -> Optional[str]:
    """Konfigurierter Pfad > PATH > uebliche Installationsorte."""
    if override:
        p = Path(override).expanduser()
        return str(p) if p.is_file() and os.access(p, os.X_OK) else None
    found = shutil.which(name)
    if found:
        return found
    for d in _EXTRA_DIRS:
        cand = Path(d).expanduser() / name
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return None


def clean_env(extra: Optional[dict[str, str]] = None) -> dict[str, str]:
    env = {k: os.environ[k] for k in _PASS_ENV if k in os.environ}
    env.update({"TERM": "dumb", "NO_COLOR": "1", "PYTHONIOENCODING": "utf-8"})
    env.update(extra or {})
    return env


@dataclass
class ProcResult:
    returncode: Optional[int]
    stdout: str
    stderr: str
    timed_out: bool = False
    cancelled: bool = False


class ProcessRunner:
    """Startet Prozesse in eigener Session, damit sie samt Kindprozessen abgebrochen werden koennen."""

    def __init__(self) -> None:
        self._procs: dict[str, subprocess.Popen] = {}
        self._cancelled: set[str] = set()
        self._lock = threading.Lock()

    def run(self, query_id: str, argv: Sequence[str], *, cwd: str, timeout: float,
            env: Optional[dict[str, str]] = None) -> ProcResult:
        with self._lock:
            if query_id in self._cancelled:
                return ProcResult(None, "", "", cancelled=True)
        proc = subprocess.Popen(list(argv), cwd=cwd, env=env or clean_env(), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        with self._lock:
            self._procs[query_id] = proc
        timed_out = False
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill(proc)
            out, err = proc.communicate()
        finally:
            with self._lock:
                self._procs.pop(query_id, None)
        with self._lock:
            cancelled = query_id in self._cancelled
            self._cancelled.discard(query_id)
        return ProcResult(proc.returncode, out[:MAX_OUTPUT_BYTES].decode("utf-8", "replace"),
                          err[:MAX_OUTPUT_BYTES].decode("utf-8", "replace"), timed_out, cancelled)

    @staticmethod
    def _kill(proc: subprocess.Popen) -> None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    def cancel(self, query_id: str) -> bool:
        with self._lock:
            proc = self._procs.get(query_id)
            self._cancelled.add(query_id)
        if proc is not None:
            self._kill(proc)
            return True
        return False


def probe_version(argv: Sequence[str], timeout: float = 10.0) -> str:
    """Erste nicht-leere Ausgabezeile eines Versionsaufrufs (leer bei Fehler)."""
    try:
        res = subprocess.run(list(argv), capture_output=True, timeout=timeout, env=clean_env(),
                             stdin=subprocess.DEVNULL, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    text = (res.stdout or b"").decode("utf-8", "replace") + "\n" + (res.stderr or b"").decode("utf-8", "replace")
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:120]
    return ""


def help_text(exe: str, timeout: float = 15.0) -> str:
    try:
        res = subprocess.run([exe, "--help"], capture_output=True, timeout=timeout, env=clean_env(),
                             stdin=subprocess.DEVNULL, check=False)
        return (res.stdout or b"").decode("utf-8", "replace") + (res.stderr or b"").decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError):
        return ""
