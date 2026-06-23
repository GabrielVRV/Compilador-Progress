"""Envio de arquivos de frontend (estaticos) e modo watch (auto-upload)."""

from __future__ import annotations

import time
from fnmatch import fnmatch
from pathlib import Path

from rich.console import Console

from .config import EnvConfig
from .deployer import DeployError, deploy_many, sftp_session


class FrontendError(Exception):
    """Erro de configuracao ou envio do frontend."""


def _matches(name: str, include: list[str]) -> bool:
    """True se o arquivo casa com algum glob de include (ou se include vazio)."""
    if not include:
        return True
    return any(fnmatch(name, pat) for pat in include)


def collect_files(local_dir: Path, include: list[str]) -> list[str]:
    """Lista (recursivo) os arquivos do frontend, como caminhos relativos."""
    base = Path(local_dir)
    if not base.is_dir():
        raise FrontendError(f"Pasta do frontend nao encontrada: {base}")
    rels: list[str] = []
    for f in base.rglob("*"):
        if f.is_file() and _matches(f.name, include):
            rels.append(str(f.relative_to(base)))
    return sorted(rels)


def _target(cfg: EnvConfig) -> tuple[Path, str, list[str]]:
    target = cfg.frontend_target()
    if not target:
        raise FrontendError(
            f"Ambiente '{cfg.name}' nao tem [frontend] configurado "
            "(local_dir e remote_dir)."
        )
    local, remote, include = target
    return Path(local).expanduser(), remote, include


def send_frontend(cfg: EnvConfig, *, console: Console) -> int:
    """Envia todos os arquivos do frontend. Retorna a quantidade enviada."""
    local_dir, remote_dir, include = _target(cfg)
    files = collect_files(local_dir, include)
    if not files:
        console.print("[yellow]Nenhum arquivo de frontend para enviar.[/]")
        return 0

    console.print(
        f"Enviando [bold]{len(files)}[/] arquivo(s) de "
        f"[bold]{local_dir}[/] -> [cyan]{cfg.host}:{remote_dir}[/]"
    )

    def _on(rel: str) -> None:
        console.print(f"  [green]+[/] {rel}")

    try:
        results = deploy_many(cfg, local_dir, remote_dir, files, on_file=_on)
    except DeployError as exc:
        raise FrontendError(str(exc)) from exc

    console.print(f"[green]OK[/] {len(results)} arquivo(s) enviado(s).")
    return len(results)


def watch_frontend(cfg: EnvConfig, *, console: Console) -> int:
    """Observa a pasta do frontend e envia cada arquivo ao ser salvo.

    Mantem uma conexao SFTP aberta. Ctrl+C encerra.
    """
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError as exc:  # pragma: no cover
        raise FrontendError(
            "Modo watch requer 'watchdog'. Instale com: pip install watchdog"
        ) from exc

    local_dir, remote_dir, include = _target(cfg)
    if not local_dir.is_dir():
        raise FrontendError(f"Pasta do frontend nao encontrada: {local_dir}")

    console.print(
        f"[bold cyan]Watch[/] em [bold]{local_dir}[/] -> "
        f"[cyan]{cfg.host}:{remote_dir}[/]\n"
        "[dim]Salve um arquivo para enviar automaticamente. Ctrl+C para parar.[/]"
    )

    # Envio inicial completo, para garantir que o servidor esteja em dia.
    try:
        send_frontend(cfg, console=console)
    except FrontendError as exc:
        console.print(f"[yellow]Aviso no envio inicial:[/] {exc}")

    sent_count = 0
    last: dict[str, float] = {}

    class Handler(FileSystemEventHandler):  # type: ignore[misc]
        def __init__(self, sftp) -> None:
            self.sftp = sftp

        def _push(self, path_str: str) -> None:
            nonlocal sent_count
            p = Path(path_str)
            if p.is_dir() or not _matches(p.name, include):
                return
            try:
                rel = str(p.resolve().relative_to(local_dir.resolve()))
            except ValueError:
                return
            # debounce: evita duplo evento do editor
            now = time.time()
            if now - last.get(rel, 0) < 0.4:
                return
            last[rel] = now
            try:
                deploy_many(
                    cfg, local_dir, remote_dir, [rel], sftp=self.sftp,
                    on_file=lambda r: console.print(
                        f"  [green]+[/] {r}  [dim]({time.strftime('%H:%M:%S')})[/]"
                    ),
                )
                sent_count += 1
            except DeployError as exc:
                console.print(f"  [red]falha:[/] {rel}: {exc}")

        def on_modified(self, event) -> None:  # noqa: D401
            self._push(event.src_path)

        def on_created(self, event) -> None:
            self._push(event.src_path)

        def on_moved(self, event) -> None:
            self._push(getattr(event, "dest_path", event.src_path))

    try:
        with sftp_session(cfg) as sftp:
            handler = Handler(sftp)
            observer = Observer()
            observer.schedule(handler, str(local_dir), recursive=True)
            observer.start()
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                console.print("\n[dim]Watch encerrado.[/]")
            finally:
                observer.stop()
                observer.join()
    except DeployError as exc:
        raise FrontendError(str(exc)) from exc

    return sent_count
