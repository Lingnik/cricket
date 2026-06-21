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
    # Control port: env overrides the toml default.
    assert cfg.control.port == 4260

    # Locations come from the toml.
    assert set(cfg.locations) == {"Public", "Cricket-Lounge", "admin"}
    public = cfg.locations["Public"]
    assert public.mode == "chat"
    assert public.engagement == "addressed"
    assert "cricket," in public.prefixes
    assert cfg.locations["Cricket-Lounge"].engagement == "always"
    assert cfg.locations["admin"].mode == "control"
    assert "#1234" in cfg.locations["admin"].admins


def test_control_port_defaults_to_toml_when_env_absent():
    cfg = load_config(CONFIG, env={})
    assert cfg.control.port == 4250  # from [control] in the example toml


def test_parse_rate_limit():
    assert parse_rate_limit("1 / 20s") == (1, 20.0)
    assert parse_rate_limit("3/5s") == (3, 5.0)
    assert parse_rate_limit(None) is None
    assert parse_rate_limit("garbage") is None
