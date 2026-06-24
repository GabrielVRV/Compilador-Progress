from pathlib import Path

import pytest
from rich.console import Console

from abl_deploy.config import EnvConfig
from abl_deploy.frontend import FrontendError, collect_files, send_frontend


def _make_web(tmp_path: Path) -> Path:
    web = tmp_path / "web"
    (web / "css").mkdir(parents=True)
    (web / "index.html").write_text("<html>")
    (web / "app.js").write_text("var x=1")
    (web / "css" / "style.css").write_text("body{}")
    (web / "notas.txt").write_text("ignorar")
    return web


def _cfg(tmp_path: Path, web: Path) -> EnvConfig:
    return EnvConfig(
        name="dev", host="h", username="u", password="p",
        build_dir=str(tmp_path / "build"),
        frontend={
            "local_dir": str(web),
            "remote_dir": "/u/app/dev/web",
            "include": ["*.html", "*.js", "*.css"],
        },
    )


def test_collect_files_filters_include(tmp_path: Path):
    web = _make_web(tmp_path)
    files = collect_files(web, ["*.html", "*.js", "*.css"])
    assert "index.html" in files and "app.js" in files
    assert str(Path("css/style.css")) in files
    assert "notas.txt" not in files


def test_collect_files_all_when_empty_include(tmp_path: Path):
    web = _make_web(tmp_path)
    assert len(collect_files(web, [])) == 4


def test_send_frontend_requires_config():
    cfg = EnvConfig(name="dev", host="h", username="u", password="p")
    with pytest.raises(FrontendError):
        send_frontend(cfg, console=Console())


def test_send_then_incremental(tmp_path: Path, mocker):
    web = _make_web(tmp_path)
    cfg = _cfg(tmp_path, web)
    calls = []
    mocker.patch(
        "abl_deploy.frontend.deploy_many",
        side_effect=lambda c, bl, br, files, on_file=None, sftp=None: (
            calls.append(list(files)) or [],
        )[0],
    )
    # 1a vez: envia os 3
    n1 = send_frontend(cfg, console=Console())
    assert n1 == 0 or calls[-1] == ["app.js", "index.html", str(Path("css/style.css"))] or len(calls[-1]) == 3
    assert len(calls[-1]) == 3
    # 2a vez sem mudancas: nao envia nada
    calls.clear()
    n2 = send_frontend(cfg, console=Console())
    assert n2 == 0
    assert calls == []
    # altera um arquivo: envia so ele
    (web / "app.js").write_text("var x=2")
    calls.clear()
    send_frontend(cfg, console=Console())
    assert calls[-1] == ["app.js"]


def test_send_all_forces_full(tmp_path: Path, mocker):
    web = _make_web(tmp_path)
    cfg = _cfg(tmp_path, web)
    calls = []
    mocker.patch(
        "abl_deploy.frontend.deploy_many",
        side_effect=lambda c, bl, br, files, on_file=None, sftp=None: (
            calls.append(list(files)) or [],
        )[0],
    )
    send_frontend(cfg, console=Console())          # popula manifest
    calls.clear()
    send_frontend(cfg, console=Console(), only_changed=False)  # --all
    assert len(calls[-1]) == 3
