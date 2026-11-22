"""Linha de comando: lakehouse generate | ingest | report | run.

`run` executa o pipeline inteiro sem orquestrador (útil no CI e para quem só quer ver funcionando);
em produção o mesmo encadeamento roda como assets do Dagster (lakehouse.definitions).
"""

from __future__ import annotations

import argparse
import collections
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

from .generator import write_landing
from .ingestion import ingest
from .report import build_report
from .settings import DBT_DIR, Settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lakehouse", description="Pipeline de dados da Locabit (fictícia).")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="gera os extratos diários das fontes na landing")
    gen.add_argument("--start", type=date.fromisoformat, default=date(2026, 7, 1))
    gen.add_argument("--days", type=int, default=123)
    gen.add_argument("--seed", type=int, default=42)

    ing = sub.add_parser("ingest", help="landing → bronze, com contrato e quarentena")
    ing.add_argument("--source", action="append", help="limita a uma fonte (pode repetir)")
    ing.add_argument("--force", action="store_true", help="reprocessa mesmo sem mudança no arquivo")

    rep = sub.add_parser("report", help="gera o painel HTML a partir dos marts")
    rep.add_argument("--out", type=Path, help="padrão: SITE_ROOT/index.html")
    rep.add_argument("--revision")

    run = sub.add_parser("run", help="generate + ingest + dbt build + report")
    run.add_argument("--days", type=int, default=123)
    run.add_argument("--out", type=Path, help="padrão: SITE_ROOT/index.html")
    return parser


def _ingest(lake: Path, landing: Path, sources: list[str] | None, force: bool) -> int:
    results = ingest(landing, lake, sources=sources, force=force)
    status = collections.Counter(r.status for r in results)
    read = sum(r.rows_read for r in results)
    quarantined = sum(r.rows_quarantined for r in results)
    print(f"partições: {dict(status)} · linhas lidas: {read} · quarentena: {quarantined}")
    reasons: collections.Counter[str] = collections.Counter()
    for r in results:
        reasons.update({f"{r.source} {k}": v for k, v in r.reasons.items()})
    for reason, count in reasons.most_common():
        print(f"  {count:>6}  {reason}")
    return 0


def _dbt(*args: str, env: dict[str, str]) -> None:
    executable = shutil.which("dbt")
    if executable is None:
        raise SystemExit("dbt não encontrado no PATH: rode `uv sync`")
    subprocess.run(  # noqa: S603 (executável resolvido e argumentos fixos, sem shell)
        [executable, *args, "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR)],
        check=True,
        env=env,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = Settings.from_env()
    landing, lake, database = settings.landing, settings.lake, settings.warehouse
    output = args.out if getattr(args, "out", None) else settings.site / "index.html"

    if args.command == "generate":
        files = write_landing(landing, args.start, args.days, args.seed)
        print(f"{len(files)} arquivos em {landing}")
        return 0
    if args.command == "ingest":
        return _ingest(lake, landing, args.source, args.force)
    if args.command == "report":
        print(build_report(database, output, revision=args.revision))
        return 0
    if args.command == "run":
        write_landing(landing, date(2026, 7, 1), args.days)
        _ingest(lake, landing, None, False)
        env = os.environ | {"LAKE_ROOT": str(lake), "DBT_DUCKDB_PATH": str(database)}
        _dbt("build", env=env)
        print(build_report(database, output))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
