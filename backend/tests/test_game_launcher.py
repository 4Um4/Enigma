import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

import game_launcher


class _Response:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Process:
    def __init__(self, exit_code=None):
        self.returncode = exit_code
        self._exit_code = exit_code
        self.pid = 1234
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls = 0

    def poll(self):
        return self._exit_code

    def terminate(self):
        self.terminate_calls += 1

    def kill(self):
        self.kill_calls += 1
        self._exit_code = -9
        self.returncode = -9

    def wait(self, timeout=None):
        self.wait_calls += 1
        if self._exit_code is None:
            self._exit_code = 0
            self.returncode = 0
        return self._exit_code


class _Surface:
    def fill(self, *_args):
        pass

    def blit(self, *_args):
        pass


class _Pygame:
    QUIT = 1

    def __init__(self):
        surface = _Surface()
        self.display = SimpleNamespace(
            get_surface=lambda: surface,
            set_mode=lambda *_args: surface,
            set_caption=lambda *_args: None,
            flip=lambda: None,
        )
        self.font = SimpleNamespace(
            SysFont=lambda *_args: SimpleNamespace(render=lambda *_args: None)
        )
        self.draw = SimpleNamespace(rect=lambda *_args: None)
        self.event = SimpleNamespace(get=lambda: [])


@pytest.fixture
def launcher_setup(monkeypatch, tmp_path):
    import app.core.config

    monkeypatch.setattr(game_launcher, "_BACKEND_DIR", str(tmp_path))
    monkeypatch.setattr(game_launcher, "_BACKEND_STARTUP_TIMEOUT", 2)
    monkeypatch.setattr(game_launcher, "_ensure_llm_running", lambda: None)
    monkeypatch.setattr(game_launcher, "_dt", lambda *_args: None)
    monkeypatch.setitem(sys.modules, "pygame", _Pygame())
    monkeypatch.setattr(app.core.config.settings, "api_host", "127.0.0.1")
    monkeypatch.setattr(app.core.config.settings, "api_port", 8000)
    game_launcher._LLM_DIAG.update(reason="", detail="", log_offset=0)
    game_launcher._BACKEND_DIAG.update(
        ready=False, reason="", detail="", exit_code=None, log_path=""
    )
    return tmp_path


def _mock_launcher(monkeypatch, urlopen, popen):
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(game_launcher.subprocess, "Popen", popen)


def _backend_not_running(*_args, **_kwargs):
    raise urllib.error.URLError("down")


def test_backend_exit_code_one_is_not_ready_and_is_preserved(
    launcher_setup, monkeypatch
):
    _mock_launcher(
        monkeypatch,
        _backend_not_running,
        lambda *_args, **_kwargs: _Process(1),
    )

    backend_proc, _ = game_launcher._ensure_servers_running()

    assert backend_proc.returncode == 1
    assert game_launcher._BACKEND_DIAG["ready"] is False
    assert game_launcher._BACKEND_DIAG["reason"] == "process_exited"
    assert game_launcher._BACKEND_DIAG["exit_code"] == 1
    assert "exit_code=1" in Path(
        game_launcher._BACKEND_DIAG["log_path"]
    ).read_text(encoding="utf-8")


def test_backend_port_conflict_is_reported_from_launch_log(
    launcher_setup, monkeypatch
):
    def popen(*_args, **kwargs):
        kwargs["stdout"].write("ERROR: [Errno 10048] address already in use\n")
        return _Process(1)

    _mock_launcher(
        monkeypatch,
        _backend_not_running,
        popen,
    )

    backend_proc, _ = game_launcher._ensure_servers_running()

    assert backend_proc.returncode == 1
    assert game_launcher._BACKEND_DIAG["ready"] is False
    assert game_launcher._BACKEND_DIAG["reason"] == "port_conflict"
    assert game_launcher._BACKEND_DIAG["exit_code"] == 1
    assert "address already in use" in Path(
        game_launcher._BACKEND_DIAG["log_path"]
    ).read_text(encoding="utf-8")


