"""The regime episode scorecard (docs/market-regime-plan.md section 4): does the regime model
warn about the reference crash episodes (``config/site/regime/episodes.toml``) early enough,
and how often does it cry wolf? Read-only, over what is stored (the market's regime and macro
rows through the read model's range read, ``services.read.instruments.series.load_series``);
the text is ``regime_report``.

- (a) **Dating.** Bear markets dated from the stored index levels (``IDX:SPX``, ``IDX:COMP`` in
  ``macro/series``, daily closes, the latest vintage) by ``quant.turning_points``: Pagan and
  Sossounov with the daily equivalents of the paper's monthly rules (``PS_DAILY``: an extreme
  of +/- 168 sessions, phases of 84 and cycles of 336 sessions, 8, 4 and 16 months of 21) and
  Lunde and Timmermann (20% both ways). Each episode is matched to the dated bear overlapping
  its peak-to-trough window the most; they agree when the peak and trough are within
  ``DATE_TOLERANCE`` sessions and the depth within ``DEPTH_TOLERANCE`` (the Nasdaq: depth
  only, its own window differs).
- (b) **Leads.** Per episode, when ``regime.macro_risk`` (``market_stress``) went to ``HIGH`` or
  above, in sessions from the peak (negative: before it): the start of the run of high sessions
  that holds on the peak (at most ``SEARCH_BEFORE`` sessions back), else the first high session
  after the peak up to the trough (a run that ended before the peak warned of nothing); the
  raw-label path from ``PATH_BEFORE`` sessions before the peak to the trough; and which revised
  series the macro score read through the ``lagged`` rule (no ALFRED vintage that early), from
  ``vintage_kind`` as of the macro crossing (else the peak). A score that never went high and
  is null (its coverage below the regime's ``min_coverage``) on every session from the search
  start to the trough is unknown for the episode: its highest coverage there is kept.
- (c) **False alarms.** Sessions labelled STRESS or CRISIS outside every episode window
  (``WINDOW_BEFORE`` sessions before the peak to ``WINDOW_AFTER`` after the trough), and the
  alarms they form (a run of consecutive flagged sessions is one alarm), per decade.
- (d) **Acceptance** (plan section 4): macro high at least ``MACRO_LEAD`` sessions before each
  recession bear's peak; stress high within ``STRESS_LAG`` sessions of each peak; fewer than one
  false CRISIS per ``CRISIS_YEARS`` years. An episode without stored regime rows is not graded,
  nor, for one score's line, an episode where that score is unknown (b); a line is PASS / FAIL
  over the graded episodes only, NO DATA when none is.
- (f) **Probit fit.** The bear-state probit (``bear_prob_6m``) fitted on the stored
  history: month-end sessions with ``curve_10y3m``, ``cpi_yoy`` and ``hy_oas`` known, ``y`` = the
  S&P 500 in a Pagan-Sossounov bear ``HORIZON`` index sessions later; the coefficients, the
  in-sample hit rate (p >= 0.5 against y) and the lines to paste into ``rollups.toml``.
- (g) **Per-indicator leads.** Each signal of the macro score (``regime.SIGNALS``, with the
  site's thresholds, from the stored inputs it reads), per episode: the first session it was on
  in the ``SEARCH_BEFORE`` sessions before the peak (else after it, up to the trough), and how
  many of those sessions before the peak it was on; per signal, its hit rate (on in the
  ``HIT_BEFORE`` sessions before a recession bear's peak) and its false alarms (runs on outside
  every episode window, ``SEARCH_BEFORE`` sessions before a recession bear's peak as a slow
  signal may lead by that much, ``WINDOW_BEFORE`` before a shock's; a run back on within
  ``MERGE_GAP`` sessions is the same alarm) per year it was known there. The evidence the
  macro tiers are set on (docs/market-regime-plan.md section 4).

Dating is ex post (a turn needs the history after it): it is the ground truth, never a signal.
"""

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from itertools import groupby

import numpy as np
import pandas as pd

from algotrade.config.site.regime.episodes import Episode
from algotrade.config.site.settings import load_rollup
from algotrade.config.user import UserContext
from algotrade.core.model.instruments import index_id, market_id
from algotrade.core.time.calendar import next_session, sessions_ending, sessions_to
from algotrade.data import StoreReader
from algotrade.data.macro.series import known_window, latest_vintages, stored_vintages
from algotrade.features.framework.declaration import FeatureGroup
from algotrade.features.rollups.market import indicators, macro, regime
from algotrade.quant.probit import ProbitFit, fit, predict
from algotrade.quant.turning_points import Phase, lunde_timmermann, pagan_sossounov
from algotrade.services.read.context import ConfigStore, NotFoundError, ReadContext, open_context
from algotrade.services.read.instruments.series import load_series

