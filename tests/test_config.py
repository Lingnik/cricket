from pathlib import Path

from cricket.config import load_config, parse_env_file, parse_rate_limit

CONFIG = Path(__file__).parents[1] / "config.example.toml"

ENV_TEXT = """
# secrets
CRICKET_MUSH_HOST=mush.test.org
CRICKET_MUSH_PORT=7777
CRICKET_MUSH_USE_TLS=true
CRICKET_MUSH_NAME=CricketBOT
CRICKET_MUSH_PASSWORD="s3cret with spaces"
CRICKET_MUSH_CONTROL_PORT=4260
CRICKET_HTTP_PORT=4290
"""


def test_parse_env_file(tmp_path):
    envfile = tmp_path / ".env"
    envfile.write_text(ENV_TEXT, encoding="utf-8")
    env = parse_env_file(envfile)
    assert env["CRICKET_MUSH_HOST"] == "mush.test.org"
    assert env["CRICKET_MUSH_PASSWORD"] == "s3cret with spaces"  # quotes stripped


def test_load_config_merges_env_and_toml(tmp_path):
    envfile = tmp_path / ".env"
    envfile.write_text(ENV_TEXT, encoding="utf-8")
    env = parse_env_file(envfile)
    cfg = load_config(CONFIG, env=env)

    # Secrets come from env.
    assert cfg.mush.host == "mush.test.org"
    assert cfg.mush.port == 7777
    assert cfg.mush.use_tls is True
    assert cfg.mush.name == "CricketBOT"

    # Ports: env overrides the toml defaults.
    assert cfg.control.port == 4260
    assert cfg.http.port == 4290
    assert cfg.http.host == "127.0.0.1"


def test_ports_default_to_toml_when_env_absent():
    cfg = load_config(CONFIG, env={})
    assert cfg.control.port == 4250  # from [control] in the example toml
    assert cfg.http.port == 4280  # from [http] in the example toml


def test_paths_come_from_toml():
    cfg = load_config(CONFIG, env={})
    assert cfg.paths.config_db.endswith("cricket-config.sqlite3")
    assert cfg.paths.memory_db.endswith("cricket-memory.sqlite3")


def test_parse_rate_limit():
    assert parse_rate_limit("1 / 20s") == (1, 20.0)
    assert parse_rate_limit("3/5s") == (3, 5.0)
    assert parse_rate_limit(None) is None
    assert parse_rate_limit("garbage") is None
