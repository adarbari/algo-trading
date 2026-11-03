"""The ``dossier-import`` task: the reviewed deep-dive dossiers of names (TOML, one per name;
ADR 0050 decision 6, EV5) -> ``instruments/factors``, ``events/factor_occurrence`` and the
reviewed causes in ``events/attribution`` (``source = "analyst_review"``).

``--path`` is one file or a folder (every ``*.toml`` under it, one import). Each file is validated
whole by ``services.attributing.dossier`` against the import session's reference snapshot (tickers
resolved through its ``SymbolResolver``, never an ``EQ:`` string built here); one problem in any
file
fails the run and stores nothing, and the error lists every problem of every file. Two files for one
name in an import are a problem too. Every row's ``known_from`` is the import session: a session
before it never sees the dossier (ADR 0050 decision 3). An import writes each name's WHOLE dossier,
so a reader takes the latest ``known_from`` per name (``instruments/factors`` note). The task
stores a dossier already stored again (the tables merge on their keys): a rerun on one session
changes nothing."""

import tomllib
from datetime import date
from pathlib import Path

import pandas as pd

from algotrade.services.attributing.dossier import (
    SOURCE,
    Dossier,
    DossierError,
    parse_dossier,
)
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.schemas import (
    ATTRIBUTION_EVENTS,
    FACTOR_OCCURRENCE_EVENTS,
    FACTOR_REFERENCE,
)
from algotrade_ingestion.tasks.framework.run import IngestRun, TaskContext

TASK = "dossier-import"
FACTORS = FACTOR_REFERENCE.name
OCCURRENCES = FACTOR_OCCURRENCE_EVENTS.name
ATTRIBUTIONS = ATTRIBUTION_EVENTS.name
SOURCE_NAME = "dossier"  # the ``source`` of the factor and occurrence rows


def dossier_files(path: Path) -> list[Path]:
    """The dossier files at ``path``: the file itself, or every ``*.toml`` below a folder."""
    if path.is_file():
        return [path]
    files = sorted(path.rglob("*.toml")) if path.is_dir() else []
    if not files:
        raise FileNotFoundError(f"no dossier (*.toml) at {path}")
    return files


def read_dossiers(run: IngestRun, session: date, path: Path) -> list[Dossier]:
    """Every dossier at ``path``, validated; ``DossierError`` with all problems otherwise."""
    resolver = run.resolver(session)
    problems: list[str] = []
    found: dict[str, Path] = {}
    out: list[Dossier] = []
    for file in dossier_files(path):
        try:
            doc = tomllib.loads(file.read_text())
            dossier = parse_dossier(
                doc, session, lambda t: resolver.id_for(t) if resolver.knows(t) else None
            )
        except (tomllib.TOMLDecodeError, DossierError) as exc:
            problems += [f"{file}: {p}" for p in getattr(exc, "problems", [str(exc)])]
            continue
        if dossier.instrument_id in found:
            problems.append(
                f"{file}: {dossier.instrument_id} is also in {found[dossier.instrument_id]}"
            )
        found[dossier.instrument_id] = file
        out.append(dossier)
    if problems:
        raise DossierError(problems)
    return out


def ingest_dossiers(ctx: TaskContext, session: date, path: Path) -> RunRecord:
    """Validate and store the dossiers at ``path`` as of the import ``session``."""
    with IngestRun(ctx, TASK, session) as run:
        dossiers = read_dossiers(run, session, path)
        factors = [
            {
                "instrument_id": d.instrument_id,
                "known_from": session,
                "reviewed_on": d.reviewed_on,
                **f,
            }
            for d in dossiers
            for f in d.factors
        ]
        occurrences = [{**o, "known_from": session} for d in dossiers for o in d.occurrences]
        attributions = [{**a, "known_from": session} for d in dossiers for a in d.attributions]
        run.stage(FACTORS, "dossiers", pd.DataFrame(factors), SOURCE_NAME)
        if occurrences:
            run.stage(OCCURRENCES, "dossiers", pd.DataFrame(occurrences), SOURCE_NAME)
        if attributions:
            run.stage_sessions(ATTRIBUTIONS, "dossiers", pd.DataFrame(attributions), SOURCE)
        counts = {
            "factors": run.publish(FACTORS),
            "occurrences": run.publish(OCCURRENCES),
            "attributions": sum(run.publish_sessions(ATTRIBUTIONS).values()),
        }
        for d in dossiers:
            run.record_item(d.instrument_id, f"OK: reviewed {d.reviewed_on}")
        run.stats.update(names=len(dossiers), **counts)
    return run.record