INDICES = ("SPX", "COMP")
PS_WINDOW, PS_MIN_PHASE, PS_MIN_CYCLE, PS_MIN_MOVE = 168, 84, 336, 0.20
LT_UP = LT_DOWN = 0.20
PS_DAILY = {"window": PS_WINDOW, "min_phase": PS_MIN_PHASE, "min_cycle": PS_MIN_CYCLE,
            "min_move": PS_MIN_MOVE}  # fmt: skip
LT_DAILY = {"up": LT_UP, "down": LT_DOWN}
DATE_TOLERANCE = 5  # sessions
DEPTH_TOLERANCE = 0.02  # 2 points of drawdown
HIGH = 50.0  # a score at or above this is high (the regime's macro_high / market_high)
SEARCH_BEFORE = 504  # sessions before a peak a crossing is looked for (two years)
PATH_BEFORE = 63  # the raw-label path starts this many sessions before the peak
WINDOW_BEFORE, WINDOW_AFTER = 63, 126  # an episode's window for false alarms
MACRO_LEAD = 63  # macro high at least this many sessions (3 months) before a recession peak
STRESS_LAG = 15  # stress high no later than this many sessions after each peak
CRISIS_YEARS = 3.0  # fewer than one false CRISIS alarm per this many years
SESSIONS_PER_YEAR = 252
HORIZON = 126  # sessions: bear_prob_6m's six months (config/site/features/regime.toml)
REGRESSORS = ("curve_10y3m", "cpi_yoy", "hy_oas")  # market_macro columns, coefficient order
MIN_PROBIT_MONTHS = 24
ALARMS = ("STRESS", "CRISIS")
REGIME_COLUMNS = ("label", "raw_label", "macro_risk", "market_stress", "macro_coverage",
                  "market_coverage")  # fmt: skip
COVERAGE = {"macro_risk": "macro_coverage", "market_stress": "market_coverage"}
US = market_id("US")
ALL_TIME = (date(1900, 1, 1), date(9999, 12, 31))
# The series the macro score reads (its signals' inputs), checked for the lagged rule.
SCORE_SERIES = ("T10Y3M", "BAMLH0A0HYM2", "EBP", "UNRATE", "IC4WSA", "NFCI", "DRTSCILM",
                "PERMIT", "FEDFUNDS", "CPIAUCSL")  # fmt: skip
NO_DATA = "no data: run the macro backfill"
HIT_BEFORE = 252  # sessions: a signal on within a year before a recession bear's peak is a hit
MERGE_GAP = 63  # sessions: a signal back on within a quarter continues the same alarm
BACKFILL = (
    "algotrade-ingest run macro --since 1970-01-01, then "
    "algotrade-ingest market-rollups --from <first session> --to <last session>"
)


@dataclass(frozen=True)
class History:
    """What the scorecard reads: index closes by date (``levels``: key -> series), the regime
    rows (``session_date`` + label and scores), the macro rows the probit reads, every stored
    vintage of the macro score's series, and each macro signal's verdict per session
    (``signals``: ``session_date`` + one column per signal, 1 on, 0 off, NaN unknown)."""

    levels: dict[str, pd.Series]
    regime: pd.DataFrame | None
    macro: pd.DataFrame | None
    vintages: pd.DataFrame
    signals: pd.DataFrame | None = None


@dataclass(frozen=True)
class Bear:
    peak: date
    trough: date
    depth: float  # trough / peak - 1


@dataclass(frozen=True)
class Match:
    index: str
    method: str
    episode: Episode
    dated: Bear | None
    peak_off: int | None
    trough_off: int | None
    reference_depth: float
    agree: bool


@dataclass(frozen=True)
class Lead:
    episode: Episode
    macro: int | None  # sessions from the peak to the first macro-high session (None: never)
    stress: int | None
    path: str
    lagged: tuple[str, ...]  # revised series the macro score read through the lagged rule
    # The score's highest coverage when it is unknown throughout the episode (not graded);
    # None when it is known on some session of it.
    macro_unknown: float | None = None
    stress_unknown: float | None = None


@dataclass(frozen=True)
class Alarms:
    by_decade: dict[int, tuple[int, int, int]]  # decade -> (sessions, alarms, CRISIS alarms)
    years: float  # labelled years


