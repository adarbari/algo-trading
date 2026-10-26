"""Task entry and declaration for the bought option history (ADR 0086).

Declared here, not in ``registry.py`` (which is at the file-length cap); the registry adds
``HISTORY_TASKS`` to ``TASKS``.
"""

from pathlib import Path

from algotrade.config.env import option_history_url
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.params import (
    FROM,
    SESSION,
    TO,
    Param,
    Params,
    Task,
    session_of,
)
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.options_history import importer
from algotrade_ingestion.tasks.verification import put_check

TABLES = (
    importer.QUOTES,
    importer.UNDERLYING,
    importer.STATS,
    importer.DIVIDENDS,
    importer.SPLITS,
)


def run_option_history_import(ctx: TaskContext, p: Params) -> RunRecord:
    options = importer.ImportOptions(
        url=option_history_url(p.get("url")),
        start=p.get("start"),
        end=p.get("end"),
        limit=p.get("limit"),
        dry_run=bool(p.get("dry_run")),
        force=bool(p.get("force")),
        init=bool(p.get("init")),
    )
    return importer.import_history(ctx, session_of(p), options)


def run_option_history_put_check(ctx: TaskContext, p: Params) -> RunRecord:
    options = put_check.PutCheckOptions(p.get("start"), p.get("end"), str(p.get("price") or "mid"))
    return put_check.put_check(ctx, option_history_url(p.get("url")), session_of(p), options)


HISTORY_TASKS = (
    Task(
        "option-history-import",
        "import bought HistoricalOptionData zips into the option-history store (ADR 0086)",
        importer,
        TABLES,
        run_option_history_import,
        sources=("hod_files",),
        settings="ALGOTRADE_OPTION_HISTORY_URL (the drive's store)",
        params=(
            SESSION,
            Param("source_dir", ("--source-dir",), Path, "folder holding the zips (any depth)"),
            Param("url", ("--url",), str, "history store URL (default: the env variable)"),
            FROM,
            TO,
            Param("limit", ("--limit",), int, "stop after N sessions"),
            Param("dry_run", ("--dry-run",), None, "parse and report, write nothing"),
            Param("force", ("--force",), None, "re-import sessions already held"),
            Param("init", ("--init",), None, "mark an existing directory as the history root"),
        ),
    ),
    Task(
        "option-history-put-check",
        "replicate Cboe's PUT index from the option history and compare it with the stored level",
        put_check,
        (),  # the result is the run record: no table
        run_option_history_put_check,
        settings="ALGOTRADE_OPTION_HISTORY_URL; macro series PUT; rates/treasury",
        params=(
            SESSION,
            Param("url", ("--url",), str, "history store URL (default: the env variable)"),
            FROM,
            TO,
            Param("price", ("--price",), str, "put price: mid (default) or bid"),
        ),
    ),
)
