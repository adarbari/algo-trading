"""Which names the nightly asks Yahoo about, and the fingerprint of an answer (ADR 0080 amendment
2026-10-23c). Pure: no I/O, no clock, no store; ``snapshot._yahoo`` gathers the inputs and asks.

The load is a **rolling baseline** with **event pulls on top**, inside one nightly ceiling:

- **Baseline.** Each name has a stable slot, ``sha256(instrument_id) mod cycle``, counted from a
  fixed anchor day (``[yahoo] cycle_anchor``), so it is due on its own day of every cycle:
  about 1/14 of the population a night (1/45 for the standby names FMP also answers), flat, with
  no weekly bunching. A name keeps its slot whatever happens to its history. A missed night costs
  nothing for long: a name whose last answer is a full cycle old is *overdue* and goes before the
  slot's names. A name never asked (a refused one, a new listing) counts as the stalest. The
  baseline alone serves every name, and is the only schedule of a name with no known report date.
- **Events** (``[yahoo] events_enabled``): analyst actions spike in the 3 days after a report
  (about 7.4% a day against 1.1% otherwise), before it they are flat, and a quarter's EPS
  consensus drifts all the way to the report, so drift says nothing of timing. So the pulls are
  timed by the report date, not by the estimates. **Post**: the day after a report (a report our
  own ``earnings@v1`` has seen, never a guess) and, only when that pull showed nothing new, once
  more about 3 days later; the first sign of new data (a changed fingerprint or a newer analyst
  action date) ends it. **Pre**: one pull in the last week before the expected report (taken
  when it is 3 days away), which stores the final pre-report consensus and refreshes the date
  itself (every answer carries Yahoo's ``calendarEvents`` date, an estimate that can be stale
  or past: a past date no report was seen for is unknown). The date is our stored
  ``earnings_expected@v1`` (the session before), Yahoo's the fallback. The owner's first sketch
  (enable about 83 days after the last pull, try daily until new data) is the post pull, timed
  by the date instead of a guessed gap.
- **Ceiling.** Calls are served in this order, up to ``ceiling`` (and the baseline up to
  ``per_night``): names about to exceed the reader's staleness (``HARD_DAYS``, the reader goes
  stale at 21), post pulls, pre pulls (each largest market cap first), then the baseline
  stalest first; a small cap past the ceiling falls back to its baseline slot. The baseline
  yields to the events, but never past ``HARD_DAYS``: a name Yahoo serves is never left older
  than that by a busy reporting week.

A **fingerprint** (``fingerprint``) hashes only the stable values of an answer (target mean, high,
low; the two annual estimates' period, average and analyst count; the rating counts), not Yahoo's
epsTrend 7 / 30-days-ago fields nor the month of the rating bucket, which move without news. The
item status carries it with Yahoo's next report date and newest analyst action date
(``OK: fp=ab12cd34 next=2026-11-03 act=2026-10-20``: ``status_label`` splits at the colon), so a
repeated fingerprint is not new data and ``snapshot.history`` needs no store read.
"""

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

HARD_DAYS = 18  # a name asked this long ago goes before every event pull (the reader: 21)
POST_AFTER = (
    1,
    4,
)  # days after a report of the first pull and (if it showed nothing new) the repeat
POST_GRACE = 2  # a missed post pull is still caught up this many days late
PRE_AHEAD = 3  # the one pre-report pull is taken when the expected report is this near (<= 7)
PRE_WINDOW = 7  # ... and only when no pull has been made since the window opened
COOLOFF_CAP = 8  # the cool-off after a 429 is 2 ** k nights, k at most this
POST, PRE, HARD, BASELINE = "post", "pre", "hard", "baseline"


@dataclass(frozen=True)
class Candidate:
    """One name Yahoo may be asked tonight, with what the history and the calendar say."""

    symbol: str
    instrument_id: str
    standby: bool = False  # FMP answers it: Yahoo's row is a standby, asked every standby cycle
    last_asked: date | None = None  # its last answered call (OK or EMPTY)
    changed: date | None = None  # the session its fingerprint last changed or a newer action came
    last_report: date | None = None  # the report before tonight, as known the session before
    next_report: date | None = None  # the expected report on or after, as known then (ours)
    yahoo_next: date | None = None  # Yahoo's date of the next report in its last answer


