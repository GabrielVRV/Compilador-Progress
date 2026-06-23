"""Assistente interativo de configuracao: cria/edita projetos e grava o .toml."""

from __future__ import annotations

from pathlib import Path

import questionary
from rich.console import Console

try:  # Python 3.11+
    import tomllib  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

import tomli_w

from .config import (
    DEFAULT_CONFIG_NAMES,
    GLOBAL_CONFIG_NAME,
)

console = Console()


def _ask(msg: str, default: str = "") -> str | None:
    return questionary.text(msg, default=default).ask()


def _default_config_path() -> Path:
    """Onde gravar: prioriza um config existente; senao pergunta local/global."""
    for name in DEFAULT_CONFIG_NAMES:
        p = Path.cwd() / name
        if p.is_file():
            return p
    gp = Path.home() / GLOBAL_CONFIG_NAME
    if gp.is_file():
        return gp
    escolha = questionary.select(
        "Onde salvar a configuracao?",
        choices=[
            "Global (~/.abl-deploy.toml) - varios projetos",
            f"Local ({DEFAULT_CONFIG_NAMES[0]}) - so este projeto",
        ],
    ).ask()
    if escolha and escolha.startswith("Global"):
        return Path.home() / GLOBAL_CONFIG_NAME
    return Path.cwd() / DEFAULT_CONFIG_NAMES[0]


def _load(path: Path) -> dict:
    if path.is_file():
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    return {}


def _build_env() -> dict:
    """Coleta os dados de um ambiente."""
    env: dict = {}
    env["host"] = _ask("Host do servidor (ex.: prod.empresa.com):") or ""
    port = _ask("Porta SSH:", "22") or "22"
    env["port"] = int(port) if port.isdigit() else 22
    env["username"] = _ask("Usuario:") or ""

    auth = questionary.select(
        "Autenticacao:",
        choices=["Chave SSH (key_file)", "Senha por variavel de ambiente"],
    ).ask()
    if auth and auth.startswith("Chave"):
        env["key_file"] = _ask("Caminho da chave:", "~/.ssh/id_rsa") or "~/.ssh/id_rsa"
    else:
        var = _ask("Nome da variavel de ambiente da senha:", "ABL_PASS") or "ABL_PASS"
        env["password"] = f"env:{var}"

    env["remote_dir"] = _ask("Pasta remota do .r (remote_dir):") or ""

    # Roteamento opcional
    if questionary.confirm(
        "Rotear arquivos por nome (ex.: *rp.p para uma pasta)?", default=False
    ).ask():
        routes = []
        while True:
            match = _ask("Padrao (ex.: *rp.p), vazio p/ terminar:")
            if not match:
                break
            rd = _ask(f"remote_dir para '{match}':") or env.get("remote_dir", "")
            routes.append({"match": match, "remote_dir": rd})
        if routes:
            env["routes"] = routes

    # Frontend opcional
    if questionary.confirm(
        "Configurar frontend (envio sem compilar)?", default=True
    ).ask():
        fe: dict = {}
        fe["local_dir"] = _ask("Pasta local do frontend:") or ""
        fe["remote_dir"] = _ask("Pasta remota do frontend:") or ""
        inc = _ask(
            "Extensoes a enviar separadas por virgula (vazio = tudo):",
            "*.html,*.js,*.css,*.png",
        )
        if inc:
            fe["include"] = [s.strip() for s in inc.split(",") if s.strip()]
        if fe.get("local_dir") and fe.get("remote_dir"):
            env["frontend"] = fe

    return env


def run_wizard() -> int:
    """Fluxo do assistente. Retorna o codigo de saida."""
    console.print("[bold cyan]Assistente de configuracao[/]\n")

    path = _default_config_path()
    if path is None:
        return 1
    data = _load(path)
    is_global = path.name == GLOBAL_CONFIG_NAME and path.parent == Path.home()

    # Nome do projeto (so faz sentido no formato global/multi-projeto)
    if is_global or "project" in data:
        proj = _ask("Nome do projeto (ex.: financeiro):") or "default"
        data.setdefault("project", {})
        proj_body = data["project"].setdefault(proj, {})
    else:
        proj = "default"
        proj_body = data  # formato legado: defaults na raiz

    src = _ask("Pasta principal dos fontes (source_dir):", proj_body.get("source_dir", "src")) or "src"
    proj_body["source_dir"] = src
    extra = _ask(
        "Pastas extras de fontes separadas por virgula (vazio = nenhuma):", ""
    )
    if extra:
        proj_body["source_dirs"] = [s.strip() for s in extra.split(",") if s.strip()]
    proj_body.setdefault("build_dir", _ask("Pasta de build (.r):", proj_body.get("build_dir", "build")) or "build")
    dlc = _ask("Diretorio do OpenEdge $DLC (vazio se _progres ja esta no PATH):", proj_body.get("dlc", "") or "")
    if dlc:
        proj_body["dlc"] = dlc

    # Ambiente
    env_name = _ask("Nome do ambiente (dev/staging/prod):", "dev") or "dev"
    proj_body.setdefault("env", {})
    console.print(f"\n[bold]Ambiente '{env_name}':[/]")
    proj_body["env"][env_name] = _build_env()

    # Grava
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        tomli_w.dump(data, fh)

    console.print(
        f"\n[green]OK[/] Configuracao salva em [bold]{path}[/] "
        f"(projeto '{proj}', ambiente '{env_name}')."
    )
    return 0