@dataclass(frozen=True)
class ProbitResult:
    fit: ProbitFit
    months: int
    hit_rate: float
    base_rate: float
    through: date  # the last month-end session of the sample: values up to it are in-sample


def _market_rows(
    ctx: ReadContext | None, group: FeatureGroup, columns: Sequence[str]
) -> pd.DataFrame | None:
    """The market's stored ``columns`` of ``group`` for every session up to the context's,
    through the read model's range read (``load_series``); ``None`` when none is stored."""
    if ctx is None:
        return None
    names = [group.feature(c).field for c in columns]
    series = load_series(ctx, [US], names, ALL_TIME[0], entity="market")[US]
    if not series.points:
        return None
    rows = [{"session_date": p.session, **dict(zip(columns, p.values, strict=True))}
            for p in series.points]  # fmt: skip
    frame = pd.DataFrame(rows, columns=["session_date", *columns])
    numeric = [c for c in columns if c not in ("label", "raw_label")]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="coerce")
    return frame


def _context(
    reader: StoreReader, configs: ConfigStore, user: UserContext, last: date | None
) -> ReadContext | None:
    """A read context for ``last`` (the newest index close; the latest session when None);
    ``None`` on a store with nothing to resolve a session from."""
    try:
        return open_context(reader, configs, user, requested=last)
    except NotFoundError:
        return None


def load_history(reader: StoreReader, configs: ConfigStore, user: UserContext) -> History:
    """Everything stored that the scorecard reads (empty parts when nothing is)."""
    ids = [index_id(k) for k in INDICES]
    closes = latest_vintages(stored_vintages(reader, ids), ALL_TIME[1])
    levels: dict[str, pd.Series] = {}
    for key, iid in zip(INDICES, ids, strict=True):
        part = closes[(closes["instrument_id"] == iid) & closes["value"].notna()]
        part = part[part["value"] > 0]
        if len(part):
            levels[key] = pd.Series(part["value"].to_numpy(float), index=list(part["obs_date"]))
    last = max((s.index[-1] for s in levels.values()), default=None)
    ctx = _context(reader, configs, user, last)
    vintages = stored_vintages(reader, [macro.ID[k] for k in SCORE_SERIES])
    reads = _signal_columns()
    macro_rows = _market_rows(ctx, macro.GROUP, [*REGRESSORS, *reads[macro.GROUP.key]])
    cards = _market_rows(ctx, indicators.GROUP, reads[indicators.GROUP.key])
    params = load_rollup(configs, regime.GROUP.key, regime.GROUP.params)
    return History(
        levels,
        _market_rows(ctx, regime.GROUP, REGIME_COLUMNS),
        macro_rows,
        vintages,
        signal_verdicts(macro_rows, cards, params),
    )


MACRO_SIGNALS = tuple(s for s in regime.SIGNALS if s.score == "macro")


def _signal_columns() -> dict[str, list[str]]:
    """The columns the macro signals read, by input group (beyond the probit's)."""
    reads = {r for s in MACRO_SIGNALS for r in s.reads}
    return {k: [f.name for f in g.features if f.key in reads and f.name not in REGRESSORS]
            for k, g in regime.GROUPS.items()}  # fmt: skip


def signal_verdicts(
    rows: pd.DataFrame | None, cards: pd.DataFrame | None, params: regime.Params
) -> pd.DataFrame | None:
    """Each macro signal's verdict per session from its stored inputs (``None``: none)."""
    parts = [f for f in (rows, cards) if f is not None]
    if not parts:
        return None
    merged = parts[0] if len(parts) == 1 else parts[0].merge(parts[1], "outer", "session_date")
    flags = set(_signal_columns()[indicators.GROUP.key])
    out = {}
    for day, values in zip(merged["session_date"], merged.to_dict("records"), strict=True):
        v = {str(k): (None if pd.isna(x) else bool(x)) if k in flags else x
             for k, x in values.items()}  # fmt: skip
        verdicts = (s.verdict(v, params) for s in MACRO_SIGNALS)
        out[day] = [np.nan if x is None else float(x) for x in verdicts]
    frame = pd.DataFrame.from_dict(out, "index", columns=[s.name for s in MACRO_SIGNALS])
    return frame.rename_axis("session_date").sort_index().reset_index()


def offset(start: date, end: date) -> int:
    """Exchange sessions from ``start`` to ``end`` (negative when ``end`` is before it)."""
    return sessions_to(start, end) if end >= start else -sessions_to(end, start)


