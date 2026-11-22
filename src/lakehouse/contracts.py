"""Contratos de dados das fontes: colunas, tipos e regras que cada linha precisa cumprir para entrar no bronze.

Um contrato explícito por fonte é o que permite à ingestão separar "dado ruim" de "pipeline quebrado":
linhas que violam o contrato vão para a quarentena com o motivo, e o restante segue.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Column:
    name: str
    type: str
    """Tipo DuckDB de destino. A leitura é sempre em VARCHAR e a conversão usa TRY_CAST."""


@dataclass(frozen=True, slots=True)
class Rule:
    name: str
    predicate: str
    """Expressão SQL sobre as colunas já tipadas; NULL conta como aprovado (regras de presença são separadas)."""


@dataclass(frozen=True, slots=True)
class SourceContract:
    name: str
    file_format: str  # "csv" ou "jsonl"
    key: str
    columns: tuple[Column, ...]
    required: tuple[str, ...] = ()
    rules: tuple[Rule, ...] = ()

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.columns)


def _in(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


CONTRACTS: dict[str, SourceContract] = {
    c.name: c
    for c in (
        SourceContract(
            name="customers",
            file_format="csv",
            key="customer_id",
            columns=(
                Column("customer_id", "VARCHAR"),
                Column("cnpj", "VARCHAR"),
                Column("name", "VARCHAR"),
                Column("segment", "VARCHAR"),
                Column("state", "VARCHAR"),
                Column("created_at", "DATE"),
            ),
            required=("cnpj", "segment"),
            rules=(
                Rule("cnpj_formato", r"regexp_full_match(cnpj, '\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}')"),
                Rule("segmento_valido", _in("segment", ("SMB", "Mid-Market", "Enterprise"))),
                Rule("uf_valida", "length(state) = 2"),
            ),
        ),
        SourceContract(
            name="contracts",
            file_format="csv",
            key="contract_id",
            columns=(
                Column("contract_id", "VARCHAR"),
                Column("customer_id", "VARCHAR"),
                Column("start_date", "DATE"),
                Column("end_date", "DATE"),
                Column("seats", "INTEGER"),
                Column("monthly_fee", "DECIMAL(14,2)"),
                Column("status", "VARCHAR"),
                Column("updated_at", "DATE"),
            ),
            required=("customer_id", "start_date", "monthly_fee", "status"),
            rules=(
                Rule("mensalidade_nao_negativa", "monthly_fee >= 0"),
                Rule("vigencia_coerente", "end_date >= start_date"),
                Rule("status_valido", _in("status", ("active", "cancelled", "ended"))),
            ),
        ),
        SourceContract(
            name="assets",
            file_format="csv",
            key="asset_id",
            columns=(
                Column("asset_id", "VARCHAR"),
                Column("serial_number", "VARCHAR"),
                Column("category", "VARCHAR"),
                Column("model", "VARCHAR"),
                Column("purchase_date", "DATE"),
                Column("purchase_cost", "DECIMAL(14,2)"),
                Column("status", "VARCHAR"),
                Column("contract_id", "VARCHAR"),
                Column("updated_at", "DATE"),
            ),
            required=("serial_number", "category", "status"),
            rules=(
                Rule("custo_positivo", "purchase_cost > 0"),
                Rule("categoria_valida", _in("category", ("notebook", "desktop", "monitor"))),
                Rule(
                    "status_valido",
                    _in("status", ("in_stock", "deployed", "returning", "in_repair", "retired")),
                ),
            ),
        ),
        SourceContract(
            name="telemetry",
            file_format="jsonl",
            key="event_id",
            columns=(
                Column("event_id", "VARCHAR"),
                Column("asset_id", "VARCHAR"),
                Column("event_ts", "TIMESTAMP"),
                Column("cpu_util_pct", "DOUBLE"),
                Column("disk_free_pct", "DOUBLE"),
                Column("battery_health_pct", "DOUBLE"),
                Column("agent_version", "VARCHAR"),
            ),
            required=("asset_id", "event_ts"),
            rules=(
                Rule("cpu_entre_0_e_100", "cpu_util_pct BETWEEN 0 AND 100"),
                Rule("disco_entre_0_e_100", "disk_free_pct BETWEEN 0 AND 100"),
                Rule("bateria_entre_0_e_100", "battery_health_pct BETWEEN 0 AND 100"),
            ),
        ),
        SourceContract(
            name="tickets",
            file_format="jsonl",
            key="ticket_id",
            columns=(
                Column("ticket_id", "VARCHAR"),
                Column("asset_id", "VARCHAR"),
                Column("customer_id", "VARCHAR"),
                Column("priority", "VARCHAR"),
                Column("category", "VARCHAR"),
                Column("status", "VARCHAR"),
                Column("opened_at", "TIMESTAMP"),
                Column("closed_at", "TIMESTAMP"),
            ),
            required=("priority", "status", "opened_at"),
            rules=(
                Rule("prioridade_valida", _in("priority", ("P1", "P2", "P3", "P4"))),
                Rule("status_valido", _in("status", ("open", "closed"))),
                Rule("fechamento_apos_abertura", "closed_at >= opened_at"),
            ),
        ),
        SourceContract(
            name="shipments",
            file_format="csv",
            key="shipment_id",
            columns=(
                Column("shipment_id", "VARCHAR"),
                Column("asset_id", "VARCHAR"),
                Column("contract_id", "VARCHAR"),
                Column("direction", "VARCHAR"),
                Column("requested_at", "TIMESTAMP"),
                Column("collected_at", "TIMESTAMP"),
                Column("received_at", "TIMESTAMP"),
                Column("condition", "VARCHAR"),
            ),
            required=("asset_id", "direction", "requested_at"),
            rules=(
                Rule("direcao_valida", _in("direction", ("outbound", "return"))),
                Rule("coleta_apos_pedido", "collected_at >= requested_at"),
                Rule("recebimento_apos_coleta", "received_at >= collected_at"),
                Rule("condicao_valida", _in("condition", ("ok", "damaged", "missing_parts"))),
            ),
        ),
    )
}
