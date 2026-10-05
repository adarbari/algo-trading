"""Site settings for the IBKR session (``sources.toml [ibkr]``): the typed section and its
loader, split from ``settings.py`` (re-exported there) to keep that file under the length limit."""

from dataclasses import dataclass

from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError

# IB market data types: 1 live (needs a subscription), 3 delayed (free, 15-20 minutes).
IBKR_MARKET_DATA_TYPES = (1, 2, 3, 4)


@dataclass(frozen=True)
class IbkrSettings:
    """``[ibkr]`` beyond ``enabled`` / ``min_interval_s`` (the IB Gateway session; host, port
    and client id come from the environment, ``config/env.py``). Pacing follows IBKR's rules:
    every message waits ``min_interval_s`` (50 messages/s), every historical-data request also
    waits ``historical_min_interval_s`` (>= 0; default 10 s = 60 requests per 10 minutes, the
    rule IBKR documents for bars of 30 s or less; daily bars are soft throttled, so the owner
    may trial a shorter gap while watching timeouts and error 162)."""

    historical_min_interval_s: float = 10.0
    market_data_type: int = 3  # 1 live, 3 delayed
    connect_timeout_s: float = 10.0
    request_timeout_s: float = 60.0
    stream_wait_s: float = 4.0  # how long a streamed tick (dividends) may take to arrive
    # IBKR enrichment (ADR 0028): contract ids, IB's IV history and the nightly IV snapshot
    contracts_refresh_days: int = 30  # re-resolve each conid once per window (spread by key)
    contracts_batch: int = 25  # contracts qualified per request
    iv_batch: int = 50  # IV streams open together (under the account's market-data lines)
    iv_history_days: int = 730  # calendar days of IV history a backfill fetches per underlying
    iv_backfill_per_night: int = 100  # underlyings without IV history the nightly backfills
    # The API's live option quotes (ADR 0028): cache, strikes per request, failing fast
    live_cache_s: float = (
        60.0  # an answer is reused for this long (per underlying, expiry, strikes)
    )
    live_strikes: int = 10  # strikes nearest the underlying asked for when none are named
    live_max_strikes: int = 20  # most strikes one request may name (x 2 rights = contracts)
    live_timeout_s: float = 20.0  # longest a request waits for IB Gateway before the fallback
    live_retry_s: float = 30.0  # after the gateway fails, requests fall back at once this long


def load_ibkr(section: Table) -> IbkrSettings:
    d = IbkrSettings()
    kind = section.integer("market_data_type", d.market_data_type, 1)
    if kind not in IBKR_MARKET_DATA_TYPES:
        raise ConfigurationError(
            f"{section.where} market_data_type: expected 1 (live), 2 (frozen), 3 (delayed) "
            f"or 4 (delayed frozen), got {kind}"
        )
    return IbkrSettings(
        historical_min_interval_s=section.number(
            "historical_min_interval_s", d.historical_min_interval_s, 0
        ),
        market_data_type=kind,
        connect_timeout_s=section.number("connect_timeout_s", d.connect_timeout_s, 0),
        request_timeout_s=section.number("request_timeout_s", d.request_timeout_s, 0),
        stream_wait_s=section.number("stream_wait_s", d.stream_wait_s, 0),
        contracts_refresh_days=section.integer(
            "contracts_refresh_days", d.contracts_refresh_days, 0
        ),
        contracts_batch=section.integer("contracts_batch", d.contracts_batch, 1),
        iv_batch=section.integer("iv_batch", d.iv_batch, 1),
        iv_history_days=section.integer("iv_history_days", d.iv_history_days, 1),
        iv_backfill_per_night=section.integer("iv_backfill_per_night", d.iv_backfill_per_night, 0),
        live_cache_s=section.number("live_cache_s", d.live_cache_s, 0),
        live_strikes=section.integer("live_strikes", d.live_strikes, 1),
        live_max_strikes=section.integer("live_max_strikes", d.live_max_strikes, 1),
        live_timeout_s=section.number("live_timeout_s", d.live_timeout_s, 0),
        live_retry_s=section.number("live_retry_s", d.live_retry_s, 0),
    )
