"""Deploy do .r para o servidor via SFTP (paramiko).

Substitui o passo manual de WinSCP: conecta no host configurado,
garante o diretório remoto e envia o arquivo.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import paramiko

from .config import EnvConfig


class DeployError(Exception):
    """Falha durante a conexão ou o envio SFTP."""


@dataclass
class DeployResult:
    local: Path
    remote: str
    size: int


def _ensure_remote_dir(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    """Cria o diretório remoto recursivamente, se não existir."""
    parts = remote_dir.strip("/").split("/")
    path = "/" if remote_dir.startswith("/") else ""
    for part in parts:
        path = posixpath.join(path, part) if path else part
        try:
            sftp.stat(path)
        except IOError:
            try:
                sftp.mkdir(path)
            except IOError as exc:  # corrida ou permissão
                raise DeployError(
                    f"Não foi possível criar o diretório remoto '{path}': {exc}"
                ) from exc


def deploy_file(
    cfg: EnvConfig,
    local_file: Path,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> DeployResult:
    """Envia ``local_file`` para o ``remote_dir`` do ambiente via SFTP."""
    cfg.require_deploy()
    local_file = Path(local_file).resolve()
    if not local_file.is_file():
        raise DeployError(f"Arquivo local não encontrado: {local_file}")

    assert cfg.host and cfg.username and cfg.remote_dir  # validado em require_deploy

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_kwargs: dict = {
        "hostname": cfg.host,
        "port": cfg.port,
        "username": cfg.username,
        "timeout": 30,
    }
    if cfg.key_file:
        connect_kwargs["key_filename"] = str(Path(cfg.key_file).expanduser())
    else:
        connect_kwargs["password"] = cfg.resolve_password()
        connect_kwargs["look_for_keys"] = False
        connect_kwargs["allow_agent"] = False

    try:
        client.connect(**connect_kwargs)
    except paramiko.AuthenticationException as exc:
        raise DeployError(
            f"Falha de autenticação em {cfg.username}@{cfg.host}."
        ) from exc
    except Exception as exc:  # noqa: BLE001 - rede/host
        raise DeployError(f"Não foi possível conectar em {cfg.host}: {exc}") from exc

    try:
        sftp = client.open_sftp()
        _ensure_remote_dir(sftp, cfg.remote_dir)
        remote_path = posixpath.join(cfg.remote_dir, local_file.name)
        sftp.put(str(local_file), remote_path, callback=progress)
        size = sftp.stat(remote_path).st_size or local_file.stat().st_size
        sftp.close()
    except DeployError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise DeployError(f"Falha no envio SFTP: {exc}") from exc
    finally:
        client.close()

    return DeployResult(local=local_file, remote=remote_path, size=int(size))
