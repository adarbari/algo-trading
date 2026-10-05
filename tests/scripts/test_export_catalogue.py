"""`scripts/export_catalogue.py`: the web app's typed site feature names (ADR 0038) are fresh
(WEB 6: the web job has no Python, so this test is the freshness check for catalogue.ts)."""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "export_catalogue.py"
_spec = importlib.util.spec_from_file_location("export_catalogue", SCRIPT)
assert _spec and _spec.loader
export_catalogue = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(export_catalogue)


def test_committed_catalogue_is_up_to_date() -> None:
    assert export_catalogue.TARGET.read_text() == export_catalogue.catalogue_ts(), (
        "run scripts/export_catalogue.py and commit apps/web/src/shared/api/generated/catalogue.ts"
    )


def test_it_lists_every_kind_of_field_once() -> None:
    text = export_catalogue.catalogue_ts()
    assert "  'instrument.symbol',\n" in text
    assert "  'rollup.earnings@v1.next_earnings_date',\n" in text
    assert "  'feature.pct_from_high_52w',\n" in text
    assert text.count("'rollup.earnings@v1.next_earnings_date'") == 1


def test_check_and_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "catalogue.ts"
    monkeypatch.setattr(export_catalogue, "TARGET", target)
    monkeypatch.setattr(sys, "argv", ["export_catalogue.py", "--check"])
    assert export_catalogue.main() == 1 and "stale" in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["export_catalogue.py"])
    assert export_catalogue.main() == 0 and target.read_text() == export_catalogue.catalogue_ts()
    monkeypatch.setattr(sys, "argv", ["export_catalogue.py", "--check"])
    assert export_catalogue.main() == 0 and "up to date" in capsys.readouterr().out
