"""What a vendor lets one API key do (responsibility ``vendor-access``): classify one un-retried
answer to a request for a name every plan covers as ``ALLOWED``, ``DENIED`` or ``LIMITED``.

- ``DENIED``: 401 / 402 / 403, or a 200 whose body is the vendor's "upgrade" / "restricted" text
  (FMP answers a premium parameter with 402 and a sentence; some vendors answer 200 with an
  error object);
- ``LIMITED``: 429, a body that says the quota is used, or an EMPTY payload (``[]``, ``{}``) for a
  large-cap every plan covers: a quota or tier cut that shows as no data, never as an error;
- ``ALLOWED``: a 200 with rows.

Any other answer (a 404, a 5xx, a 200 that is not JSON and says nothing) is not a verdict:
``UnclassifiedError``, so the caller keeps what it knew. The ``note`` is fixed text, never the
vendor's body, so a probe can store it without a key or a vendor sentence in it.

``AccessProbe`` is the base of a vendor's probe source: a table of endpoint -> URL (one request
each, for one covered large-cap) and ``probe(endpoint)``. The task ``analyst-probe`` runs it and
stores the verdicts (``analyst/vendor_access``); the vendor module only names the endpoints.
"""

import json
from collections.abc import Mapping

from algotrade_sources.framework.base import Access, FetchRequest, Normalized, Verdict
from algotrade_sources.framework.http import Answer, Http

DENIED_STATUSES = (401, 402, 403)
DENIED_WORDS = ("upgrade", "restricted", "premium", "don't have access", "not available under")
LIMITED_WORDS = ("limit reach", "rate limit", "too many requests", "quota")
MESSAGE_KEYS = ("Error Message", "error", "message")


class UnclassifiedError(RuntimeError):
    """The answer is neither a success nor a refusal the vendor documents (an outage, a bad
    request): the endpoint's access is unknown, not denied."""


def classify(answer: Answer) -> Verdict:
    """The verdict for ``answer`` (see the module docstring)."""
    code = answer.status
    if code in DENIED_STATUSES:
        return Verdict(Access.DENIED, code, 0, f"HTTP {code}")
    if code == 429:
        return Verdict(Access.LIMITED, code, 0, "HTTP 429")
    if code != 200:
        raise UnclassifiedError(f"HTTP {code}")
    rows, message = _payload(answer.body)
    if message is not None:
        text = message.lower()
        if any(word in text for word in LIMITED_WORDS):
            return Verdict(Access.LIMITED, code, 0, "body: quota used")
        if any(word in text for word in DENIED_WORDS):
            return Verdict(Access.DENIED, code, 0, "body: upgrade or restricted")
        raise UnclassifiedError("HTTP 200 with a message that is not a refusal")
    if rows == 0:
        return Verdict(Access.LIMITED, code, 0, "empty payload for a covered name")
    return Verdict(Access.ALLOWED, code, rows, "rows returned")


def _payload(body: bytes) -> tuple[int, str | None]:
    """(records, the vendor's message when the body is one). A plain-text body is a message."""
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        return 0, None
    try:
        data = json.loads(text)
    except ValueError:
        return 0, text
    if isinstance(data, list):
        return len(data), None
    if isinstance(data, dict):
        for key in MESSAGE_KEYS:
            if isinstance(data.get(key), str):
                return 0, data[key]
        return (1 if data else 0), None
    return 0, str(data)


class AccessProbe:
    """Implements ``sources.base.Source`` for a vendor's probe. ``endpoints`` maps an endpoint
    name (``estimates_annual``) to the URL asked for, built WITHOUT the key. ``probe`` makes ONE
    un-retried request (a probe must see the 402 / 429, not retry through it); ``fetch`` is the
    plain retried read of the same URL, keyed by endpoint."""

    name: str
    dataset = "vendor_access"
    endpoints: Mapping[str, str]

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the vendor's shared limiter (sources.toml)

    def probe(self, endpoint: str) -> Verdict:
        return classify(self._http.answer(self.endpoints[endpoint]))

    def fetch(self, request: FetchRequest) -> bytes | None:
        return self._http.get(self.endpoints[request.key])

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        return Normalized(request.session_date, {}, {"rows": _payload(payload)[0]}, {})
