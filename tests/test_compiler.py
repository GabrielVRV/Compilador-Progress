from pathlib import Path

import pytest

from abl_deploy.compiler import CompileError, _r_code_path, compile_source
from abl_deploy.config import EnvConfig


def test_r_code_path():
    out = _r_code_path(Path("/src/escq9986rp.p"), Path("/build"))
    assert out == Path("/build/escq9986rp.r")


def test_compile_missing_source(tmp_path: Path):
    cfg = EnvConfig(name="dev", source_dir=str(tmp_path), build_dir=str(tmp_path / "b"))
    with pytest.raises(CompileError) as exc:
        compile_source(cfg, "naoexiste.p")
    assert "não encontrado" in str(exc.value)


def test_compile_success(tmp_path: Path, mocker):
    # fonte fake
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "x.p").write_text("/* fake */")
    build = tmp_path / "build"
    cfg = EnvConfig(name="dev", source_dir=str(src_dir), build_dir=str(build))

    # _progres não existe no CI: simulamos a saída e criamos o .r
    def fake_run(cmd, **kwargs):
        build.mkdir(parents=True, exist_ok=True)
        (build / "x.r").write_bytes(b"\x00\x01")

        class P:
            stdout = "COMPILE-OK x.p\n"
            stderr = ""

        return P()

    mocker.patch("abl_deploy.compiler.subprocess.run", side_effect=fake_run)
    result = compile_source(cfg, "x.p")
    assert result.r_code.name == "x.r"
    assert result.r_code.is_file()


def test_compile_reports_error(tmp_path: Path, mocker):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "x.p").write_text("/* fake */")
    cfg = EnvConfig(name="dev", source_dir=str(src_dir), build_dir=str(tmp_path / "b"))

    class P:
        stdout = "COMPILE-ERROR\n  ** Unknown field foo. (201)\n"
        stderr = ""

    mocker.patch("abl_deploy.compiler.subprocess.run", return_value=P())
    with pytest.raises(CompileError) as exc:
        compile_source(cfg, "x.p")
    assert "COMPILE-ERROR" in str(exc.value)
