"""Teste ponta a ponta: o grafo do Dagster materializado em processo, com o dbt de verdade."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def pipeline_env(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    base = tmp_path_factory.mktemp("pipeline")
    env = {
        "LANDING_ROOT": str(base / "landing"),
        "LAKE_ROOT": str(base / "lake"),
        "DBT_DUCKDB_PATH": str(base / "warehouse" / "locabit.duckdb"),
        "SITE_ROOT": str(base / "site"),
    }
    previous = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    dbt = shutil.which("dbt")
    assert dbt is not None
    subprocess.run(  # noqa: S603
        [dbt, "parse", "--project-dir", str(ROOT / "dbt"), "--profiles-dir", str(ROOT / "dbt"), "--quiet"],
        check=True,
    )
    yield base
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_definitions_load_with_full_lineage(pipeline_env: Path) -> None:
    from dagster import AssetKey

    from lakehouse.definitions import defs

    graph = defs.resolve_asset_graph()
    keys = graph.get_all_asset_keys()
    assert AssetKey(["bronze", "telemetry"]) in keys
    assert AssetKey("fleet_report") in keys
    # o modelo de staging depende do asset de ingestão (via source do dbt)
    assert AssetKey(["bronze", "telemetry"]) in graph.get(AssetKey(["staging", "stg_telemetry"])).parent_keys
    assert AssetKey(["marts", "rpt_fleet_kpis"]) in graph.get(AssetKey("fleet_report")).parent_keys
    # nenhuma dependência aponta para asset inexistente
    assert all(parent in keys for key in keys for parent in graph.get(key).parent_keys)
    assert defs.get_job_def("daily_pipeline") is not None


def test_materializes_end_to_end(pipeline_env: Path) -> None:
    from dagster import materialize

    from lakehouse.definitions import bronze, fleet_report, landing_extracts, locabit_dbt
    from lakehouse.definitions import defs as definitions

    result = materialize(
        [landing_extracts, bronze, locabit_dbt, fleet_report],
        resources=definitions.resources,
        run_config={"ops": {"landing_extracts": {"config": {"start": "2026-07-01", "days": 45}}}},
    )
    assert result.success
    from dagster import AssetCheckSeverity

    checks = result.get_asset_check_evaluations()
    bronze_checks = [c for c in checks if c.check_name == "quarantine_rate_below_5pct"]
    assert len(bronze_checks) == 6 and all(c.passed for c in bronze_checks)
    # testes do dbt viram asset checks; os de severidade error precisam passar
    failed = [c.check_name for c in checks if not c.passed and c.severity == AssetCheckSeverity.ERROR]
    assert len(checks) > 60 and failed == []
    assert any(c.check_name == "assert_mrr_movements_reconcile" and c.passed for c in checks)

    con = duckdb.connect(str(pipeline_env / "warehouse" / "locabit.duckdb"), read_only=True)
    kpis = con.execute("select active_customers, mrr, assets_deployed from marts.rpt_fleet_kpis").fetchone()
    con.close()
    assert kpis is not None and kpis[0] > 0 and kpis[1] > 0 and kpis[2] > 0
    report = (pipeline_env / "site" / "index.html").read_text(encoding="utf-8")
    assert "Locabit" in report and "<svg" in report
