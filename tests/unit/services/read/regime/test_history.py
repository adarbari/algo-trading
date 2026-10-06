"""``load_regime_bands`` (ADR 0047): each session's label from its own partition, consecutive
equal labels merged, a session with none an UNKNOWN band (never carried forward), a window
past the session refused."""

from datetime import date

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.read.regime.history import RegimeBand, load_regime_bands
from algotrade.services.read.regime.regime import RegimeLabel
from tests.unit.services.read.instruments.conftest import D0, D1, context, store_with
from tests.unit.services.read.regime.conftest import (
    SEP28,
    SEP29,
    SEP30,
    regime_ctx,
    with_regime,
    write_regime,
)

CALM, STRESS, UNKNOWN = RegimeLabel.CALM, RegimeLabel.STRESS, RegimeLabel.UNKNOWN


def test_consecutive_labels_are_merged_and_a_missing_session_is_unknown() -> None:
    # stored: 28 and 29 Sep CALM, nothing for 30 Sep, 1 Oct STRESS
    assert load_regime_bands(regime_ctx(), SEP28, D1) == (
        RegimeBand(SEP28, SEP29, CALM),
        RegimeBand(SEP30, SEP30, UNKNOWN),
        RegimeBand(D1, D1, STRESS),
    )


def test_a_window_inside_one_run_is_one_band_and_weekends_are_skipped() -> None:
    def long_calm(writer: object) -> None:
        for day in (date(2026, 9, 24), date(2026, 9, 25), date(2026, 9, 28), date(2026, 9, 29)):
            write_regime(writer, day, "CALM")

    ctx = with_regime(context(store_with(long_calm)))
    # Fri 25 Sep .. Mon 28 Sep: the weekend is not a session, so the run is not broken
    assert load_regime_bands(ctx, date(2026, 9, 24), SEP29) == (
        RegimeBand(date(2026, 9, 24), SEP29, CALM),
    )
    assert load_regime_bands(ctx, date(2026, 9, 26), date(2026, 9, 27)) == ()  # no session


def test_the_bands_are_read_as_of_the_requested_session_only() -> None:
    assert load_regime_bands(regime_ctx(D0), SEP28, D0) == (
        RegimeBand(SEP28, SEP29, CALM),
        RegimeBand(SEP30, SEP30, UNKNOWN),
    )
    with pytest.raises(ConfigurationError, match=f"end {D1} is after the session {D0}"):
        load_regime_bands(regime_ctx(D0), SEP28, D1)


def test_nothing_stored_or_no_group_yet_is_one_unknown_band() -> None:
    expected = (RegimeBand(SEP28, D1, UNKNOWN),)
    assert load_regime_bands(context(store_with()), SEP28, D1) == expected  # not in the catalogue
    assert load_regime_bands(with_regime(context(store_with())), SEP28, D1) == expected  # no data


def test_an_unrecognised_or_null_label_is_unknown() -> None:
    def odd(writer: object) -> None:
        write_regime(writer, SEP29, "SUNNY")
        write_regime(writer, SEP30, None)
        write_regime(writer, D1, "CRISIS")

    ctx = with_regime(context(store_with(odd)))
    assert load_regime_bands(ctx, SEP29, D1) == (
        RegimeBand(SEP29, SEP30, UNKNOWN),
        RegimeBand(D1, D1, RegimeLabel.CRISIS),
    )


def test_a_window_that_ends_before_it_starts_is_refused() -> None:
    with pytest.raises(ConfigurationError, match=f"end {SEP28} is before start {D1}"):
        load_regime_bands(regime_ctx(), D1, SEP28)
