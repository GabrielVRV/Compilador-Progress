from pathlib import Path

import pytest

from abl_deploy.config import EnvConfig
from abl_deploy.frontend import FrontendError, collect_files, send_frontend
from rich.console import Console


def _make_web(tmp_path: Path) -> Path:
    web = tmp_path / "web"
    (web / "css").mkdir(parents=True)
    (web / "index.html").write_text("<html>")
    (web / "app.js").write_text("var x=1")
    (web / "css" / "style.css").write_text("body{}")
    (web / "notas.txt").write_text("ignorar")
    return web


def test_collect_files_filters_include(tmp_path: Path):
    web = _make_web(tmp_path)
    files = collect_files(web, ["*.html", "*.js", "*.css"])
    assert "index.html" in files
    assert "app.js" in files
    assert str(Path("css/style.css")) in files
    assert "notas.txt" not in files


def test_collect_files_all_when_empty_include(tmp_path: Path):
    web = _make_web(tmp_path)
    files = collect_files(web, [])
    assert "notas.txt" in files
    assert len(files) == 4


def test_send_frontend_requires_config(tmp_path: Path):
    cfg = EnvConfig(name="dev", host="h", username="u", password="p")
    with pytest.raises(FrontendError):
        send_frontend(cfg, console=Console())


def test_send_frontend_uploads(tmp_path: Path, mocker):
    web = _make_web(tmp_path)
    cfg = EnvConfig(
        name="dev",
        host="h",
        username="u",
        password="p",
        frontend={
            "local_dir": str(web),
            "remote_dir": "/u/app/dev/web",
            "include": ["*.html", "*.js", "*.css"],
        },
    )
    sent = []
    mocker.patch(
        "abl_deploy.frontend.deploy_many",
        side_effect=lambda c, bl, br, files, on_file=None, sftp=None: (
            [sent.append(f) for f in files], sent
        )[1],
    )
    n = send_frontend(cfg, console=Console())
    assert n == 3
    assert "index.html" in sent
