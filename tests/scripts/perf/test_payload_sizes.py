"""`scripts/perf/payload_sizes.py`: the link estimate and the printed table (no server)."""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "perf" / "payload_sizes.py"
_spec = importlib.util.spec_from_file_location("perf_payload_sizes", SCRIPT)
assert _spec and _spec.loader
payload = importlib.util.module_from_spec(_spec)
sys.modules["perf_payload_sizes"] = payload
_spec.loader.exec_module(payload)


def test_link_seconds_is_a_round_trip_plus_the_bytes_at_link_speed() -> None:
    # 1.25 MB over 10 Mbit/s is one second, plus 0.28 s of round trip
    assert payload.link_seconds(1_250_000, 0.28, 10.0) == pytest.approx(1.28)


def test_render_totals_each_page_and_marks_an_error() -> None:
    sizes = [
        payload.OpSize("ideas", "IdeasPage", 4_700_000, 340_000, "gzip", 900.0),
        payload.OpSize("ideas", "Regime", 30_000, 8_000, "gzip", 20.0),
        payload.OpSize("edges", "EdgesPage", 0, 0, "error ReadTimeout", 0.0),
    ]
    text = payload.render(sizes, 280.0, 10.0)
    assert "| **ideas** | total | | **348.0 kB** |" in text
    assert "error ReadTimeout" in text
    assert "280 ms round trip, 10 Mbit/s" in text
