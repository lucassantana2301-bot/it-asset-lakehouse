from __future__ import annotations

from pathlib import Path

import pytest

from lakehouse.cli import main


@pytest.fixture
def paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name, folder in (
        ("LANDING_ROOT", "landing"),
        ("LAKE_ROOT", "lake"),
        ("SITE_ROOT", "site"),
        ("DBT_DUCKDB_PATH", "warehouse/locabit.duckdb"),
    ):
        monkeypatch.setenv(name, str(tmp_path / folder))
    return tmp_path


def test_generate_and_ingest(paths: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["generate", "--days", "4"]) == 0
    assert "24 arquivos" in capsys.readouterr().out
    assert main(["ingest"]) == 0
    out = capsys.readouterr().out
    assert "partições" in out and (paths / "lake" / "bronze" / "telemetry").is_dir()
    assert main(["ingest", "--source", "contracts"]) == 0
    assert "'unchanged': 4" in capsys.readouterr().out


def test_unknown_command_exits_with_usage_error() -> None:
    with pytest.raises(SystemExit) as error:
        main(["deploy"])
    assert error.value.code == 2
