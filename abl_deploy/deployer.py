"""Deploy via SFTP (paramiko). Substitui o passo manual de WinSCP."""

from __future__ import annotations

import posixpath
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator

import paramiko

from .config import EnvConfig


class DeployError(Exception):
    """Falha durante a conexao ou o envio SFTP."""


@dataclass
class DeployResult:
    local: Path
    remote: str
    size: int
    backup: Path | None = None


def _connect_kwargs(cfg: EnvConfig) -> dict:
    kwargs: dict = {
        "hostname": cfg.host,
        "port": cfg.port,
        "username": cfg.username,
        "timeout": 30,
    }
    if cfg.key_file:
        kwargs["key_filename"] = str(Path(cfg.key_file).expanduser())
    else:
        kwargs["password"] = cfg.resolve_password()
        kwargs["look_for_keys"] = False
        kwargs["allow_agent"] = False
    return kwargs


@contextmanager
def sftp_session(cfg: EnvConfig) -> Iterator[paramiko.SFTPClient]:
    """Abre uma conexao SSH/SFTP e garante o fechamento."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(**_connect_kwargs(cfg))
    except paramiko.AuthenticationException as exc:
        raise DeployError(
            f"Falha de autenticacao em {cfg.username}@{cfg.host}."
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise DeployError(f"Nao foi possivel conectar em {cfg.host}: {exc}") from exc

    try:
        sftp = client.open_sftp()
        yield sftp
        sftp.close()
    finally:
        client.close()


def ensure_remote_dir(
    sftp: paramiko.SFTPClient, remote_dir: str, _cache: set[str] | None = None
) -> None:
    """Cria o diretorio remoto recursivamente, se nao existir."""
    if not remote_dir:
        return
    if _cache is not None and remote_dir in _cache:
        return
    parts = remote_dir.strip("/").split("/")
    path = "/" if remote_dir.startswith("/") else ""
    for part in parts:
        if not part:
            continue
        path = posixpath.join(path, part) if path else part
        try:
            sftp.stat(path)
        except IOError:
            try:
                sftp.mkdir(path)
            except IOError as exc:
                raise DeployError(
                    f"Nao foi possivel criar o diretorio remoto '{path}': {exc}"
                ) from exc
    if _cache is not None:
        _cache.add(remote_dir)


def _remote_exists(sftp: paramiko.SFTPClient, remote_path: str) -> bool:
    try:
        sftp.stat(remote_path)
        return True
    except IOError:
        return False


def deploy_file(
    cfg: EnvConfig,
    local_file: Path,
    *,
    remote_dir: str | None = None,
    progress: Callable[[int, int], None] | None = None,
    backup_dir: Path | None = None,
) -> DeployResult:
    """Envia um unico arquivo para o servidor.

    Se ``backup_dir`` for informado e ja existir um arquivo de mesmo nome no
    destino, baixa a versao atual para ``backup_dir`` (com timestamp) antes de
    sobrescrever, permitindo rollback depois.
    """
    cfg.require_deploy()
    local_file = Path(local_file).resolve()
    if not local_file.is_file():
        raise DeployError(f"Arquivo local nao encontrado: {local_file}")
    target_dir = remote_dir or cfg.remote_dir
    if not target_dir:
        raise DeployError("remote_dir nao definido para o envio.")

    backup_path: Path | None = None
    with sftp_session(cfg) as sftp:
        ensure_remote_dir(sftp, target_dir)
        remote_path = posixpath.join(target_dir, local_file.name)

        if backup_dir is not None and _remote_exists(sftp, remote_path):
            backup_dir = Path(backup_dir)
            backup_dir.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d-%H%M%S")
            backup_path = backup_dir / f"{local_file.stem}.{ts}{local_file.suffix}"
            try:
                sftp.get(remote_path, str(backup_path))
            except Exception as exc:  # noqa: BLE001
                raise DeployError(
                    f"Falha ao fazer backup de {remote_path}: {exc}"
                ) from exc

        try:
            sftp.put(str(local_file), remote_path, callback=progress)
        except DeployError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DeployError(f"Falha no envio SFTP: {exc}") from exc

    return DeployResult(
        local=local_file, remote=remote_path,
        size=local_file.stat().st_size, backup=backup_path,
    )


def restore_file(cfg: EnvConfig, local_file: Path, remote_path: str) -> DeployResult:
    """Reenvia um arquivo (de backup) para um caminho remoto exato (rollback)."""
    local_file = Path(local_file)
    if not local_file.is_file():
        raise DeployError(f"Backup nao encontrado: {local_file}")
    with sftp_session(cfg) as sftp:
        ensure_remote_dir(sftp, posixpath.dirname(remote_path))
        try:
            sftp.put(str(local_file), remote_path)
        except Exception as exc:  # noqa: BLE001
            raise DeployError(f"Falha ao restaurar {remote_path}: {exc}") from exc
    return DeployResult(
        local=local_file, remote=remote_path, size=local_file.stat().st_size
    )


def deploy_many(
    cfg: EnvConfig,
    base_local: Path,
    base_remote: str,
    rel_files: Iterable[str],
    *,
    on_file: Callable[[str], None] | None = None,
    sftp: paramiko.SFTPClient | None = None,
) -> list[DeployResult]:
    """Envia varios arquivos preservando a estrutura de pastas.

    ``rel_files`` sao caminhos relativos a ``base_local``; cada um vai para
    ``base_remote/<rel>``. Se ``sftp`` for informado, reutiliza a conexao
    (usado pelo modo watch para nao reconectar a cada arquivo).
    """
    base_local = Path(base_local)
    results: list[DeployResult] = []
    cache: set[str] = set()

    def _send(s: paramiko.SFTPClient) -> None:
        for rel in rel_files:
            rel_posix = Path(rel).as_posix()
            local = (base_local / rel).resolve()
            if not local.is_file():
                continue
            remote_path = posixpath.join(base_remote, rel_posix)
            ensure_remote_dir(s, posixpath.dirname(remote_path), cache)
            try:
                s.put(str(local), remote_path)
            except Exception as exc:  # noqa: BLE001
                raise DeployError(f"Falha ao enviar {rel_posix}: {exc}") from exc
            if on_file:
                on_file(rel_posix)
            results.append(
                DeployResult(local=local, remote=remote_path, size=local.stat().st_size)
            )

    if sftp is not None:
        _send(sftp)
    else:
        with sftp_session(cfg) as s:
            _send(s)
    return results
