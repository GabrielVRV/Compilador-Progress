"""Envio de arquivos de frontend (estaticos) e modo watch (auto-upload).

Envio incremental: um manifest de hash (sha1) guarda o estado da ultima
sincronizacao; so os arquivos novos ou alterados sao enviados.
"""

from __future__ import annotations

import hashlib
import json
import time
from fnmatch import fnmatch
from pathlib import Path

from rich.console import Console

from .config import EnvConfig
from .deployer import DeployError, deploy_many, sftp_session


class FrontendError(Exception):
    """Erro de configuracao ou envio do frontend."""


def _matches(name: str, include: list[str]) -> bool:
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


def _hash_file(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _manifest_path(cfg: EnvConfig) -> Path:
    safe = f"{cfg.project}-{cfg.name}".replace("/", "_")
    return Path(cfg.build_dir).resolve() / f".frontend-manifest-{safe}.json"


def _load_manifest(cfg: EnvConfig) -> dict[str, str]:
    p = _manifest_path(cfg)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_manifest(cfg: EnvConfig, manifest: dict[str, str]) -> None:
    p = _manifest_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _target(cfg: EnvConfig) -> tuple[Path, str, list[str]]:
    target = cfg.frontend_target()
    if not target:
        raise FrontendError(
            f"Ambiente '{cfg.name}' nao tem [frontend] configurado "
            "(local_dir e remote_dir)."
        )
    local, remote, include = target
    return Path(local).expanduser(), remote, include


def _changed(local_dir: Path, files: list[str], manifest: dict[str, str]) -> tuple[list[str], dict[str, str]]:
    """Devolve (arquivos alterados/novos, hashes atuais de todos)."""
    changed: list[str] = []
    hashes: dict[str, str] = {}
    for rel in files:
        h = _hash_file(local_dir / rel)
        hashes[rel] = h
        if manifest.get(rel) != h:
            changed.append(rel)
    return changed, hashes


def send_frontend(cfg: EnvConfig, *, console: Console, only_changed: bool = True) -> int:
    """Envia o frontend. Por padrao, so o que mudou desde a ultima vez."""
    local_dir, remote_dir, include = _target(cfg)
    files = collect_files(local_dir, include)
    if not files:
        console.print("[yellow]Nenhum arquivo de frontend para enviar.[/]")
        return 0

    manifest = _load_manifest(cfg) if only_changed else {}
    to_send, hashes = _changed(local_dir, files, manifest)

    if not to_send:
        console.print(
            f"[green]Tudo em dia.[/] {len(files)} arquivo(s) ja sincronizado(s)."
        )
        return 0

    skipped = len(files) - len(to_send)
    console.print(
        f"Enviando [bold]{len(to_send)}[/] arquivo(s) alterado(s)"
        + (f" [dim](+{skipped} inalterado(s))[/]" if skipped else "")
        + f" -> [cyan]{cfg.host}:{remote_dir}[/]"
    )

    def _on(rel: str) -> None:
        console.print(f"  [green]+[/] {rel}")

    try:
        results = deploy_many(cfg, local_dir, remote_dir, to_send, on_file=_on)
    except DeployError as exc:
        raise FrontendError(str(exc)) from exc

    # atualiza manifest com os hashes dos enviados
    for rel in to_send:
        manifest[rel] = hashes[rel]
    _save_manifest(cfg, manifest)

    console.print(f"[green]OK[/] {len(results)} arquivo(s) enviado(s).")
    return len(results)


def watch_frontend(cfg: EnvConfig, *, console: Console) -> int:
    """Observa a pasta do frontend e envia cada arquivo alterado ao salvar."""
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

    # sincronizacao inicial (so o que mudou)
    try:
        send_frontend(cfg, console=console, only_changed=True)
    except FrontendError as exc:
        console.print(f"[yellow]Aviso no envio inicial:[/] {exc}")

    manifest = _load_manifest(cfg)
    sent_count = 0
    last: dict[str, float] = {}

    class Handler(FileSystemEventHandler):  # type: ignore[misc]
        def __init__(self, sftp) -> None:
            self.sftp = sftp

        def _push(self, path_str: str) -> None:
            nonlocal sent_count
            p = Path(path_str)
            if p.is_dir() or not p.is_file() or not _matches(p.name, include):
                return
            try:
                rel = str(p.resolve().relative_to(local_dir.resolve()))
            except ValueError:
                return
            now = time.time()
            if now - last.get(rel, 0) < 0.4:
                return
            last[rel] = now
            try:
                h = _hash_file(p)
            except OSError:
                return
            if manifest.get(rel) == h:
                return  # nada mudou de fato
            try:
                deploy_many(
                    cfg, local_dir, remote_dir, [rel], sftp=self.sftp,
                    on_file=lambda r: console.print(
                        f"  [green]+[/] {r}  [dim]({time.strftime('%H:%M:%S')})[/]"
                    ),
                )
                manifest[rel] = h
                _save_manifest(cfg, manifest)
                sent_count += 1
            except DeployError as exc:
                console.print(f"  [red]falha:[/] {rel}: {exc}")

        def on_modified(self, event) -> None:
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
