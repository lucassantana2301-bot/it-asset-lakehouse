"""Orquestração com Dagster: o pipeline como um grafo de assets com linhagem ponta a ponta.

landing_extracts → bronze/<fonte> (6 assets, com checagem de quarentena) → modelos dbt → fleet_report

A linhagem entre o bronze e o dbt vem dos sources declarados no dbt (bronze.<fonte>), que o
dagster-dbt mapeia para as mesmas chaves dos assets de ingestão.
"""

# Sem `from __future__ import annotations`: o Dagster lê as anotações (ex.: o tipo do Config) em tempo de execução.
from collections.abc import Iterator
from datetime import date
from typing import Any

from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetCheckSpec,
    AssetExecutionContext,
    AssetKey,
    AssetSelection,
    AssetSpec,
    Config,
    Definitions,
    MaterializeResult,
    MetadataValue,
    ScheduleDefinition,
    asset,
    define_asset_job,
    multi_asset,
)
from dagster_dbt import DbtCliResource, DbtProject, dbt_assets

from .contracts import CONTRACTS
from .generator import write_landing
from .ingestion import ingest
from .report import build_report
from .settings import DBT_DIR, Settings

MAX_QUARANTINE_RATE = 0.05
MART_KEYS = [
    AssetKey(["marts", name])
    for name in (
        "rpt_fleet_kpis",
        "fct_mrr_movements",
        "fct_asset_health",
        "fct_ticket_sla",
        "dim_customers",
        "rpt_data_quality",
    )
]

settings = Settings.from_env()
dbt_project = DbtProject(project_dir=DBT_DIR, profiles_dir=DBT_DIR)
dbt_project.prepare_if_dev()


class LandingConfig(Config):
    """Janela simulada de entregas das fontes (em produção, os arquivos chegam dos sistemas)."""

    start: str = "2026-07-01"
    days: int = 123
    seed: int = 42


@asset(group_name="landing", description="Extratos diários dos 5 sistemas de origem (CSV e JSONL).")
def landing_extracts(context: AssetExecutionContext, config: LandingConfig) -> MaterializeResult[Any]:
    files = write_landing(settings.landing, date.fromisoformat(config.start), config.days, config.seed)
    context.log.info("%d arquivos gravados em %s", len(files), settings.landing)
    return MaterializeResult(metadata={"arquivos": len(files), "landing": MetadataValue.path(str(settings.landing))})


@multi_asset(
    specs=[
        AssetSpec(
            AssetKey(["bronze", name]),
            deps=[landing_extracts],
            group_name="bronze",
            description=f"Partições Parquet de {name} validadas pelo contrato (inválidas vão para a quarentena).",
            kinds={"parquet", "duckdb"},
        )
        for name in CONTRACTS
    ],
    check_specs=[
        AssetCheckSpec(
            "quarantine_rate_below_5pct",
            asset=AssetKey(["bronze", name]),
            description="Menos de 5% das linhas lidas podem ir para a quarentena.",
        )
        for name in CONTRACTS
    ],
)
def bronze(context: AssetExecutionContext) -> Iterator[MaterializeResult[Any] | AssetCheckResult]:
    results = ingest(settings.landing, settings.lake)
    for name in CONTRACTS:
        partitions = [r for r in results if r.source == name]
        read = sum(r.rows_read for r in partitions)
        quarantined = sum(r.rows_quarantined for r in partitions)
        rate = quarantined / read if read else 0.0
        key = AssetKey(["bronze", name])
        yield MaterializeResult(
            asset_key=key,
            metadata={
                "partições ingeridas": sum(r.status == "ingested" for r in partitions),
                "partições sem mudança": sum(r.status == "unchanged" for r in partitions),
                "linhas lidas": read,
                "linhas em quarentena": quarantined,
            },
        )
        yield AssetCheckResult(
            asset_key=key,
            check_name="quarantine_rate_below_5pct",
            passed=rate < MAX_QUARANTINE_RATE,
            severity=AssetCheckSeverity.WARN,
            metadata={"taxa": MetadataValue.float(round(rate, 5))},
        )


@dbt_assets(manifest=dbt_project.manifest_path, project=dbt_project)
def locabit_dbt(context: AssetExecutionContext, dbt: DbtCliResource) -> Iterator[object]:
    yield from dbt.cli(["build"], context=context).stream()


@asset(deps=MART_KEYS, group_name="serving", kinds={"html"}, description="Painel executivo estático.")
def fleet_report(context: AssetExecutionContext) -> MaterializeResult[Any]:
    output = build_report(settings.warehouse, settings.site / "index.html")
    context.log.info("painel gravado em %s", output)
    return MaterializeResult(metadata={"arquivo": MetadataValue.path(str(output))})


daily_pipeline = define_asset_job("daily_pipeline", selection=AssetSelection.all())

defs = Definitions(
    assets=[landing_extracts, bronze, locabit_dbt, fleet_report],
    jobs=[daily_pipeline],
    schedules=[
        ScheduleDefinition(job=daily_pipeline, cron_schedule="0 6 * * *", execution_timezone="America/Sao_Paulo")
    ],
    resources={"dbt": DbtCliResource(project_dir=dbt_project)},
)
