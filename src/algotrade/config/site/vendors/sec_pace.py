"""``sources.toml [sec_edgar] filing_text_*``: the stepped pace of a filing-text run
(``libs/sources/.../framework/limiter.py`` ``StepLimiter``), validated.

Read by ``SourcesSettings.from_document`` (``config/site/settings.py``), the one loader; it lives
in its own module to keep that file under the length limit. 1 <= min_rps <= max_rps <=
``SEC_RPS_CAP`` (SEC's published fair-access limit); the two periods are > 0.
"""

from typing import Any

from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError

SEC_RPS_CAP = 10  # SEC fair access: at most 10 requests a second
MAX_RPS, MIN_RPS = 8, 5  # start / ceiling, and the floor an error stream steps down to
RECOVER_S, ERROR_COOLDOWN_S = 900.0, 30.0  # quiet seconds per step up; errors this close count once
KEYS: tuple[str, ...] = (
    "filing_text_max_rps",
    "filing_text_min_rps",
    "filing_text_recover_s",
    "filing_text_error_cooldown_s",
)


def filing_text_pace(section: Table) -> dict[str, Any]:
    """The ``SourcesSettings`` keyword arguments for the four ``filing_text_*`` pace keys."""
    top = section.integer("filing_text_max_rps", MAX_RPS, 1)
    low = section.integer("filing_text_min_rps", MIN_RPS, 1)
    if top > SEC_RPS_CAP:
        raise ConfigurationError(
            f"{section.where} filing_text_max_rps: expected <= {SEC_RPS_CAP} (SEC's cap), got {top}"
        )
    if low > top:
        raise ConfigurationError(
            f"{section.where} filing_text_min_rps: expected <= filing_text_max_rps ({top}), "
            f"got {low}"
        )
    periods = {
        "recover_s": section.number("filing_text_recover_s", RECOVER_S, 0),
        "error_cooldown_s": section.number("filing_text_error_cooldown_s", ERROR_COOLDOWN_S, 0),
    }
    for key, value in periods.items():
        if value <= 0:
            raise ConfigurationError(
                f"{section.where} filing_text_{key}: expected > 0, got {value}"
            )
    return {
        "sec_filing_text_max_rps": top,
        "sec_filing_text_min_rps": low,
        "sec_filing_text_recover_s": periods["recover_s"],
        "sec_filing_text_error_cooldown_s": periods["error_cooldown_s"],
    }
