"""The reader of paged raw payloads: JSON documents one after another."""

import pytest

from algotrade_sources.framework.pages import json_documents


def test_documents_are_read_in_order_whatever_separates_them() -> None:
    assert json_documents(b'{"a": 1}\n{"b": 2}\n\n  {"c": 3}', "X") == [
        {"a": 1},
        {"b": 2},
        {"c": 3},
    ]
    assert json_documents(b'\xef\xbb\xbf{"a": 1}', "X") == [{"a": 1}]  # a byte-order mark


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"", "X answer is empty"),
        (b"<html>", "X answer is not JSON"),
        (b"[1]", "X answer is not a"),
    ],
)
def test_an_unusable_answer_names_the_vendor(payload: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        json_documents(payload, "X")
