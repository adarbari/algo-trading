"""Save a user's train / test split (``config/users/<u>/evaluation.toml``; ADR 0053 amendment,
ED5f): ``split_from``, the first session of the test slice, or none to clear it (each edge's
own ``frozen_from`` is then the split). The date must be an exchange session (not a weekend or
holiday) from ``EARLIEST`` to ``latest``, the latest stored session: a split nobody can score
is refused, never saved. Only the user's own file is written, never the site's; the run that
uses it is the owner's ``algotrade-backtest evaluate-edges`` and its result is labelled
exploratory (the harness decides)."""

from datetime import date

from algotrade.config.edges.evaluation import EvaluationSettings, load_evaluation
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import is_session
from algotrade.services.authoring.scope import author
from algotrade.storage.configs.writer import ConfigWriter

EARLIEST = date(2000, 1, 1)  # no stored session is older


def save_split(
    writer: ConfigWriter, user: str, split_from: date | None, latest: date
) -> EvaluationSettings:
    """Replace ``user``'s ``split_from`` (None clears it); returns what is now saved."""
    who = author(user).user_id
    if split_from is not None and not (EARLIEST <= split_from <= latest and is_session(split_from)):
        raise ConfigurationError(
            f"split_from {split_from}: expected a trading session from {EARLIEST} to {latest}"
        )
    # Read first: a stored file this module cannot parse is reported, not overwritten blindly.
    load_evaluation(writer, who)
    writer.save_evaluation(who, {} if split_from is None else {"split_from": split_from})
    return EvaluationSettings(split_from)
