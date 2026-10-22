"""The run a rule screen is compared with when its ``results/screen_runs`` row is written: the
config's latest run in the previous stored session of ``results/rule_screen`` (the read model's
rule, ``load_previous_run``), found from the run records of the config's screen job and that
run's own file, never the session's every run."""

from datetime import date

from algotrade.data import StoreReader
from algotrade.services.screening.rule_results import RULE_SCREEN, Lineage
from algotrade.storage.tables.schemas import result_table

TABLE = result_table(RULE_SCREEN)


def previous_lineage(reader: StoreReader, job: str, session_date: date) -> Lineage:
    """The lineage of the run of ``job`` (its screen job name) for ``session_date``: the newest
    run record of the job in the latest earlier session of ``results/rule_screen`` that stored
    rows. An empty ``Lineage``: no earlier session, or the screener has no rows in it."""
    earlier = [d for d in reader.dates(TABLE) if d < session_date]
    if not earlier:
        return Lineage()
    day = max(earlier)
    for record in sorted(reader.runs(job, day), key=lambda r: r.started_at, reverse=True):
        rows = reader.read_run(TABLE, day, record.run_id, ("decision", "config_version"))
        if rows is None or rows.empty:
            continue
        versions = rows["config_version"].dropna()
        return Lineage(
            previous_run_id=record.run_id,
            previous_session=day,
            previous_version=int(versions.iloc[0]) if not versions.empty else None,
            previous_decisions={
                str(i): str(d) for i, d in zip(rows["instrument_id"], rows["decision"], strict=True)
            },
        )
    return Lineage()
