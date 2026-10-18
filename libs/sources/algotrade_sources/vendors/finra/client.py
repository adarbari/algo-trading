"""FINRA Query API pieces shared by both sources: the URL, the filter transport and the pager.

``https://api.finra.org/data/group/otcMarket/name/<dataset>``. The API answers anonymously
(no credential is held or sent here). A GET ignores filters, so a filtered read is a POST with
the filter in a JSON body; the sources stay on ``Http.get`` and name the filter in the URL
(``?limit=5000&offset=0&equal.settlementDate=2026-09-30``), which ``query_transport`` turns into
that POST. Pages are 5,000 rows (the sync cap) and ``offset`` stops at 500,000; one partition
(a settlement or trade date) is read page by page into one JSON list, the raw payload.

Terms (``docs/data/vendors.md``): the API terms carry no machine-learning clause but the finra.org
website terms do, so the stored rows are marked ``no_ml`` in ``architecture/tables.toml`` and no
learned scorer may read them.
"""

import json
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

from algotrade_sources.framework.http import (
    DEFAULT_USER_AGENT,
    Http,
    Transport,
    json_post_transport,
)

HOST = "https://api.finra.org/data/group/otcMarket/name"
PAGE = 5000  # rows a sync request returns at most
OFFSET_CAP = 500_000  # the API refuses a larger ``offset``
EQUAL = "equal."


def url(dataset: str, field: str, value: str, offset: int) -> str:
    """The read of one page of ``dataset`` where ``field`` equals ``value``."""
    query = urlencode({"limit": PAGE, "offset": offset, f"{EQUAL}{field}": value})
    return f"{HOST}/{dataset}?{query}"


def query_transport(headers: dict[str, str]) -> Transport:
    """A GET transport that sends the URL's ``limit`` / ``offset`` / ``equal.<field>`` as the
    JSON POST body the Query API filters by; an empty answer (204) is an empty body."""
    post = json_post_transport(DEFAULT_USER_AGENT, headers=headers)

    def get(url_: str) -> bytes:
        parts = urlsplit(url_)
        filters: list[dict[str, Any]] = []
        body: dict[str, Any] = {}
        for name, value in parse_qsl(parts.query):
            if name.startswith(EQUAL):
                filters.append(
                    {"compareType": "EQUAL", "fieldName": name[len(EQUAL) :], "fieldValue": value}
                )
            else:
                body[name] = int(value)
        body["compareFilters"] = filters
        base = f"{parts.scheme}://{parts.netloc}{parts.path}"
        return post(base, json.dumps(body).encode())

    return get


def read_partition(http: Http, dataset: str, field: str, value: str) -> bytes | None:
    """Every row of ``dataset`` whose ``field`` is ``value``, as one JSON list; ``None`` when
    FINRA holds none (no such partition)."""
    rows: list[Any] = []
    for offset in range(0, OFFSET_CAP + 1, PAGE):
        payload = http.get(url(dataset, field, value, offset))
        page = json.loads(payload) if payload and payload.strip() else []
        if not isinstance(page, list):
            raise ValueError(f"FINRA {dataset}: expected a JSON list, got {str(page)[:120]!r}")
        rows.extend(page)
        if len(page) < PAGE:
            return json.dumps(rows, separators=(",", ":")).encode() if rows else None
    raise ValueError(f"FINRA {dataset} {value}: more than {OFFSET_CAP} rows")


def records(payload: bytes) -> list[dict[str, Any]]:
    """The JSON list ``read_partition`` returned, as records."""
    data = json.loads(payload)
    if not isinstance(data, list):
        raise ValueError(f"expected a JSON list, got {str(data)[:120]!r}")
    return [r for r in data if isinstance(r, dict)]
