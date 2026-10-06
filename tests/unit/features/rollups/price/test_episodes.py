"""``episode_behaviour@v1``: beta and correlation against SPY, and each reference episode's
drawdown and recovery, on synthetic series with known falls (32-bit floats), including the
nulls (before ``known_from``, thin coverage, not recovered, bars that do not reach the
episode), a backfill equal to the per-session compute, and the episode constants against
``config/site/regime/episodes.toml``. The cost of one nightly session over a store sized up
to 2,000 instruments is the ``perf`` test (``make perf``, an idle machine) with a loose
ceiling in the default run, as in ``services/preview/test_performance.py``."""

import time
import tracemalloc
from datetime import date

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from algotrade.config.site.regime.episodes import load_episodes
from algotrade.core.time.calendar import sessions_between
from algotrade.features.framework.runner import compute_one, compute_sessions
from algotrade.features.rollups.price import episodes as ep
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.helpers.rollup_store import series, store, write_bars
from tests.helpers.stored_frames import write_reference

GROUP = ep.GROUP
COVID = ep.EPISODES[0]
F32 = 1e-6
SPY = "EQ:SPYID"


def row(frame: pd.DataFrame | None, iid: str) -> dict[str, object]:
    assert frame is not None
    return frame.set_index("instrument_id").loc[iid].to_dict()


def covid_closes(end: date, recover_after: int | None = 12, fall: float = 0.3) -> list[float]:
    """One close per session from the COVID window start to ``end``: 100 up to the peak, a
    straight fall of ``fall`` to the trough, then back to 100 ``recover_after`` sessions after
    the trough (``None``: it stays at the trough)."""
    days = sessions_between(COVID.first, max(end, COVID.trough))
    peak, trough = days.index(COVID.peak), days.index(COVID.trough)
    out = []
    for i in range(len(sessions_between(COVID.first, end))):
        if i <= peak:
            out.append(100.0)
        elif i <= trough:
            out.append(100.0 * (1 - fall * (i - peak) / (trough - peak)))
        elif recover_after is not None and i - trough >= recover_after:
            out.append(100.0)
        else:
            out.append(100.0 * (1 - fall) + 1e-3 * (i - trough))
    return out


def covid_store(end: date, **closes: list[float]) -> tuple:
    writer, reader = store()
    write_bars(writer, closes, end)
    return writer, reader


def test_drawdown_and_recovery_are_exact_on_a_known_fall() -> None:
    end = sessions_between(COVID.trough, date(2020, 6, 30))[30]
    _, reader = covid_store(
        end, **{"EQ:A": covid_closes(end), "EQ:STUCK": covid_closes(end, None, 0.2)}
    )
    frame = compute_one(reader, GROUP, end).frame
    a, stuck = row(frame, "EQ:A"), row(frame, "EQ:STUCK")
    assert a["dd_covid_2020"] == pytest.approx(-0.30, abs=F32)
    assert a["recovery_sessions_covid_2020"] == 12
    assert stuck["dd_covid_2020"] == pytest.approx(-0.20, abs=F32)
    assert pd.isna(stuck["recovery_sessions_covid_2020"])  # not yet recovered: null, not 0
    for column in ("dd_hikes_2022", "dd_tariffs_2025", "recovery_sessions_hikes_2022"):
        assert pd.isna(a[column])  # the bars do not reach those episodes


def test_recovery_counts_the_sessions_from_the_trough_and_zero_at_the_trough() -> None:
    end = sessions_between(COVID.trough, date(2020, 6, 30))[20]
    closes = covid_closes(end, recover_after=7)
    days = sessions_between(COVID.first, end)
    above = closes[:]  # EQ:UP is above its pre-episode high already at the trough
    above[days.index(COVID.trough)] = 101.0
    _, reader = covid_store(end, **{"EQ:A": closes, "EQ:UP": above})
    frame = compute_one(reader, GROUP, end).frame
    assert row(frame, "EQ:A")["recovery_sessions_covid_2020"] == 7
    assert row(frame, "EQ:UP")["recovery_sessions_covid_2020"] == 0


def test_a_new_high_before_the_peak_counts_in_the_pre_episode_high_and_the_drawdown() -> None:
    end = sessions_between(COVID.trough, date(2020, 6, 30))[30]
    closes = covid_closes(end, recover_after=12)
    days = sessions_between(COVID.first, end)
    closes[days.index(COVID.peak) - 2] = 120.0  # tops out two sessions before the index
    _, reader = covid_store(end, **{"EQ:A": closes})
    out = row(compute_one(reader, GROUP, end).frame, "EQ:A")
    assert out["dd_covid_2020"] == pytest.approx(70.0 / 120.0 - 1, abs=F32)
    assert pd.isna(out["recovery_sessions_covid_2020"])  # the 100 close never regains 120


