"""The text cache backends (ADR 0041, amended): the same behaviour in memory and on disk, a
half-written or foreign file is a miss, a key is never a path."""

from pathlib import Path

import pytest

from algotrade.storage.backends.text_cache import LocalTextCache, MemoryTextCache


@pytest.fixture(params=["memory", "local"])
def cache(request: pytest.FixtureRequest, tmp_path: Path) -> LocalTextCache | MemoryTextCache:
    return MemoryTextCache() if request.param == "memory" else LocalTextCache(tmp_path / "c")


def test_a_text_is_kept_by_key_and_replaced(cache: LocalTextCache | MemoryTextCache) -> None:
    assert cache.get("2026-10-01_a") is None
    cache.put("2026-10-01_a", "one")
    cache.put("2026-10-01_b", "two")
    cache.put("2026-10-01_a", "three")
    assert (cache.get("2026-10-01_a"), cache.get("2026-10-01_b")) == ("three", "two")


def test_a_key_is_never_a_path(cache: LocalTextCache | MemoryTextCache) -> None:
    for key in ("../x", "a/b", ".hidden", ""):
        with pytest.raises(ValueError, match="invalid storage key"):
            cache.put(key, "x")


def test_the_cache_sits_beside_the_data_root(tmp_path: Path) -> None:
    cache = LocalTextCache.beside(tmp_path / "var" / "data")
    cache.put("k", "text")
    assert (tmp_path / "var" / "cache" / "explanations" / "k.json").read_text() == (
        '{"text": "text"}'
    )


@pytest.mark.parametrize("content", ["{not json", '{"text": 3}', "[]", ""])
def test_a_file_that_is_not_ours_is_a_miss(tmp_path: Path, content: str) -> None:
    cache = LocalTextCache(tmp_path)
    (tmp_path / "k.json").write_text(content)
    assert cache.get("k") is None
