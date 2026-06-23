import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    """Config de projeto unico (formato legado)."""
    content = textwrap.dedent(
        """
        [default]
        source_dir = "src"
        source_dirs = ["src/rp"]
        build_dir = "build"
        propath = ["src"]

        [env.dev]
        host = "dev.example.com"
        username = "deploy"
        password = "env:ABL_DEV_PASS"
        remote_dir = "/u/app/dev/rcode"

        [[env.dev.routes]]
        match = "*rp.p"
        remote_dir = "/u/app/dev/rp"

        [[env.dev.routes]]
        match = "*.p"
        remote_dir = "/u/app/dev/telas"

        [env.prod]
        host = "prod.example.com"
        username = "deploy"
        key_file = "~/.ssh/id_rsa"
        remote_dir = "/u/app/prod/rcode"
        """
    )
    path = tmp_path / "abl-deploy.toml"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def multi_config_file(tmp_path: Path) -> Path:
    """Config global multi-projeto."""
    content = textwrap.dedent(
        """
        [project.financeiro]
        source_dir = "fin/src"
        build_dir = "fin/build"

        [project.financeiro.env.prod]
        host = "fin.example.com"
        username = "deploy"
        key_file = "~/.ssh/id_rsa"
        remote_dir = "/u/app/fin/rcode"

        [project.estoque]
        source_dir = "est/src"

        [project.estoque.env.dev]
        host = "est.example.com"
        username = "deploy"
        password = "env:EST_PASS"
        remote_dir = "/u/app/est/rcode"
        """
    )
    path = tmp_path / "global.toml"
    path.write_text(content, encoding="utf-8")
    return path
