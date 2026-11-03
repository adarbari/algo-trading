"""The dossier schema's validation: a good dossier yields its rows stamped for the import session,
and every kind of problem is listed together (nothing is stored from a file with one)."""

import copy
import tomllib
from datetime import UTC, date, datetime

import pytest

from algotrade.services.attributing.dossier import SOURCE, DossierError, parse_dossier

SESSION = date(2026, 11, 3)
GOOD = """
schema = 1
ticker = "MU"
reviewed_on = 2026-11-02

[[factor]]
id = "hbm-pricing"
kind = "commodity"
description = "DRAM and HBM contract prices set the margin."
  [[factor.occurrence]]
  date = 2026-10-24
  label = "SK Hynix results"
  [[factor.watch]]
  expected_from = 2026-12-01
  expected_to = 2026-12-20
  label = "Korean export data"

[[factor]]
id = "old-capex"
kind = "financing"
status = "retired"
description = "The 2023 capex worry, no longer driving."

[[attribution]]
date = 2026-10-26
cause = "read_across"
text = "SK Hynix guided HBM supply up."
confidence = 0.7
evidence = "SK Hynix Q3 call, 2026-10-24"
"""


def _doc(text: str = GOOD) -> dict:
    return tomllib.loads(text)


def _resolve(ticker: str) -> str | None:
    return {"MU": "EQ:MU"}.get(ticker)


def _problems(doc: dict) -> list[str]:
    with pytest.raises(DossierError) as info:
        parse_dossier(doc, SESSION, _resolve)
    return info.value.problems


def test_a_good_dossier_yields_factors_occurrences_and_a_reviewed_attribution() -> None:
    d = parse_dossier(_doc(), SESSION, _resolve)
    assert d.instrument_id == "EQ:MU" and d.reviewed_on == date(2026, 11, 2)
    assert [f["status"] for f in d.factors] == ["active", "retired"]
    kinds = {o["date_kind"]: o for o in d.occurrences}
    assert kinds["dated"]["ts"] == datetime(2026, 10, 24, tzinfo=UTC)
    assert kinds["window"]["window_end"] == date(2026, 12, 20)
    (a,) = d.attributions
    assert a["cause_class"] == "read_across" and a["session_date"] == date(2026, 10, 26)
    assert SOURCE == "analyst_review"


@pytest.mark.parametrize(
    ("mutate", "fragment"),
    [
        (lambda d: d.update(ticker="ZZZZ"), "not in the reference snapshot"),
        (lambda d: d.update(schema=2), "`schema` must be 1"),
        (lambda d: d.update(reviewed_on=date(2026, 11, 4)), "after the import session"),
        (lambda d: d["factor"][0].update(kind="vibes"), "kind 'vibes'"),
        (lambda d: d["factor"][0].update(id="Bad Id"), "not a slug"),
        (lambda d: d["factor"][1].update(id="hbm-pricing"), "duplicate factor id"),
        (lambda d: d["factor"][0].update(status="paused"), "not active or retired"),
        (
            lambda d: d["factor"][0]["watch"][0].update(expected_to=date(2026, 11, 30)),
            "before expected_from",
        ),
        (
            lambda d: d["factor"][0]["watch"][0].update(
                expected_from=date(2026, 10, 1), expected_to=date(2026, 10, 9)
            ),
            "before the import session",
        ),
        (lambda d: d["attribution"][0].update(cause="astrology"), "not in the taxonomy"),
        (lambda d: d["attribution"][0].update(confidence=1.5), "outside 0..1"),
        (lambda d: d["attribution"][0].update(date=date(2026, 10, 25)), "not a trading session"),
        (lambda d: d["attribution"][0].update(date=date(2026, 11, 20)), "after the review"),
        (lambda d: d["attribution"][0].pop("evidence"), "`evidence` must be"),
        (
            lambda d: d["factor"][0]["occurrence"].append(
                {"date": date(2026, 10, 24), "label": "x"}
            ),
            "already has an entry",
        ),
        (
            lambda d: d["factor"][0]["watch"][0].update(expected_from=date(2026, 10, 24)),
            "already has an entry",
        ),
        (lambda d: d["attribution"].append(dict(d["attribution"][0])), "attributed twice"),
        (lambda d: d.update(factor=[]), "at least one [[factor]]"),
    ],
)
def test_each_kind_of_problem_is_reported(mutate, fragment: str) -> None:
    doc = copy.deepcopy(_doc())
    mutate(doc)
    assert any(fragment in p for p in _problems(doc)), _problems(doc)


def test_every_problem_is_listed_not_just_the_first() -> None:
    doc = _doc()
    doc["ticker"] = "ZZZZ"
    doc["factor"][0]["kind"] = "vibes"
    doc["attribution"][0]["cause"] = "astrology"
    assert len(_problems(doc)) >= 3
