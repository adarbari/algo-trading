"""The ``filing-text`` fetch pipeline: documents downloaded and parsed AHEAD of the task's loop.

The task reads one CIK after another (list, then one document per filing, parse, stage), so a
run went at ``1 / (latency + parse)`` documents a second, far under the SEC pacing floor. This
module runs the two slow halves of that loop concurrently and leaves the loop itself, its
per-filing failure handling, its ``known_from`` stamping and its staging, exactly as they were:

- a pool of ``LIST_THREADS`` threads lists each CIK (``list_fn``: the submissions request and the
  documents still to read), at most ``LOOKAHEAD`` CIKs ahead of the CIK the loop is on;
- a pool of ``threads`` threads downloads each document (``body_fn``, through the same shared
  SEC limiter every other request waits on, so the rate is the limiter's, never this module's);
- the parse (``parse_fn``, pure: HTML to the extraction document) runs in a pool of ``procs``
  worker processes (``spawn``: no fork after threads, no inherited limiter locks), because it is
  CPU in pure Python and the GIL would otherwise cap the run at one core. ``procs = 0`` parses in
  the download thread (tests, tiny runs).

The loop asks ``PrefetchedListing`` / ``PrefetchedText`` (``Source`` wrappers) for each payload
in its own order; a failure of a download or a parse is held and raised when the loop reaches
that document, so one bad filing fails the same item it failed before.

**SEC blocking**: a request that fails the way a block or an outage does (``blocking``) stops the
pipeline at once: no document not yet started is fetched, every later ask raises
``TransientFetchError`` (the loop's ``STOP_AFTER_FAILED`` then ends the run PARTIAL), and
``on_block`` holds the shared limiter so no process sends a request for a while. ``close`` (always
called by the task, before the run ends and releases the lock) cancels what is queued and waits
for what is running: no request leaves after the run is over.
"""

import multiprocessing
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import CancelledError, Future, ProcessPoolExecutor, ThreadPoolExecutor
from typing import Any

from algotrade_sources.framework.base import FetchRequest, Normalized, Source, TransientFetchError
from algotrade_sources.framework.series import FilingTextRequest

LIST_THREADS = 2  # listing requests in flight (one per CIK, plus older pages)
LOOKAHEAD = 6  # CIKs listed and fetched ahead of the one the loop is on (bounds the memory)
BLOCK_HOLD_S = 600.0  # SEC's rate-threshold block page lasts about ten minutes

type ListFn = Callable[[str], tuple[bytes | None, Sequence[FilingTextRequest]]]
type BodyFn = Callable[[FilingTextRequest], bytes | None]
type ParseFn = Callable[[bytes, str, str, tuple[str, ...]], bytes]


def _warm(_: int) -> int:
    return 0


