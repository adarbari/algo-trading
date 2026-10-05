"""The dataloaders of one request (ADR 0037): a type resolves a child object or a per-object
read only through one, so a list of N parents costs one read, not N (no N+1).

``features``: keyed ``(instrument_id, names)``; one ``load_feature_values`` call per distinct
``names`` across the batch. The other loaders of the spec (``instruments``, ``events``,
``screener_latest_run``, ``holdings``) arrive with the read-model PRs that first need them."""

from collections.abc import Sequence

from anyio import to_thread
from strawberry.dataloader import DataLoader

from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.features import FeatureValue, load_feature_values

FeatureKey = tuple[str, tuple[str, ...]]  # (instrument_id, catalogue names in the order asked)


async def _feature_values(
    ctx: ReadContext, keys: Sequence[FeatureKey]
) -> list[tuple[FeatureValue, ...] | BaseException]:
    by_names: dict[tuple[str, ...], list[str]] = {}
    for iid, names in keys:
        by_names.setdefault(names, []).append(iid)
    found: dict[FeatureKey, tuple[FeatureValue, ...] | BaseException] = {}
    for names, ids in by_names.items():
        try:  # off the event loop: the read is parquet and pandas work
            values = await to_thread.run_sync(load_feature_values, ctx, ids, names)
        except Exception as error:  # the error is the result of each key that asked
            found.update({(iid, names): error for iid in ids})
        else:
            found.update({(iid, names): values[iid] for iid in ids})
    return [found[key] for key in keys]


class Loaders:
    """The dataloaders of one request, over its ``ReadContext`` (one session)."""

    def __init__(self, ctx: ReadContext) -> None:
        async def feature_values(
            keys: list[FeatureKey],
        ) -> list[tuple[FeatureValue, ...] | BaseException]:
            return await _feature_values(ctx, keys)

        self.features: DataLoader[FeatureKey, tuple[FeatureValue, ...]] = DataLoader(
            load_fn=feature_values
        )
