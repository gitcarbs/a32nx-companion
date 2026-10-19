import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class SimbriefConfig:
    username: str | None = None
    userid: str | None = None


@dataclass(frozen=True)
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8765


@dataclass(frozen=True)
class SopConfig:
    landing_lights_off_ft: int = 10000
    single_engine_taxi: bool = False
    apu_start_before_push_min: int = 5
    units: Literal["kg", "lb"] = "kg"


@dataclass(frozen=True)
class Config:
    simbrief: SimbriefConfig
    server: ServerConfig = field(default_factory=ServerConfig)
    sop: SopConfig = field(default_factory=SopConfig)


def load_config(path: Path) -> Config:
    try:
        raw = tomllib.loads(path.read_text())
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc

    simbrief = _build(SimbriefConfig, raw, "simbrief")
    if (simbrief.username is None) == (simbrief.userid is None):
        raise ConfigError("[simbrief] needs exactly one of username or userid")

    sop = _build(SopConfig, raw, "sop")
    if sop.units not in ("kg", "lb"):
        raise ConfigError(f"[sop] units must be 'kg' or 'lb', got {sop.units!r}")

    return Config(simbrief=simbrief, server=_build(ServerConfig, raw, "server"), sop=sop)


def _build[T](cls: type[T], raw: dict[str, Any], name: str) -> T:
    # A typo'd key reaches the dataclass constructor as a TypeError.
    try:
        return cls(**_section(raw, name))
    except TypeError as exc:
        raise ConfigError(f"[{name}] {exc}") from exc


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    section = raw.get(name, {})
    if not isinstance(section, dict):
        raise ConfigError(f"[{name}] must be a table")
    return cast(dict[str, Any], section)
