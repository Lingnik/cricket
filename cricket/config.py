"""Configuration: infrastructure structure from a TOML file, secrets from the environment.

Config is split into two tiers (see docs/DESIGN.md):

  * Infrastructure (this module) -- MUSH host/port/account/password, the control-socket
    port, the HTTP bind/port, and database paths. Secrets come from .env / the process
    environment so they never land in the committed TOML.
  * Behavior -- the bot identity, per-location engagement/directives, prompts, and
    inference params live in *persona profiles* in the committed config DB, edited at
    runtime over HTTP. See cricket/profiles/.

LocationConfig is still defined here because the profile layer derives LocationConfigs
from the active profile and the rest of the program consumes them.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

VALID_MODES = ("chat", "rp", "control")
VALID_ENGAGEMENT = ("always", "addressed")

_TRUE = ("1", "true", "yes", "on")


@dataclass
class MushConfig:
    host: str
    port: int
    use_tls: bool
    name: str
    password: str


@dataclass
class ControlConfig:
    port: int


@dataclass
class HttpConfig:
    host: str
    port: int


@dataclass
class PathsConfig:
    config_db: str
    memory_db: str


@dataclass
class AuthConfig:
    """Global, infrastructure-level grants. Per-location admins live in profiles."""

    operators: list = field(default_factory=list)
    wizards: list = field(default_factory=list)
    admins: list = field(default_factory=list)


@dataclass
class LocationConfig:
    name: str
    mode: str
    engagement: str = "addressed"
    prefixes: list = field(default_factory=list)
    directives: str = ""
    rate_limit: Union[str, None] = None
    enabled: bool = True
    admins: list = field(default_factory=list)


@dataclass
class Config:
    mush: MushConfig
    control: ControlConfig
    http: HttpConfig
    auth: AuthConfig
    paths: PathsConfig


def parse_env_file(path: Union[str, Path]) -> dict:
    """Parse a simple KEY=VALUE .env file. Ignores blanks and # comments; strips
    optional surrounding quotes. No interpolation, no exports."""
    env: dict = {}
    text = Path(path).read_text(encoding="utf-8")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        env[key] = value
    return env


def _truthy(value: Union[str, None]) -> bool:
    return (value or "").strip().lower() in _TRUE


def load_config(toml_path: Union[str, Path], env: Union[dict, None] = None) -> Config:
    """Build a Config from an infra TOML file plus an environment mapping (default {})."""
    env = dict(env or {})
    data = tomllib.loads(Path(toml_path).read_text(encoding="utf-8"))

    mush = MushConfig(
        host=env.get("CRICKET_MUSH_HOST", ""),
        port=int(env.get("CRICKET_MUSH_PORT", "4201")),
        use_tls=_truthy(env.get("CRICKET_MUSH_USE_TLS", "false")),
        name=env.get("CRICKET_MUSH_NAME", ""),
        password=env.get("CRICKET_MUSH_PASSWORD", ""),
    )

    control_default = int(data.get("control", {}).get("port", 4250))
    control = ControlConfig(
        port=int(env.get("CRICKET_MUSH_CONTROL_PORT", str(control_default)))
    )

    http_raw = data.get("http", {})
    http = HttpConfig(
        host=http_raw.get("host", "127.0.0.1"),
        port=int(env.get("CRICKET_HTTP_PORT", str(http_raw.get("port", 4280)))),
    )

    auth_raw = data.get("auth", {})
    auth = AuthConfig(
        operators=list(auth_raw.get("operators", [])),
        wizards=list(auth_raw.get("wizards", [])),
        admins=list(auth_raw.get("admins", [])),
    )

    paths_raw = data.get("paths", {})
    paths = PathsConfig(
        config_db=paths_raw.get("config_db", "data/cricket-config.sqlite3"),
        memory_db=paths_raw.get("memory_db", "data/cricket-memory.sqlite3"),
    )

    return Config(mush=mush, control=control, http=http, auth=auth, paths=paths)


def parse_rate_limit(spec: Union[str, None]):
    """Parse a "count / Ns" rate spec into (count, seconds), or None.

    Examples: "1 / 20s" -> (1, 20.0); "3/5s" -> (3, 5.0).
    """
    if not spec:
        return None
    count_part, sep, per_part = spec.partition("/")
    if not sep:
        return None
    count = int(count_part.strip())
    per = per_part.strip().rstrip("s").strip()
    return (count, float(per))
