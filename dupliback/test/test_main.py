# the dupliback.py entry point: gui registry, command line parsing and backup runs
import os
import runpy

import pytest

import backup
import dupliback
import select_backup_gui
from conftest import SRC_DIR

MAIN = os.path.join(SRC_DIR, 'dupliback.py')


@pytest.fixture
def quits(monkeypatch):
    calls = []
    monkeypatch.setattr(dupliback.Gtk, 'main_quit', lambda: calls.append('quit'))
    return calls


def run_main(monkeypatch, *args):
    monkeypatch.setattr('sys.argv', [MAIN] + list(args))
    runpy.run_path(MAIN, run_name='__main__')


def test_app_quits_when_last_window_closes(quits, monkeypatch):
    monkeypatch.setattr(dupliback, 'GUIS', set())
    first, second = object(), object()
    dupliback.register_gui(first)
    dupliback.register_gui(second)
    dupliback.unregister_gui(first)
    assert quits == []
    dupliback.unregister_gui(second)
    assert quits == ['quit']


def test_run_all_backups_runs_every_known_backup(monkeypatch):
    monkeypatch.setattr(backup, 'get_known_backups', lambda: [
        {'uuid': 'A', 'host': 'h', 'path': '/a'}, {'uuid': 'B', 'host': 'h', 'path': '/b'}])
    runs = []
    monkeypatch.setattr(dupliback, 'run_backup', lambda uuid, path, host=None: runs.append((uuid, path, host)))
    dupliback.run_all_backups()
    assert runs == [('A', '/a', 'h'), ('B', '/b', 'h')]


@pytest.fixture
def passing_backup(monkeypatch):
    # a backup that passes all assertions, with the duplicity run recorded
    runs = []
    monkeypatch.setattr(backup, 'test_backup_assertions', lambda *args: True)
    monkeypatch.setattr(backup, 'backup', lambda uuid, host, path, password: runs.append((uuid, host, path, password)))
    monkeypatch.setattr(backup, 'upgrade_password_hash', lambda *args: False)
    return runs


def test_run_backup_defaults_to_this_host(passing_backup, monkeypatch):
    monkeypatch.setattr(backup, 'get_preferences', lambda *args: {'password_protect': False})
    dupliback.run_backup('U', '/src')
    assert passing_backup == [('U', backup.get_hostname(), '/src', None)]


def test_run_backup_without_password_is_skipped(passing_backup, monkeypatch, capsys):
    monkeypatch.delenv('PASSPHRASE', raising=False)
    monkeypatch.setattr(backup, 'get_preferences', lambda *args: {'password_protect': True})
    monkeypatch.setattr(backup, 'get_properties', lambda *args: {'password': backup.gen_passwordEncrypt('pw')})
    dupliback.run_backup('U', '/src', 'h')
    assert passing_backup == []
    assert 'wrong or missing password' in capsys.readouterr().out


def test_run_backup_prompts_on_a_terminal(passing_backup, monkeypatch):
    monkeypatch.delenv('PASSPHRASE', raising=False)
    monkeypatch.setattr(backup, 'get_preferences', lambda *args: {'password_protect': True})
    monkeypatch.setattr(backup, 'get_properties', lambda *args: {'password': backup.gen_passwordEncrypt('pw')})
    monkeypatch.setattr(dupliback.sys.stdin, 'isatty', lambda: True, raising=False)
    monkeypatch.setattr(dupliback.getpass, 'getpass', lambda prompt: 'pw')
    dupliback.run_backup('U', '/src', 'h')
    assert passing_backup == [('U', 'h', '/src', 'pw')]


def test_run_backup_reports_failures(monkeypatch, capsys):
    monkeypatch.setattr(backup, 'test_backup_assertions', lambda *args: True)
    monkeypatch.setattr(backup, 'get_preferences', lambda *args: {'password_protect': False})
    def failing_backup(*args):
        raise RuntimeError('disk on fire')
    monkeypatch.setattr(backup, 'backup', failing_backup)
    dupliback.run_backup('U', '/src', 'h')
    assert 'disk on fire' in capsys.readouterr().err


def test_main_without_arguments_opens_the_gui(monkeypatch):
    opened = []
    monkeypatch.setattr(select_backup_gui, 'GUI', lambda register, unregister: opened.append('select') or object())
    monkeypatch.setattr(dupliback.Gtk, 'main', lambda: opened.append('main loop'))
    run_main(monkeypatch)
    assert opened == ['select', 'main loop']


def test_main_backup_all(monkeypatch, capsys):
    monkeypatch.setattr(backup, 'get_known_backups', lambda: [])
    run_main(monkeypatch, '--backup-all')
    assert 'dupliBack - Backup for Linux' in capsys.readouterr().out
    assert backup.SHOW_ERROR_DIALOGS is False


def test_main_single_backup(monkeypatch, capsys):
    monkeypatch.setattr(backup, 'test_backup_assertions', lambda *args: False)
    run_main(monkeypatch, 'U', '/src')
    assert 'skipped backup: U /src' in capsys.readouterr().out


def test_main_prints_usage_for_bad_arguments(monkeypatch, capsys):
    run_main(monkeypatch, 'just-one-argument')
    out = capsys.readouterr().out
    assert 'to backup all detected repositories' in out and '$PASSPHRASE' in out
