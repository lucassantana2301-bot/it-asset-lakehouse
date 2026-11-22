from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from lakehouse.ingestion import discover, ingest, ingest_partition

CONTRACTS_HEADER = "contract_id,customer_id,start_date,end_date,seats,monthly_fee,status,updated_at\n"


def _write(landing: Path, source: str, dt: str, content: str, ext: str = "csv") -> Path:
    path = landing / source / f"dt={dt}" / f"extract.{ext}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _query(sql: str) -> list[tuple[object, ...]]:
    relation = duckdb.sql(sql)
    assert relation is not None
    return relation.fetchall()


def _rows(path: Path) -> list[tuple[object, ...]]:
    return _query(f"select * from read_parquet('{path}')")


def test_valid_and_invalid_rows_are_split_with_reasons(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "landing",
        "contracts",
        "2026-07-01",
        CONTRACTS_HEADER
        + "CTR-1,CUS-1,2026-07-01,2027-07-01,10,1890.00,active,2026-07-01\n"
        + ",CUS-2,2026-07-01,2027-07-01,5,900.00,active,2026-07-01\n"  # chave nula
        + "CTR-3,CUS-3,2026-07-01,2026-06-01,5,900.00,active,2026-07-01\n"  # fim antes do início
        + "CTR-4,CUS-4,2026-07-01,2027-07-01,5,muito,active,2026-07-01\n"  # tipo inválido
        + "CTR-5,CUS-5,2026-07-01,2027-07-01,5,-1,paused,2026-07-01\n",  # duas regras
    )
    lake = tmp_path / "lake"
    result = ingest_partition(source, lake)

    assert (result.rows_read, result.rows_valid, result.rows_quarantined) == (5, 1, 4)
    assert result.reasons == {
        "obrigatorio:contract_id": 1,
        "obrigatorio:monthly_fee": 1,
        "regra:mensalidade_nao_negativa": 1,
        "regra:status_valido": 1,
        "regra:vigencia_coerente": 1,
        "tipo_invalido:monthly_fee": 1,
    }
    valid = _rows(lake / "bronze/contracts/dt=2026-07-01/data.parquet")
    assert [row[0] for row in valid] == ["CTR-1"]
    quarantine = lake / "quarantine/contracts/dt=2026-07-01/data.parquet"
    quarantined = _query(f"select contract_id, monthly_fee, _errors from read_parquet('{quarantine}') order by _line")
    assert quarantined[2][1] == "muito", "a quarentena guarda o valor original para investigação"


def test_reingesting_same_file_is_a_no_op_and_changes_replace_the_partition(tmp_path: Path) -> None:
    landing, lake = tmp_path / "landing", tmp_path / "lake"
    path = _write(
        landing,
        "contracts",
        "2026-07-01",
        CONTRACTS_HEADER + "CTR-1,CUS-1,2026-07-01,2027-07-01,1,10.00,active,2026-07-01\n",
    )
    assert ingest(landing, lake)[0].status == "ingested"
    assert ingest(landing, lake)[0].status == "unchanged"

    path.write_text(
        CONTRACTS_HEADER
        + "CTR-1,CUS-1,2026-07-01,2027-07-01,1,10.00,active,2026-07-01\n"
        + "CTR-2,CUS-2,2026-07-01,2027-07-01,1,20.00,active,2026-07-01\n",
        encoding="utf-8",
    )
    assert ingest(landing, lake)[0].status == "ingested"
    assert len(_rows(lake / "bronze/contracts/dt=2026-07-01/data.parquet")) == 2, "partição substituída, sem duplicar"
    assert ingest(landing, lake, force=True)[0].status == "ingested"


def test_fixed_partition_removes_stale_quarantine(tmp_path: Path) -> None:
    landing, lake = tmp_path / "landing", tmp_path / "lake"
    path = _write(
        landing,
        "contracts",
        "2026-07-01",
        CONTRACTS_HEADER + ",CUS-1,2026-07-01,2027-07-01,1,10.00,active,2026-07-01\n",
    )
    ingest(landing, lake)
    quarantine = lake / "quarantine/contracts/dt=2026-07-01/data.parquet"
    assert quarantine.exists()
    path.write_text(
        CONTRACTS_HEADER + "CTR-1,CUS-1,2026-07-01,2027-07-01,1,10.00,active,2026-07-01\n", encoding="utf-8"
    )
    ingest(landing, lake)
    assert not quarantine.exists()


def test_jsonl_ranges_and_manifest(tmp_path: Path) -> None:
    landing, lake = tmp_path / "landing", tmp_path / "lake"
    events = [
        {
            "event_id": "E1",
            "asset_id": "A1",
            "event_ts": "2026-07-01T09:00:00",
            "cpu_util_pct": 30.5,
            "disk_free_pct": 50,
            "battery_health_pct": 90,
            "agent_version": "3.5.0",
        },
        {
            "event_id": "E2",
            "asset_id": "A1",
            "event_ts": "2026-07-01T09:00:00",
            "cpu_util_pct": 340,
            "disk_free_pct": 50,
            "battery_health_pct": None,
            "agent_version": "3.5.0",
        },
    ]
    _write(landing, "telemetry", "2026-07-01", "\n".join(json.dumps(e) for e in events), "jsonl")
    result = ingest(landing, lake)[0]
    assert result.reasons == {"regra:cpu_entre_0_e_100": 1}
    manifest = json.loads((lake / "_manifests/telemetry/dt=2026-07-01.json").read_text(encoding="utf-8"))
    assert manifest["rows_quarantined"] == 1 and manifest["checksum"] == result.checksum


def test_empty_file_is_recorded_and_skipped_next_time(tmp_path: Path) -> None:
    landing, lake = tmp_path / "landing", tmp_path / "lake"
    _write(landing, "shipments", "2026-07-01", "")
    assert ingest(landing, lake)[0].status == "empty"
    assert ingest(landing, lake)[0].status == "unchanged"


def test_rejects_unknown_source_and_bad_partition(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="sem contrato"):
        ingest_partition(_write(tmp_path, "payroll", "2026-07-01", "a\n1\n"), tmp_path / "lake")
    bad = tmp_path / "contracts" / "2026-07-01" / "extract.csv"
    bad.parent.mkdir(parents=True)
    bad.write_text(CONTRACTS_HEADER, encoding="utf-8")
    with pytest.raises(ValueError, match="partição"):
        ingest_partition(bad, tmp_path / "lake")


def test_discover_ignores_unknown_folders(tmp_path: Path) -> None:
    _write(tmp_path, "contracts", "2026-07-01", CONTRACTS_HEADER)
    _write(tmp_path, "contracts", "latest", CONTRACTS_HEADER)
    _write(tmp_path, "unknown", "2026-07-01", "x\n")
    assert [p.parent.name for p in discover(tmp_path)] == ["dt=2026-07-01"]
    assert not any(path.name.startswith(".") for path in tmp_path.iterdir())