# ----------------------------------------------------------------------------- (a) dating


def dated_phases(levels: pd.Series) -> list[Phase]:
    """Pagan-Sossounov with the daily rules (``PS_DAILY``)."""
    return pagan_sossounov(
        levels.to_numpy(float),
        window=PS_WINDOW,
        min_phase=PS_MIN_PHASE,
        min_cycle=PS_MIN_CYCLE,
        min_move=PS_MIN_MOVE,
    )


def _bears(phases: Iterable[Phase], days: Sequence[date]) -> list[Bear]:
    return [Bear(days[p.start], days[p.end], p.change) for p in phases if p.kind == "bear"]


def date_bears(levels: pd.Series) -> dict[str, list[Bear]]:
    """The bear markets of one index by each dating rule (``PS``, ``LT``)."""
    days = list(levels.index)
    values = levels.to_numpy(float)
    return {
        "PS": _bears(dated_phases(levels), days),
        "LT": _bears(lunde_timmermann(values, up=LT_UP, down=LT_DOWN), days),
    }


def _overlap(bear: Bear, e: Episode) -> int:
    return (min(bear.trough, e.trough) - max(bear.peak, e.peak)).days


def match(index: str, method: str, bears: Sequence[Bear], e: Episode) -> Match:
    """The dated bear that overlaps the episode most, and whether it agrees with it."""
    reference = e.spx_drawdown if index == "SPX" else e.nasdaq_drawdown
    best = max(bears, key=lambda b: _overlap(b, e), default=None)
    if best is None or _overlap(best, e) < 0:
        return Match(index, method, e, None, None, None, reference, False)
    peak_off, trough_off = offset(e.peak, best.peak), offset(e.trough, best.trough)
    deep = abs(best.depth - reference) <= DEPTH_TOLERANCE
    dated = abs(peak_off) <= DATE_TOLERANCE and abs(trough_off) <= DATE_TOLERANCE
    return Match(index, method, e, best, peak_off, trough_off, reference,
                 deep and (dated or index != "SPX"))  # fmt: skip


def agreement(history: History, episodes: Sequence[Episode]) -> list[Match]:
    """Every (index, rule, episode) match over the index's stored history (an episode before
    the history starts is skipped)."""
    out: list[Match] = []
    for index, levels in sorted(history.levels.items(), key=lambda kv: INDICES.index(kv[0])):
        dated = date_bears(levels)
        covered = [
            e for e in episodes if levels.index[0] <= e.peak and e.trough <= levels.index[-1]
        ]
        out += [match(index, m, dated[m], e) for m in dated for e in covered]
    return out


# ----------------------------------------------------------------------------- (b) leads


def _first_high(rows: pd.DataFrame, column: str, start: date, peak: date, end: date) -> date | None:
    """The warning in force at the peak: the first session of the run of high sessions that
    holds on the peak (not before ``start``); else the first high session after the peak, up
    to ``end``. A run that ended before the peak is no warning of it."""
    window = rows[(rows["session_date"] >= start) & (rows["session_date"] <= end)]
    days, high = list(window["session_date"]), list(window[column].fillna(-1.0) >= HIGH)
    at = sum(d <= peak for d in days) - 1
    if at >= 0 and high[at]:
        while at > 0 and high[at - 1]:
            at -= 1
        first: date = days[at]
        return first
    after: list[date] = [d for d, h in zip(days, high, strict=True) if h and d > peak]
    return after[0] if after else None


def _unknown(rows: pd.DataFrame, column: str, start: date, end: date) -> float | None:
    """The score's highest coverage from ``start`` to ``end`` when it never went high and is
    null on every session there (its coverage below ``min_coverage``); ``None`` otherwise."""
    window = rows[(rows["session_date"] >= start) & (rows["session_date"] <= end)]
    if window.empty or window[column].notna().any():
        return None
    coverage = window[COVERAGE[column]] if COVERAGE[column] in window.columns else None
    return 0.0 if coverage is None or coverage.isna().all() else float(coverage.max())


def _path(rows: pd.DataFrame, start: date, end: date) -> str:
    """The raw labels from ``start`` to ``end`` as runs: ``CALM 40 > CRISIS 12``."""
    labels = rows[(rows["session_date"] >= start) & (rows["session_date"] <= end)]["raw_label"]
    named = (label if isinstance(label, str) else "UNKNOWN" for label in labels)
    return " > ".join(f"{label} {len(list(run))}" for label, run in groupby(named))


