"""Exception hierarchy. Catch ``AlgoTradeError`` to handle anything raised by this package."""


class AlgoTradeError(Exception):
    """Base class for all errors raised by algotrade."""


class DataValidationError(AlgoTradeError):
    """Market data failed a schema or sanity check."""

    def __init__(self, source: str, problems: list[str]) -> None:
        self.source = source
        self.problems = problems
        super().__init__(f"{source}: " + "; ".join(problems))


class ConfigurationError(AlgoTradeError):
    """A strategy, backtest or evaluation was configured incorrectly."""


class MissingDataError(AlgoTradeError):
    """Requested data is not in the store. Backtests and screens never fetch (ADR 0008)."""

    def __init__(self, dataset: str, detail: str, hint: str) -> None:
        self.dataset = dataset
        super().__init__(f"{dataset}: {detail}. To fill it: {hint}")


class ModelUnavailableError(AlgoTradeError):
    """The text model (ADR 0041: screener drafts, regime explanations) cannot answer now: it is
    off in the site settings, the provider refused or timed out, or its answer was not text. The
    message says which; it never carries a credential."""


class RateLimitedError(AlgoTradeError):
    """The caller asked for something too often (an on-demand model call, ADR 0041): the API
    answers 429 with ``retry_after_s`` as ``Retry-After``."""

    def __init__(self, what: str, retry_after_s: int) -> None:
        self.retry_after_s = retry_after_s
        super().__init__(f"{what}: too many requests, try again in {retry_after_s} s")


class PermissionDeniedError(AlgoTradeError):
    """The caller may not do this (ADR 0040): an ops read for a trader, or another user's job.
    The API answers 403 (REST) or ``FORBIDDEN`` (GraphQL)."""