def test_backend_health_timeout_is_not_ready(launcher_setup, monkeypatch):
    _mock_launcher(
        monkeypatch,
        _backend_not_running,
        lambda *_args, **_kwargs: _Process(),
    )
    now = [0]

    def monotonic():
        now[0] += 1
        return now[0]

    monkeypatch.setattr(game_launcher.time, "monotonic", monotonic)

    backend_proc, _ = game_launcher._ensure_servers_running()

    assert backend_proc.poll() is None
    assert game_launcher._BACKEND_DIAG["ready"] is False
    assert game_launcher._BACKEND_DIAG["reason"] == "health_timeout"
    assert game_launcher._BACKEND_DIAG["exit_code"] is None
    assert "reason=health_timeout" in Path(
        game_launcher._BACKEND_DIAG["log_path"]
    ).read_text(encoding="utf-8")


def test_backend_becomes_ready_only_after_health_200(launcher_setup, monkeypatch):
    calls = []

    def urlopen(*_args, **_kwargs):
        calls.append(True)
        if len(calls) == 1:
            raise urllib.error.URLError("not ready yet")
        return _Response(200)

    _mock_launcher(monkeypatch, urlopen, lambda *_args, **_kwargs: _Process())

    backend_proc, _ = game_launcher._ensure_servers_running()

    assert backend_proc.poll() is None
    assert game_launcher._BACKEND_DIAG["ready"] is True
    assert game_launcher._BACKEND_DIAG["reason"] == ""
    assert len(calls) == 2


def test_each_backend_launch_gets_a_unique_preserved_log(launcher_setup, monkeypatch):
    logs_dir = launcher_setup / "logs"
    logs_dir.mkdir()
    previous_log = logs_dir / "cds_backend_launch_previous.log"
    previous_log.write_text("previous launch output\n", encoding="utf-8")
    legacy_log = logs_dir / "cds_backend.log"
    legacy_log.write_text("existing diagnostics\n", encoding="utf-8")
    launches = iter(("first launch output\n", "second launch output\n"))

    def popen(*_args, **kwargs):
        kwargs["stdout"].write(next(launches))
        return _Process()

    requests = [0]

    def urlopen(*_args, **_kwargs):
        requests[0] += 1
        if requests[0] % 2:
            raise urllib.error.URLError("not running")
        return _Response(200)

    _mock_launcher(monkeypatch, urlopen, popen)
    game_launcher._ensure_servers_running()
    first_log = game_launcher._BACKEND_DIAG["log_path"]
    game_launcher._ensure_servers_running()
    second_log = game_launcher._BACKEND_DIAG["log_path"]

    assert first_log != second_log
    assert Path(first_log).read_text(encoding="utf-8") == "first launch output\n"
    assert Path(second_log).read_text(encoding="utf-8") == "second launch output\n"
    assert previous_log.read_text(encoding="utf-8") == "previous launch output\n"
    assert legacy_log.read_text(encoding="utf-8") == "existing diagnostics\n"


def test_shutdown_does_not_target_a_foreign_process_on_backend_port(
    launcher_setup, monkeypatch
):
    def popen(*_args, **_kwargs):
        raise AssertionError("an already healthy backend must not be spawned")

    _mock_launcher(
        monkeypatch,
        lambda *_args, **_kwargs: _Response(200),
        popen,
    )
    subprocess_calls = []
    monkeypatch.setattr(
        game_launcher.subprocess,
        "run",
        lambda *args, **kwargs: subprocess_calls.append((args, kwargs)),
    )

    backend_proc, llm_proc = game_launcher._ensure_servers_running()
    assert backend_proc is None

    game_launcher._shutdown_owned_processes(backend_proc, llm_proc)

    assert subprocess_calls == []


def test_shutdown_skips_owned_backend_that_already_exited():
    process = _Process(exit_code=0)

    game_launcher._shutdown_owned_processes(process)

    assert process.terminate_calls == 0
    assert process.wait_calls == 0


def test_shutdown_terminates_running_owned_backend():
    process = _Process()

    game_launcher._shutdown_owned_processes(process)

    assert process.terminate_calls == 1
    assert process.wait_calls == 1
    assert process.poll() == 0


def test_repeated_shutdown_is_idempotent():
    process = _Process()

    game_launcher._shutdown_owned_processes(process)
    game_launcher._shutdown_owned_processes(process)

    assert process.terminate_calls == 1
    assert process.wait_calls == 1
