from pathlib import Path

import pytest
from rich.console import Console

from abl_deploy.config import EnvConfig
from abl_deploy.pipeline import PipelineError, run_pipeline


def _make_source(tmp_path: Path) -> EnvConfig:
    src = tmp_path / "src"
    src.mkdir()
    (src / "escq9986rp.p").write_text("/* fake */")
    return EnvConfig(
        name="prod",
        project="financeiro",
        source_dir=str(src),
        build_dir=str(tmp_path / "build"),
        host="h",
        username="u",
        password="p",
        remote_dir="/u/app/prod/rcode",
        routes=[{"match": "*rp.p", "remote_dir": "/u/app/prod/rp"}],
    )


def test_pipeline_routes_to_rp_dir(tmp_path: Path, mocker):
    cfg = _make_source(tmp_path)
    build = Path(cfg.build_dir)

    def fake_run(cmd, **kwargs):
        build.mkdir(parents=True, exist_ok=True)
        (build / "escq9986rp.r").write_bytes(b"\x00")

        class P:
            stdout = "COMPILE-OK escq9986rp.p\n"
            stderr = ""

        return P()

    mocker.patch("abl_deploy.compiler.subprocess.run", side_effect=fake_run)

    captured = {}

    def fake_deploy(target, r_code, progress=None):
        captured["remote_dir"] = target.remote_dir

        class R:
            local = r_code
            remote = target.remote_dir + "/" + r_code.name
            size = 1

        return R()

    mocker.patch("abl_deploy.pipeline.deploy_file", side_effect=fake_deploy)

    res = run_pipeline(cfg, "escq9986rp.p", console=Console())
    # roteado para a pasta rp, não para o remote_dir padrão
    assert captured["remote_dir"] == "/u/app/prod/rp"
    assert res.remote.endswith("escq9986rp.r")


def test_pipeline_compile_only(tmp_path: Path, mocker):
    cfg = _make_source(tmp_path)
    build = Path(cfg.build_dir)

    def fake_run(cmd, **kwargs):
        build.mkdir(parents=True, exist_ok=True)
        (build / "escq9986rp.r").write_bytes(b"\x00")

        class P:
            stdout = "COMPILE-OK\n"
            stderr = ""

        return P()

    mocker.patch("abl_deploy.compiler.subprocess.run", side_effect=fake_run)
    deploy = mocker.patch("abl_deploy.pipeline.deploy_file")

    res = run_pipeline(cfg, "escq9986rp.p", console=Console(), compile_only=True)
    assert res.remote is None
    deploy.assert_not_called()