def _lagged(vintages: pd.DataFrame, session: date, revised: Collection[str]) -> tuple[str, ...]:
    if vintages.empty:
        return ()
    known = known_window(vintages, session, 0)
    ids = known["instrument_id"].astype(str)
    lagged = known[(known["vintage_kind"] == "lagged") & ids.isin(list(revised))]
    return tuple(sorted(set(lagged["instrument_id"].astype(str))))


def covers(rows: pd.DataFrame | None, e: Episode) -> bool:
    """Whether regime rows reach from before the episode's peak to its trough."""
    if rows is None:
        return False
    days = rows["session_date"]
    return bool(days.iloc[0] <= e.peak and days.iloc[-1] >= e.trough)


def leads(history: History, episodes: Sequence[Episode], revised: Collection[str]) -> list[Lead]:
    """Each episode the regime rows cover: when each score went high, relative to the peak."""
    rows = history.regime
    out: list[Lead] = []
    for e in episodes:
        if rows is None or not covers(rows, e):
            continue
        start = sessions_ending(e.peak, SEARCH_BEFORE + 1)[0]
        m, k = (
            _first_high(rows, c, start, e.peak, e.trough) for c in ("macro_risk", "market_stress")
        )
        path = _path(rows, sessions_ending(e.peak, PATH_BEFORE + 1)[0], e.trough)
        lagged = _lagged(history.vintages, m or e.peak, revised)
        unknown = (_unknown(rows, c, start, e.trough) for c in ("macro_risk", "market_stress"))
        out.append(Lead(e, None if m is None else offset(e.peak, m),
                        None if k is None else offset(e.peak, k), path, lagged,
                        *unknown))  # fmt: skip
    return out


# ----------------------------------------------------------------------------- (c) false alarms


def _after(day: date, n: int) -> date:
    for _ in range(n):
        day = next_session(day)
    return day


def _windows(
    episodes: Sequence[Episode], recession_before: int = WINDOW_BEFORE
) -> list[tuple[date, date]]:
    """Each episode's window: ``recession_before`` (a recession bear) or ``WINDOW_BEFORE``
    sessions before the peak to ``WINDOW_AFTER`` after the trough."""
    out = []
    for e in episodes:
        before = recession_before if e.kind == "recession" else WINDOW_BEFORE
        out.append((sessions_ending(e.peak, before + 1)[0], _after(e.trough, WINDOW_AFTER)))
    return out


def _runs(flags: Sequence[bool]) -> list[int]:
    """The start index of each run of consecutive True values."""
    return [i for i, f in enumerate(flags) if f and (i == 0 or not flags[i - 1])]


