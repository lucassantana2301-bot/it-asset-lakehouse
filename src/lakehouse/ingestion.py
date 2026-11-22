"""Ingestão landing → bronze.

Para cada arquivo de origem (uma partição `dt=AAAA-MM-DD` por fonte):

1. calcula o SHA-256 do arquivo e pula a partição se ela já foi ingerida com o mesmo conteúdo;
2. lê tudo como texto e converte cada coluna com TRY_CAST, registrando falhas de tipo;
3. aplica as regras do contrato; linhas reprovadas vão para a quarentena com a lista de motivos;
4. grava o Parquet (zstd) da partição em um arquivo temporário e troca de forma atômica,
   então reprocessar um dia substitui a partição inteira e nunca duplica dados;
5. grava o manifesto da partição com contagens e motivos, usado pelas checagens de qualidade.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from .contracts import CONTRACTS, SourceContract

PARTITION_RE = re.compile(r"^dt=(\d{4}-\d{2}-\d{2})$")


@dataclass(frozen=True, slots=True)
class PartitionResult:
    source: str
    dt: str
    status: str  # "ingested" | "unchanged" | "empty"
    rows_read: int = 0
    rows_valid: int = 0
    rows_quarantined: int = 0
    reasons: dict[str, int] = field(default_factory=dict)
    checksum: str = ""

    @property
    def quarantine_rate(self) -> float:
        return self.rows_quarantined / self.rows_read if self.rows_read else 0.0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _reader(contract: SourceContract, path: Path) -> str:
    columns = "{" + ", ".join(f"{_sql_literal(c)}: 'VARCHAR'" for c in contract.column_names) + "}"
    if contract.file_format == "csv":
        return f"read_csv({_sql_literal(str(path))}, header = true, columns = {columns}, quote = '\"', escape = '\"')"
    return f"read_json({_sql_literal(str(path))}, format = 'newline_delimited', columns = {columns})"


def _checks_sql(contract: SourceContract) -> str:
    """Lista de motivos de reprovação por linha (vazia quando a linha é válida)."""
    checks: list[str] = []
    for column in contract.columns:
        # Valor presente no arquivo que não converte para o tipo do contrato.
        checks.append(
            f"CASE WHEN _raw_{column.name} IS NOT NULL AND {column.name} IS NULL THEN 'tipo_invalido:{column.name}' END"
        )
    for name in (contract.key, *contract.required):
        checks.append(f"CASE WHEN {name} IS NULL THEN 'obrigatorio:{name}' END")
    for rule in contract.rules:
        checks.append(f"CASE WHEN NOT coalesce(({rule.predicate}), true) THEN 'regra:{rule.name}' END")
    return "list_filter([" + ", ".join(checks) + "], lambda x: x IS NOT NULL)"


def _write_parquet(con: duckdb.DuckDBPyConnection, query: str, target: Path) -> None:
    """Escrita atômica: grava ao lado e renomeia, para um leitor nunca ver Parquet pela metade."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp")
    con.execute(f"COPY ({query}) TO {_sql_literal(str(tmp))} (FORMAT parquet, COMPRESSION zstd)")
    tmp.replace(target)


def ingest_partition(source_file: Path, lake: Path, *, force: bool = False) -> PartitionResult:
    source = source_file.parent.parent.name
    contract = CONTRACTS.get(source)
    if contract is None:
        raise ValueError(f"fonte sem contrato: {source}")
    match = PARTITION_RE.match(source_file.parent.name)
    if not match:
        raise ValueError(f"partição fora do padrão dt=AAAA-MM-DD: {source_file.parent}")
    dt = match.group(1)

    bronze_file = lake / "bronze" / source / f"dt={dt}" / "data.parquet"
    quarantine_file = lake / "quarantine" / source / f"dt={dt}" / "data.parquet"
    manifest_file = lake / "_manifests" / source / f"dt={dt}.json"
    checksum = _sha256(source_file)

    if not force and manifest_file.exists():
        previous = json.loads(manifest_file.read_text(encoding="utf-8"))
        same_content = previous.get("checksum") == checksum
        if same_content and (bronze_file.exists() or previous.get("status") == "empty"):
            return PartitionResult(source, dt, "unchanged", checksum=checksum)

    if source_file.stat().st_size == 0:
        result = PartitionResult(source, dt, "empty", checksum=checksum)
        for stale in (bronze_file, quarantine_file):
            stale.unlink(missing_ok=True)
        _write_manifest(manifest_file, result)
        return result

    ingested_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    typed_cols = ", ".join(f"TRY_CAST(nullif(trim({c.name}), '') AS {c.type}) AS {c.name}" for c in contract.columns)
    raw_cols = ", ".join(f"nullif(trim({c}), '') AS _raw_{c}" for c in contract.column_names)
    con = duckdb.connect()
    try:
        con.execute(
            f"CREATE TEMP TABLE raw AS SELECT row_number() OVER () AS _line, * FROM {_reader(contract, source_file)}"
        )
        con.execute(
            f"""
            CREATE TEMP TABLE checked AS
            WITH typed AS (SELECT _line, {typed_cols}, {raw_cols} FROM raw)
            SELECT *, {_checks_sql(contract)} AS _errors FROM typed
            """
        )
        rows_read = con.execute("SELECT count(*) FROM raw").fetchone()[0]  # type: ignore[index]
        valid_cols = ", ".join(contract.column_names)
        lineage = f"{_sql_literal(dt)}::DATE AS _partition_dt, {_sql_literal(ingested_at)}::TIMESTAMP AS _ingested_at"
        _write_parquet(con, f"SELECT {valid_cols}, {lineage} FROM checked WHERE len(_errors) = 0", bronze_file)

        reasons = dict(
            con.execute(
                "SELECT split_part(e, ':', 1) || ':' || split_part(e, ':', 2), count(*) "
                "FROM (SELECT unnest(_errors) AS e FROM checked) GROUP BY 1 ORDER BY 1"
            ).fetchall()
        )
        quarantined = con.execute("SELECT count(*) FROM checked WHERE len(_errors) > 0").fetchone()[0]  # type: ignore[index]
        if quarantined:
            raw_select = ", ".join(f"_raw_{c} AS {c}" for c in contract.column_names)
            _write_parquet(
                con,
                f"SELECT _line, {raw_select}, _errors, {lineage} FROM checked WHERE len(_errors) > 0",
                quarantine_file,
            )
        else:
            quarantine_file.unlink(missing_ok=True)
    finally:
        con.close()

    result = PartitionResult(source, dt, "ingested", rows_read, rows_read - quarantined, quarantined, reasons, checksum)
    _write_manifest(manifest_file, result, ingested_at)
    return result


def _write_manifest(path: Path, result: PartitionResult, ingested_at: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(result) | {"ingested_at": ingested_at or datetime.now(UTC).replace(microsecond=0).isoformat()}
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def discover(landing: Path, sources: Iterable[str] | None = None) -> list[Path]:
    wanted = set(sources) if sources else set(CONTRACTS)
    files = [
        path
        for path in landing.glob("*/dt=*/extract.*")
        if path.parent.parent.name in wanted and PARTITION_RE.match(path.parent.name)
    ]
    return sorted(files)


def ingest(
    landing: Path, lake: Path, *, sources: Iterable[str] | None = None, force: bool = False
) -> list[PartitionResult]:
    return [ingest_partition(path, lake, force=force) for path in discover(landing, sources)]
