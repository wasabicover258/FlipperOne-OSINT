"""Pfade und Einstellungen (rein lokal, XDG-konform)."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AppPaths:
    data_dir: Path
    config_dir: Path

    @classmethod
    def default(cls) -> "AppPaths":
        home = os.environ.get("PERSONINTEL_HOME")
        if home:
            base = Path(home).expanduser()
            return cls(data_dir=base / "data", config_dir=base / "config")
        xdg_data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        xdg_conf = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return cls(data_dir=xdg_data / "personintel", config_dir=xdg_conf / "personintel")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "personintel.db"

    @property
    def settings_path(self) -> Path:
        return self.config_dir / "settings.json"

    @property
    def credentials_path(self) -> Path:
        return self.config_dir / "credentials.enc"

    def ensure(self) -> None:
        for d in (self.data_dir, self.config_dir):
            d.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(d, 0o700)
            except OSError:
                pass


@dataclass
class Limits:
    """Grenzen der Recherchekontrolle (anpassbar, aber nie unbegrenzt)."""

    max_targets_per_case: int = 10
    max_active_queries_per_case_per_day: int = 25
    min_active_interval_seconds: float = 5.0
    max_purpose_days: int = 90
    min_purpose_chars: int = 20
    query_timeout_seconds: int = 300


@dataclass
class Settings:
    enabled_adapters: dict[str, bool] = field(default_factory=dict)
    adapter_config: dict[str, dict[str, Any]] = field(default_factory=dict)  # nur nicht-geheime Werte
    limits: Limits = field(default_factory=Limits)
    credential_backend: str = "file"  # file | keyring

    def is_enabled(self, adapter_id: str) -> bool:
        return self.enabled_adapters.get(adapter_id, True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled_adapters": self.enabled_adapters,
            "adapter_config": self.adapter_config,
            "limits": self.limits.__dict__,
            "credential_backend": self.credential_backend,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Settings":
        lim = Limits()
        for k, v in (d.get("limits") or {}).items():
            if hasattr(lim, k):
                setattr(lim, k, type(getattr(lim, k))(v))
        return cls(
            enabled_adapters=dict(d.get("enabled_adapters") or {}),
            adapter_config={k: dict(v) for k, v in (d.get("adapter_config") or {}).items()},
            limits=lim,
            credential_backend=d.get("credential_backend", "file"),
        )

    @classmethod
    def load(cls, path: Path) -> "Settings":
        try:
            return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return cls()
        except (ValueError, OSError):
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".settings-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