class Prefetch:
    """Downloads and parses the documents of ``ciks`` ahead of the loop that consumes them in
    order (module doc). Build, ask ``listing`` / ``document``, ``close`` in a ``finally``."""

    def __init__(
        self,
        ciks: Sequence[str],
        list_fn: ListFn,
        body_fn: BodyFn,
        parse_fn: ParseFn,
        *,
        threads: int,
        procs: int,
        blocking: Callable[[Exception], bool],
        on_block: Callable[[], None] = lambda: None,
    ) -> None:
        self._ciks = list(ciks)
        self._list_fn, self._body_fn, self._parse_fn = list_fn, body_fn, parse_fn
        self._blocking, self._on_block = blocking, on_block
        self._stopped = threading.Event()
        self._lock = threading.Lock()
        self._lists: dict[str, Future[bytes | None]] = {}
        self._docs: dict[str, Future[bytes | None]] = {}
        self._next = 0  # the next CIK (index) not yet submitted
        self._procs: ProcessPoolExecutor | None = None
        if procs > 0:  # started before any thread: workers spawn clean, then are warm
            self._procs = ProcessPoolExecutor(
                procs, mp_context=multiprocessing.get_context("spawn")
            )
            list(self._procs.map(_warm, range(procs)))
        self._list_pool = ThreadPoolExecutor(LIST_THREADS, thread_name_prefix="ft-list")
        self._doc_pool = ThreadPoolExecutor(max(1, threads), thread_name_prefix="ft-doc")
        self._advance(LOOKAHEAD)

    # ------------------------------------------------------------------ the loop's side

    def listing(self, cik: str) -> bytes | None:
        """The submissions payload of ``cik`` (``None``: SEC has none); a failure re-raises."""
        self._advance(self._index(cik) + LOOKAHEAD)
        future = self._lists.get(cik)
        if future is None:  # never scheduled: the pipeline stopped first
            raise TransientFetchError("filing text fetch stopped: SEC is blocking us")
        return self._result(future)

    def document(self, accession: str) -> bytes | None:
        """The extraction document of one filing (``None``: a 404); a failure re-raises."""
        with self._lock:
            future = self._docs.pop(accession, None)
        if future is None:
            if self._stopped.is_set():  # its CIK was listed, then the pipeline stopped
                raise TransientFetchError("filing text fetch stopped: SEC is blocking us")
            raise LookupError(f"filing {accession} was not scheduled")
        return self._result(future)

    def close(self) -> None:
        """Stop, cancel what is queued, wait for what runs, release the workers."""
        self._stopped.set()
        self._cancel()
        self._list_pool.shutdown(wait=True, cancel_futures=True)
        self._doc_pool.shutdown(wait=True, cancel_futures=True)
        if self._procs is not None:
            self._procs.shutdown(wait=True, cancel_futures=True)

    # ------------------------------------------------------------------ the work

    def _index(self, cik: str) -> int:
        return self._ciks.index(cik)

    def _advance(self, upto: int) -> None:
        with self._lock:
            end = min(upto, len(self._ciks))
            while self._next < end and not self._stopped.is_set():
                cik = self._ciks[self._next]
                self._lists[cik] = self._list_pool.submit(self._list, cik)
                self._next += 1

    def _result(self, future: Future[bytes | None]) -> bytes | None:
        try:
            return future.result()
        except CancelledError:
            raise TransientFetchError("filing text fetch stopped: SEC is blocking us") from None

    def _list(self, cik: str) -> bytes | None:
        if self._stopped.is_set():
            raise TransientFetchError("filing text fetch stopped: SEC is blocking us")
        try:
            payload, requests = self._list_fn(cik)
        except Exception as exc:
            self._failed(exc)
            raise
        with self._lock:
            if not self._stopped.is_set():
                for request in requests:
                    self._docs[request.key] = self._doc_pool.submit(self._doc, request)
        return payload

    def _doc(self, request: FilingTextRequest) -> bytes | None:
        if self._stopped.is_set():
            raise TransientFetchError("filing text fetch stopped: SEC is blocking us")
        try:
            body = self._body_fn(request)
            if body is None:
                return None
            if self._procs is None:
                return self._parse_fn(body, request.key, request.form, request.items)
            return self._procs.submit(
                self._parse_fn, body, request.key, request.form, request.items
            ).result()
        except Exception as exc:
            self._failed(exc)
            raise

    def _failed(self, exc: Exception) -> None:
        """A request that fails like a block or an outage stops everything not yet started."""
        if self._blocking(exc) and not self._stopped.is_set():
            self._stopped.set()
            self._on_block()
            self._cancel()

    def _cancel(self) -> None:
        with self._lock:
            pending: list[Future[Any]] = [*self._lists.values(), *self._docs.values()]
        for future in pending:
            future.cancel()


class PrefetchedListing:
    """A ``Source`` whose ``fetch`` hands out the payload ``Prefetch`` already read."""

    def __init__(self, real: Source, prefetch: Prefetch) -> None:
        self._real, self._prefetch = real, prefetch
        self.name, self.dataset = real.name, real.dataset

    def fetch(self, request: FetchRequest) -> bytes | None:
        return self._prefetch.listing(request.key)

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        return self._real.normalize(request, payload)


class PrefetchedText:
    """A ``Source`` whose ``fetch`` hands out the extraction ``Prefetch`` already built."""

    def __init__(self, real: Source, prefetch: Prefetch) -> None:
        self._real, self._prefetch = real, prefetch
        self.name, self.dataset = real.name, real.dataset

    def fetch(self, request: FetchRequest) -> bytes | None:
        return self._prefetch.document(request.key)

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        return self._real.normalize(request, payload)
