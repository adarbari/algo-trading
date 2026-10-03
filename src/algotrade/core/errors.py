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
