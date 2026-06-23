"""Menu interativo: hub central. Roda com 'abl-deploy' (sem argumentos).

Configura uma vez (assistente) e depois e so escolher a acao:
deploy ABL, enviar frontend, observar frontend (watch).
"""

from __future__ import annotations

from pathlib import Path

import questionary
from rich.console import Console

from .config import ConfigError, ProjectConfig, load_projects
from .frontend import FrontendError, send_frontend, watch_frontend
from .pipeline import PipelineError, run_pipeline
from .wizard import run_wizard

console = Console()

SOURCE_GLOBS = ("*.p", "*.w", "*.cls")


def _select(message: str, choices: list[str]) -> str | None:
    return questionary.select(message, choices=choices).ask()


def _list_sources(project: ProjectConfig, env_name: str) -> list[str]:
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


def _pick_project_env(projects: dict[str, ProjectConfig]) -> tuple[ProjectConfig, str] | None:
    if len(projects) == 1:
        proj_name = next(iter(projects))
    else:
        proj_name = _select("Projeto:", sorted(projects))
        if proj_name is None:
            return None
    project = projects[proj_name]
    env_names = project.env_names()
    if not env_names:
        console.print(f"[red]O projeto '{proj_name}' nao tem ambientes.[/]")
        return None
    env_name = env_names[0] if len(env_names) == 1 else _select("Ambiente:", env_names)
    if env_name is None:
        return None
    return project, env_name


def _action_deploy_abl(projects: dict[str, ProjectConfig]) -> None:
    picked = _pick_project_env(projects)
    if not picked:
        return
    project, env_name = picked
    cfg = project.env(env_name)

    sources = _list_sources(project, env_name)
    if sources:
        source = questionary.autocomplete(
            "Fonte (digite para filtrar):", choices=sources
        ).ask()
    else:
        console.print("[yellow]Nenhum fonte encontrado nas pastas; digite o nome.[/]")
        source = questionary.text("Fonte:").ask()
    if not source:
        return

    destino = cfg.resolve_remote_dir(Path(source).name)
    if not questionary.confirm(
        f"Compilar e enviar {source} -> {project.name}/{env_name} -> {destino}?"
    ).ask():
        console.print("[dim]Cancelado.[/]")
        return
    try:
        run_pipeline(cfg, source, console=console)
    except PipelineError as exc:
        console.print(f"[red]X {exc}[/]")


def _action_frontend(projects: dict[str, ProjectConfig], watch: bool) -> None:
    picked = _pick_project_env(projects)
    if not picked:
        return
    project, env_name = picked
    cfg = project.env(env_name)
    try:
        if watch:
            watch_frontend(cfg, console=console)
        else:
            send_frontend(cfg, console=console)
    except FrontendError as exc:
        console.print(f"[red]X {exc}[/]")


def run_menu() -> int:
    """Loop do menu. Retorna o codigo de saida."""
    console.print("[bold cyan]ABL Deploy[/]\n")

    try:
        projects = load_projects()
    except ConfigError:
        console.print(
            "[yellow]Nenhuma configuracao encontrada.[/] Vamos criar uma agora."
        )
        if run_wizard() != 0:
            return 1
        try:
            projects = load_projects()
        except ConfigError as exc:
            console.print(f"[red]Erro de config:[/] {exc}")
            return 1

    while True:
        action = _select(
            "O que voce quer fazer?",
            [
                "Compilar e enviar ABL",
                "Enviar frontend (uma vez)",
                "Observar frontend (watch, auto-envio)",
                "Configurar (assistente)",
                "Sair",
            ],
        )
        if action is None or action == "Sair":
            return 0
        if action == "Configurar (assistente)":
            run_wizard()
            try:
                projects = load_projects()
            except ConfigError as exc:
                console.print(f"[red]Erro de config:[/] {exc}")
            continue
        if action == "Compilar e enviar ABL":
            _action_deploy_abl(projects)
        elif action.startswith("Enviar frontend"):
            _action_frontend(projects, watch=False)
        elif action.startswith("Observar frontend"):
            _action_frontend(projects, watch=True)
