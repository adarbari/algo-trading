"""``ClaudeCli``: a text-model provider that runs Claude Code headless (``claude -p``) on this
machine under the owner's own login (ADR 0041, amended 2026-10-08). System text and user text in,
a ``Completion`` out (the answer, the tokens, the notional cost the CLI reports), like
``ChatCompletions``. The login is the logged-in keychain entry of the user running the API; no
token or key is passed and none is accepted: the child gets only ``HOME``, ``USER``, ``PATH`` and
``LANG`` (``config.env.claude_cli_env``). ``--bare`` is never used: it skips the keychain read, so
the login would not be found. The child is locked down: no tools (``--tools ""``), no user,
project or local settings (``--setting-sources ""``), and, with ``--safe-mode`` (CLAUDE.md,
skills, installed plugins and their hooks, MCP servers, custom commands and agents all off; the
login stays), ``--strict-mcp-config``, no session kept, an empty temporary directory as its
working directory, the prompt on stdin, an argv list never a shell, and never
``--dangerously-skip-permissions``. One call runs at a time (a lock the caller waits on for at
most ``timeout_s``, then the chain moves on); the child runs in its own process group and the
timeout kills the whole group. Who may be answered is the chain's ``only_users`` (a subscription
login must not serve other users), not this module's. Any failure is a ``ModelUnavailableError``
that names the cause (never stderr, which may hold a path or a token)."""

import contextlib
import json
import os
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from algotrade.core.model.completion import CallTag, Completion
from algotrade.core.model.errors import ModelUnavailableError

Runner = Callable[
    [Sequence[str], str, Path, Mapping[str, str], float], "subprocess.CompletedProcess[str]"
]
_LOCK = threading.Lock()  # one headless run at a time on this machine

LOCKDOWN = (
    "--safe-mode",
    "--tools",
    "",
    "--strict-mcp-config",
    "--setting-sources",
    "",
    "--disable-slash-commands",
    "--no-session-persistence",
)


def run_process(
    argv: Sequence[str], stdin: str, cwd: Path, env: Mapping[str, str], timeout: float
) -> "subprocess.CompletedProcess[str]":
    """Run ``argv`` (an argv list, no shell) in its own process group; on timeout the whole
    group is killed and reaped, so no grandchild outlives the call."""
    with subprocess.Popen(  # an argv list, no shell
        list(argv),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        env=dict(env),
        start_new_session=True,
    ) as proc:
        try:
            out, err = proc.communicate(stdin, timeout=timeout)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            raise
        return subprocess.CompletedProcess(list(argv), proc.returncode, out, err)


@dataclass(frozen=True)
class ClaudeCli:
    """One ``claude`` command and model. ``env`` is the child's whole environment; ``runner``
    starts it (``run_process``, or a fake in tests)."""

    command: str
    model: str
    env: Mapping[str, str]
    timeout_s: float = 60.0
    retries: int = 0
    provider: str = "claude"
    runner: Runner = run_process
    clock: Callable[[], float] = time.monotonic

    @property
    def names(self) -> tuple[str, ...]:
        """Qualified by the kind, so no other provider's model of the same id shares a cache
        key with the owner's login."""
        return (self.answers_as,)

    @property
    def answers_as(self) -> str:
        return f"claude-cli:{self.model}"

    def names_for(self, user: str | None) -> tuple[str, ...]:
        """The chain limits who may use this provider, not the adapter."""
        return self.names

    def argv(self, system: str) -> list[str]:
        """The command line: the lockdown flags always, the system prompt as an argument, the
        user text on stdin."""
        return [
            self.command,
            "-p",
            "--output-format",
            "json",
            "--model",
            self.model,
            "--system-prompt",
            system,
            *LOCKDOWN,
        ]

    def complete(self, system: str, user: str, *, tag: CallTag | None = None) -> Completion:
        started = self.clock()
        where = f"claude-cli {self.model}"
        failure: ModelUnavailableError | None = None
        for _ in range(self.retries + 1):
            try:
                return replace(self._once(system, user, where), latency_s=self.clock() - started)
            except ModelUnavailableError as exc:
                failure = exc
        assert failure is not None
        raise failure

    def _once(self, system: str, user: str, where: str) -> Completion:
        if not _LOCK.acquire(timeout=self.timeout_s):
            raise ModelUnavailableError(f"{where}: busy with another request")
        try:
            with tempfile.TemporaryDirectory(
                prefix="algotrade-claude-", ignore_cleanup_errors=True
            ) as cwd:
                done = self._run(system, user, Path(cwd), where)
        finally:
            _LOCK.release()
        return self._completion(done, where)

    def _run(
        self, system: str, user: str, cwd: Path, where: str
    ) -> "subprocess.CompletedProcess[str]":
        try:
            return self.runner(self.argv(system), user, cwd, self.env, self.timeout_s)
        except subprocess.TimeoutExpired as exc:
            raise ModelUnavailableError(f"{where}: timed out after {self.timeout_s:g} s") from exc
        except OSError as exc:
            raise ModelUnavailableError(
                f"{where}: cannot run {self.command}: {exc.strerror}"
            ) from exc

    def _completion(self, done: "subprocess.CompletedProcess[str]", where: str) -> Completion:
        result = _result(done, where)
        usage = result.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        cost = result.get("total_cost_usd")
        return Completion(
            _answer(result, where),
            self.answers_as,
            self.provider,
            _count(usage.get("input_tokens")),
            _count(usage.get("output_tokens")),
            0.0,
            cost_usd=float(cost)
            if isinstance(cost, int | float) and not isinstance(cost, bool)
            else None,
        )


def _result(done: "subprocess.CompletedProcess[str]", where: str) -> dict[str, Any]:
    """The CLI's JSON result object; a failure never quotes stderr."""
    try:
        parsed = json.loads(done.stdout)
    except ValueError:
        parsed = None
    result = parsed if isinstance(parsed, dict) else None
    if result is not None and result.get("is_error"):
        raise ModelUnavailableError(f"{where}: {_reason(result)}")
    if done.returncode != 0:
        raise ModelUnavailableError(f"{where}: exited with status {done.returncode}")
    if result is None:
        raise ModelUnavailableError(f"{where}: the output is not a JSON object")
    return result


def _reason(result: dict[str, Any]) -> str:
    """Why the CLI reported an error: its own short message when it gave a string (a login that
    is gone, a used-up limit), else just that it failed."""
    message = result.get("result")
    if isinstance(message, str) and message.strip():
        return " ".join(message.split())[:200]
    return "the CLI reported an error"


def _answer(result: dict[str, Any], where: str) -> str:
    text = result.get("result")
    if not isinstance(text, str) or not text.strip():
        raise ModelUnavailableError(f"{where}: the answer is empty")
    return text


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
