"""Menu interativo: roda 'abl-deploy' sem argumentos.

Fluxo: escolhe projeto -> acao -> ambiente -> fonte (.p listado da pasta) ->
confirma -> compila e envia.
"""

from __future__ import annotations

from pathlib import Path

import questionary
from rich.console import Console

from .config import ConfigError, ProjectConfig, load_projects
from .pipeline import PipelineError, run_pipeline

console = Console()

SOURCE_GLOBS = ("*.p", "*.w", "*.cls")


def _list_sources(project: ProjectConfig, env_name: str) -> list[str]:
    """Lista os fontes encontrados nas pastas de busca do ambiente."""
    cfg = project.env(env_name)
    found: dict[str, str] = {}
    for d in cfg.search_dirs():
        base = Path(d)
        if not base.is_dir():
            continue
        for pattern in SOURCE_GLOBS:
            for f in sorted(base.glob(pattern)):
                found.setdefault(f.name, str(f))
    return sorted(found)


def _select(message: str, choices: list[str]) -> str | None:
    return questionary.select(message, choices=choices).ask()


def run_menu() -> int:
    """Loop do menu interativo. Retorna o codigo de saida."""
    try:
        projects = load_projects()
    except ConfigError as exc:
        console.print(f"[red]Erro de config:[/] {exc}")
        return 1

    console.print("[bold cyan]ABL Deploy[/] - menu interativo\n")

    # 1) Projeto
    if len(projects) == 1:
        proj_name = next(iter(projects))
    else:
        proj_name = _select("Projeto:", sorted(projects))
        if proj_name is None:
            return 1
    project = projects[proj_name]

    # 2) Ambiente
    env_names = project.env_names()
    if not env_names:
        console.print(f"[red]O projeto '{proj_name}' nao tem ambientes.[/]")
        return 1
    env_name = env_names[0] if len(env_names) == 1 else _select("Ambiente:", env_names)
    if env_name is None:
        return 1

    # 3) Acao
    action = _select(
        "O que fazer?",
        ["Compilar e enviar", "So compilar", "Enviar .r existente"],
    )
    if action is None:
        return 1
    compile_only = action == "So compilar"
    skip_compile = action == "Enviar .r existente"

    # 4) Fonte
    sources = _list_sources(project, env_name)
    if sources:
        source = questionary.autocomplete(
            "Fonte (digite para filtrar):", choices=sources
        ).ask()
    else:
        console.print("[yellow]Nenhum fonte encontrado nas pastas; digite o nome.[/]")
        source = questionary.text("Fonte:").ask()
    if not source:
        return 1

    # 5) Confirmacao
    cfg = project.env(env_name)
    destino = "(so compila)" if compile_only else cfg.resolve_remote_dir(
        Path(source).name
    )
    if not questionary.confirm(
        f"Confirmar: {source} -> {proj_name}/{env_name}  ->  {destino}?"
    ).ask():
        console.print("[dim]Cancelado.[/]")
        return 1

    # 6) Executa
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
        return 1
    return 0
