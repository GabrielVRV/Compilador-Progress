"""Orquestra o fluxo compila -> envia, reutilizado pela CLI e pelo menu."""

from __future__ import annotations

import copy
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
from .deployer import DeployError, deploy_file


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

    target = copy.copy(cfg)
    target.remote_dir = remote_dir

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
            res = deploy_file(target, r_code, progress=_cb)
        except DeployError as exc:
            raise PipelineError(str(exc)) from exc

    console.print(
        Panel.fit(
            f"[green]OK Deploy concluido[/]\n"
            f"local:  {res.local}\n"
            f"remoto: {cfg.username}@{cfg.host}:{res.remote}\n"
            f"tamanho: {res.size} bytes",
            border_style="green",
        )
    )
    return PipelineResult(r_code=r_code, remote=res.remote)
