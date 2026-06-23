import os
from pathlib import Path

import pytest

from abl_deploy.config import (
    ConfigError,
    EnvConfig,
    list_environments,
    load_config,
)


def test_load_env_merges_defaults(config_file: Path):
    cfg = load_config("dev", config_file)
    assert cfg.name == "dev"
    assert cfg.host == "dev.example.com"
    assert cfg.source_dir == "src"      # vindo de [default]
    assert cfg.build_dir == "build"
    assert cfg.propath == ["src"]


def test_unknown_env_raises(config_file: Path):
    with pytest.raises(ConfigError) as exc:
        load_config("homolog", config_file)
    assert "homolog" in str(exc.value)


def test_list_environments(config_file: Path):
    assert list_environments(config_file) == ["dev", "prod"]


def test_require_deploy_ok(config_file: Path):
    cfg = load_config("prod", config_file)
    cfg.require_deploy()  # não levanta


def test_require_deploy_missing_auth():
    cfg = EnvConfig(name="x", host="h", username="u", remote_dir="/r")
    with pytest.raises(ConfigError):
        cfg.require_deploy()


def test_resolve_password_from_env(config_file: Path, monkeypatch):
    monkeypatch.setenv("ABL_DEV_PASS", "segredo123")
    cfg = load_config("dev", config_file)
    assert cfg.resolve_password() == "segredo123"


def test_resolve_password_missing_env(config_file: Path, monkeypatch):
    monkeypatch.delenv("ABL_DEV_PASS", raising=False)
    cfg = load_config("dev", config_file)
    with pytest.raises(ConfigError):
        cfg.resolve_password()
