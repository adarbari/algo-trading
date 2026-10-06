"""The regime episode scorecard as deterministic text (``regime_scorecard`` computes it).

Sections (a) dating agreement, (b) leads per episode, (c) false alarms per decade, (d) the
plan's acceptance as PASS / FAIL lines, (f) the bear-state probit fit with the params to paste
into ``config/site/features/regime.toml`` (or "not converged: do not paste"), (g) each macro
signal's own leads, hit rate and false alarms. A section with
nothing stored to read prints ``regime_scorecard.NO_DATA`` and the backfill command instead
(e): the report never fails for want of data. Numbers are rounded the same way every run, rows
sorted, so two runs over the same store print the same text.
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


def _signed(n: int | None, unknown: float | None = None) -> str:
    if unknown is not None:
        return f"unknown (coverage {unknown:.2f})"
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
        [lead.episode.key, lead.episode.kind, _signed(lead.macro, lead.macro_unknown),
         _signed(lead.stress, lead.stress_unknown),
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


type Graded = tuple[str, bool | float]  # episode key, passed, or the coverage: not graded


def _grade(name: str, episodes: Sequence[Graded]) -> list[str]:
    """PASS / FAIL over the graded episodes (NO DATA when none is), then one line per episode
    not graded (its score unknown: the coverage)."""
    graded = [(key, ok) for key, ok in episodes if isinstance(ok, bool)]
    skipped = [f"         not graded (coverage {c:.2f}): {key}"
               for key, c in episodes if not isinstance(c, bool)]  # fmt: skip
    if not graded:
        return [f"NO DATA  {name}", *skipped]
    failed = [key for key, ok in graded if not ok]
    verdict = "FAIL" if failed else "PASS"
    detail = f" (failed: {', '.join(failed)})" if failed else ""
    return [f"{verdict}     {name}: {len(graded) - len(failed)} of {len(graded)}{detail}", *skipped]


def acceptance_section(found: Sequence[Lead], alarms: sc.Alarms | None) -> list[str]:
    macro: list[Graded] = [
        (lead.episode.key, lead.macro_unknown if lead.macro_unknown is not None
         else lead.macro is not None and lead.macro <= -sc.MACRO_LEAD)
        for lead in found if lead.episode.kind == "recession"
    ]  # fmt: skip
    stress: list[Graded] = [
        (lead.episode.key, lead.stress_unknown if lead.stress_unknown is not None
         else lead.stress is not None and lead.stress <= sc.STRESS_LAG)
        for lead in found
    ]  # fmt: skip
    lines = [
        "(d) Acceptance (plan section 4)",
        *_grade(f"macro_risk >= {sc.HIGH:g} at least {sc.MACRO_LEAD} sessions before each "
                "recession bear's peak", macro),
        *_grade(f"market_stress >= {sc.HIGH:g} within {sc.STRESS_LAG} sessions of each peak",
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
    summary = (
        f"  months {result.months} through {result.through}, bear share "
        f"{result.base_rate:.3f}, converged {str(result.fit.converged).lower()}, "
        f"log-likelihood {result.fit.loglik:.3f}, in-sample hit rate {result.hit_rate:.3f}"
    )
    if not result.fit.converged:
        return [*head, summary, "  not converged: do not paste"]
    b = [f"{c:.4f}" for c in result.fit.coef]
    return [
        *head,
        summary,
        "  paste into config/site/features/regime.toml, bump both versions (a new fit is a new",
        f"  definition) and note that sessions up to {result.through} are in-sample:",
        f"  [bear_prob_6m] params = {{ b0 = {b[0]}, b_curve = {b[1]}, b_cpi = {b[2]}, "
        f"b_hy = {b[3]} }}",
        f'  [bear_prob_source] params = {{ fitted = 1, fitted_through = "{result.through}" }}',
    ]


def _lead_cell(cell: tuple[int | None, int] | None) -> str:
    """``-269/79``: first on 269 sessions before the peak, on 79 of them; ``after +93``."""
    if cell is None:
        return "n/a"
    first, on = cell
    if first is None:
        return "never"
    return f"{first:+d}/{on}" if first <= 0 else f"after {first:+d}"


def signal_section(found: Sequence[sc.SignalLead], episodes: Sequence[Episode]) -> list[str]:
    head = [
        f"(g) Per-indicator leads: each macro signal (its tier), per episode the first session "
        f"it was on in the {sc.SEARCH_BEFORE} sessions before the peak, from the peak / the "
        "sessions it was on before the peak (after +N: first on after the peak, to the "
        "trough; n/a: unknown throughout)"
    ]
    if not found:
        return head + _no_data()
    lines = list(head)
    for kind in ("recession", "shock"):
        keys = [e.key for e in episodes if e.kind == kind and e.key in found[0].episodes]
        rows = [[f.signal, f.tier, *(_lead_cell(f.episodes[k]) for k in keys)]
                for f in found]  # fmt: skip
        lines += _table(["signal", "tier", *keys], rows) if keys else []
    lines.append(
        f"    hit: on in the {sc.HIT_BEFORE} sessions before a recession bear's peak; alarms: "
        f"runs on outside every window ({sc.SEARCH_BEFORE} sessions before a recession bear's "
        f"peak, {sc.WINDOW_BEFORE} before a shock's, to {sc.WINDOW_AFTER} after the trough; "
        f"back on within {sc.MERGE_GAP} sessions is the same run), per year known there"
    )
    rows = [[f.signal, f.tier, f"{f.hits} of {f.graded}", str(f.alarms), f"{f.years:.1f}",
             f"{f.alarms / f.years:.2f}" if f.years else "-", f"{f.share:.0%}"]
            for f in found]  # fmt: skip
    return lines + _table(["signal", "tier", "hit", "alarms", "years", "per year", "on"], rows)


def render(history: History, episodes: Sequence[Episode], revised: Collection[str]) -> str:
    """The whole scorecard. ``revised``: the instrument ids of the revised series (ALFRED
    vintages, or ``revised = true`` in the registry), whose ``lagged`` values in an episode
    are reported."""
    found = sc.leads(history, episodes, revised)
    alarms = sc.false_alarms(history, episodes)
    sections = (
        dating_section(sc.agreement(history, episodes)),
        leads_section(found),
        alarms_section(alarms),
        acceptance_section(found, alarms),
        probit_section(sc.fit_probit(history)),
        signal_section(sc.signal_leads(history, episodes), episodes),
    )
    lines = [TITLE, "=" * len(TITLE)]
    for section in sections:
        lines += ["", *section]
    return "\n".join(lines) + "\n"
