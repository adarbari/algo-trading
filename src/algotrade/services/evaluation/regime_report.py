"""The regime episode scorecard as deterministic text (``regime_scorecard`` computes it).

Sections (a) dating agreement, (b) leads per episode, (c) false alarms per decade, (d) the
plan's acceptance as PASS / FAIL lines, (f) the bear-state probit fit with the lines to paste
into ``config/site/rollups.toml``. A section with nothing stored to read prints
``regime_scorecard.NO_DATA`` and the backfill command instead (e): the report never fails for
want of data. Numbers are rounded the same way every run, rows sorted, so two runs over the
same store print the same text.
"""

from collections.abc import Collection, Sequence

from algotrade.config.site.regime.episodes import Episode
from algotrade.services.evaluation import regime_scorecard as sc
from algotrade.services.evaluation.regime_scorecard import History, Lead, Match

TITLE = "Regime episode scorecard (docs/market-regime-plan.md section 4)"


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    widths = [max(len(str(c)) for c in col) for col in zip(header, *rows, strict=True)]
    return [
        "  ".join(str(c).ljust(w) for c, w in zip(row, widths, strict=True)).rstrip()
        for row in (header, *rows)
    ]


def _no_data() -> list[str]:
    return [f"  {sc.NO_DATA}: {sc.BACKFILL}"]


def _args(args: dict[str, float]) -> str:
    return ", ".join(f"{k} {v:g}" for k, v in args.items())


def _pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def _signed(n: int | None) -> str:
    return "never" if n is None else f"{n:+d}"


def dating_section(matches: Sequence[Match]) -> list[str]:
    head = [
        f"(a) Bear-market dating vs episodes.toml (peak and trough within {sc.DATE_TOLERANCE} "
        f"sessions, depth within {sc.DEPTH_TOLERANCE * 100:g} points; the Nasdaq: depth only)",
        f"    PS = Pagan-Sossounov ({_args(sc.PS_DAILY)}), LT = Lunde-Timmermann "
        f"({_args(sc.LT_DAILY)})",
    ]
    if not matches:
        return head + _no_data()
    rows = [
        [m.index, m.method, m.episode.key, str(m.episode.peak),
         "-" if m.dated is None else str(m.dated.peak), _signed(m.peak_off),
         str(m.episode.trough), "-" if m.dated is None else str(m.dated.trough),
         _signed(m.trough_off), _pct(m.reference_depth),
         "-" if m.dated is None else _pct(m.dated.depth), "yes" if m.agree else "NO"]
        for m in matches
    ]  # fmt: skip
    header = ["index", "rule", "episode", "peak", "dated", "d", "trough", "dated", "d",
              "depth", "dated", "agree"]  # fmt: skip
    agreed = sum(m.agree for m in matches)
    return head + _table(header, rows) + [f"    agree: {agreed} of {len(matches)}"]


def leads_section(found: Sequence[Lead]) -> list[str]:
    head = [
        f"(b) Leads, in sessions from the peak (negative: before): the start of the run of "
        f"score >= {sc.HIGH:g} holding on the peak (at most {sc.SEARCH_BEFORE} back), else the "
        f"first such session up to the trough; raw labels from {sc.PATH_BEFORE} sessions "
        "before the peak"
    ]
    if not found:
        return head + _no_data()
    rows = [
        [lead.episode.key, lead.episode.kind, _signed(lead.macro), _signed(lead.stress),
         ", ".join(lead.lagged) or "none"]
        for lead in found
    ]  # fmt: skip
    lines = _table(["episode", "kind", "macro", "stress", "revised series on the lag rule"], rows)
    return head + lines + [f"    {lead.episode.key}: {lead.path}" for lead in found]


def alarms_section(alarms: sc.Alarms | None) -> list[str]:
    head = [
        f"(c) False alarms: STRESS / CRISIS sessions outside every episode window "
        f"({sc.WINDOW_BEFORE} sessions before the peak to {sc.WINDOW_AFTER} after the trough); "
        "an alarm is a run of consecutive flagged sessions"
    ]
    if alarms is None:
        return head + _no_data()
    rows = [[f"{d}s", str(n), str(a), str(c)] for d, (n, a, c) in alarms.by_decade.items()]
    return head + _table(["decade", "sessions", "alarms", "CRISIS alarms"], rows)