def test_every_column_is_null_before_the_episodes_known_from() -> None:
    before = sessions_between(COVID.peak, COVID.trough)[-2]  # a session before the trough
    _, reader = covid_store(before, **{"EQ:A": covid_closes(before)})
    out = row(compute_one(reader, GROUP, before).frame, "EQ:A")
    assert pd.isna(out["dd_covid_2020"]) and pd.isna(out["recovery_sessions_covid_2020"])
    at = COVID.trough
    _, reader = covid_store(at, **{"EQ:A": covid_closes(at)})
    assert row(compute_one(reader, GROUP, at).frame, "EQ:A")["dd_covid_2020"] == pytest.approx(
        -0.30, abs=F32
    )  # known from the trough itself


def test_an_instrument_with_too_few_sessions_of_the_episode_is_null() -> None:
    end = sessions_between(COVID.trough, date(2020, 6, 30))[30]
    days = sessions_between(COVID.first, end)
    window = sessions_between(COVID.peak, COVID.trough)
    few = [days.index(d) for d in window[: len(window) // 2]]  # half of peak..trough missing
    one = [days.index(window[-3])]  # one missing bar is within the 80%
    writer, reader = store()
    write_bars(
        writer,
        {"EQ:THIN": covid_closes(end), "EQ:ONE": covid_closes(end)},
        end,
        skip={"EQ:THIN": few, "EQ:ONE": one},
    )
    frame = compute_one(reader, GROUP, end).frame
    thin, one_gap = row(frame, "EQ:THIN"), row(frame, "EQ:ONE")
    assert pd.isna(thin["dd_covid_2020"]) and pd.isna(thin["recovery_sessions_covid_2020"])
    assert one_gap["dd_covid_2020"] == pytest.approx(-0.30, abs=F32)


def test_a_young_listing_after_the_peak_is_null() -> None:
    end = sessions_between(COVID.trough, date(2020, 6, 30))[30]
    _, reader = covid_store(end, **{"EQ:A": covid_closes(end), "EQ:NEW": covid_closes(end)[40:]})
    out = row(compute_one(reader, GROUP, end).frame, "EQ:NEW")
    assert pd.isna(out["dd_covid_2020"])


def beta_store(days: int = 300) -> tuple:
    spy = series(days, seed=7)
    levered = 100.0 * (spy / spy[0]) ** 2  # log returns exactly twice SPY's
    writer, reader = store()
    sessions = write_bars(
        writer, {SPY: spy, "EQ:LEV": levered, "EQ:SHORT": levered[-150:], "EQ:FLAT": [5.0] * days}
    )
    write_reference(writer, sessions[0], {"SPY": SPY, "LEV": "EQ:LEV", "FLAT": "EQ:FLAT"})
    return writer, reader, sessions[-1]


def test_beta_of_a_two_times_levered_series_is_two_and_spy_is_one() -> None:
    _, reader, end = beta_store()
    frame = compute_one(reader, GROUP, end).frame
    lev, spy = row(frame, "EQ:LEV"), row(frame, SPY)
    assert lev["beta_252d"] == pytest.approx(2.0, abs=1e-5)
    assert lev["corr_252d"] == pytest.approx(1.0, abs=1e-6)
    assert spy["beta_252d"] == pytest.approx(1.0, abs=1e-6)


def test_beta_is_null_under_200_overlapping_returns_without_spy_or_a_flat_market() -> None:
    _, reader, end = beta_store()
    frame = compute_one(reader, GROUP, end).frame
    assert pd.isna(row(frame, "EQ:SHORT")["beta_252d"])  # 149 returns
    flat = row(frame, "EQ:FLAT")
    assert flat["beta_252d"] == 0.0 and pd.isna(flat["corr_252d"])  # no variance: no correlation
    writer, reader = store()  # no reference: no SPY
    write_bars(writer, {"EQ:A": series(300)})
    assert pd.isna(row(compute_one(reader, GROUP, date(2026, 10, 2)).frame, "EQ:A")["beta_252d"])


def test_beta_uses_only_sessions_where_both_returns_exist() -> None:
    writer, reader = store()
    spy = series(300, seed=7)
    levered = 100.0 * (spy / spy[0]) ** 2
    skip = list(range(100, 130))  # 30 sessions without a bar: ~60 returns lost
    sessions = write_bars(writer, {SPY: spy, "EQ:LEV": levered}, skip={"EQ:LEV": skip})
    write_reference(writer, sessions[0], {"SPY": SPY})
    out = row(compute_one(reader, GROUP, sessions[-1]).frame, "EQ:LEV")
    assert out["beta_252d"] == pytest.approx(2.0, abs=1e-5)  # the same slope on 195+ returns
    assert out["corr_252d"] == pytest.approx(1.0, abs=1e-6)


def test_a_backfill_equals_the_per_session_compute() -> None:
    end = sessions_between(COVID.trough, date(2020, 6, 30))[10]
    days = sessions_between(COVID.first, end)
    writer, reader = store()
    spy = series(len(days), seed=3)
    sessions = write_bars(
        writer,
        {SPY: spy, "EQ:A": covid_closes(end), "EQ:B": covid_closes(end, None, 0.2)},
        end,
    )
    write_reference(writer, sessions[0], {"SPY": SPY})
    wanted = days[-14:]  # sessions either side of the trough
    together = {r.session: r.frame for r in compute_sessions(reader, GROUP, wanted, chunk=5)}
    for session in wanted:
        assert_frame_equal(together[session], compute_one(reader, GROUP, session).frame)
    assert pd.isna(row(together[wanted[0]], "EQ:A")["dd_covid_2020"])  # before the trough
    assert row(together[wanted[-1]], "EQ:A")["dd_covid_2020"] == pytest.approx(-0.30, abs=F32)


def test_the_episode_constants_equal_episodes_toml() -> None:
    shipped = load_episodes(FileConfigStore(REPO_ROOT / "config"))
    for e in ep.EPISODES:
        listed = shipped.by_key(e.key)
        assert (e.peak, e.trough) == (listed.peak, listed.trough), e.key
        assert listed.known_from == e.trough  # a column is null before the trough
        assert e.first < e.peak < e.trough < e.last
        assert {f"dd_{e.key}", f"recovery_sessions_{e.key}"} <= set(GROUP.columns)
    assert {c for c in GROUP.columns if c.startswith(("dd_", "recovery_"))} == {
        f"{p}{e.key}" for e in ep.EPISODES for p in ("dd_", "recovery_sessions_")
    }
    assert len(set(ep.WINDOWS)) == len(ep.EPISODES)


# ------------------------------------------------------------------------------- the budget
N = 2_000  # instruments: a sixth of the stored universe (12.6k)
SESSION = date(2026, 10, 2)  # every episode window, from 2020-02-12 to now, is stored
# Strict budgets for one session over N instruments (measured: 1.2-1.7 s, 210 MB).
BUDGET = 2.5  # CPU seconds
MEMORY = 300e6  # bytes of peak allocation
LOOSE = 5.0  # the default run's ceiling multiple


def sized_store() -> tuple:
    """N instruments with a bar on every session from the first COVID window session to
    ``SESSION``: the beta window and all three episode windows are stored (1,700 sessions)."""
    writer, reader = store()
    days = sessions_between(COVID.first, SESSION)
    rng = np.random.default_rng(5)
    levels = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, (len(days), N)), axis=0))
    ids = [f"EQ:I{i}" for i in range(N)]
    for i, day in enumerate(days):
        rows = pd.DataFrame(
            {
                "instrument_id": ids,
                "ts": pd.Timestamp(day, tz="UTC") + pd.Timedelta(hours=20),
                "open": levels[i], "high": levels[i], "low": levels[i],
                "close": levels[i], "volume": 1000.0,
                "session_date": day, "knowledge_ts": pd.Timestamp(day, tz="UTC"),
                "source": "test", "run_id": "b",
            }
        )  # fmt: skip
        writer.write_table("bars/1d", day, f"bars-{day}", rows)
    write_reference(writer, days[0], {"SPY": ids[0]})
    return reader


