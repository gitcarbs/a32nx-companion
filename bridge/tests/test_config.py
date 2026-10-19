from pathlib import Path

import pytest

from companion.config import ConfigError, load_config

EXAMPLE = Path(__file__).resolve().parents[2] / "config.example.toml"


def write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(body)
    return path


def test_example_config_loads() -> None:
    config = load_config(EXAMPLE)
    assert config.simbrief.username == "navigraph-alias"
    assert config.simbrief.userid is None
    assert config.server.port == 8765
    assert config.sop.units == "kg"


def test_defaults_fill_missing_sections(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, '[simbrief]\nuserid = "42"\n'))
    assert config.simbrief.userid == "42"
    assert config.server.host == "0.0.0.0"
    assert config.sop.landing_lights_off_ft == 10000


def test_simbrief_needs_exactly_one_identity(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="username or userid"):
        load_config(write(tmp_path, "[simbrief]\n"))
    with pytest.raises(ConfigError, match="username or userid"):
        load_config(write(tmp_path, '[simbrief]\nusername = "a"\nuserid = "1"\n'))


def test_rejects_unknown_units(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="units"):
        load_config(write(tmp_path, '[simbrief]\nuserid = "1"\n[sop]\nunits = "st"\n'))


def test_missing_file_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.toml")


def test_unknown_key_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"\[server\]"):
        load_config(write(tmp_path, '[simbrief]\nuserid = "1"\n[server]\nprot = 1\n'))
