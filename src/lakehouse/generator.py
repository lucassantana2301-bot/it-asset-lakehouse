"""Gerador determinístico dos extratos diários dos sistemas de origem da Locabit (empresa fictícia).

Simula cinco sistemas que entregam arquivos na zona de pouso (landing), um por dia:

- ERP: clientes e contratos (CSV, foto completa do dia);
- gestão de ativos: notebooks, desktops e monitores (CSV, foto completa do dia);
- agente de telemetria dos equipamentos (JSONL, eventos do dia);
- service desk: chamados (JSONL, chamados abertos ou alterados no dia);
- logística reversa: envios e coletas (CSV, movimentações do dia).

Os problemas que um pipeline real enfrenta são injetados de propósito e de forma reprodutível:
eventos duplicados, eventos que chegam no arquivo do dia seguinte, leituras fora da faixa física,
equipamentos desconhecidos e chaves nulas. A ingestão e o dbt precisam lidar com cada um deles.
"""

from __future__ import annotations

import csv
import json
import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

SEGMENTS = (("SMB", 0.55, 5, 20), ("Mid-Market", 0.33, 20, 60), ("Enterprise", 0.12, 60, 180))
STATES = ("SP", "SP", "SP", "RJ", "MG", "PR", "RS", "SC", "BA", "PE", "DF", "GO")
MODELS = {
    "notebook": (
        ("Dell Latitude 5450", 5900.0, 189.0),
        ("Lenovo ThinkPad E14", 5400.0, 175.0),
        ("HP ProBook 440", 4800.0, 159.0),
    ),
    "desktop": (("Dell OptiPlex 7010", 4200.0, 139.0), ("Lenovo ThinkCentre M70", 3900.0, 129.0)),
    "monitor": (("Dell P2425", 1300.0, 45.0), ("LG 24MP400", 900.0, 35.0)),
}
CATEGORY_MIX = (("notebook", 0.62), ("desktop", 0.18), ("monitor", 0.20))
TICKET_CATEGORIES = (("hardware", 0.5), ("software", 0.35), ("logistics", 0.15))
PRIORITIES = (("P1", 0.05), ("P2", 0.2), ("P3", 0.5), ("P4", 0.25))
FIRST_NAMES = (
    "Atlas",
    "Boreal",
    "Cobalto",
    "Delta",
    "Eixo",
    "Fluxo",
    "Granito",
    "Horizonte",
    "Índigo",
    "Jade",
    "Kairós",
    "Lumen",
    "Magma",
    "Norte",
    "Órbita",
    "Prisma",
    "Quartzo",
    "Rumo",
    "Safira",
    "Trama",
)
SUFFIXES = ("Tecnologia", "Logística", "Saúde", "Engenharia", "Varejo", "Educação", "Consultoria", "Alimentos")


@dataclass
class Customer:
    customer_id: str
    cnpj: str
    name: str
    segment: str
    state: str
    created_at: date


@dataclass
class Contract:
    contract_id: str
    customer_id: str
    start_date: date
    end_date: date
    seats: int
    monthly_fee: float
    status: str = "active"
    updated_at: date = date.min


@dataclass
class Asset:
    asset_id: str
    serial_number: str
    category: str
    model: str
    purchase_date: date
    purchase_cost: float
    unit_fee: float
    status: str = "in_stock"
    contract_id: str | None = None
    battery_health: float = 100.0
    degradation: float = 0.0
    cpu_baseline: float = 35.0
    disk_free: float = 60.0
    silent: bool = False
    updated_at: date = date.min


@dataclass
class SourceDay:
    """Linhas de cada fonte entregues num dia."""

    customers: list[dict[str, Any]] = field(default_factory=list)
    contracts: list[dict[str, Any]] = field(default_factory=list)
    assets: list[dict[str, Any]] = field(default_factory=list)
    telemetry: list[dict[str, Any]] = field(default_factory=list)
    tickets: list[dict[str, Any]] = field(default_factory=list)
    shipments: list[dict[str, Any]] = field(default_factory=list)


def _cnpj(rng: random.Random) -> str:
    """CNPJ com dígitos verificadores válidos (número fictício)."""
    base = [rng.randint(0, 9) for _ in range(8)] + [0, 0, 0, 1]
    for weights in ((5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2), (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)):
        total = sum(d * w for d, w in zip(base, weights, strict=False))
        rest = total % 11
        base.append(0 if rest < 2 else 11 - rest)
    digits = "".join(map(str, base))
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def _pick(rng: random.Random, options: tuple[tuple[Any, ...], ...]) -> Any:
    return rng.choices([o[0] for o in options], weights=[o[1] for o in options], k=1)[0]


