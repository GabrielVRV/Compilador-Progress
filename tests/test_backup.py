from pathlib import Path

import pytest
from rich.console import Console

from abl_deploy.config import EnvConfig
from abl_deploy.deployer import deploy_file, restore_file
from abl_deploy.history import (
    backup_dir_for,
    last_restorable,
    load_history,
    record_deploy,
    recent,
)
from abl_deploy.pipeline import run_rollback


def _cfg(tmp_path: Path) -> EnvConfig:
    return EnvConfig(
        name="prod", project="fin", host="h", username="u", password="p",
        remote_dir="/u/app/prod/rcode", build_dir=str(tmp_path / "build"),
    )


def _mock_sftp(mocker, remote_exists: bool):
    sftp = mocker.MagicMock()
    if remote_exists:
        sftp.stat.return_value = mocker.MagicMock(st_size=5)
    else:
        # primeira chamada (existe?) falha; demais (mkdir checks) tambem -> cria dirs
        sftp.stat.side_effect = IOError()
    client = mocker.MagicMock()
    client.open_sftp.return_value = sftp
    mocker.patch("abl_deploy.deployer.paramiko.SSHClient", return_value=client)
    return sftp


def test_backup_downloads_when_remote_exists(tmp_path: Path, mocker):
    cfg = _cfg(tmp_path)
    rfile = tmp_path / "x.r"
    rfile.write_bytes(b"\x00")
    sftp = _mock_sftp(mocker, remote_exists=True)
    bdir = backup_dir_for(cfg)

    res = deploy_file(cfg, rfile, backup_dir=bdir)
    assert res.backup is not None
    sftp.get.assert_called_once()          # baixou a versao anterior
    sftp.put.assert_called_once()          # enviou a nova


def test_no_backup_when_remote_absent(tmp_path: Path, mocker):
    cfg = _cfg(tmp_path)
    rfile = tmp_path / "x.r"
    rfile.write_bytes(b"\x00")
    sftp = _mock_sftp(mocker, remote_exists=False)
    res = deploy_file(cfg, rfile, backup_dir=backup_dir_for(cfg))
    assert res.backup is None
    sftp.get.assert_not_called()


def test_history_record_and_recent(tmp_path: Path):
    cfg = _cfg(tmp_path)
    record_deploy(cfg, source="x.p", r_name="x.r", remote_path="/r/x.r", backup=None)
    record_deploy(cfg, source="y.p", r_name="y.r", remote_path="/r/y.r", backup=None)
    recs = recent(cfg)
    assert [r.r_name for r in recs] == ["y.r", "x.r"]  # mais recente primeiro


def test_last_restorable_skips_without_backup(tmp_path: Path):
    cfg = _cfg(tmp_path)
    bkp = tmp_path / "x.20240101.r"
    bkp.write_bytes(b"old")
    record_deploy(cfg, source="x.p", r_name="x.r", remote_path="/r/x.r", backup=bkp)
    record_deploy(cfg, source="y.p", r_name="y.r", remote_path="/r/y.r", backup=None)
    rec = last_restorable(cfg)
    assert rec is not None and rec.r_name == "x.r"  # pula o y sem backup


def test_run_rollback_restores(tmp_path: Path, mocker):
    cfg = _cfg(tmp_path)
    bkp = tmp_path / "x.20240101.r"
    bkp.write_bytes(b"old")
    record_deploy(cfg, source="x.p", r_name="x.r", remote_path="/r/x.r", backup=bkp)
    restore = mocker.patch("abl_deploy.pipeline.restore_file")
    code = run_rollback(cfg, console=Console())
    assert code == 0
    restore.assert_called_once()
    args = restore.call_args.args
    assert args[2] == "/r/x.r"  # remote_path


def test_run_rollback_nothing(tmp_path: Path):
    cfg = _cfg(tmp_path)
    assert run_rollback(cfg, console=Console()) == 1
