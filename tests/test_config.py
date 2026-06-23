from pathlib import Path

import pytest

from abl_deploy.config import (
    ConfigError,
    EnvConfig,
    list_environments,
    load_config,
    load_projects,
)


# --- Projeto único (legado) ---

def test_load_env_merges_defaults(config_file: Path):
    cfg = load_config("dev", config_path=config_file)
    assert cfg.name == "dev"
    assert cfg.project == "default"
    assert cfg.host == "dev.example.com"
    assert cfg.source_dir == "src"
    assert cfg.source_dirs == ["src/rp"]


def test_unknown_env_raises(config_file: Path):
    with pytest.raises(ConfigError) as exc:
        load_config("homolog", config_path=config_file)
    assert "homolog" in str(exc.value)


def test_list_environments(config_file: Path):
    assert list_environments(config_path=config_file) == ["dev", "prod"]


def test_require_deploy_ok(config_file: Path):
    load_config("prod", config_path=config_file).require_deploy()


def test_require_deploy_missing_auth():
    cfg = EnvConfig(name="x", host="h", username="u", remote_dir="/r")
    with pytest.raises(ConfigError):
        cfg.require_deploy()


def test_resolve_password_from_env(config_file: Path, monkeypatch):
    monkeypatch.setenv("ABL_DEV_PASS", "segredo123")
    cfg = load_config("dev", config_path=config_file)
    assert cfg.resolve_password() == "segredo123"


# --- Roteamento por nome ---

def test_routes_route_rp(config_file: Path):
    cfg = load_config("dev", config_path=config_file)
    assert cfg.resolve_remote_dir("escq9986rp.p") 