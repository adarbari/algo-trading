from algotrade.services.run_items import failed_items, normalise, status_code


def test_normalise_drops_the_key_urls_dates_and_numbers() -> None:
    message = "FETCH_ERROR: AAPL giving up on https://x.test/a?b=1 for 2026-10-02 after 3 tries"
    assert (
        normalise(message, "AAPL")
        == "FETCH_ERROR: <id> giving up on <url> for <date> after <n> tries"
    )


def test_normalise_replaces_the_key_only_as_a_whole_token() -> None:
    # A one-letter ticker inside a status code stays put.
    assert (
        normalise("STALE_DATA: chain is for 2026-10-01", "E") == "STALE_DATA: chain is for <date>"
    )
    assert normalise("NO_CHAIN for E", "E") == "NO_CHAIN for <id>"


def test_failed_items_groups_one_cause_across_keys() -> None:
    items = {
        "E": "STALE_DATA: chain is for 2026-10-01",
        "AB": "STALE_DATA: chain is for 2026-09-30",
    }
    items |= {"OK1": "OK"}
    [(reason, rows)] = failed_items(items)
    assert reason == "STALE_DATA: chain is for <date>"
    assert [k for k, _ in rows] == ["AB", "E"]
    assert status_code(rows[0][1]) == "STALE_DATA"
