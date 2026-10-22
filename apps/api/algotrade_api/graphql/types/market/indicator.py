"""``RegimeIndicator`` (ADR 0047): one regime card with its value for the session, its verdict,
the threshold and direction of its rule, its linked how-line and the sources its value is
derived from (with their provenance). Split from ``regime.py`` (``MarketRegime``)."""

import asyncio
import datetime as dt
from typing import Self

import strawberry
from strawberry.scalars import JSON

from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.catalogue import FeatureFormat
from algotrade.services.read.regime import indicators, sources
from algotrade_api.graphql.offload import off_loop
from algotrade_api.graphql.types.instruments.feature import Unknown

strawberry.enum(
    indicators.IndicatorStatus, description="An indicator's own verdict: ON, OFF or UNKNOWN"
)
strawberry.enum(
    indicators.RiskDirection,
    description="Which side of its threshold an indicator warns on: HIGHER_IS_RISK (on above "
    "it) or LOWER_IS_RISK (on below it)",
)


@strawberry.type(description="One reading-list entry of an indicator card")
class IndicatorLink:
    title: str
    url: str

    @classmethod
    def of(cls, d: indicators.IndicatorLink) -> Self:
        return cls(title=d.title, url=d.url)


@strawberry.type(description="An indicator meter's display range, in the value's stored unit")
class IndicatorRange:
    min: float
    max: float

    @classmethod
    def of(cls, d: indicators.IndicatorRange) -> Self:
        return cls(min=d.min, max=d.max)


@strawberry.type(description="A run of a sentence: plain text, or a term linked to `url`")
class TextPart:
    text: str
    url: str | None

    @classmethod
    def of(cls, d: indicators.TextPart) -> Self:
        return cls(text=d.text, url=d.url)


class LazyProvenance:
    """The provenance of every source of one request, read on first use and shared: the
    provenance fields of all the indicators' sources resolve at once, and only the first of
    them does the stored-vintage read. The outcome is memoised, a failure too: a read that
    raises is not repeated by each of the other fields, they all re-raise the same error."""

    def __init__(self, ctx: ReadContext) -> None:
        self._ctx = ctx
        self._lock = asyncio.Lock()
        self._found: dict[str, sources.SeriesProvenance] | None = None
        self._error: Exception | None = None

    async def of(self, series: str | None) -> sources.SeriesProvenance:
        """The series' provenance (none stored, or a table: all fields null)."""
        async with self._lock:
            if self._found is None and self._error is None:
                try:
                    self._found = await off_loop(indicators.load_indicator_provenance, self._ctx)
                except Exception as exc:
                    self._error = exc
        if self._error is not None:
            raise self._error
        assert self._found is not None
        return self._found.get(series or "", sources.NO_PROVENANCE)


@strawberry.type(
    description="One source of an indicator's value, from the catalogue's lineage: a macro "
    "series (`series`: its key; `releaseLagDays`, `terms` and the provenance only for one) or "
    "a stored table. `lastObservation`: the latest observation the session knew, public on "
    "`vintageDate` (`vintageKind`: alfred or lagged); `firstVintage`: the series' earliest "
    "ALFRED vintage the session knew, before which the history is today's revised figures "
    "(null: an unrevised series, or nothing stored). `active`: it fed the value for the "
    "session (false: the source a per-session switch did not choose, e.g. SPY's bars when "
    "the S&P 500 trend came from the index level). The four provenance fields are read "
    "from the stored vintages only when a query selects them"
)
class IndicatorSource:
    label: str
    series: str | None
    cadence: str
    release_lag_days: int | None
    url: str | None
    licence: str
    terms: str | None
    active: bool
    lazy: strawberry.Private[LazyProvenance]

    @classmethod
    def of(cls, d: sources.IndicatorSource, lazy: LazyProvenance) -> Self:
        return cls(
            label=d.label,
            series=d.series,
            cadence=d.cadence,
            release_lag_days=d.release_lag_days,
            url=d.url,
            licence=d.licence,
            terms=d.terms,
            active=d.active,
            lazy=lazy,
        )

    async def _provenance(self) -> sources.SeriesProvenance:
        """The series' provenance, read (once per request) only when the query selects one of
        the four provenance fields."""
        return await self.lazy.of(self.series)

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The latest observation the session knew"
    )
    async def last_observation(self) -> dt.date | None:
        return (await self._provenance()).last_observation

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="When that observation became public"
    )
    async def vintage_date(self) -> dt.date | None:
        return (await self._provenance()).vintage_date

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="`alfred` or `lagged`"
    )
    async def vintage_kind(self) -> str | None:
        return (await self._provenance()).vintage_kind

    @strawberry.field(  # type: ignore[untyped-decorator]
        description="The series' earliest ALFRED vintage the session knew"
    )
    async def first_vintage(self) -> dt.date | None:
        return (await self._provenance()).first_vintage


@strawberry.type(description="What an indicator did before one episode, in one line")
class IndicatorBefore:
    episode: str
    line: str

    @classmethod
    def of(cls, d: indicators.IndicatorBefore) -> Self:
        return cls(episode=d.episode, line=d.line)


@strawberry.type(
    description="One indicator card with its value for the session: the plain-language text "
    "first, the technical name and `value` behind it. `value` is null exactly when `unknown` "
    "says why (format it with `format`); `status` is the indicator's own verdict and `changed` "
    "whether it differs from 5 sessions earlier (null: not stored; the verdict's field is "
    "`verdictFeature`). `pace`: slow (macro) or fast (market). `range` is the meter's display "
    "range and `threshold` the site's primary threshold (both in the value's stored unit; "
    "null: no rule in code), `direction` the side that is the risk; `how` the calculation as "
    "linked parts; `sources` where the value comes from. `range` and `threshold` format with "
    "`format`; when `format` is null (NOT_IN_CATALOGUE) the web falls back to NUMBER"
)
class RegimeIndicator:
    key: str
    pace: str
    plain_name: str
    technical_name: str
    one_liner: str
    why_it_matters: str
    what_on_means: str
    before: list[IndicatorBefore]
    lead_time: str
    false_alarms: str
    links: list[IndicatorLink]
    feature: str
    value: JSON | None
    unknown: Unknown | None
    format: FeatureFormat | None
    status: indicators.IndicatorStatus
    changed: bool | None
    range: IndicatorRange
    threshold: float | None
    direction: indicators.RiskDirection | None
    how: list[TextPart]
    sources: list[IndicatorSource]
    verdict_feature: str

    @classmethod
    def of(cls, d: indicators.RegimeIndicator, lazy: LazyProvenance) -> Self:
        return cls(
            key=d.key,
            pace=d.pace,
            plain_name=d.plain_name,
            technical_name=d.technical_name,
            one_liner=d.one_liner,
            why_it_matters=d.why_it_matters,
            what_on_means=d.what_on_means,
            before=[IndicatorBefore.of(b) for b in d.before],
            lead_time=d.lead_time,
            false_alarms=d.false_alarms,
            links=[IndicatorLink.of(link) for link in d.links],
            feature=d.feature,
            value=JSON(d.value),
            unknown=Unknown.of(d.unknown) if d.unknown is not None else None,
            format=d.format,
            status=d.status,
            changed=d.changed,
            range=IndicatorRange.of(d.range),
            threshold=d.threshold,
            direction=d.direction,
            how=[TextPart.of(p) for p in d.how],
            sources=[IndicatorSource.of(s, lazy) for s in d.sources],
            verdict_feature=d.verdict_feature,
        )