class LocabitSimulator:
    """Simula o negócio dia a dia; o mesmo seed produz exatamente os mesmos arquivos."""

    def __init__(self, start: date, days: int, seed: int = 42) -> None:
        if days < 1:
            raise ValueError("days precisa ser >= 1")
        self.start = start
        self.days = days
        self.rng = random.Random(seed)
        self.customers: list[Customer] = []
        self.contracts: list[Contract] = []
        self.assets: list[Asset] = []
        self.open_tickets: dict[str, dict[str, Any]] = {}
        self.pending_shipments: dict[str, dict[str, Any]] = {}
        self.late_telemetry: list[dict[str, Any]] = []
        self._seq: dict[str, int] = {}

    def _next(self, prefix: str, width: int = 6) -> str:
        self._seq[prefix] = self._seq.get(prefix, 0) + 1
        return f"{prefix}-{self._seq[prefix]:0{width}d}"

    # --- frota e clientes -------------------------------------------------------------------
    def _buy_assets(self, day: date, category: str, quantity: int) -> list[Asset]:
        bought = []
        for _ in range(quantity):
            model, cost, fee = self.rng.choice(MODELS[category])
            asset = Asset(
                asset_id=self._next("AST"),
                serial_number=f"SN{self.rng.randrange(16**10):010X}",
                category=category,
                model=model,
                purchase_date=day,
                purchase_cost=round(cost * self.rng.uniform(0.95, 1.05), 2),
                unit_fee=fee,
                # ~8% das baterias degradam bem mais rápido (lote ruim): viram "trocar_bateria" no mart.
                degradation=(
                    (self.rng.uniform(0.18, 0.35) if self.rng.random() < 0.08 else self.rng.uniform(0.01, 0.05))
                    if category == "notebook"
                    else 0.0
                ),
                cpu_baseline=self.rng.choice((self.rng.uniform(3, 9), *(self.rng.uniform(20, 55) for _ in range(6)))),
                disk_free=self.rng.uniform(14, 80),
                updated_at=day,
            )
            self.assets.append(asset)
            bought.append(asset)
        return bought

    def _allocate(self, day: date, contract: Contract, quantity: int) -> None:
        category = _pick(self.rng, CATEGORY_MIX)
        stock = [a for a in self.assets if a.status == "in_stock" and a.category == category]
        if len(stock) < quantity:
            stock += self._buy_assets(day, category, quantity - len(stock))
        for asset in stock[:quantity]:
            asset.status, asset.contract_id, asset.updated_at = "deployed", contract.contract_id, day
            self._ship(day, asset, "outbound")

    def _new_customer(self, day: date) -> None:
        segment, _, lo, hi = self.rng.choices(SEGMENTS, weights=[s[1] for s in SEGMENTS], k=1)[0]
        customer = Customer(
            customer_id=self._next("CUS", 5),
            cnpj=_cnpj(self.rng),
            name=f"{self.rng.choice(FIRST_NAMES)} {self.rng.choice(SUFFIXES)} Ltda",
            segment=segment,
            state=self.rng.choice(STATES),
            created_at=day,
        )
        self.customers.append(customer)
        seats = self.rng.randint(lo, hi)
        contract = Contract(
            contract_id=self._next("CTR", 5),
            customer_id=customer.customer_id,
            start_date=day,
            end_date=day + timedelta(days=self.rng.choice((365, 730, 1095))),
            seats=seats,
            monthly_fee=0.0,
            updated_at=day,
        )
        self.contracts.append(contract)
        self._allocate(day, contract, seats)
        self._reprice(contract)

    def _reprice(self, contract: Contract) -> None:
        fees = [a.unit_fee for a in self.assets if a.contract_id == contract.contract_id and a.status == "deployed"]
        contract.seats = len(fees)
        contract.monthly_fee = round(sum(fees), 2)

    def _contract_events(self, day: date) -> None:
        for contract in self.contracts:
            if contract.status != "active":
                continue
            roll = self.rng.random()
            if roll < 0.004:  # expansão
                self._allocate(day, contract, max(1, int(contract.seats * self.rng.uniform(0.05, 0.25))))
                self._reprice(contract)
                contract.updated_at = day
            elif roll < 0.006:  # redução: devolve parte dos equipamentos
                deployed = [a for a in self.assets if a.contract_id == contract.contract_id and a.status == "deployed"]
                for asset in deployed[: max(1, int(len(deployed) * self.rng.uniform(0.1, 0.3)))]:
                    self._request_return(day, asset)
                self._reprice(contract)
                contract.updated_at = day
            elif roll < 0.0072 or day >= contract.end_date:  # cancelamento ou fim de vigência
                contract.status = "cancelled" if day < contract.end_date else "ended"
                contract.updated_at = day
                for asset in [
                    a for a in self.assets if a.contract_id == contract.contract_id and a.status == "deployed"
                ]:
                    self._request_return(day, asset)
                self._reprice(contract)

    # --- logística reversa -----------------------------------------------------------------
    def _ship(self, day: date, asset: Asset, direction: str) -> None:
        shipment: dict[str, Any] = {
            "shipment_id": self._next("SHP", 7),
            "asset_id": asset.asset_id,
            "contract_id": asset.contract_id,
            "direction": direction,
            "requested_at": datetime.combine(day, time(self.rng.randint(8, 17), self.rng.randint(0, 59))),
            "collected_at": None,
            "received_at": None,
            "condition": None,
            "_collect_in": self.rng.choices((1, 2, 3, 5, 8), weights=(30, 30, 20, 15, 5), k=1)[0],
            "_receive_in": self.rng.choice((1, 2, 3)),
        }
        self.pending_shipments[shipment["shipment_id"]] = shipment

    def _request_return(self, day: date, asset: Asset) -> None:
        asset.status, asset.updated_at = "returning", day
        self._ship(day, asset, "return")

    def _advance_shipments(self, day: date, out: SourceDay) -> None:
        for shipment_id in list(self.pending_shipments):
            s = self.pending_shipments[shipment_id]
            requested: datetime = s["requested_at"]
            changed = requested.date() == day
            if s["collected_at"] is None and (day - requested.date()).days >= s["_collect_in"]:
                s["collected_at"] = datetime.combine(day, time(self.rng.randint(9, 18), self.rng.randint(0, 59)))
                changed = True
            collected: datetime | None = s["collected_at"]
            if collected is not None and s["received_at"] is None and (day - collected.date()).days >= s["_receive_in"]:
                s["received_at"] = datetime.combine(day, time(self.rng.randint(8, 18), self.rng.randint(0, 59)))
                s["condition"] = self.rng.choices(("ok", "damaged", "missing_parts"), weights=(88, 8, 4), k=1)[0]
                changed = True
                if s["direction"] == "return":
                    asset = next(a for a in self.assets if a.asset_id == s["asset_id"])
                    asset.contract_id, asset.updated_at = None, day
                    asset.status = "in_repair" if s["condition"] != "ok" else "in_stock"
                del self.pending_shipments[shipment_id]
            if changed:
                out.shipments.append({k: v for k, v in s.items() if not k.startswith("_")})
        for asset in self.assets:  # reparo leva alguns dias
            if asset.status == "in_repair" and self.rng.random() < 0.2:
                asset.status, asset.updated_at = ("retired", day) if self.rng.random() < 0.15 else ("in_stock", day)

    # --- telemetria e chamados ----------------------------------------------------------------
    def _telemetry(self, day: date, out: SourceDay) -> None:
        out.telemetry.extend(self.late_telemetry)  # eventos atrasados do dia anterior
        self.late_telemetry = []
        weekday = day.weekday() < 5
        for asset in self.assets:
            if asset.status != "deployed" or asset.category == "monitor":
                continue
            if asset.category == "notebook":
                asset.battery_health = max(35.0, asset.battery_health - asset.degradation * self.rng.uniform(0.5, 1.5))
            asset.disk_free = min(90.0, max(2.0, asset.disk_free - self.rng.uniform(-0.3, 0.45)))
            if not asset.silent and self.rng.random() < 0.0004:
                asset.silent = True  # agente parou de reportar: aparece como "investigar_sem_sinal"
            if asset.silent:
                continue
            for hour in (9, 13, 17) if weekday else (14,):
                if self.rng.random() < 0.12:  # equipamento desligado ou sem rede
                    continue
                event = {
                    "event_id": self._next("EVT", 9),
                    "asset_id": asset.asset_id,
                    "event_ts": datetime.combine(day, time(hour, self.rng.randint(0, 59))).isoformat(),
                    "cpu_util_pct": round(
                        min(100.0, max(0.0, self.rng.gauss(asset.cpu_baseline * (1 if weekday else 0.3), 8))), 1
                    ),
                    "disk_free_pct": round(asset.disk_free + self.rng.uniform(-1.5, 1.5), 1),
                    "battery_health_pct": round(asset.battery_health, 1) if asset.category == "notebook" else None,
                    "agent_version": self.rng.choice(("3.4.1", "3.4.1", "3.5.0")),
                }
                roll = self.rng.random()
                if roll < 0.002:
                    event["cpu_util_pct"] = round(self.rng.uniform(140, 400), 1)  # leitura impossível
                elif roll < 0.003:
                    event["asset_id"] = None  # chave nula
                if roll > 0.994:
                    out.telemetry.append(dict(event))  # duplicata (reenvio do agente)
                if roll > 0.985 and roll <= 0.994:
                    self.late_telemetry.append(event)  # chega no arquivo de amanhã
                else:
                    out.telemetry.append(event)
        if self.rng.random() < 0.3:  # equipamento fora do inventário (agente instalado à mão)
            out.telemetry.append(
                {
                    "event_id": self._next("EVT", 9),
                    "asset_id": "AST-UNKNOWN",
                    "event_ts": f"{day}T12:00:00",
                    "cpu_util_pct": 20.0,
                    "disk_free_pct": 50.0,
                    "battery_health_pct": None,
                    "agent_version": "3.5.0",
                }
            )

    def _tickets(self, day: date, out: SourceDay) -> None:
        deployed = [a for a in self.assets if a.status == "deployed"]
        by_contract = {c.contract_id: c for c in self.contracts}
        for _ in range(self.rng.randint(len(deployed) // 120, len(deployed) // 70 + 1)):
            asset = self.rng.choice(deployed)
            priority = _pick(self.rng, PRIORITIES)
            ticket = {
                "ticket_id": self._next("TCK", 6),
                "asset_id": asset.asset_id,
                "customer_id": by_contract[asset.contract_id].customer_id if asset.contract_id else None,
                "priority": priority,
                "category": _pick(self.rng, TICKET_CATEGORIES),
                "status": "open",
                "opened_at": datetime.combine(day, time(self.rng.randint(7, 20), self.rng.randint(0, 59))).isoformat(),
                "closed_at": None,
                "_hours": self.rng.expovariate(1 / {"P1": 2, "P2": 5, "P3": 14, "P4": 40}[priority]),
            }
            self.open_tickets[ticket["ticket_id"]] = ticket
            out.tickets.append({k: v for k, v in ticket.items() if not k.startswith("_")})
        end_of_day = datetime.combine(day, time(23, 59))
        for ticket_id in list(self.open_tickets):
            t = self.open_tickets[ticket_id]
            closes_at = datetime.fromisoformat(t["opened_at"]) + timedelta(hours=t["_hours"])
            if closes_at <= end_of_day:
                t["status"], t["closed_at"] = "closed", closes_at.replace(microsecond=0).isoformat()
                out.tickets.append({k: v for k, v in t.items() if not k.startswith("_")})
                del self.open_tickets[ticket_id]

    # --- execução ---------------------------------------------------------------------------
    def run(self) -> dict[date, SourceDay]:
        days: dict[date, SourceDay] = {}
        self._buy_assets(self.start, "notebook", 120)
        for _ in range(15):
            self._new_customer(self.start)
        for offset in range(self.days):
            day = self.start + timedelta(days=offset)
            out = SourceDay()
            if offset > 0:
                for _ in range(self.rng.choices((0, 1, 2), weights=(80, 17, 3), k=1)[0]):
                    self._new_customer(day)
                self._contract_events(day)
            self._advance_shipments(day, out)
            self._telemetry(day, out)
            self._tickets(day, out)
            out.customers = [vars(c).copy() for c in self.customers]
            out.contracts = [vars(c).copy() for c in self.contracts]
            out.assets = [
                {
                    k: v
                    for k, v in vars(a).items()
                    if k not in {"battery_health", "degradation", "unit_fee", "cpu_baseline", "disk_free", "silent"}
                }
                for a in self.assets
            ]
            if offset % 17 == 5 and out.contracts:  # registro com chave nula vindo do ERP
                out.contracts.append({**out.contracts[0], "contract_id": None})
            days[day] = out
        return days


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return value


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows({k: _serialize(v) for k, v in row.items()} for row in rows)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps({k: _serialize(v) for k, v in row.items()}, ensure_ascii=False) + "\n")


FILE_FORMATS = {
    "customers": "csv",
    "contracts": "csv",
    "assets": "csv",
    "telemetry": "jsonl",
    "tickets": "jsonl",
    "shipments": "csv",
}


def write_landing(landing: Path, start: date, days: int, seed: int = 42) -> list[Path]:
    """Gera os extratos diários em landing/<fonte>/dt=AAAA-MM-DD/extract.<csv|jsonl>."""
    written: list[Path] = []
    for day, out in LocabitSimulator(start, days, seed).run().items():
        for source, fmt in FILE_FORMATS.items():
            path = landing / source / f"dt={day.isoformat()}" / f"extract.{fmt}"
            rows: list[dict[str, Any]] = getattr(out, source)
            (_write_csv if fmt == "csv" else _write_jsonl)(path, rows)
            written.append(path)
    return written
