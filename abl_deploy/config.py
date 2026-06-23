"""Carregamento e validação da configuração (.toml).

Dois formatos são suportados:

1. Multi-projeto (recomendado, geralmente em ~/.abl-deploy.toml)::

       [project.financeiro]
       source_dir = "C:/projetos/financeiro/src"

       [project.financeiro.env.prod]
       host = "prod.empresa.com"

2. Projeto único (legado, em ./abl-deploy.toml)::

       [default]
       source_dir = "src"

       [env.prod]
       host = "..."
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback 3.9/3.10
    import tomli as tomllib  # type: ignore


DEFAULT_CONFIG_NAMES = ("abl-deploy.toml", ".abl-deploy.toml")
GLOBAL_CONFIG_NAME = ".abl-deploy.toml"
ENV_CONFIG_VAR = "ABL_DEPLOY_CONFIG"


class ConfigError(Exception):
    """Erro de configuração legível para o usuário."""


@dataclass
class EnvConfig:
    """Configuração resolvida de um ambiente (dev/staging/prod)."""

    name: str
    project: str = "default"

    # --- Compilação (local) ---
    dlc: str | None = None
    progres: str = "_progres"
    source_dir: str = "."
    source_dirs: list[str] = field(default_factory=list)
    build_dir: str = "build"
    propath: list[str] = field(default_factory=list)
    pf_file: str | None = None
    db_connect: str | None = None

    # --- Deploy (SFTP) ---
    host: str | None = None
    port: int = 22
    username: str | None = None
    password: str | None = None
    key_file: str | None = None
    remote_dir: str | None = None

    # --- Roteamento por nome do arquivo ---
    routes: list[dict] = field(default_factory=list)

    # --- Frontend (arquivos estáticos enviados sem compilar) ---
    # { local_dir = "web", remote_dir = "/u/app/dev/web", include = ["*.html","*.js"] }
    frontend: dict | None = None

    def require_deploy(self) -> None:
        """Valida campos obrigatórios para o passo de deploy."""
        missing = [k for k in ("host", "username") if not getattr(self, k)]
        if missing:
            raise ConfigError(
                f"Projeto '{self.project}', ambiente '{self.name}': faltam "
                f"campos de deploy: {', '.join(missing)}"
            )
        if not self.remote_dir and not self.routes:
            raise ConfigError(
                f"Projeto '{self.project}', ambiente '{self.name}': defina "
                "'remote_dir' ou ao menos uma regra em 'routes'."
            )
        if not self.password and not self.key_file:
            raise ConfigError(
                f"Projeto '{self.project}', ambiente '{self.name}': defina "
                "'password' ou 'key_file' para autenticar no SFTP."
            )

    def resolve_password(self) -> str | None:
        """Resolve a senha, permitindo o formato ``env:NOME_DA_VAR``."""
        if self.password and self.password.startswith("env:"):
            var = self.password[4:]
            value = os.environ.get(var)
            if not value:
                raise ConfigError(
                    f"Variável de ambiente '{var}' (senha) não está definida."
                )
            return value
        return self.password

    def search_dirs(self) -> list[str]:
        """Todas as pastas onde procurar o fonte (source_dir + source_dirs)."""
        dirs: list[str] = []
        for d in [self.source_dir, *self.source_dirs]:
            if d and d not in dirs:
                dirs.append(d)
        return dirs

    def resolve_remote_dir(self, filename: str) -> str | None:
        """Resolve o diretório remoto para um arquivo, aplicando as routes."""
        from fnmatch import fnmatch

        for rule in self.routes:
            pattern = rule.get("match")
            if pattern and fnmatch(filename, pattern):
                return rule.get("remote_dir", self.remote_dir)
        return self.remote_dir

    def frontend_target(self) -> tuple[str, str, list[str]] | None:
        """Devolve (local_dir, remote_dir, include) do frontend, se houver."""
        if not self.frontend:
            return None
        fe = self.frontend
        local = fe.get("local_dir")
        remote = fe.get("remote_dir")
        if not local or not remote:
            return None
        return local, remote, list(fe.get("include", []))


@dataclass
class ProjectConfig:
    """Um projeto com seus defaults e ambientes."""

    name: str
    defaults: dict[str, Any]
    environments: dict[str, dict[str, Any]]

    def env_names(self) -> list[str]:
        return sorted(self.environments)

    def env(self, env_name: str) -> EnvConfig:
        if env_name not in self.environments:
            disponiveis = ", ".join(self.env_names()) or "(nenhum)"
            raise ConfigError(
                f"Ambiente '{env_name}' não existe no projeto '{self.name}'. "
                f"Disponíveis: {disponiveis}."
            )
        merged = _merge(self.defaults, self.environments[env_name])
        known = set(EnvConfig.__dataclass_fields__) - {"name", "project"}
        unknown = set(merged) - known
        if unknown:
            raise ConfigError(
                f"Chaves desconhecidas na config: {', '.join(sorted(unknown))}"
            )
        return EnvConfig(
            name=env_name,
            project=self.name,
            **{k: merged[k] for k in merged if k in known},
        )


def _merge(default: dict[str, Any], env: dict[str, Any]) -> dict[str, Any]:
    merged = dict(default)
    merged.update({k: v for k, v in env.items() if v is not None})
    return merged


def find_config_file(start: Path | None = None) -> Path:
    """Localiza o arquivo de config (env var, local, depois global)."""
    env_path = os.environ.get(ENV_CONFIG_VAR)
    if env_path:
        p = Path(env_path).expanduser()
        if p.is_file():
            return p
        raise ConfigError(f"{ENV_CONFIG_VAR} aponta para um arquivo inexistente: {p}")

    start = (start or Path.cwd()).resolve()
    for directory in (start, *start.parents):
        for name in DEFAULT_CONFIG_NAMES:
            candidate = directory / name
            if candidate.is_file():
                return candidate

    global_path = Path.home() / GLOBAL_CONFIG_NAME
    if global_path.is_file():
        return global_path

    raise ConfigError(
        "Nenhum arquivo de config encontrado. Rode 'abl-deploy init' para criar "
        f"um {DEFAULT_CONFIG_NAMES[0]}, ou 'abl-deploy init --global' para o "
        "config global (~/.abl-deploy.toml)."
    )


def _parse(path: Path) -> dict[str, Any]:
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:  # type: ignore[attr-defined]
        raise ConfigError(f"TOML inválido em {path}: {exc}") from exc


def load_projects(config_path: Path | None = None) -> dict[str, ProjectConfig]:
    """Carrega todos os projetos definidos no config."""
    path = config_path or find_config_file()
    raw = _parse(path)
    projects: dict[str, ProjectConfig] = {}

    for name, body in raw.get("project", {}).items():
        if not isinstance(body, dict):
            continue
        defaults = {k: v for k, v in body.items() if k != "env"}
        environments = body.get("env", {})
        projects[name] = ProjectConfig(name, defaults, environments)

    if "default" in raw or "env" in raw:
        projects.setdefault(
            "default",
            ProjectConfig("default", raw.get("default", {}), raw.get("env", {})),
        )

    if not projects:
        raise ConfigError(
            f"Nenhum projeto ou ambiente definido em {path}. "
            "Veja abl-deploy.example.toml."
        )
    return projects


def load_config(
    env_name: str,
    project: str | None = None,
    config_path: Path | None = None,
) -> EnvConfig:
    """Resolve o ``EnvConfig`` de um ambiente (e projeto, se houver vários)."""
    projects = load_projects(config_path)

    if project is None:
        if len(projects) == 1:
            project = next(iter(projects))
        else:
            disponiveis = ", ".join(sorted(projects))
            raise ConfigError(
                "Há mais de um projeto na config; informe --project. "
                f"Disponíveis: {disponiveis}."
            )

    if project not in projects:
        disponiveis = ", ".join(sorted(projects))
        raise ConfigError(
            f"Projeto '{project}' não existe. Disponíveis: {disponiveis}."
        )

    return projects[project].env(env_name)


def list_environments(
    project: str | None = None, config_path: Path | None = None
) -> list[str]:
    projects = load_projects(config_path)
    if project is None and len(projects) == 1:
        project = next(iter(projects))
    if project is None:
        names: set[str] = set()
        for proj in projects.values():
            names.update(proj.env_names())
        return sorted(names)
    if project not in projects:
        raise ConfigError(f"Projeto '{project}' não existe.")
    return projects[project].env_names()
