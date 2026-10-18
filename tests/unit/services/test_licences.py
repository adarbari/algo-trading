"""The data-licence gate (ADR 0028): which licences a user holds, the licence of a catalogue
field (an expression feature inherits the strictest of what it reads) and the fields a user
may not see."""

from algotrade.config.site.users import UsersSettings
from algotrade.services.features import site_features
from algotrade.services.licences import (
    ALL_LICENCES,
    held_by,
    hidden_fields,
    hidden_stored,
    licence_of,
    recorded_licences,
)

USERS = UsersSettings.from_document(
    {
        "user": [
            {"id": "owner", "role": "admin", "licences": ["personal"]},
            {"id": "admin2", "role": "admin"},
            {"id": "trader", "role": "trader"},
        ]
    }
)
STORED = "rollup.ibkr_iv@v1.iv30_ibkr"
OVER_IT = "feature.vrp_iv30"  # coalesce(iv30_ibkr, iv30_cboe)
OPEN = "rollup.price_stats@v2.close"


def test_licences_come_from_the_registry_never_from_the_role() -> None:
    assert held_by(USERS, "owner") == ALL_LICENCES
    assert held_by(USERS, "admin2") == {"open"}  # an admin holds no more than a trader
    assert held_by(USERS, "trader") == {"open"}
    assert held_by(USERS, "nobody") == {"open"}


def test_an_expression_inherits_the_strictest_licence_of_what_it_reads() -> None:
    features = site_features()
    assert licence_of(features, STORED) == "personal"
    assert licence_of(features, OVER_IT) == "personal"
    assert licence_of(features, OPEN) == "open"
    assert licence_of(features, "instrument.sector") == "open"  # a reference fact
    # a name the catalogue does not resolve (a run owner's own feature) fails closed
    assert licence_of(features, "feature.no_such_feature") == "personal"


def test_hidden_fields_are_those_outside_the_held_licences() -> None:
    features, asked = site_features(), [STORED, OVER_IT, OPEN]
    assert hidden_fields(features, asked, {"open"}) == {STORED, OVER_IT}
    assert hidden_fields(features, asked, ALL_LICENCES) == frozenset()


def test_a_stored_run_is_gated_by_its_record_and_the_site_catalogue_never_a_viewers_name() -> None:
    features = site_features()
    recorded = recorded_licences(features, [OPEN, STORED, OVER_IT, OPEN])
    assert recorded == {OPEN: "open", STORED: "personal", OVER_IT: "personal"}
    own = "feature.owners_own"  # not in the site catalogue
    asked = [OPEN, STORED, own]
    assert hidden_stored(features, recorded, asked, {"open"}) == {STORED, own}  # no record: hidden
    assert hidden_stored(features, {own: "open"}, asked, {"open"}) == {STORED}
    assert hidden_stored(features, {own: "personal"}, asked, ALL_LICENCES) == frozenset()
    # the stricter of the record and today's licence wins; a run with no record reads by today's
    assert hidden_stored(features, {STORED: "open"}, [STORED], {"open"}) == {STORED}
    assert hidden_stored(features, None, [OPEN, STORED], {"open"}) == {STORED}
