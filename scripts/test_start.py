"""Regression checks for repeated startup, port conflicts and process cleanup."""
import importlib.util
import os
from pathlib import Path
import socket
import sys
import time
from unittest.mock import Mock

import pytest

spec = importlib.util.spec_from_file_location('launcher', Path(__file__).with_name('start.py'))
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_existing_app_is_reused_without_installing_or_spawning(monkeypatch, capsys):
    monkeypatch.setattr(launcher, 'port_busy', lambda port: True)
    monkeypatch.setattr(launcher, 'meetingflow_running', lambda: True)
    run = Mock()
    spawn = Mock()
    monkeypatch.setattr(launcher, 'run', run)
    monkeypatch.setattr(launcher, 'spawn', spawn)
    monkeypatch.setattr(sys, 'argv', ['start.py'])
    launcher.main()
    run.assert_not_called()
    spawn.assert_not_called()
    assert 'уже запущен' in capsys.readouterr().out


@pytest.mark.parametrize('busy', [{5173}, {8000}, {8000, 5173}])
def test_foreign_or_partial_servers_fail_before_setup(monkeypatch, busy, capsys):
    monkeypatch.setattr(launcher, 'port_busy', lambda port: port in busy)
    monkeypatch.setattr(launcher, 'meetingflow_running', lambda: False)
    run = Mock()
    spawn = Mock()
    monkeypatch.setattr(launcher, 'run', run)
    monkeypatch.setattr(launcher, 'spawn', spawn)
    with pytest.raises(RuntimeError, match='Порты заняты'):
        launcher.main()
    run.assert_not_called()
    spawn.assert_not_called()
    assert 'MeetingFlow: http' not in capsys.readouterr().out


def test_dead_child_does_not_report_success_and_other_child_is_stopped(monkeypatch, capsys):
    monkeypatch.setattr(launcher, 'port_busy', lambda port: False)
    monkeypatch.setattr(launcher, 'run', Mock())
    monkeypatch.setattr(launcher, 'NPM', 'npm')
    children = [Mock(), Mock()]
    children[0].poll.return_value = 1
    children[1].poll.return_value = None
    monkeypatch.setattr(launcher, 'spawn', Mock(side_effect=children))
    stop = Mock()
    monkeypatch.setattr(launcher, 'stop', stop)
    with pytest.raises(RuntimeError, match='завершился при запуске'):
        launcher.main()
    stop.assert_called_once_with(children)
    assert 'MeetingFlow: http' not in capsys.readouterr().out


@pytest.mark.skipif(os.name == 'nt', reason='POSIX process group regression')
def test_stopping_launcher_children_releases_descendant_server_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    # The immediate child starts a descendant HTTP server, just as npm starts Vite.
    code = ('import subprocess, sys, time; '
            f'subprocess.Popen([sys.executable,"-m","http.server","{port}","--bind","127.0.0.1"]); '
            'time.sleep(60)')
    process = launcher.spawn([sys.executable, '-c', code], launcher.ROOT)
    try:
        for _ in range(100):
            if launcher.port_busy(port):
                break
            time.sleep(.05)
        else:
            pytest.fail('Descendant test server did not start')
    finally:
        launcher.stop([process])
    for _ in range(100):
        if not launcher.port_busy(port):
            break
        time.sleep(.05)
    assert not launcher.port_busy(port)
