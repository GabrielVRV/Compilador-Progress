"""Interface de linha de comando da ABL Deploy CLI.

Comandos:
    abl-deploy deploy <fonte.p> --env prod   compila + envia via SFTP
    abl-deploy init                          cria um abl-deploy.toml de exemplo
    abl-deploy envs                          lista os ambientes da config
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from . import __version__
from .compiler import CompileError, compile_source
from .config import (
    DEFAULT_CONFIG_NAMES,
    ConfigError,
    list_environments,
    load_config,
)
from .deployer import DeployError, deploy_file

app = typer.Typer(
    add_completion=False,
    help="Pipeline de deploy para Progress OpenEdge ABL.",
    no_args_is_help=True,
)
console = Console()


EXAMPLE_TOML = """\
# Configuração da ABL Deploy CLI
# Valores em [default] valem para todos os ambientes e podem ser
# sobrescritos em cada [env.<nome>].

[default]
# dlc = "C:/Progress/OpenEdge"   # diretório do OpenEdge ($DLC)
progres = "_progres"             # executável de batch (ou "prowin")
source_dir = "src"               # raiz dos seus fontes .p/.w/.cls
build_dir = "build"              # onde os .r serão gerados localmente
propath = ["src", "src/lib"]     # diretórios adicionados ao PROPATH

[env.dev]
host = "dev.suaempresa.com"
port = 22
username = "deploy"
password = "env:ABL_DEV_PASS"    # lê a senha da variável de ambiente
remote_dir = "/u/app/dev/rcode"

[env.staging]
host = "staging.suaempresa.com"
username = "deploy"
key_file = "~/.ssh/id_rsa"       # autenticação por chave SSH
remote_dir = "/u/app/staging/rcode"

[env.prod]
host = "prod.suaempresa.com"
username = "deploy"
key_file = "~/.ssh/id_rsa"
remote_dir = "/u/app/prod/rcode"
"""


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"abl-deploy {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    _version: Optional[bool] = typer.Option(
        None, "--version", "-V", callback=_version_callback, is_eager=True,
        help="Mostra a versão e sai.",
    ),
) -> None:
    """Pipeline de deploy para Progress OpenEdge ABL."""


@app.command()
def init(
    force: bool = typer.Option(False, "--force", "-f", help="Sobrescreve se já existir."),
) -> None:
    """Cria um arquivo de configuração de exemplo no diretório atual."""
    target = Path(DEFAULT_CONFIG_NAMES[0])
    if target.exists() and not force:
        console.print(
            f"[yellow]{target} já existe.[/] Use --force para sobrescrever."
        )
        raise typer.Exit(code=1)
    target.write_text(EXAMPLE_TOML, encoding="utf-8")
    console.print(
        Panel.fit(
            f"Config criada em [bold]{target}[/].\n"
            "Edite os ambientes e rode: [bold]abl-deploy deploy <fonte.p> --env dev[/]",
            title="abl-deploy init",
            border_style="green",
        )
    )


@app.command()
def envs() -> None:
    """Lista os ambientes definidos na configuração."""
    try:
        environments = list_environments()
    except ConfigError as exc:
        console.print(f"[red]Erro:[/] {exc}")
        raise typer.Exit(code=1)

    table = Table(title="Ambientes", show_header=True, header_style="bold cyan")
    table.add_column("Ambiente")
    for name in environments:
        table.add_row(name)
    console.print(table)


@app.command()
def deploy(
    source: str = typer.Argument(..., help="Fonte ABL a compilar (ex.: escq9986rp.p)."),
    env: str = typer.Option(..., "--env", "-e", help="Ambiente (dev/staging/prod)."),
    compile_only: bool = typer.Option(
        False, "--compile-only", "-c", help="Apenas compila, sem enviar."
    ),
    skip_compile: bool = typer.Option(
        False, "--skip-compile", help="Envia um .r já existente em build_dir."
    ),
) -> None:
    """Compila o fonte e envia o .r para o ambiente via SFTP."""
    try:
        cfg = load_config(env)
    except ConfigError as exc:
        console.print(f"[red]Erro de config:[/] {exc}")
        raise typer.Exit(code=1)

    console.print(
        Panel.fit(
            f"[bold]{source}[/]  →  ambiente [bold cyan]{env}[/]",
            title="ABL Deploy",
            border_style="cyan",
        )
    )

    r_code: Path

    # --- Passo 1: compilar ---
    if skip_compile:
        from .compiler import _r_code_path  # reuso interno

        src = Path(source)
        r_code = _r_code_path(src, Path(cfg.build_dir).resolve())
        if not r_code.is_file():
            console.print(f"[red]Erro:[/] .r não encontrado em {r_code}")
            raise typer.Exit(code=1)
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
                console.print("[red]✗ Falha na compilação:[/]")
                console.print(Panel(str(exc), border_style="red"))
                raise typer.Exit(code=1)
        r_code = result.r_code
        console.print(f"[green]✓[/] Compilado: [bold]{r_code.name}[/]")

    if compile_only:
        console.print("[dim]--compile-only: deploy ignorado.[/]")
        raise typer.Exit()

    # --- Passo 2: enviar via SFTP ---
    try:
        cfg.require_deploy()
    except ConfigError as exc:
        console.print(f"[red]Erro de config:[/] {exc}")
        raise typer.Exit(code=1)

    size = r_code.stat().st_size
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total} bytes"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(
            f"Enviando para {cfg.host}", total=size
        )

        def _cb(done: int, total: int) -> None:
            progress.update(task, completed=done, total=total)

        try:
            res = deploy_file(cfg, r_code, progress=_cb)
        except DeployError as exc:
            console.print(f"[red]✗ Falha no deploy:[/] {exc}")
            raise typer.Exit(code=1)

    console.print(
        Panel.fit(
            f"[green]✓ Deploy concluído[/]\n"
            f"local:  {res.local}\n"
            f"remoto: {cfg.username}@{cfg.host}:{res.remote}\n"
            f"tamanho: {res.size} bytes",
            border_style="green",
        )
    )


if __name__ == "__main__":  # pragma: no cover
    app()
