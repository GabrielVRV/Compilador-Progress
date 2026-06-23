import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    content = textwrap.dedent(
        """
        [default]
        source_dir = "src"
        build_dir = "build"
        propath = ["src"]

        [env.dev]
        host = "dev.example.com"
        username = "deploy"
        password = "env:ABL_DEV_PASS"
        remote_dir = "/u/app/dev/rcode"

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
