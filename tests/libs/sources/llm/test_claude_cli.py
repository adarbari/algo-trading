"""``ClaudeCli`` (ADR 0041, amended 2026-10-08): the command line it runs always carries the
lockdown flags and never ``--bare`` or ``--dangerously-skip-permissions``, the child gets the
scrubbed environment and an empty directory, a timeout is an unavailable model, the JSON result
is parsed (a missing usage is ``None``), and every failure is a ``ModelUnavailableError`` that
never quotes stderr. No test starts ``claude``: a fake runner answers."""

import json
import os
import signal
import subprocess
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from algotrade.config.env import claude_cli_env
from algotrade.config.site.llm import ProviderSettings
from algotrade.core.model.errors import ModelUnavailableError
from algotrade_sources.framework.registry import build_claude_cli
from algotrade_sources.llm import claude_cli
from algotrade_sources.llm.claude_cli import LOCKDOWN, ClaudeCli, run_process

OK = {
    "type": "result",
    "is_error": False,
    "result": '{"criteria": []}',
    "usage": {"input_tokens": 120, "output_tokens": 30},
    "total_cost_usd": 0.0042,
}


class Runner:
    """Records each run and answers with ``stdout`` / ``returncode``, or raises."""

    def __init__(
        self, stdout: str = "", returncode: int = 0, raises: Exception | None = None
    ) -> None:
        self.stdout, self.returncode, self.raises = stdout, returncode, raises
        self.runs: list[tuple[list[str], str, Path, dict[str, str], float]] = []
        self.cwd_was_empty: list[bool] = []

    def __call__(
        self, argv: Sequence[str], stdin: str, cwd: Path, env: Mapping[str, str], timeout: float
    ) -> "subprocess.CompletedProcess[str]":
        self.runs.append((list(argv), stdin, cwd, dict(env), timeout))
        self.cwd_was_empty.append(cwd.is_dir() and not any(cwd.iterdir()))
        if self.raises is not None:
            raise self.raises
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, "SECRET-stderr")


def client(runner: Runner, retries: int = 0) -> ClaudeCli:
    env = {"HOME": "/Users/o", "PATH": "/usr/bin"}
    return ClaudeCli("/Users/o/.local/bin/claude", "haiku", env, retries=retries, runner=runner)


def test_the_command_line_always_carries_the_lockdown_and_never_skips_permissions() -> None:
    runner = Runner(json.dumps(OK))
    client(runner).complete("the task", "the sentence")
    ((argv, stdin, _, _, timeout),) = runner.runs
    assert argv[:2] == ["/Users/o/.local/bin/claude", "-p"]
    assert argv[argv.index("--output-format") + 1] == "json"
    assert argv[argv.index("--model") + 1] == "haiku"
    assert argv[argv.index("--system-prompt") + 1] == "the task"
    assert all(flag in argv for flag in LOCKDOWN)
    assert argv[argv.index("--tools") + 1] == ""  # no tools
    assert argv[argv.index("--setting-sources") + 1] == ""  # no settings, hooks, CLAUDE.md
    assert "--strict-mcp-config" in argv and "--no-session-persistence" in argv
    assert "--safe-mode" in argv  # no CLAUDE.md, skills, plugins (and their hooks), MCP
    assert "--bare" not in argv  # --bare skips the keychain read: the login would not be found
    assert not any("dangerously" in a or "permission" in a for a in argv)
    assert stdin == "the sentence" and "the sentence" not in argv  # the prompt is on stdin
    assert 59.0 < timeout <= 60.0


def test_the_child_gets_the_given_environment_and_a_fresh_empty_directory() -> None:
    runner = Runner(json.dumps(OK))
    client(runner).complete("s", "u")
    ((_, _, cwd, env, _),) = runner.runs
    assert env == {"HOME": "/Users/o", "PATH": "/usr/bin"}
    assert runner.cwd_was_empty == [True] and not cwd.exists()  # then removed


