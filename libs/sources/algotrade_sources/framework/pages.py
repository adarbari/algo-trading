"""Paged raw payloads: a vendor answer that took several requests is saved as its JSON
documents one after another (``b"\\n".join(pages)``); this is the one reader of that form.

FRED (observations, release dates) and SEC (a company's submissions plus its older pages) save
their pages this way, so ``normalize`` can rerun from the raw file alone.
"""

import json
from typing import Any


def json_documents(payload: bytes, vendor: str) -> list[dict[str, Any]]:
    """The JSON object documents in ``payload`` (one per page, whitespace between); ``vendor``
    names the source in the error of an answer that is empty, not JSON or not an object."""
    text, decoder, pos, documents = payload.decode("utf-8-sig"), json.JSONDecoder(), 0, []
    while True:
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text):
            break
        try:
            document, pos = decoder.raw_decode(text, pos)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{vendor} answer is not JSON: {exc}") from exc
        if not isinstance(document, dict):
            raise ValueError(f"{vendor} answer is not a JSON object")
        documents.append(document)
    if not documents:
        raise ValueError(f"{vendor} answer is empty")
    return documents
