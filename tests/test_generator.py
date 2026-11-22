from __future__ import annotations

import hashlib
import json
import random
import re
from datetime import date
from pathlib import Path

import pytest

from lakehouse.generator import LocabitSimulator, _cnpj, write_landing


def _digest(folder: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(folder.rglob("extract.*")):
        digest.update(path.relative_to(folder).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_same_seed_produces_identical_files(tmp_path: Path) -> None:
    write_landing(tmp_path / "a", date(2026, 7, 1), 6, seed=7)
    write_landing(tmp_path / "b", date(2026, 7, 1), 6, seed=7)
    write_landing(tmp_path / "c", date(2026, 7, 1), 6, seed=8)
    assert _digest(tmp_path / "a") == _digest(tmp_path / "b")
    assert _digest(tmp_path / "a") != _digest(tmp_path / "c")


def test_layout_is_one_partition_per_source_and_day(tmp_path: Path) -> None:
    files = write_landing(tmp_path, date(2026, 7, 1), 3)
    assert len(files) == 6 * 3
    assert all(re.fullmatch(r"dt=\d{4}-\d{2}-\d{2}", f.parent.name) for f in files)


def test_cnpj_check_digits_are_valid() -> None:
    def valid(cnpj: str) -> bool:
        digits = [int(d) for d in re.sub(r"\D", "", cnpj)]
        for size, weights in (
            (12, (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
            (13, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
        ):
            rest = sum(d * w for d, w in zip(digits[:size], weights, strict=True)) % 11
            if digits[size] != (0 if rest < 2 else 11 - rest):
                return False
        return True

    rng = random.Random(1)
    assert all(valid(_cnpj(rng)) for _ in range(200))


def test_simulation_injects_the_data_problems_the_pipeline_must_handle(tmp_path: Path) -> None:
    days = LocabitSimulator(date(2026, 7, 1), 40, seed=42).run()
    telemetry = [e for d in days.values() for e in d.telemetry]
    ids = [e["event_id"] for e in telemetry]
    assert len(ids) > len(set(ids)), "deveria haver eventos duplicados"
    assert any(e["asset_id"] is None for e in telemetry), "deveria haver chave nula"
    assert any(e["cpu_util_pct"] > 100 for e in telemetry), "deveria haver leitura fora da faixa"
    assert any(e["asset_id"] == "AST-UNKNOWN" for e in telemetry), "deveria haver equipamento fora do inventário"
    late = [
        (day, e)
        for day, d in days.items()
        for e in d.telemetry
        if e["asset_id"] and not e["event_ts"].startswith(str(day))
    ]
    assert late, "deveria haver evento chegando no arquivo do dia seguinte"


def test_rejects_invalid_window() -> None:
    with pytest.raises(ValueError, match="days"):
        LocabitSimulator(date(2026, 7, 1), 0)


def test_jsonl_is_valid_utf8_json(tmp_path: Path) -> None:
    write_landing(tmp_path, date(2026, 7, 1), 2)
    for path in tmp_path.glob("*/dt=*/extract.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            json.loads(line)