def test_the_scrubbed_environment_keeps_four_variables_and_drops_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kept = {"HOME": "/Users/o", "USER": "o", "PATH": "/usr/bin", "LANG": "en_US.UTF-8"}
    secrets = {
        "ALGOTRADE_LLM_API_KEY": "k",
        "ANTHROPIC_API_KEY": "k",
        "CLAUDE_CODE_OAUTH_TOKEN": "t",
    }
    for name, value in (kept | secrets).items():
        monkeypatch.setenv(name, value)
    assert claude_cli_env() == kept


def test_the_json_result_gives_text_tokens_and_the_notional_cost() -> None:
    done = client(Runner(json.dumps(OK))).complete("s", "u")
    assert (done.text, done.model, done.provider) == (
        '{"criteria": []}',
        "claude-cli:haiku",  # qualified: no other provider's "haiku" shares its cache key
        "claude",
    )
    assert (done.input_tokens, done.output_tokens, done.cost_usd) == (120, 30, 0.0042)


def test_a_result_without_usage_or_cost_has_none_never_zero() -> None:
    done = client(Runner(json.dumps({"is_error": False, "result": "hi"}))).complete("s", "u")
    assert (done.text, done.input_tokens, done.output_tokens, done.cost_usd) == (
        "hi",
        None,
        None,
        None,
    )


def test_a_timeout_is_an_unavailable_model() -> None:
    runner = Runner(raises=subprocess.TimeoutExpired("claude", 60))
    with pytest.raises(ModelUnavailableError, match="timed out after 60 s"):
        client(runner).complete("s", "u")


def test_the_real_runner_kills_a_child_that_outlives_the_timeout(tmp_path: Path) -> None:
    with pytest.raises(subprocess.TimeoutExpired):
        run_process(["/bin/sleep", "30"], "", tmp_path, {"PATH": "/bin"}, 0.2)


def test_the_root_guard_refuses_to_start_the_claude_cli(tmp_path: Path) -> None:
    """A test can never start a real ``claude`` (the child does its own networking, so the socket
    guard would not stop it): the default runner, Popen and a shell string all raise."""
    for argv in (["claude", "-p"], ["/Users/x/.local/bin/claude", "-p"]):
        with pytest.raises(RuntimeError, match="real Claude CLI call is refused"):
            run_process(argv, "", tmp_path, {"PATH": "/bin"}, 5)
        with pytest.raises(RuntimeError, match="real Claude CLI call is refused"):
            subprocess.run(argv, check=False)
    with pytest.raises(RuntimeError, match="real Claude CLI call is refused"):
        subprocess.Popen("claude -p", shell=True)
    assert subprocess.run(["/bin/echo", "claude"], capture_output=True, check=True).returncode == 0


def test_a_command_that_cannot_start_is_unavailable() -> None:
    runner = Runner(raises=FileNotFoundError(2, "No such file or directory"))
    with pytest.raises(ModelUnavailableError, match=r"cannot run /Users/o/\.local/bin/claude"):
        client(runner).complete("s", "u")


@pytest.mark.parametrize(
    ("stdout", "code", "message"),
    [
        ("", 1, "exited with status 1"),
        ("not json", 0, "not a JSON object"),
        ("[1]", 0, "not a JSON object"),
        (json.dumps({"is_error": False, "result": "  "}), 0, "the answer is empty"),
        (json.dumps({"is_error": False}), 0, "the answer is empty"),
        (json.dumps({"is_error": True, "result": "Not logged in"}), 0, "Not logged in"),
        (json.dumps({"is_error": True, "result": "Usage limit reached"}), 1, "Usage limit"),
        (json.dumps({"is_error": True}), 0, "the CLI reported an error"),
    ],
)
def test_every_failure_is_unavailable_and_never_quotes_stderr(
    stdout: str, code: int, message: str
) -> None:
    with pytest.raises(ModelUnavailableError, match=message) as caught:
        client(Runner(stdout, code)).complete("s", "u")
    assert "SECRET" not in str(caught.value)


def test_retries_default_to_none_and_run_again_when_set() -> None:
    bad = Runner("", 1)
    with pytest.raises(ModelUnavailableError):
        client(bad).complete("s", "u")
    assert len(bad.runs) == 1
    with pytest.raises(ModelUnavailableError):
        client(bad, retries=2).complete("s", "u")
    assert len(bad.runs) == 4


