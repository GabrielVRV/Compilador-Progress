from pathlib import Path

import pytest

from abl_deploy.config import EnvConfig
from abl_deploy.deployer import DeployError, deploy_file


def test_deploy_missing_file(tmp_path: Path):
    cfg = EnvConfig(
        name="dev", host="h", username="u", password="p", remote_dir="/r"
    )
    with pytest.raises(DeployError):
        deploy_file(cfg, tmp_path / "naoexiste.r")


def test_deploy_success(tmp_path: Path, mocker):
    rfile = tmp_path / "x.r"
    rfile.write_bytes(b"\x00\x01\x02")
    cfg = EnvConfig(
        name="dev", host="h", username="u", password="p", remote_dir="/u/app/rcode"
    )

    sftp = mocker.MagicMock()
    sftp.stat.return_value = mocker.MagicMock(st_size=3)
    client = mocker.MagicMock()
    client.open_sftp.return_value = sftp
    mocker.patch("abl_deploy.deployer.paramiko.SSHClient", return_value=client)

    res = deploy_file(cfg, rfile)
    assert res.remote == "/u/app/rcode/x.r"
    assert res.size == 3
    sftp.put.assert_called_once()
    client.connect.assert_called_once()
