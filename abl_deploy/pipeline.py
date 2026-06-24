"""Orquestra o fluxo compila -> envia, reutilizado pela CLI e pelo menu."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from .compiler import CompileError, _r_code_path, compile_source, find_source
from .config import ConfigError, EnvConfig
from .history import backup_dir_for, last_restorable, recent, record_deploy
from .deployer import DeployError, deploy_file, restore_file


class PipelineError(Exception):
    """Falha em qualquer etapa do pipeline (mensagem amigavel)."""


@dataclass
class PipelineResult:
    r_code: Path
    remote: str | None


def run_pipeline(
    cfg: EnvConfig,
    source: str,
    *,
    console: Console,
    compile_only: bool = False,
    skip_compile: bool = False,
) -> PipelineResult:
    """Compila o fonte e envia o .r, com feedback visual via rich."""
    console.print(
        Panel.fit(
            f"[bold]{source}[/]  ->  projeto [bold magenta]{cfg.project}[/]  "
            f"ambiente [bold cyan]{cfg.name}[/]",
            title="ABL Deploy",
            border_style="cyan",
        )
    )

    # --- Passo 1: compilar ---
    if skip_compile:
        r_code = _r_code_path(find_source(cfg, source), Path(cfg.build_dir).resolve())
        if not r_code.is_file():
            raise PipelineError(f".r nao encontrado em {r_code}")
        console.print(f"[dim]Usando .r existente:[/] {r_code}")
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("Compilando ABL...", total=None)
            try:
                result = compile_source(cfg, source)
            except CompileError as exc:
                console.print("[red]X Falha na compilacao:[/]")
                console.print(Panel(str(exc), border_style="red"))
                raise PipelineError("compilacao falhou") from exc
        r_code = result.r_code
        console.print(f"[green]OK[/] Compilado: [bold]{r_code.name}[/]")

    if compile_only:
        console.print("[dim]--compile-only: deploy ignorado.[/]")
        return PipelineResult(r_code=r_code, remote=None)

    # --- Passo 2: resolver destino e enviar ---
    try:
        cfg.require_deploy()
    except ConfigError as exc:
        raise PipelineError(str(exc)) from exc

    # Roteia pelo nome do FONTE (ex.: "*rp.p"), nao pelo .r gerado.
    remote_dir = cfg.resolve_remote_dir(Path(source).name)
    if not remote_dir:
        raise PipelineError(
            f"Nenhum remote_dir resolvido para '{Path(source).name}'. "
            "Verifique remote_dir/routes."
        )

    bdir = backup_dir_for(cfg) if cfg.backup else None

    size = r_code.stat().st_size
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total} bytes"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(f"Enviando para {cfg.host}", total=size)

        def _cb(done: int, total: int) -> None:
            progress.update(task, completed=done, total=total)

        try:
            res = deploy_file(
                cfg, r_code, remote_dir=remote_dir, progress=_cb, backup_dir=bdir
            )
        except DeployError as exc:
            raise PipelineError(str(exc)) from exc

    record_deploy(
        cfg,
        source=Path(source).name,
        r_name=r_code.name,
        remote_path=res.remote,
        backup=res.backup,
    )

    backup_line = (
        f"\nbackup: {res.backup}" if res.backup else "\n[dim](sem versao anterior no servidor)[/]"
    )
    console.print(
        Panel.fit(
            f"[green]OK Deploy concluido[/]\n"
            f"local:  {res.local}\n"
            f"remoto: {cfg.username}@{cfg.host}:{res.remote}\n"
            f"tamanho: {res.size} bytes" + backup_line,
            border_style="green",
        )
    )
    return PipelineResult(r_code=r_code, remote=res.remote)


def run_rollback(cfg: EnvConfig, *, console: Console, r_name: str | None = None) -> int:
    """Restaura a versao anterior do .r (ultimo backup). Retorna codigo de saida."""
    rec = last_restorable(cfg, r_name)
    if not rec:
        console.print(
            "[yellow]Nada para reverter:[/] nenhum backup disponivel para "
            f"{cfg.project}/{cfg.name}."
        )
        return 1
    console.print(
        Panel.fit(
            f"Reverter [bold]{rec.r_name}[/] em "
            f"[magenta]{rec.project}[/]/[cyan]{rec.env}[/]\n"
            f"deploy de {rec.timestamp}\n"
            f"restaurando: {rec.backup}\n"
            f"para: {rec.remote_path}",
            title="Rollback",
            border_style="yellow",
        )
    )
    try:
        restore_file(cfg, Path(rec.backup), rec.remote_path)
    except DeployError as exc:
        console.print(f"[red]X Falha no rollback:[/] {exc}")
        return 1
    console.print("[green]OK[/] versao anterior restaurada.")
    return 0