def false_alarms(history: History, episodes: Sequence[Episode]) -> Alarms | None:
    """Flagged sessions and alarms outside every episode window, per decade."""
    rows = history.regime
    if rows is None:
        return None
    labelled = rows[rows["label"].notna()]
    if labelled.empty:
        return None
    windows = _windows(episodes)
    days = list(labelled["session_date"])
    outside = [not any(a <= d <= b for a, b in windows) for d in days]
    labels = list(labelled["label"])
    flagged = [o and lb in ALARMS for o, lb in zip(outside, labels, strict=True)]
    crisis = [o and lb == "CRISIS" for o, lb in zip(outside, labels, strict=True)]
    by: dict[int, list[int]] = {}
    for d in days:
        by.setdefault(d.year // 10 * 10, [0, 0, 0])
    for i, f in enumerate(flagged):
        by[days[i].year // 10 * 10][0] += int(f)
    for kind, flags in ((1, flagged), (2, crisis)):
        for i in _runs(flags):
            by[days[i].year // 10 * 10][kind] += 1
    decades = {k: (v[0], v[1], v[2]) for k, v in sorted(by.items())}
    return Alarms(decades, len(days) / SESSIONS_PER_YEAR)


# ----------------------------------------------------------------------------- (f) probit


def bear_states(levels: pd.Series) -> tuple[list[date], np.ndarray, int]:
    """The index's days, 1 on days inside a Pagan-Sossounov bear (peak to trough), and the
    position of its last confirmed turn (after it the state is not known yet)."""
    days = list(levels.index)
    phases = dated_phases(levels)
    state = np.zeros(len(days))
    for p in phases:
        if p.kind == "bear":
            state[p.start : p.end + 1] = 1.0
    return days, state, (phases[-1].end if phases else -1)


def probit_sample(history: History) -> tuple[np.ndarray, np.ndarray, date] | None:
    """(X with a constant, y, the last sample session) over month-end sessions, or ``None``
    with no history."""
    spx, rows = history.levels.get("SPX"), history.macro
    if spx is None or rows is None:
        return None
    days, state, last = bear_states(spx)
    rows = rows.dropna(subset=list(REGRESSORS))
    month = pd.to_datetime(rows["session_date"]).dt.to_period("M")
    ends = rows.groupby(month, sort=True).tail(1)
    xs, ys, used = [], [], []
    positions = np.array(days, dtype="datetime64[D]")
    for _, r in ends.iterrows():
        day = np.datetime64(r["session_date"], "D")
        at = int(np.searchsorted(positions, day, side="right")) - 1
        ahead = at + HORIZON
        if at < 0 or ahead > last:
            continue
        xs.append([1.0, *(float(r[c]) for c in REGRESSORS)])
        ys.append(state[ahead])
        used.append(r["session_date"])
    if not xs:
        return None
    return np.array(xs), np.array(ys), max(used)


def fit_probit(history: History) -> ProbitResult | None:
    """The probit on the stored history; ``None`` when too few months or one class only."""
    sample = probit_sample(history)
    if sample is None:
        return None
    x, y, through = sample
    if len(y) < MIN_PROBIT_MONTHS or y.min() == y.max():
        return None
    result = fit(x, y, max_iter=100, tol=1e-9)
    hits = (predict(x, result.coef) >= 0.5) == (y == 1)
    return ProbitResult(result, len(y), float(hits.mean()), float(y.mean()), through)


# ----------------------------------------------------------------------------- (g) indicator leads


@dataclass(frozen=True)
class SignalLead:
    """One macro signal: per episode key, ``(first, on)``: the first session it was on from the
    peak (``None``: never) and its sessions on before the peak, or ``None`` when it is unknown
    throughout; its hits over the graded recession bears; its false alarms over the ``years``
    it was known outside every window, and the share of those sessions it was on."""

    signal: str
    tier: str
    episodes: dict[str, tuple[int | None, int] | None]
    hits: int
    graded: int
    alarms: int
    years: float
    share: float


def _episode_lead(col: pd.Series, days: list[date], e: Episode) -> tuple[int | None, int] | None:
    start = sessions_ending(e.peak, SEARCH_BEFORE + 1)[0]
    seen = [
        (d, x) for d, x in zip(days, col.to_numpy(float), strict=True) if start <= d <= e.trough
    ]
    if all(np.isnan(x) for _, x in seen):
        return None
    on = [d for d, x in seen if x == 1.0]
    first = None if not on else offset(e.peak, on[0])
    return first, sum(d <= e.peak for d in on)


def _alarms(on: Sequence[bool]) -> int:
    """Runs of ``on``, a run starting within ``MERGE_GAP`` sessions of the last one's end
    continuing it."""
    count, gap = 0, MERGE_GAP
    for x in on:
        if x and gap >= MERGE_GAP:
            count += 1
        gap = 0 if x else gap + 1
    return count


def signal_leads(history: History, episodes: Sequence[Episode]) -> list[SignalLead]:
    """Every macro signal's leads, hit rate and false alarms over the stored history."""
    frame = history.signals
    if frame is None or frame.empty:
        return []
    days = list(frame["session_date"])
    covered = [e for e in episodes if days[0] <= e.peak and e.trough <= days[-1]]
    windows = _windows(episodes, SEARCH_BEFORE)
    outside = [not any(a <= d <= b for a, b in windows) for d in days]
    out = []
    for s in MACRO_SIGNALS:
        col = pd.Series(frame[s.name].to_numpy(float), index=days)
        leads = {e.key: _episode_lead(col, days, e) for e in covered}
        recent = [col[[sessions_ending(e.peak, HIT_BEFORE + 1)[0] <= d <= e.peak for d in days]]
                  for e in covered if e.kind == "recession"]  # fmt: skip
        graded = [w for w in recent if w.notna().any()]
        known = [o and not np.isnan(x) for o, x in zip(outside, col, strict=True)]
        flagged = [k and x == 1.0 for k, x in zip(known, col, strict=True)]
        n, hits = sum(known), sum(bool((w == 1.0).any()) for w in graded)
        out.append(SignalLead(s.name, str(s.tier), leads, hits, len(graded), _alarms(flagged),
                              n / SESSIONS_PER_YEAR, sum(flagged) / n if n else 0.0))  # fmt: skip
    return out
