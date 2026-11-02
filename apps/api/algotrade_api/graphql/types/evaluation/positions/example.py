"""``ExamplePosition`` (ADR 0083 decision 3, ADR 0088 design 2.8): thin types over
``services/read/evaluation/positions/example.py``, served as ``Edge.examplePositions``. Every
figure and reason is the read model's; nothing is formatted or derived here."""

from datetime import date
from typing import Self

import strawberry

from algotrade.services.read.evaluation.positions import example
from algotrade_api.graphql.types.evaluation.exit_rule import Stop
from algotrade_api.graphql.types.instruments.feature import Unknown

strawberry.enum(example.Shape, name="ExampleShape", description="The shape of a share pick")


@strawberry.type(
    description="What a share setup's rule would open on one pick at the served session, never "
    "a size: `referenceClose` (the session's close; the entry is `entrySession`'s close), "
    "`stopPrice` from `stop` (the setup's exit rule), `exitSession` (the hold counted from the "
    "entry, a book's next rebalance). Each null figure says why in its `...Unknown`; "
    "`borrowAssumed`: a short pick"
)
class ExamplePosition:
    edge_id: str
    instrument_id: str
    shape: example.Shape
    reference_close: float | None
    stop_price: float | None
    stop: Stop | None
    entry_session: date | None
    exit_session: date | None
    borrow_assumed: bool
    close_unknown: Unknown | None
    stop_unknown: Unknown | None
    exit_unknown: Unknown | None

    @classmethod
    def of(cls, d: example.ExamplePosition) -> Self:
        return cls(
            edge_id=d.edge_id, instrument_id=d.instrument_id, shape=d.shape,
            reference_close=d.reference_close, stop_price=d.stop_price,
            stop=Stop.of(d.stop) if d.stop is not None else None,
            entry_session=d.entry_session, exit_session=d.exit_session,
            borrow_assumed=d.borrow_assumed,
            close_unknown=Unknown.of(d.close_unknown) if d.close_unknown else None,
            stop_unknown=Unknown.of(d.stop_unknown) if d.stop_unknown else None,
            exit_unknown=Unknown.of(d.exit_unknown) if d.exit_unknown else None,
        )  # fmt: skip
