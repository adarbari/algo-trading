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
    """The text model behind a screener draft (ADR 0040) cannot answer now: drafting is off in
    the site settings, the provider refused or timed out, or its answer was not text. The
    message says which; it never carries a credential."""
