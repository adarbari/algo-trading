"""The move attribution's settings (``config/site/events/attribution.toml``, ADR 0050 EV4b): how
many big movers the nightly asks Massive news and the text model about. The free tier is 5 requests
a minute (``[massive] min_interval_s``), so 40 movers are about 8 minutes under the ingest lock; 0
turns the headline source off (the filing causes are unaffected). Missing file: the default."""

from dataclasses import dataclass
from typing import Any

from algotrade.config.site.events.scope import Documents
from algotrade.config.site.fields import Table, reject_secrets

FOLDER = "events"
NAME = "attribution"
KEYS = ("news_per_night",)
DEFAULT_NEWS_PER_NIGHT = 40


@dataclass(frozen=True)
class AttributionSettings:
    news_per_night: int = DEFAULT_NEWS_PER_NIGHT  # movers asked for headlines a night (0: none)

    @classmethod
    def from_document(cls, doc: dict[str, Any] | None) -> "AttributionSettings":
        where = f"{FOLDER}/{NAME}.toml"
        reject_secrets(doc or {}, where)
        root = Table(doc, where)
        root.only(KEYS)
        return cls(root.integer("news_per_night", DEFAULT_NEWS_PER_NIGHT, 0))


def load_attribution(configs: Documents | None) -> AttributionSettings:
    """``config/site/events/attribution.toml``; no store or no file: the defaults."""
    if configs is None:
        return AttributionSettings()
    doc = configs.load("site", FOLDER, NAME)
    return AttributionSettings.from_document(None if doc is None else dict(doc))
