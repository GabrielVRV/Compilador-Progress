from pathlib import Path

from abl_deploy.config import EnvConfig
from abl_deploy.deployer import deploy_many, ensure_remote_dir


def test_ensure_remote_dir_creates(mocker):
    sftp = mocker.MagicMock()
    sftp.stat.side_effect = IOError()  # nada existe
    ensure_remote_dir(sftp, "/u/app/dev/web")
    # criou cada nivel
    created = [c.args[0] for c in sftp.mkdir.call_args_list]
    assert created == ["/u", "/u/app", "/u/app/dev", "/u/app/dev/web"]


def test_deploy_many_preserves_structure(tmp_path: Path, mocker):
    base = tmp_path / "web"
    (base / "css").mkdir(parents=True)
    (base / "index.html").write_text("x")
    (base / "css" / "s.css").write_text("y")
    cfg = EnvConfig(name="dev", host="h", username="u", password="p")

    sftp = mocker.MagicMock()
    sftp.stat.return_value = mocker.MagicMock(st_size=1)
    client = mocker.MagicMock()
    client.open_sftp.return_value = sftp
    mocker.patch("abl_deploy.deployer.paramiko.SSHClient", return_value=client)

    res = deploy_many(
        cfg, base, "/u/app/dev/web",
        ["index.html", str(Path("css/s.css"))],
    )
    remotes = sorted(r.remote for r in res)
    assert remotes == ["/u/app/dev/web/css/s.css", "/u/app/dev/web/index.html"]
