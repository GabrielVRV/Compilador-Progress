"""Historico de deploys ABL (ledger em JSON), base para o rollback."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import EnvConfig

HISTORY_FILE = ".abl-history.json"
BACKUP_DIRNAME = ".abl-backups"


@dataclass
class DeployRecord:
    timestamp: str        # ISO-ish, ordenavel
    project: str
    env: str
    source: str           # nome do fonte (.p)
    r_name: str           # nome do .r
    remote_path: str      # caminho remoto exato do .r
    backup: str | None    # caminho local do backup da versao anterior (ou None)


def _history_path(cfg: EnvConfig) -> Path:
    return Path(cfg.build_dir).resolve() / HISTORY_FILE


def backup_dir_for(cfg: EnvConfig) -> Path:
    """Pasta de backups para este projeto/ambiente."""
    return Path(cfg.build_dir).resolve() / BACKUP_DIRNAME / cfg.project / cfg.name


def load_history(cfg: EnvConfig) -> list[DeployRecord]:
    path = _history_path(cfg)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return [DeployRecord(**r) for r in raw]


def _save(cfg: EnvConfig, records: list[DeployRecord]) -> None:
    path = _history_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(r) for r in records], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def record_deploy(
    cfg: EnvConfig,
    *,
    source: str,
    r_name: str,
    remote_path: str,
    backup: Path | None,
) -> DeployRecord:
    """Acrescenta um registro ao historico e devolve o registro criado."""
    rec = DeployRecord(
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        project=cfg.project,
        env=cfg.name,
        source=source,
        r_name=r_name,
        remote_path=remote_path,
        backup=str(backup) if backup else None,
    )
    history = load_history(cfg)
    history.append(rec)
    _save(cfg, history)
    return rec


def recent(cfg: EnvConfig, limit: int = 20) -> list[DeployRecord]:
    """Deploys mais recentes primeiro (apenas deste projeto/ambiente)."""
    items = [
        r for r in load_history(cfg)
        if r.project == cfg.project and r.env == cfg.name
    ]
    return list(reversed(items))[:limit]


def last_restorable(cfg: EnvConfig, r_name: str | None = None) -> DeployRecord | None:
    """Ultimo deploy que tem backup (opcionalmente filtrando por .r)."""
    for rec in recent(cfg, limit=200):
        if rec.backup and Path(rec.backup).is_file():
            if r_name is None or rec.r_name == r_name:
                return rec
    return None
