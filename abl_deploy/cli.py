"""Interface de linha de comando da ABL Deploy CLI.

Comandos:
    abl-deploy                                menu interativo
    abl-deploy deploy <fonte.p> -e prod       compila + envia via SFTP
    abl-deploy init [--global]                cria um arquivo de config de exemplo
    abl-deploy envs [-p projeto]              lista os ambientes
    abl-deploy projects                       lista os projetos
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .config import (
    DEFAULT_CONFIG_NAMES,
    GLOBAL_CONFIG_NAME,
    ConfigError,
    list_environments,
    load_config,
    load_projects,
)
from .frontend import FrontendError, send_frontend, watch_frontend
from .menu import run_menu
from .pipeline import PipelineError, run_pipeline
from .wizard import run_wizard

app = typer.Typer(
    add_completion=False,
    help="Pipeline de deploy para Progress OpenEdge ABL.",
    invoke_without_command=True,
)
console = Console()


EXAMPLE_SINGLE = """\
# Config da ABL Deploy CLI (projeto unico).
# [default] vale para todos os ambientes; cada [env.X] sobrescreve.

[default]
# dlc = "C:/Progress/OpenEdge"
progres = "_progres"
source_dir = "src"
source_dirs = ["src/telas", "src/rp"]
build_dir = "build"
propath = ["src", "src/lib"]

[env.dev]
host = "dev.suaempresa.com"
username = "deploy"
password = "env:ABL_DEV_PASS"
remote_dir = "/u/app/dev/rcode"

[[env.dev.routes]]
match = "*rp.p"
remote_dir = "/u/app/dev/rp"

[[env.dev.routes]]
match = "*.p"
remote_dir = "/u/app/dev/telas"

[env.dev.frontend]
local_dir = "web"
remote_dir = "/u/app/dev/web"
include = ["*.html", "*.js", "*.css", "*.png"]

[env.prod]
host = "prod.suaempresa.com"
username = "deploy"
key_file = "~/.ssh/id_rsa"
remote_dir = "/u/app/prod/rcode"
"""

EXAMPLE_GLOBAL = """\
# Config GLOBAL da ABL Deploy CLI (~/.abl-deploy.toml) - multi-projeto.

[project.financeiro]
source_dir = "C:/projetos/financeiro/src"
source_dirs = ["C:/projetos/financeiro/src/telas", "C:/projetos/financeiro/src/rp"]
build_dir  = "C:/projetos/financeiro/build"
propath = ["C:/projetos/financeiro/src"]

[project.financeiro.env.prod]
host = "prod.suaempresa.com"
username = "deploy"
key_file = "~/.ssh/id_rsa"
remote_dir = "/u/app/prod/rcode"

[[project.financeiro.env.prod.routes]]
match = "*rp.p"
remote_dir = "/u/app/prod/rp"

[[project.financeiro.env.prod.routes]]
match = "*.p"
remote_dir = "/u/app/prod/telas"

[project.estoque]
source_dir = "C:/projetos/estoque/src"
build_dir  = "C:/projetos/estoque/build"

[project.estoque.env.prod]
host = "prod.suaempresa.com"
username = "deploy"
key_file = "~/.ssh/id_rsa"
remote_dir = "/u/app/estoque/rcode"
"""


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"abl-deploy {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    _version: Optional[bool] = typer.Option(
        None, "--version", "-V", callback=_version_callback, is_eager=True,
        help="Mostra a versao e sai.",
    ),
) -> None:
    """Sem subcomando: abre o menu interativo."""
    if ctx.invoked_subcommand is None:
        raise typer.Exit(code=run_menu())


@app.command()
def init(
    global_: bool = typer.Option(
        False, "--global", "-g", help="Cria o config global (~/.abl-deploy.toml)."
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Sobrescreve se ja existir."),
) -> None:
    """Cria um arquivo de configuracao de exemplo."""
    if global_:
        target = Path.home() / GLOBAL_CONFIG_NAME
        content = EXAMPLE_GLOBAL
    else:
        target = Path(DEFAULT_CONFIG_NAMES[0])
        content = EXAMPLE_SINGLE

    if target.exists() and not force:
        console.print(f"[yellow]{target} ja existe.[/] Use --force para sobrescrever.")
        raise typer.Exit(code=1)

    target.write_text(content, encoding="utf-8")
    console.print(
        Panel.fit(
            f"Config criada em [bold]{target}[/].\n"
            "Edite e rode [bold]abl-deploy[/] para abrir o menu.",
            title="abl-deploy init",
            border_style="green",
        )
    )


@app.command()
def projects() -> None:
    """Lista os projetos definidos na configuracao."""
    try:
        projs = load_projects()
    except ConfigError as exc:
        console.print(f"[red]Erro:[/] {exc}")
        raise typer.Exit(code=1)
    table = Table(title="Projetos", show_header=True, header_style="bold magenta")
    table.add_column("Projeto")
    table.add_column("Ambientes")
    for name, proj in sorted(projs.items()):
        table.add_row(name, ", ".join(proj.env_names()) or "[dim](nenhum)[/]")
    console.print(table)


@app.command()
def envs(
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Projeto."),
) -> None:
    """Lista os ambientes definidos na configuracao."""
    try:
        environments = list_environments(project)
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
    project: Optional[str] = typer.Option(
        None, "--project", "-p", help="Projeto (se houver mais de um na config)."
    ),
    compile_only: bool = typer.Option(
        False, "--compile-only", "-c", help="Apenas compila, sem enviar."
    ),
    skip_compile: bool = typer.Option(
        False, "--skip-compile", help="Envia um .r ja existente em build_dir."
    ),
) -> None:
    """Compila o fonte e envia o .r para o ambiente via SFTP."""
    try:
        cfg = load_config(env, project)
    except ConfigError as exc:
        console.print(f"[red]Erro de config:[/] {exc}")
        raise typer.Exit(code=1)

    try:
        run_pipeline(
            cfg,
            source,
            console=console,
            compile_only=compile_only,
            skip_compile=skip_compile,
        )
    except PipelineError as exc:
        console.print(f"[red]X {exc}[/]")
        raise typer.Exit(code=1)


@app.command()
def config() -> None:
    """Abre o assistente de configuracao (cria/edita o .toml)."""
    raise typer.Exit(code=run_wizard())


@app.command()
def frontend(
    env: str = typer.Option(..., "--env", "-e", help="Ambiente (dev/staging/prod)."),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Projeto."),
) -> None:
    """Envia todos os arquivos de frontend (sem compilar)."""
    try:
        cfg = load_config(env, project)
    except ConfigError as exc:
        console.print(f"[red]Erro de config:[/] {exc}")
        raise typer.Exit(code=1)
    try:
        send_frontend(cfg, console=console)
    except FrontendError as exc:
        console.print(f"[red]X {exc}[/]")
        raise typer.Exit(code=1)


@app.command()
def watch(
    env: str = typer.Option(..., "--env", "-e", help="Ambiente (dev/staging/prod)."),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Projeto."),
) -> None:
    """Observa a pasta do frontend e envia cada arquivo ao salvar (Ctrl+C para parar)."""
    try:
        cfg = load_config(env, project)
    except ConfigError as exc:
        console.print(f"[red]Erro de config:[/] {exc}")
        raise typer.Exit(code=1)
    try:
        watch_frontend(cfg, console=console)
    except FrontendError as exc:
        console.print(f"[red]X {exc}[/]")
        raise typer.Exit(code=1)



if __name__ == "__main__":  # pragma: no cover
    app()
