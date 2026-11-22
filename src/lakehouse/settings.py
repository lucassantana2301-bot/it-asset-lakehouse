"""Caminhos do pipeline, configuráveis por variável de ambiente (12-factor)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DBT_DIR = ROOT / "dbt"


@dataclass(frozen=True, slots=True)
class Settings:
    landing: Path
    lake: Path
    warehouse: Path
    site: Path

    @classmethod
    def from_env(cls) -> Settings:
        data = ROOT / "data"
        settings = cls(
            landing=Path(os.environ.get("LANDING_ROOT", data / "landing")).resolve(),
            lake=Path(os.environ.get("LAKE_ROOT", data / "lake")).resolve(),
            warehouse=Path(os.environ.get("DBT_DUCKDB_PATH", data / "warehouse" / "locabit.duckdb")).resolve(),
            site=Path(os.environ.get("SITE_ROOT", ROOT / "site")).resolve(),
        )
        settings.warehouse.parent.mkdir(parents=True, exist_ok=True)
        # O dbt lê os mesmos caminhos via env_var(): exporta para os subprocessos do dbt.
        os.environ.setdefault("LAKE_ROOT", str(settings.lake))
        os.environ.setdefault("DBT_DUCKDB_PATH", str(settings.warehouse))
        return settings
