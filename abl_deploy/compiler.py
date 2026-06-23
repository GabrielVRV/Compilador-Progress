"""Compilação de fontes ABL via _progres em batch.

Invoca o executável OpenEdge em modo batch (``-b``) rodando o template
``compile.p``, que faz ``COMPILE ... SAVE INTO`` e reporta o resultado.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import EnvConfig

TEMPLATE = Path(__file__).parent / "templates" / "compile.p"


class CompileError(Exception):
    """Falha de compilação com a saída do compilador ABL."""


@dataclass
class CompileResult:
    source: Path
    r_code: Path
    output: str


def _executable(cfg: EnvConfig) -> str:
    """Resolve o caminho do executável _progres, usando DLC se informado."""
    progres = cfg.progres
    if cfg.dlc:
        candidate = Path(cfg.dlc) / "bin" / progres
        if candidate.exists() or sys.platform.startswith("win"):
            return str(candidate)
    return progres


def _r_code_path(source: Path, build_dir: Path) -> Path:
    """Caminho esperado do .r gerado para um fonte."""
    return build_dir / (source.stem + ".r")


def find_source(cfg: EnvConfig, source: str) -> Path:
    """Localiza o fonte procurando em todas as pastas configuradas.

    Aceita caminho absoluto, ou nome relativo buscado em source_dir e
    em cada uma das source_dirs. Levanta ``CompileError`` se não achar.
    """
    if Path(source).is_absolute():
        p = Path(source).resolve()
        if p.is_file():
            return p
        raise CompileError(f"Fonte não encontrado: {p}")

    tried: list[str] = []
    for d in cfg.search_dirs():
        candidate = (Path(d) / source).resolve()
        tried.append(str(candidate))
        if candidate.is_file():
            return candidate
    raise CompileError(
        "Fonte não encontrado. Procurei em:\n  " + "\n  ".join(tried)
    )


def compile_source(cfg: EnvConfig, source: str) -> CompileResult:
    """Compila um fonte e devolve o caminho do .r gerado.

    Levanta ``CompileError`` se o compilador reportar erro ou se o .r
    não for produzido.
    """
    src_path = find_source(cfg, source)
    source_root = src_path.parent

    build_dir = Path(cfg.build_dir).resolve()
    build_dir.mkdir(parents=True, exist_ok=True)

    propath = ",".join(str(Path(p).resolve()) for p in cfg.propath)
    param = f"{src_path}|{build_dir}|{propath}"

    cmd: list[str] = [_executable(cfg), "-b", "-p", str(TEMPLATE), "-param", param]
    if cfg.pf_file:
        cmd += ["-pf", str(Path(cfg.pf_file).resolve())]
    if cfg.db_connect:
        cmd += cfg.db_connect.split()

    env = os.environ.copy()
    if cfg.dlc:
        env["DLC"] = cfg.dlc
        env["PATH"] = str(Path(cfg.dlc) / "bin") + os.pathsep + env.get("PATH", "")

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(source_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError as exc:
        raise CompileError(
            f"Executável '{cfg.progres}' não encontrado. Verifique 'dlc'/'progres' "
            "na config e se o OpenEdge está instalado."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise CompileError("Compilação excedeu o tempo limite (300s).") from exc

    output = (proc.stdout or "") + (proc.stderr or "")

    if "COMPILE-ERROR" in output or "COMPILE-OK" not in output:
        raise CompileError(output.strip() or "Compilação falhou sem saída.")

    r_path = _r_code_path(src_path, build_dir)
    if not r_path.is_file():
        raise CompileError(
            f"Compilação reportou sucesso mas o .r não foi encontrado em {r_path}."
        )

    return CompileResult(source=src_path, r_code=r_path, output=output.strip())