def test_the_registry_builds_it_with_the_given_environment() -> None:
    built = build_claude_cli("/bin/claude", "sonnet", 90, 0, {"HOME": "/h"}, "claude")
    assert (built.command, built.model, built.timeout_s, dict(built.env)) == (
        "/bin/claude",
        "sonnet",
        90,
        {"HOME": "/h"},
    )
    assert built.names == ("claude-cli:sonnet",) and built.names_for("x") == built.names


def test_a_second_request_waits_at_most_the_timeout_for_the_lock_then_is_busy() -> None:
    held = Runner(json.dumps(OK))
    waiting = ClaudeCli("/c", "haiku", {}, timeout_s=0.2, runner=held)
    claude_cli._LOCK.acquire()
    try:
        with pytest.raises(ModelUnavailableError, match="busy with another request"):
            waiting.complete("s", "u")
    finally:
        claude_cli._LOCK.release()
    assert held.runs == []  # never started
    assert waiting.complete("s", "u").text  # and the lock is free again


def test_the_lock_is_released_after_a_failure() -> None:
    with pytest.raises(ModelUnavailableError):
        client(Runner("", 1)).complete("s", "u")
    assert claude_cli._LOCK.acquire(timeout=0.1)
    claude_cli._LOCK.release()


def test_a_timeout_kills_the_whole_process_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    killed: list[tuple[int, int]] = []
    real = os.killpg

    def killpg(pid: int, sig: int) -> None:
        killed.append((pid, sig))
        real(pid, sig)

    monkeypatch.setattr(claude_cli.os, "killpg", killpg)
    with pytest.raises(subprocess.TimeoutExpired):
        run_process(["/bin/sh", "-c", "sleep 30 & wait"], "", tmp_path, {"PATH": "/bin"}, 0.2)
    ((pid, sig),) = killed
    assert sig == signal.SIGKILL and pid != os.getpgid(0)  # a group of its own, not ours


def test_lock_contention_between_threads_serialises_runs() -> None:
    inside, peak = [0], [0]
    guard = threading.Lock()

    def runner(
        argv: Sequence[str], stdin: str, cwd: Path, env: Mapping[str, str], timeout: float
    ) -> "subprocess.CompletedProcess[str]":
        with guard:
            inside[0] += 1
            peak[0] = max(peak[0], inside[0])
        threading.Event().wait(0.05)
        with guard:
            inside[0] -= 1
        return subprocess.CompletedProcess(argv, 0, json.dumps(OK), "")

    model = ClaudeCli("/c", "haiku", {}, timeout_s=5, runner=runner)
    threads = [threading.Thread(target=model.complete, args=("s", "u")) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak[0] == 1


def test_an_attempt_that_waited_for_the_lock_runs_with_only_the_time_left() -> None:
    runner = Runner(json.dumps(OK))
    model = ClaudeCli("/c", "haiku", {}, timeout_s=2.0, runner=runner)
    claude_cli._LOCK.acquire()
    threading.Timer(0.5, claude_cli._LOCK.release).start()
    model.complete("s", "u")
    ((*_, timeout),) = runner.runs
    assert 0 < timeout <= 1.5 + 0.1  # the wait and the run together stay within timeout_s


def test_an_attempt_with_no_time_left_after_the_lock_is_busy() -> None:
    ticks = iter([0.0, 5.0])  # the lock came at 5 s of a 2 s budget
    runner = Runner(json.dumps(OK))
    model = ClaudeCli("/c", "haiku", {}, timeout_s=2.0, runner=runner, clock=lambda: next(ticks))
    with pytest.raises(ModelUnavailableError, match="busy"):
        model._once("s", "u", "claude-cli haiku")
    assert runner.runs == [] and claude_cli._LOCK.acquire(timeout=0.1)  # and the lock is free
    claude_cli._LOCK.release()


def test_the_providers_worst_case_is_one_timeout_per_attempt() -> None:
    cli = ProviderSettings("c", "", "haiku", 60.0, 8000, 1, kind="claude-cli")
    assert cli.worst_case_s == 120.0  # timeout_s x (retries + 1): wait and run share one timeout_s
