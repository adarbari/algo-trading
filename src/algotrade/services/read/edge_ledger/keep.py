"""Which ``results/edge_trades`` partitions the retention purge spares (ADR 0064 decision 2): the
read model's one statement of which run ledgers are still read, open and history runs alike."""

from datetime import date

from algotrade.config.edges.document import job_name
from algotrade.config.edges.loading import load_all_edges
from algotrade.config.edges.positions.chain import OPTION_HISTORY
from algotrade.config.site.settings import load_users
from algotrade.config.user import SITE_USER
from algotrade.data import StoreReader
from algotrade.services.read.evaluation.runs import is_exploratory
from algotrade.storage.configs.store import ConfigStore
from algotrade.storage.runs import RunRecord, RunStatus


def _newest(runs: list[RunRecord]) -> list[RunRecord]:
    done = [r for r in runs if r.status is RunStatus.COMPLETE]
    return sorted(done, key=lambda r: r.finished_at or r.started_at, reverse=True)


def ledger_keep(reader: StoreReader, configs: ConfigStore, since: date) -> frozenset[date]:
    """The ``results/edge_trades`` partitions the retention purge spares: those of every run that
    finished on or after ``since`` (the retention cutoff: a partition is dated by its run's range
    end, so an old range run yesterday is still recent), of every edge's canonical run (the latest
    committed site run at its frozen split), of the latest committed run of each edge and user
    (the declared users and those with config files), the same of each history run (its own run
    job, ADR 0088 d11) and of every run an edge's ``[evidence]`` cites."""
    declared = [u.user_id for u in load_users(configs).users]
    users = list(dict.fromkeys([SITE_USER, *declared, *configs.users()]))
    keep: set[date] = set()
    for edge in load_all_edges(configs):
        for user in users:
            done = _newest(reader.runs(job_name(edge.id, user)))
            history = _newest(reader.runs(job_name(edge.id, user, OPTION_HISTORY)))
            for runs in (done, history):
                keep.update(
                    r.session_date for r in runs if (r.finished_at or r.started_at).date() >= since
                )
                keep.update(r.session_date for r in runs[:1])
            if user == SITE_USER and edge.frozen_from is not None:
                canon = next(
                    (r for r in done if not is_exploratory(r.stats, edge.frozen_from)), None
                )
                if canon is not None:
                    keep.add(canon.session_date)
        if edge.evidence is not None:
            cited = reader.run(edge.evidence.run_id)
            if cited is not None:
                keep.add(cited.session_date)
    return frozenset(keep)
