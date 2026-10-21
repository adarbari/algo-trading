"""Task parameter and task declarations shared by the registry and the entry modules.

``Param`` / ``Task`` and the session helpers live here so the entry modules
(``entries_*.py``) import them without importing the registry (no cycle).
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from types import ModuleType
from typing import Any

from algotrade.storage.runs import RunRecord
from algotrade_ingestion.tasks.framework.run import TaskContext

type Params = Mapping[str, Any]


@dataclass(frozen=True)
class Param:
    """One task parameter; ``flags`` are its CLI spelling. ``kind=None`` is an on/off flag."""

    name: str
    flags: tuple[str, ...]
    kind: Callable[[str], Any] | None = str
    help: str = ""
    required: bool = False
    default: Any = None


@dataclass(frozen=True)
class Task:
    name: str
    description: str
    module: ModuleType  # the module that produces ``tables``
    tables: tuple[str, ...]
    run: Callable[[TaskContext, Params], RunRecord]
    sources: tuple[str, ...] = ()  # required, by name in ``TaskContext.sources``
    optional_sources: tuple[str, ...] = ()
    stepped: tuple[str, ...] = ()  # of ``sources``: the ones that take the stepped SEC limiter
    settings: str | None = None  # the config/site section it reads
    params: tuple[Param, ...] = ()
    # Workflows (nightly) skip the task when this returns a reason; explicit runs ignore it.
    skip: Callable[[TaskContext], str | None] | None = None


SESSION = Param("session", ("--date",), date.fromisoformat, "session (default: last session)")
FROM = Param("start", ("--from",), date.fromisoformat, "window start")
TO = Param("end", ("--to",), date.fromisoformat, "window end")


def session_of(params: Params) -> date:
    session = params.get("session")
    if not isinstance(session, date):
        raise ValueError("task parameter 'session' (a date) is required")
    return session


def symbols(p: Params, name: str = "symbols") -> list[str]:
    return [s.strip() for s in str(p.get(name) or "").split(",") if s.strip()]
