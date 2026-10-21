"""The filing comparison: the comparator window (330-400 days, same form, closest to a year),
amendments never a subject or a comparator, SHORT and under-floor items not compared, NO_PRIOR
and NOT_COMPARABLE with null measures, the risk-factor pair, golden cosine / Jaccard values, and
the recent-session window of a subject."""

from datetime import date, timedelta

import pandas as pd
import pytest

from algotrade.features.rollups.text import comparison as cmp
from algotrade.features.rollups.text.comparison import compare_filings

SESSION = date(2026, 10, 2)
RECENT_FROM = date(2026, 9, 28)  # five sessions ending on SESSION
REPORT = date(2026, 6, 30)  # the subject 10-Q's quarter


def words(n: int, start: int = 0) -> list[str]:
    """``n`` distinct letter-only words (digits are dropped by the tokeniser, so no ``w1``)."""
    out = []
    for i in range(start, start + n):
        letters = ""
        k = i
        for _ in range(3):
            letters += chr(ord("a") + k % 26)
            k //= 26
        out.append("zq" + letters)
    return out


def body(vocab: list[str], total: int) -> str:
    """A text of ``total`` words cycling through ``vocab``."""
    return " ".join(vocab[i % len(vocab)] for i in range(total))


def filing(
    accession: str,
    form: str,
    report: date | None,
    known: date,
    items: dict[str, str],
    iid: str | None = "EQ:AAA",
    cik: str = "0000000001",
    quality: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    return [
        {"instrument_id": iid, "cik": cik, "form": form, "accession": accession,
         "report_date": report, "known_from": known, "accepted_session": known, "item": item,
         "quality": (quality or {}).get(item, "OK"), "text": text}
        for item, text in items.items()
    ]  # fmt: skip


def frame(*filings: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame([r for f in filings for r in f])


def ten_q(accession: str, report: date, known: date, **kw: object) -> list[dict[str, object]]:
    items = {"I-2": body(words(150), 600), "II-1A": body(words(150, 150), 600)}
    return filing(accession, "10-Q", report, known, items, **kw)  # type: ignore[arg-type]


def run(data: pd.DataFrame) -> list[cmp.Comparison]:
    return compare_filings(data, RECENT_FROM, SESSION)


def test_an_unchanged_filing_has_cosine_and_jaccard_one_and_both_items_compared() -> None:
    [c] = run(frame(ten_q("NEW", REPORT, date(2026, 9, 30)),
                    ten_q("OLD", REPORT - timedelta(days=365), date(2025, 8, 5))))  # fmt: skip
    assert (c.status, c.accession, c.prior_accession) == (cmp.OK, "NEW", "OLD")
    assert c.cosine == pytest.approx(1.0) and c.jaccard == 1.0 and c.items_compared == 2
    assert c.rf_cosine is None and c.rf_len_change is None  # a 10-Q has no 10-K Item 1A pair


def test_golden_cosine_and_jaccard_over_the_composite_of_compared_items() -> None:
    old = filing("OLD", "10-Q", REPORT - timedelta(days=365), date(2025, 8, 5),
                 {"I-2": " ".join(["zqaaa"] * 300 + ["zqbbb"] * 300)})  # fmt: skip
    new = filing("NEW", "10-Q", REPORT, date(2026, 9, 30),
                 {"I-2": " ".join(["zqaaa"] * 300 + ["zqccc"] * 300)})  # fmt: skip
    [c] = run(frame(new, old))
    assert c.cosine == pytest.approx(0.5)  # dot 90000 over 180000
    assert c.jaccard == pytest.approx(1 / 3)  # {aaa} over {aaa, bbb, ccc}


def test_the_comparator_window_is_330_to_400_days_and_the_closest_to_a_year_wins() -> None:
    new = ten_q("NEW", REPORT, date(2026, 9, 30))
    for days, expected in [(300, cmp.NO_PRIOR), (329, cmp.NO_PRIOR), (330, cmp.OK),
                           (400, cmp.OK), (401, cmp.NO_PRIOR), (420, cmp.NO_PRIOR)]:  # fmt: skip
        [c] = run(frame(new, ten_q("OLD", REPORT - timedelta(days=days), date(2025, 8, 5))))
        assert c.status == expected, days
    near = ten_q("NEAR", REPORT - timedelta(days=366), date(2025, 8, 5))
    far = ten_q("FAR", REPORT - timedelta(days=335), date(2025, 7, 5))
    assert run(frame(new, far, near))[0].prior_accession == "NEAR"


def test_no_stored_comparator_is_no_prior_with_null_measures_not_zero() -> None:
    [c] = run(frame(ten_q("NEW", REPORT, date(2026, 9, 30))))
    assert c.status == cmp.NO_PRIOR and c.prior_accession is None
    assert c.cosine is None and c.jaccard is None and c.items_compared is None


def test_the_comparator_is_the_same_form_and_the_same_company() -> None:
    k_items = {"1A": body(words(150), 300), "7": body(words(150, 150), 300)}
    annual = filing("K", "10-K", REPORT - timedelta(days=365), date(2025, 8, 5), k_items)
    other = ten_q("OTHER", REPORT - timedelta(days=365), date(2025, 8, 5), cik="0000000002")
    [c] = run(frame(ten_q("NEW", REPORT, date(2026, 9, 30)), annual, other))
    assert c.status == cmp.NO_PRIOR


def test_amendments_are_never_a_comparator_or_a_subject() -> None:
    old = ten_q("OLD", REPORT - timedelta(days=365), date(2025, 8, 5))
    amended = [dict(r, form="10-Q/A") for r in old]
    [c] = run(frame(ten_q("NEW", REPORT, date(2026, 9, 30)), amended))
    assert c.status == cmp.NO_PRIOR  # the only year-ago filing is an amendment
    newer_amendment = [dict(r, form="10-Q/A", accession="AMD", known_from=date(2026, 10, 1),
                            accepted_session=date(2026, 10, 1))
                       for r in ten_q("X", REPORT, date(2026, 10, 1))]  # fmt: skip
    got = run(frame(ten_q("NEW", REPORT, date(2026, 9, 30)), old, newer_amendment))
    assert [g.accession for g in got] == ["NEW"]  # the amendment is not the latest subject


def test_a_short_or_under_floor_item_is_not_compared() -> None:
    old = ten_q("OLD", REPORT - timedelta(days=365), date(2025, 8, 5))
    new = filing("NEW", "10-Q", REPORT, date(2026, 9, 30),
                 {"I-2": body(words(150), 600), "II-1A": body(words(150, 150), 60)})  # fmt: skip
    [c] = run(frame(new, old))
    assert c.status == cmp.OK and c.items_compared == 1  # II-1A has 60 words: not compared
    short = ten_q("NEW", REPORT, date(2026, 9, 30))
    flagged = frame(short, old)
    flagged.loc[flagged["accession"].eq("OLD") & flagged["item"].eq("II-1A"), "quality"] = "SHORT"
    [c2] = run(flagged)
    assert c2.items_compared == 1


def test_nothing_passing_or_a_composite_under_500_words_is_not_comparable() -> None:
    old_short = filing("OLD", "10-Q", REPORT - timedelta(days=365), date(2025, 8, 5),
                       {"I-2": body(words(50), 80)})  # fmt: skip
    new = ten_q("NEW", REPORT, date(2026, 9, 30))
    [c] = run(frame(new, old_short))
    assert c.status == cmp.NOT_COMPARABLE and c.cosine is None and c.items_compared is None
    small = {"I-2": body(words(60), 150), "II-1A": body(words(60, 60), 150)}  # 300 words total
    year_ago = REPORT - timedelta(days=365)
    both = frame(filing("NEW", "10-Q", REPORT, date(2026, 9, 30), small),
                 filing("OLD", "10-Q", year_ago, date(2025, 8, 5), small))  # fmt: skip
    assert run(both)[0].status == cmp.NOT_COMPARABLE
    off = frame(new, filing("OLD", "10-Q", REPORT - timedelta(days=365), date(2025, 8, 5),
                            {"7": body(words(150), 600)}))  # fmt: skip
    assert run(off)[0].status == cmp.NOT_COMPARABLE  # no item in common for the form


def test_the_10k_risk_factor_pair_and_its_length_change() -> None:
    def annual(acc: str, report: date, known: date, n: int) -> list[dict[str, object]]:
        return filing(acc, "10-K", report, known,
                      {"1A": body(words(150), n), "7": body(words(150, 150), 300)})  # fmt: skip

    k_report = date(2026, 3, 31)
    [c] = compare_filings(
        frame(annual("NEW", k_report, date(2026, 9, 30), 600),
              annual("OLD", k_report - timedelta(days=365), date(2025, 5, 1), 450)),
        RECENT_FROM, SESSION,
    )  # fmt: skip
    assert c.form == "10-K" and c.status == cmp.OK and c.items_compared == 2
    assert c.rf_cosine == pytest.approx(1.0) and c.rf_len_change == pytest.approx(1 / 3)


def test_a_subject_must_be_known_in_the_recent_sessions_and_not_after_the_session() -> None:
    old = ten_q("OLD", REPORT - timedelta(days=365), date(2025, 8, 5))
    stale = ten_q("STALE", REPORT, date(2026, 9, 25))
    future = ten_q("FUTURE", REPORT, date(2026, 10, 5))
    assert run(frame(stale, old)) == []
    assert run(frame(future, old)) == []
    latest = run(frame(stale, ten_q("LATE", REPORT, date(2026, 10, 1)), old))
    assert [c.accession for c in latest] == ["LATE"]  # the latest known_from per company and form


def test_a_10k_and_a_10q_of_one_company_in_the_window_are_both_compared() -> None:
    """The gap of #720 (review finding 3): one comparison per company, so the 10-K's risk-factor
    comparison was never stored when a 10-Q was accepted in the same window."""
    k_report = date(2026, 3, 31)

    def annual(acc: str, report: date, known: date) -> list[dict[str, object]]:
        return filing(acc, "10-K", report, known,
                      {"1A": body(words(150), 600), "7": body(words(150, 150), 300)})  # fmt: skip

    got = run(frame(
        annual("K1", k_report, date(2026, 9, 29)),
        annual("K0", k_report - timedelta(days=365), date(2025, 5, 1)),
        ten_q("Q1", REPORT, date(2026, 10, 1)),
        ten_q("Q0", REPORT - timedelta(days=365), date(2025, 8, 5)),
    ))  # fmt: skip
    assert [(c.form, c.accession, c.status) for c in got] == [
        ("10-K", "K1", cmp.OK), ("10-Q", "Q1", cmp.OK)]  # fmt: skip
    assert got[0].rf_cosine == pytest.approx(1.0)


def test_the_constants_are_the_decided_ones() -> None:
    assert (cmp.MIN_ITEM_TOKENS, cmp.MIN_COMPOSITE_TOKENS) == (100, 500)
    assert cmp.WINDOW_DAYS == (330, 400) and cmp.RECENT_SESSIONS == 5
    assert cmp.ITEMS == {"10-K": ("1", "1A", "3", "7"), "10-Q": ("I-2", "II-1A")}


def test_a_reparsed_old_filing_never_replaces_the_real_new_filing_as_subject() -> None:
    """Review of #720: a parser re-run gives an old 10-K a late ``known_from``; the subject is
    chosen by the acceptance session, so the recent 10-Q stays the subject."""
    new_q = ten_q("NEWQ", REPORT, date(2026, 9, 28))
    old_k = [dict(r, form="10-K", accession="OLDK", report_date=REPORT - timedelta(days=240),
                  known_from=date(2026, 9, 29), accepted_session=date(2026, 2, 20))
             for r in ten_q("X", REPORT, date(2026, 9, 29))]  # fmt: skip
    got = run(frame(new_q, old_k))
    assert [(g.accession, g.known_from) for g in got] == [("NEWQ", date(2026, 9, 28))]


def test_the_subject_date_does_not_depend_on_the_order_of_a_filings_item_rows() -> None:
    rows = ten_q("NEW", REPORT, date(2026, 9, 30))
    rows[0] = dict(rows[0], known_from=date(2026, 10, 2))  # one item re-parsed later
    for ordered in (rows, rows[::-1]):
        [c] = run(frame(ordered))
        assert c.known_from == date(2026, 9, 30)


def _uncached(data: pd.DataFrame, recent_from: date, session: date) -> list[cmp.Comparison]:
    """The comparison as it was before the memo: a boolean filter per subject, every filing
    tokenised at every call (the reference the memoised path must equal)."""
    filings = cmp._filings(data)
    subjects = filings[[recent_from <= k <= session for k in filings["known_from"]]]
    subjects = subjects.sort_values(["cik", "form", "known_from", "accession"], kind="stable")
    subjects = subjects.drop_duplicates(["cik", "form"], keep="last")

    def counts(cik: str, accession: str, form: str) -> dict[str, cmp.Counter[str]]:
        rows = data[(data["cik"] == cik) & (data["accession"] == accession)]
        out = {}
        for item, quality, text in zip(rows["item"], rows["quality"], rows["text"], strict=True):
            if (
                item not in cmp.ITEMS[form]
                or quality != cmp.OK_QUALITY
                or not isinstance(text, str)
            ):
                continue
            found = cmp.term_counts(text)
            if sum(found.values()) >= cmp.MIN_ITEM_TOKENS:
                out[str(item)] = found
        return out

    def comparator(all_filings: pd.DataFrame, subject: pd.Series) -> pd.Series | None:
        report = subject["report_date"]
        if report is None:
            return None
        low, high = (report - timedelta(days=d) for d in cmp.WINDOW_DAYS[::-1])
        same = all_filings[
            (all_filings["cik"] == subject["cik"]) & (all_filings["form"] == subject["form"])
        ]
        same = same[[r is not None and low <= r <= high for r in same["report_date"]]]
        same = same[same["accession"] != subject["accession"]]
        if same.empty:
            return None
        gap = [abs((report - r).days - cmp.YEAR_DAYS) for r in same["report_date"]]
        best = same.assign(_gap=gap).sort_values(["_gap", "accession"], kind="stable").iloc[0]
        return best  # type: ignore[no-any-return]

    out = []
    for _, s in subjects.iterrows():
        base = {"cik": s["cik"], "accession": s["accession"], "form": s["form"],
                "known_from": s["known_from"]}  # fmt: skip
        prior = comparator(filings, s)
        if prior is None:
            out.append(cmp.Comparison(**base, prior_accession=None, status=cmp.NO_PRIOR))
            continue
        measured = cmp._measure(
            counts(s["cik"], s["accession"], s["form"]),
            counts(prior["cik"], prior["accession"], prior["form"]),
            s["form"],
        )
        out.append(cmp.Comparison(**base, prior_accession=prior["accession"], **measured))
    return out


def test_the_memoised_comparison_equals_the_uncached_one_over_a_run_of_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The memo changes no value: per session of a run (a filing leaving the five-session window,
    a late-arriving filing, a filing whose text changed under the same accession, a 10-K with the
    risk-factor pair) the frames are equal to the uncached path's, and each filing's words are
    tokenised once across the window, not once per session."""
    cmp._MEMO.clear()
    year_ago, base_known = date(2025, 6, 30), date(2025, 8, 5)
    k_items = {i: body(words(150, n), 600) for n, i in enumerate(("1", "1A", "3", "7"))}
    k_new = {**k_items, "1A": body(words(150, 400), 700)}
    full = frame(
        ten_q("OLD1", year_ago, base_known),
        ten_q("OLD2", year_ago, base_known, cik="0000000002", iid="EQ:BBB"),
        filing("OLDK", "10-K", date(2025, 12, 31), date(2026, 2, 20), k_items),
        ten_q("NEW1", REPORT, date(2026, 9, 29)),  # leaves the window after 5 sessions
        ten_q("NEW2", REPORT, date(2026, 10, 1), cik="0000000002", iid="EQ:BBB"),  # a different
        filing("NEWK", "10-K", date(2026, 12, 31), date(2026, 10, 5), k_new),
        ten_q("LATE", REPORT, date(2026, 10, 6), cik="0000000003", iid="EQ:CCC"),
    )  # fmt: skip
    full.loc[full["accession"] == "NEW2", "text"] = body(words(150, 300), 600)  # reworded
    sessions = [date(2026, 9, d) for d in (29, 30)]
    sessions += [date(2026, 10, d) for d in (1, 2, 5, 6, 7, 8, 9)]
    tokenised = []
    real = cmp.term_counts
    monkeypatch.setattr(cmp, "term_counts", lambda t: tokenised.append(t) or real(t))
    got, want, per_session = {}, {}, {}
    for s in sessions:
        known = full[[k <= s for k in full["known_from"]]]  # the late filing is absent before
        first = sessions[max(0, sessions.index(s) - 4)]
        before = len(tokenised)
        got[s] = compare_filings(known, first, s)
        per_session[s] = len(tokenised) - before
        assert compare_filings(known, first, s) == got[s]  # a repeat is a pure memo hit
        assert len(tokenised) == before + per_session[s]
        want[s] = _uncached(known, first, s)
    assert got == want
    assert got[date(2026, 10, 9)] != got[date(2026, 10, 2)]  # the fixture does move over time
    assert any(c.status == cmp.OK for c in got[date(2026, 10, 9)])
    assert sum(per_session.values()) <= 16  # 3 pairs, 2 + 2 + 4 + 8 texts: once each, all run