def _grade(name: str, graded: Sequence[tuple[str, bool]]) -> str:
    if not graded:
        return f"NO DATA  {name}"
    failed = [key for key, ok in graded if not ok]
    verdict = "FAIL" if failed else "PASS"
    detail = f" (failed: {', '.join(failed)})" if failed else ""
    return f"{verdict}     {name}: {len(graded) - len(failed)} of {len(graded)}{detail}"


def acceptance_section(found: Sequence[Lead], alarms: sc.Alarms | None) -> list[str]:
    macro = [(lead.episode.key, lead.macro is not None and lead.macro <= -sc.MACRO_LEAD)
             for lead in found if lead.episode.kind == "recession"]  # fmt: skip
    stress = [(lead.episode.key, lead.stress is not None and lead.stress <= sc.STRESS_LAG)
              for lead in found]  # fmt: skip
    lines = [
        "(d) Acceptance (plan section 4)",
        _grade(f"macro_risk >= {sc.HIGH:g} at least {sc.MACRO_LEAD} sessions before each "
               "recession bear's peak", macro),
        _grade(f"market_stress >= {sc.HIGH:g} within {sc.STRESS_LAG} sessions of each peak",
               stress),
    ]  # fmt: skip
    name = f"fewer than one false CRISIS per {sc.CRISIS_YEARS:g} years"
    if alarms is None or alarms.years <= 0:
        return [*lines, f"NO DATA  {name}", *([] if macro or stress else _no_data())]
    crises = sum(c for _, _, c in alarms.by_decade.values())
    rate = crises / alarms.years * sc.CRISIS_YEARS
    verdict = "PASS" if rate < 1 else "FAIL"
    return [*lines, f"{verdict}     {name}: {crises} over {alarms.years:.1f} years "
                    f"= {rate:.2f} per {sc.CRISIS_YEARS:g} years"]  # fmt: skip


def probit_section(result: sc.ProbitResult | None) -> list[str]:
    head = [
        f"(f) Bear-state probit fitted on the stored history: y = the S&P 500 in a "
        f"Pagan-Sossounov bear {sc.HORIZON} sessions on, x = 1, curve_10y3m, cpi_yoy, hy_oas "
        "(decimals), month-end sessions"
    ]
    if result is None:
        too_few = f"or fewer than {sc.MIN_PROBIT_MONTHS} months with both states"
        return [*head, f"  {sc.NO_DATA} ({too_few}): {sc.BACKFILL}"]
    b = [f"{c:.4f}" for c in result.fit.coef]
    return [
        *head,
        f"  months {result.months}, bear share {result.base_rate:.3f}, converged "
        f"{str(result.fit.converged).lower()}, log-likelihood {result.fit.loglik:.3f}, "
        f"in-sample hit rate {result.hit_rate:.3f}",
        "  paste into config/site/rollups.toml:",
        '  ["market_bear_probit@v1"]',
        f"  b0 = {b[0]}",
        f"  b_curve = {b[1]}",
        f"  b_cpi = {b[2]}",
        f"  b_hy = {b[3]}",
        f"  fitted = {str(result.fit.converged).lower()}",
    ]


def render(history: History, episodes: Sequence[Episode], revised: Collection[str]) -> str:
    """The whole scorecard. ``revised``: the registry keys with ALFRED vintages (``pit =
    "alfred"``), whose ``lagged`` values in an episode are reported."""
    found = sc.leads(history, episodes, revised)
    alarms = sc.false_alarms(history, episodes)
    sections = (
        dating_section(sc.agreement(history, episodes)),
        leads_section(found),
        alarms_section(alarms),
        acceptance_section(found, alarms),
        probit_section(sc.fit_probit(history)),
    )
    lines = [TITLE, "=" * len(TITLE)]
    for section in sections:
        lines += ["", *section]
    return "\n".join(lines) + "\n"
