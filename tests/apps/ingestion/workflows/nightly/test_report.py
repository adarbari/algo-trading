"""The nightly report: statistics, failure grouping with capped examples, text and HTML."""

from html.parser import HTMLParser

from algotrade_ingestion.workflows.nightly.render import duration, render_html, render_text
from algotrade_ingestion.workflows.nightly.report import build_report, normalise
from tests.helpers import nightly_runs as fx

LABELS = {"EQ:BBG000QL42S5": "XMAX"}


def test_normalise_strips_ids_urls_dates_and_numbers() -> None:
    assert normalise("STALE_DATA: chain is for 2026-10-01") == "STALE_DATA: chain is for <date>"
    assert (
        normalise("FETCH_ERROR: giving up on https://api.x.com/v2/2024-10-01?a=1: HTTP 403")
        == "FETCH_ERROR: giving up on <url> HTTP <n>"
    )
    assert normalise("no quote for EQ:AAPL today", "EQ:AAPL") == "no quote for <id> today"


def test_statistics_per_step() -> None:
    report = build_report(fx.summary(), fx.records(), LABELS)
    steps = {s.step: s for s in report.steps}
    assert [s.step for s in report.steps][-1] == "purge-raw" and steps["purge-raw"].session == ""
    chains = steps["chains"]
    assert dict(chains.items) == {"OK": 4, "STALE_DATA": 7, "NO_CHAIN": 2, "FETCH_ERROR": 1}
    assert chains.counts == (("universe", 14),)
    assert steps["bars"].items == (("STORED", 1),)  # no record: the result's status counts
    assert steps["rollups"].counts == (("rollups", 2), ("rows", 16804))
    assert steps["screens"].counts == (("screens", 1),)
    assert steps["shares"].counts[0] == ("rows", 417993)
    assert steps["universe-build"].note.startswith("DataValidationError")
    assert report.rollups == (
        (fx.D.isoformat(), "option_liquidity@v1", 4203, 0),
        (fx.D.isoformat(), "price_stats@v1", 12601, 0),
    )
    assert [s.step for s in report.bad_steps] == [
        "universe-build",
        "shares",
        "chains",
        "screens",
        "quality",
    ]
    assert report.warnings == ("took long",)
    assert report.duration_s == 1559.67 and report.started == fx.START


def test_failures_grouped_by_reason_with_capped_examples() -> None:
    report = build_report(fx.summary(), fx.records(), LABELS, max_examples=3)
    groups = {(g.step, g.reason): g for g in report.failures}
    stale = groups[("chains", "STALE_DATA: chain is for <date>")]
    assert stale.count == 7 and len(stale.examples) == 3
    assert stale.examples[0].key == "EQ:ST0"
    assert stale.examples[0].message == "STALE_DATA: chain is for 2026-09-20"
    no_chain = groups[("chains", "NO_CHAIN")]
    assert [e.label for e in no_chain.examples] == ["XMAX", None]
    assert groups[("shares", "FETCH_ERROR: companyfacts document has no CIK")].count == 2
    assert ("shares", "FETCH_ERROR: HTTP <n> for <url>") in groups
    assert not any(step == "quality" for step, _ in groups)  # checks are listed separately
    assert not any("NO_SHARE_FACTS" in reason or reason == "OK" for _, reason in groups)
    # Most common reason first within a step.
    assert next(g.reason for g in report.failures if g.step == "chains").startswith("STALE")
    assert [(c.name, c.status) for c in report.checks] == [
        ("chains_fetch", "FAIL"),
        ("chains_stale", "WARN"),
    ]
    (screen,) = report.screens
    assert screen.gaps == (("STALE_DATA: chain is for <date>", 451),)
    assert screen.decisions[0] == ("LIQUIDITY_RISK", 3299)


def test_hints_for_known_failure_kinds() -> None:
    hints = " ".join(build_report(fx.summary(), fx.records()).hints)
    for expected in ("Circuit breaker", "STALE_DATA", "NO_CHAIN", "Duplicate table keys"):
        assert expected in hints
    assert "SEC companyfacts" in hints and "HTTP 401" not in hints
    assert "max_chain_fetch_failures" in hints and "max_chain_stale_share_core" in hints


def test_subject() -> None:
    assert (
        build_report(fx.summary(), fx.records()).subject()
        == "[algotrade] 2026-10-02 nightly: PARTIAL · chains 4 OK · 5 steps with failures"
    )
    clean = fx.summary("COMPLETE")
    clean["runs"][0]["steps"] = {"bars": {"status": "COMPLETE", "duration_s": 1.0}}
    assert (
        build_report(clean, {}).subject() == "[algotrade] 2026-10-02 nightly: COMPLETE · 0 failures"
    )
    multi = {**clean, "sessions": ["2026-09-30", "2026-10-01", "2026-10-02"]}
    assert build_report(multi, {}).subject().startswith("[algotrade] 2026-09-30..2026-10-02")
    assert (
        build_report({"status": "COMPLETE"}, {})
        .subject()
        .startswith("[algotrade] no session nightly")
    )


