"""Basisklasse fuer lokal installierte CLI-Tools."""

from __future__ import annotations

from typing import Any, ClassVar, Optional

from ..core.errors import AdapterNotAvailable
from .base import Adapter, ConfigField, ConfigValidation, InstallInfo
from ._process import ProcessRunner, find_executable, probe_version


class LocalToolAdapter(Adapter):
    executable_name: ClassVar[str] = ""
    version_argv: ClassVar[tuple[str, ...]] = ("--version",)
    install_text: ClassVar[str] = ""

    config_fields: ClassVar[tuple[ConfigField, ...]] = (
        ConfigField("executable_path", "Pfad zur ausführbaren Datei (optional)",
                    help="Leer lassen, um das Tool automatisch im PATH zu suchen."),
        ConfigField("timeout_seconds", "Timeout in Sekunden", default="300"),
    )

    def __init__(self, *a: Any, **kw: Any):
        super().__init__(*a, **kw)
        self.runner = ProcessRunner()

    # ------------------------------------------------------------------
    def exe(self) -> Optional[str]:
        return find_executable(self.executable_name, str(self.config.get("executable_path", "") or ""))

    def require_exe(self) -> str:
        exe = self.exe()
        if not exe:
            raise AdapterNotAvailable(f"{self.name} ist nicht installiert.", self.install_hint())
        return exe

    def timeout(self) -> float:
        try:
            return max(10.0, min(float(self.config.get("timeout_seconds") or 300), 3600.0))
        except (TypeError, ValueError):
            return 300.0

    def install_hint(self) -> str:
        return self.install_text

    def tool_version(self, exe: str) -> str:
        return probe_version([exe, *self.version_argv]) if self.version_argv else ""

    def detect_installation(self) -> InstallInfo:
        exe = self.exe()
        if not exe:
            return InstallInfo(False, message=f"{self.name} wurde nicht gefunden.")
        return InstallInfo(True, path=exe, version=self.tool_version(exe), message=f"Gefunden: {exe}")

    def validate_configuration(self, config: Optional[dict[str, Any]] = None) -> ConfigValidation:
        cfg = config if config is not None else self.config
        errors: list[str] = []
        t = cfg.get("timeout_seconds")
        if t not in (None, ""):
            try:
                if not 10 <= float(t) <= 3600:
                    errors.append("Timeout muss zwischen 10 und 3600 Sekunden liegen.")
            except (TypeError, ValueError):
                errors.append("Timeout muss eine Zahl sein.")
        path = str(cfg.get("executable_path", "") or "")
        if path and not find_executable(self.executable_name, path):
            errors.append(f"Konfigurierter Pfad ist nicht ausfuehrbar: {path}")
        return ConfigValidation(not errors, errors)

    def cancel_query(self, query_id: str) -> bool:
        return self.runner.cancel(query_id)