def measure() -> tuple[float, float]:
    """(CPU seconds, peak bytes allocated) of one nightly session over the sized store."""
    reader = sized_store()
    compute_one(reader, GROUP, SESSION)  # warm the imports and caches
    started = time.process_time()
    result = compute_one(reader, GROUP, SESSION)
    seconds = time.process_time() - started
    assert result.frame is not None and len(result.frame) == N
    assert result.frame["dd_covid_2020"].notna().all()
    assert result.frame["dd_tariffs_2025"].notna().all()
    tracemalloc.start()
    try:
        compute_one(reader, GROUP, SESSION)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    return seconds, float(peak)


@pytest.mark.slow
def test_a_nightly_session_over_a_sized_store_has_a_ceiling() -> None:
    seconds, peak = measure()
    assert seconds <= BUDGET * LOOSE, f"{seconds:.2f}s (ceiling {BUDGET * LOOSE}s)"
    assert peak <= MEMORY * LOOSE, f"{peak / 1e6:.0f} MB (ceiling {MEMORY * LOOSE / 1e6:.0f} MB)"


@pytest.mark.perf
def test_a_nightly_session_meets_the_budget() -> None:
    seconds, peak = measure()
    assert seconds <= BUDGET, f"{seconds:.2f}s (budget {BUDGET}s)"
    assert peak <= MEMORY, f"{peak / 1e6:.0f} MB (budget {MEMORY / 1e6:.0f} MB)"