def test_text_rendering() -> None:
    text = render_text(build_report(fx.summary(), fx.records(), LABELS, max_examples=2))
    assert text.splitlines()[0].startswith("[algotrade] 2026-10-02 nightly: PARTIAL")
    for section in ("STATISTICS", "FAILURE DEEP DIVE", "WHAT TO DO", "Rollups", "Screens"):
        assert section in text
    (chains,) = [line for line in text.splitlines() if line.startswith("chains ")]
    assert chains.split()[1:4] == ["PARTIAL", "20m", "37s"]
    assert "STALE_DATA 7, OK 4, NO_CHAIN 2, FETCH_ERROR 1" in chains and "universe 14" in chains
    assert "[chains] STALE_DATA: chain is for <date>: 7" in text
    assert "... and 5 more" in text
    assert "XMAX (EQ:BBG000QL42S5): NO_CHAIN" in text
    assert "FAIL chains_fetch: 7.1% failed to fetch (max 5%); of 14 underlyings" in text
    assert "WARN chains_stale: 50.0% stale (max 20%)" in text
    assert "short_premium_liquidity: STALE_DATA: chain is for <date>: 451" in text
    assert "Warning:" in text and "took long" in text
    assert "universe-build FAILED: DataValidationError" in text


def test_text_without_failures() -> None:
    clean = fx.summary("COMPLETE")
    clean["runs"][0]["steps"] = {"bars": {"status": "COMPLETE", "duration_s": 75.0}}
    text = render_text(build_report(clean, {}))
    assert "No failures." in text and "WHAT TO DO" not in text


class _Tags(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: object) -> None:
        self.tags.append(tag)


def test_html_rendering_is_self_contained_and_escaped() -> None:
    summary = fx.summary()
    summary["runs"][0]["steps"]["universe-build"]["error"] = "ValueError: <script>x</script>"
    html = render_html(build_report(summary, fx.records(), LABELS))
    parser = _Tags()
    parser.feed(html)
    assert "script" not in parser.tags and "img" not in parser.tags and "link" not in parser.tags
    assert "&lt;script&gt;" in html
    assert "Failure deep dive" in html and "Failed items by reason" in html
    assert "Screen coverage gaps" in html and "Quality checks not passing" in html
    assert '<b style="color:#cf222e">FAILED</b>' in html
    assert "http://" not in html.replace("https://cdn.cboe.com", "")


def test_duration_format() -> None:
    assert (duration(0.4), duration(83.7), duration(3725)) == ("0.4s", "1m 24s", "1h 02m")


def test_run_timing_section() -> None:
    history = [{"chains": 300.0, "rollups": 20.0}, {"chains": 320.0}]
    report = build_report(fx.summary(), fx.records(), LABELS, 5, history, 150 * 60)
    by = {t.step: t for t in report.timings}
    assert by["universe-build"].start == fx.START
    assert by["chains"].slower and by["chains"].items == 14
    assert report.max_duration_s == 9000
    text = render_text(report)
    assert "RUN TIMING (times America/Los_Angeles)" in text
    assert "26m 00s (within the alert threshold of 2h 30m)" in text
    assert "Slower than usual:   chains (>50% above the 7-run median)" in text
    assert "*chains" in text and "SLOWER" in text
    assert "rollups: option_liquidity@v1 12.5s, price_stats@v1 2.9s" in text
    assert "2026-10-03 06:26 PDT (13:26 UTC)" in text
    html = render_html(report)
    assert "Run timing (America/Los_Angeles)" in html and "background:#fff8c5" in html
    over = build_report(fx.summary(), fx.records(), None, 5, (), 600)
    assert "OVER the alert threshold" in render_text(over)


def test_vendor_pacing_per_step_in_run_timing() -> None:
    records = fx.records()
    chains = records[(fx.D.isoformat(), "chains")]
    chains.stats["pacing"] = {
        "cboe": {
            "requests": 4210,
            "throttled_429": 3,
            "retry_after_wait_s": 150.0,
            "limiter_wait_s": 4400.0,
            "error_rate_slowdowns": 1,
            "interval_min_s": 1.05,
            "interval_max_s": 2.363,
            "interval_final_s": 1.1,
        },
        "bad": "not a mapping",
    }
    report = build_report(fx.summary(), records, LABELS)
    assert [(p.step, p.key, p.requests) for p in report.pacing] == [("chains", "cboe", 4210)]
    line = (
        "chains / cboe: 4,210 requests, 3 x 429 (Retry-After 2m 30s), rate-limit wait "
        "1h 13m, 1 error-rate slowdown(s), interval 1.05-2.363s (final 1.1s)"
    )
    assert line in render_text(report)
    assert "Vendor pacing" in render_html(report)
    assert build_report(fx.summary(), fx.records()).pacing == ()
