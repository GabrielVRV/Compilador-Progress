"""Carregamento e validação da configuração (.toml).

A config define valores padrão (seção [default]) e um bloco por ambiente
(seção [env.<nome>]). Os valores de ambiente sobrescrevem os defaults.
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


class ConfigError(Exception):
    """Erro de configuração legível para o usuário."""


@dataclass
class EnvConfig:
    """Configuração resolvida de um ambiente (dev/staging/prod)."""

    name: str

    # --- Compilação (local) ---
    dlc: str | None = None              # diretório de instalação do OpenEdge ($DLC)
    progres: str = "_progres"           # executável de batch (ou prowin)
    source_dir: str = "."               # raiz dos fontes .p/.w/.cls
    build_dir: str = "build"            # onde os .r serão gerados localmente
    propath: list[str] = field(default_factory=list)
    pf_file: str | None = None          # parameter file (-pf) opcional
    db_connect: str | None = None       # string de conexão opcional p/ compilar

    # --- Deploy (SFTP) ---
    host: str | None = None
    port: int = 22
    username: str | None = None
    password: str | None = None         # pode vir de env var, ver resolução abaixo
    key_file: str | None = None         # chave privada SSH
    remote_dir: str | None = None       # destino do .r no servidor

    def require_deploy(self) -> None:
        """Valida campos obrigatórios para o passo de deploy."""
        missing = [
            k
            for k in ("host", "username", "remote_dir")
            if not getattr(self, k)
        ]
        if missing:
            raise ConfigError(
                f"Ambiente '{self.name}': faltam campos de deploy: "
                + ", ".join(missing)
            )
        if not self.password and not self.key_file:
            raise ConfigError(
                f"Ambiente '{self.name}': defina 'password' ou 'key_file' "
                "para autenticar no SFTP."
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


def find_config_file(start: Path | None = None) -> Path:
    """Procura o arquivo de config no diretório atual e nos pais."""
    start = (start or Path.cwd()).resolve()
    for directory in (start, *start.parents):
        for name in DEFAULT_CONFIG_NAMES:
            candidate = directory / name
            if candidate.is_file():
                return candidate
    raise ConfigError(
        "Nenhum arquivo de config encontrado. Rode 'abl-deploy init' para "
        f"criar um {DEFAULT_CONFIG_NAMES[0]}."
    )


def _merge(default: dict[str, Any], env: dict[str, Any]) -> dict[str, Any]:
    merged = dict(default)
    merged.update({k: v for k, v in env.items() if v is not None})
    return merged


def load_config(env_name: str, config_path: Path | None = None) -> EnvConfig:
    """Carrega a config e devolve o ``EnvConfig`` resolvido do ambiente."""
    path = config_path or find_config_file()
    try:
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:  # type: ignore[attr-defined]
        raise ConfigError(f"TOML inválido em {path}: {exc}") from exc

    defaults = raw.get("default", {})
    environments = raw.get("env", {})

    if env_name not in environments:
        disponiveis = ", ".join(sorted(environments)) or "(nenhum)"
        raise ConfigError(
            f"Ambiente '{env_name}' não existe em {path}. "
            f"Ambientes disponíveis: {disponiveis}."
        )

    merged = _merge(defaults, environments[env_name])

    known = EnvConfig.__dataclass_fields__.keys()
    unknown = set(merged) - set(known) - {"name"}
    if unknown:
        raise ConfigError(
            f"Chaves desconhecidas na config: {', '.join(sorted(unknown))}"
        )

    return EnvConfig(name=env_name, **{k: merged[k] for k in merged if k in known})


def list_environments(config_path: Path | None = None) -> list[str]:
    path = config_path or find_config_file()
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    return sorted(raw.get("env", {}))
