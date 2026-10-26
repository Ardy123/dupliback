import atexit
import hashlib
import os
import pickle
import re
import shutil
import subprocess
import sys
import time

import pytest

SRC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')
sys.path.insert(0, SRC_DIR)

GUI_TESTS_ON_DESKTOP = bool(os.environ.get('DUPLIBACK_GUI_TESTS_ON_DESKTOP'))


def start_virtual_display():
    # the gui tests open hundreds of real windows, which crashed kwin on the
    # desktop, so they run on a private xvfb server (skipped without xvfb).
    # must happen before gtk is imported, as that connects to the display.
    if GUI_TESTS_ON_DESKTOP:
        return
    os.environ.pop('WAYLAND_DISPLAY', None)
    os.environ['GDK_BACKEND'] = 'x11'
    xvfb = shutil.which('Xvfb')
    display = None
    if xvfb:
        read_fd, write_fd = os.pipe()
        # -displayfd picks a free display, writes its number once ready
        server = subprocess.Popen(
            [xvfb, '-displayfd', str(write_fd), '-screen', '0',
             '1280x1024x24', '-nolisten', 'tcp'],
            pass_fds=[write_fd], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        os.close(write_fd)
        with os.fdopen(read_fd) as ready:
            display = ready.readline().strip()
        atexit.register(server.terminate)
    if display:
        os.environ['DISPLAY'] = ':' + display
    else:
        os.environ.pop('DISPLAY', None)


start_virtual_display()

import backup
import util

PRODUCTION_HASH_ITERATIONS = backup.PASSWORD_HASH_ITERATIONS


@pytest.fixture(autouse=True)
def no_error_dialogs(monkeypatch):
    monkeypatch.setattr(backup, 'SHOW_ERROR_DIALOGS', False)


@pytest.fixture(autouse=True)
def fast_password_hashing(monkeypatch):
    # the iteration count is stored in each hash, so checking still works; it is
    # only lowered to keep the many password protected test backups fast
    monkeypatch.setattr(backup, 'PASSWORD_HASH_ITERATIONS', 1000)


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(content)


def read(path):
    with open(path) as f:
        return f.read()


def write_legacy_hash(repo, password):
    # an unsalted md5 hash, as backups made before 0.5.0 stored it
    properties = backup.get_properties(*repo.args)
    properties['password'] = hashlib.md5(password.encode('utf-8')).hexdigest()
    with open(os.path.join(backup.get_backupPath(*repo.args),
                           backup.PROPERTIES_FILE), 'wb') as f:
        pickle.dump(properties, f)
    return properties['password']


def stored_hash(repo):
    return backup.get_properties(*repo.args)['password']


@pytest.fixture
def fake_drive(tmp_path, monkeypatch):
    # a plain directory standing in for a mounted removable drive
    drive = tmp_path / 'drive'
    drive.mkdir()
    monkeypatch.setattr(backup, 'is_dev_present', lambda uuid: True)
    monkeypatch.setattr(backup, 'get_mount_point_for_uuid',
                        lambda uuid: str(drive))
    # keep duplicity's signature cache out of ~/.cache
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    return str(drive)


@pytest.fixture
def source_dir(tmp_path):
    src = tmp_path / 'src'
    src.mkdir()
    return str(src)


class Repo(object):
    def __init__(self, uuid, host, path):
        self.uuid = uuid
        self.host = host
        self.path = path

    @property
    def args(self):
        return (self.uuid, self.host, self.path)


@pytest.fixture
def repo(fake_drive, source_dir):
    return Repo('TEST-UUID', backup.get_hostname(), source_dir)


@pytest.fixture
def protected(repo):
    # a password protected repo with one backup, needs duplicity
    write(os.path.join(repo.path, 'my docs', 'file with spaces.txt'), 'v1')
    write(os.path.join(repo.path, 'small.bin'), 'x')
    pin_dir_mtimes(repo.path)
    assert backup.init_backup(*repo.args, 'pw')
    assert backup.backup(*repo.args, 'pw') == 0
    return repo


# duplicity compares mtimes to the second, so a change made in the same second
# as a backup may not count; tests that check change counts pin mtimes.
PINNED_MTIME = 1600000000


def pin_dir_mtimes(root):
    for dirpath, dirnames, filenames in os.walk(root):
        os.utime(dirpath, (PINNED_MTIME, PINNED_MTIME))


def mark_modified(path):
    # a later mtime than the pinned backup, so duplicity always sees the change
    os.utime(path, (PINNED_MTIME + 60, PINNED_MTIME + 60))


def status_count(label, text):
    # 'New Files: 2 - Size of New Files: 141 Bytes' -> 2
    match = re.match(r'%s: (\d+)' % label, text)
    assert match, '%r does not start with %r' % (text, label)
    return int(match.group(1))


HAS_DISPLAY = bool(os.environ.get('DISPLAY')
                   or os.environ.get('WAYLAND_DISPLAY'))
NO_DISPLAY_REASON = ('GUI tests need Xvfb (apt install xvfb); '
                     'set DUPLIBACK_GUI_TESTS_ON_DESKTOP=1 '
                     'to run them on your desktop instead')
requires_display = pytest.mark.skipif(not HAS_DISPLAY,
                                      reason=NO_DISPLAY_REASON)


def run_in_main_loop(func):
    # runs func from inside the gtk main loop, like the real app does
    from gi.repository import Gtk, GLib
    result = {}
    def run():
        try:
            result['value'] = func()
        except Exception as e:
            result['error'] = e
        Gtk.main_quit()
        return False
    GLib.idle_add(run)
    Gtk.main()
    if 'error' in result:
        raise result['error']
    return result.get('value')


def wait_until(predicate, timeout=60):
    # pumps gtk events until predicate() holds, so worker threads can reply
    from gi.repository import Gtk
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, 'timed out waiting for the gui'
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(0.01)


class GuiEnv(object):
    # answers modal dialogs, records actions that would touch the desktop
    def __init__(self):
        self.dialog_response = None
        self.dialogs_run = []
        self.opened_files = []
        self.takedowns = []
        self.chosen_folder = None
        self.guis = set()

    def register(self, gui):
        self.guis.add(gui)

    def unregister(self, gui):
        self.guis.discard(gui)

    def find(self, cls):
        return [g for g in self.guis if isinstance(g, cls)]

    def wait_for_takedowns(self, count, timeout=60):
        wait_until(lambda: len(self.takedowns) >= count, timeout)


@pytest.fixture
def gui_env(monkeypatch):
    if not HAS_DISPLAY:
        pytest.skip(NO_DISPLAY_REASON)
    from gi.repository import Gtk
    import backup_progress_gui
    env = GuiEnv()
    env.dialog_response = Gtk.ResponseType.OK
    def run_dialog(dialog):
        env.dialogs_run.append(dialog)
        return env.dialog_response
    monkeypatch.setattr(Gtk.Dialog, 'run', run_dialog)
    monkeypatch.setattr(Gtk.FileChooserDialog, 'get_filename',
                        lambda self: env.chosen_folder)
    monkeypatch.setattr(Gtk.Menu, 'popup', lambda self, *args: None)
    monkeypatch.setattr(util, 'open_file', env.opened_files.append)
    takedown = backup_progress_gui.GUI.takedownProgressBar
    def record_takedown(self):
        takedown(self)
        env.takedowns.append(self)
    monkeypatch.setattr(backup_progress_gui.GUI, 'takedownProgressBar',
                        record_takedown)
    yield env
    wait_until(lambda: True)