@dataclass(frozen=True)
class Rules:
    cycle: int  # ``[yahoo] refresh_days``
    standby_cycle: int  # ``[yahoo] standby_days``
    anchor: date  # ``[yahoo] cycle_anchor``
    ceiling: int  # ``[yahoo] nightly_ceiling`` (the caller lowers it to a hand-run ``limit``)
    baseline_cap: int  # ``[yahoo] per_night``
    events: bool  # ``[yahoo] events_enabled``


@dataclass(frozen=True)
class Plan:
    take: list[str]  # the symbols to ask, in order
    why: dict[str, str] = field(default_factory=dict)  # symbol -> post / pre / hard / baseline
    due_baseline: int = 0  # names the baseline would take with no ceiling
    due_events: int = 0  # event pulls wanted tonight

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for reason in self.why.values():
            out[reason] = out.get(reason, 0) + 1
        return out


def slot(instrument_id: str, cycle: int) -> int:
    """The day of the cycle a name is due on: a stable hash (never Python's per-process one)."""
    digest = hashlib.sha256(instrument_id.encode()).digest()
    return int.from_bytes(digest[:8], "big") % cycle


def on_slot(instrument_id: str, session: date, anchor: date, cycle: int) -> bool:
    """Whether ``session`` is the name's own day of the cycle."""
    return last_slot_day(instrument_id, session, anchor, cycle) == session


def gap(candidate: Candidate, session: date) -> int | None:
    """Days since the last answer; ``None`` for a name never asked."""
    return None if candidate.last_asked is None else (session - candidate.last_asked).days


def last_slot_day(instrument_id: str, session: date, anchor: date, cycle: int) -> date:
    """The latest day on or before ``session`` that is the name's own day of the cycle."""
    back = ((session - anchor).days - slot(instrument_id, cycle)) % cycle
    return session - timedelta(days=back)


def baseline_due(c: Candidate, session: date, rules: Rules) -> bool:
    """Never asked, a full cycle since the last answer (overdue), or the name's latest slot day
    (today's, or one a missed night left behind) came after its last answer."""
    cycle = rules.standby_cycle if c.standby else rules.cycle
    since = gap(c, session)
    if since is None or c.last_asked is None or since >= cycle:
        return True
    return c.last_asked < last_slot_day(c.instrument_id, session, rules.anchor, cycle)


def post_due(c: Candidate, session: date) -> bool:
    """The day after a report a pull is owed; about 3 days later one more, only when the first
    showed nothing new (no fingerprint change and no newer analyst action since the report)."""
    if c.last_report is None:
        return False
    first, again = (c.last_report + timedelta(days=d) for d in POST_AFTER)
    late = timedelta(days=POST_GRACE)
    if c.last_asked is None or c.last_asked < first:
        return timedelta(0) <= session - first <= late
    if c.changed is not None and c.changed >= first:
        return False
    return c.last_asked < again and timedelta(0) <= session - again <= late


def expected_report(c: Candidate, session: date) -> date | None:
    """Our date, else Yahoo's; a date not after ``session`` is no date (stale, or past with no
    report seen)."""
    for day in (c.next_report, c.yahoo_next):
        if day is not None and day > session:
            return day
    return None


def pre_due(c: Candidate, session: date) -> bool:
    """One pull in the last week before the expected report, taken ``PRE_AHEAD`` days before it,
    unless a pull was already made since the window opened."""
    date_ = expected_report(c, session)
    if date_ is None or not 0 < (date_ - session).days <= PRE_AHEAD:
        return False
    return c.last_asked is None or c.last_asked < date_ - timedelta(days=PRE_WINDOW)


def staleness(c: Candidate, session: date) -> int:
    since = gap(c, session)
    return 10**6 if since is None else since


def plan(
    session: date, candidates: Sequence[Candidate], rules: Rules, rank: Sequence[str] = ()
) -> Plan:
    """Tonight's names, in order, at most ``rules.ceiling``: hard-overdue, post, pre, baseline.
    ``rank`` (symbols, largest market cap first) breaks ties; a symbol not in it goes last."""
    order = {s: i for i, s in enumerate(rank)}
    last = len(order)

    def key(c: Candidate) -> tuple[int, int, str]:
        return (-staleness(c, session), order.get(c.symbol, last), c.symbol)

    hard: list[Candidate] = []
    post: list[Candidate] = []
    pre: list[Candidate] = []
    base: list[Candidate] = []
    for c in candidates:
        since = gap(c, session)
        if not c.standby and since is not None and since >= HARD_DAYS:
            hard.append(c)
            continue
        if rules.events:
            if post_due(c, session):
                post.append(c)
                continue
            if pre_due(c, session):
                pre.append(c)
                continue
        if baseline_due(c, session, rules):
            base.append(c)
    hard.sort(key=key)
    by_rank = lambda c: (order.get(c.symbol, last), c.symbol)  # noqa: E731
    post.sort(key=by_rank)
    pre.sort(key=by_rank)
    base.sort(key=key)
    take: list[str] = []
    why: dict[str, str] = {}
    for reason, group in ((HARD, hard), (POST, post), (PRE, pre)):
        for c in group:
            if len(take) < rules.ceiling:
                take.append(c.symbol)
                why[c.symbol] = reason
    for c in base[: rules.baseline_cap]:
        if len(take) < rules.ceiling:
            take.append(c.symbol)
            why[c.symbol] = BASELINE
    return Plan(take, why, len(base), len(post) + len(pre))


def fingerprint(parsed: Mapping[str, pd.DataFrame]) -> str:
    """Eight hex digits over the stable values of one answer's parsed frames (``price_target``,
    ``estimates_annual``, ``recommendation``); the same answer, however fetched, gives the same."""
    parts: list[str] = []
    for kind, columns in STABLE.items():
        frame = parsed.get(kind)
        if frame is None or frame.empty:
            parts.append(f"{kind}:-")
            continue
        cols = [c for c in columns if c in frame.columns]
        for row in frame[cols].itertuples(index=False):
            parts.append(f"{kind}:" + ",".join(part(v) for v in row))
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:8]


# What an answer is fingerprinted by: not epsTrend's 7 / 30-days-ago fields (never parsed) and not
# the recommendation's month ``period`` (a roll of the calendar, not of the analysts).
STABLE: dict[str, tuple[str, ...]] = {
    "price_target": ("target_consensus", "target_high", "target_low"),
    "estimates_annual": ("fiscal_date", "eps_avg", "num_analysts_eps"),
    "recommendation": ("strong_buy", "buy", "hold", "sell", "strong_sell"),
}


def part(value: object) -> str:
    if value is None or value is pd.NA or value is pd.NaT or value != value:  # noqa: PLR0124
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    return str(value)


@dataclass(frozen=True)
class Answer:
    """What an answered item's status carries."""

    fp: str | None = None
    next_report: date | None = None  # Yahoo's date of the next report
    action: date | None = None  # its newest analyst action


def with_answer(label: str, fp: str, calendar: pd.DataFrame | None) -> str:
    """The item status of an answer: ``OK: fp=ab12cd34 next=2026-11-03 act=2026-10-20`` (a date
    Yahoo does not give is left out)."""
    parts = [f"fp={fp}"]
    if calendar is not None and not calendar.empty:
        row = calendar.iloc[0]
        for tag, column in (("next", "next_report"), ("act", "last_action")):
            if row[column] is not None and not pd.isna(row[column]):
                parts.append(f"{tag}={row[column]}")
    return f"{label}: {' '.join(parts)}"


def answer_of(status: str) -> Answer:
    """The ``Answer`` an item status carries (empty for a status without one)."""
    found = dict(p.split("=", 1) for p in status.partition(": ")[2].split() if "=" in p)

    def day(tag: str) -> date | None:
        try:
            return date.fromisoformat(found[tag])
        except (KeyError, ValueError):
            return None

    return Answer(found.get("fp"), day("next"), day("act"))


def cooloff_nights(consecutive: int) -> int:
    """Nights to wait after the ``consecutive``-th night in a row that Yahoo answered 429."""
    return int(2 ** min(max(consecutive, 1), COOLOFF_CAP))


def cooling(until: date | None, session: date) -> bool:
    return until is not None and session < until
