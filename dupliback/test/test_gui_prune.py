# the Prune screen and its place in the manage window, on real duplicity
import os
import shutil

import pytest

import backup
import merge
from conftest import build_moments, write

pytestmark = pytest.mark.skipif(shutil.which('duplicity') is None,
                                reason='duplicity is not installed')


def edit(n):
    return lambda root: write(os.path.join(root, 'f.txt'), 'version %d' % n)


@pytest.fixture
def chain(repo):
    return repo, build_moments(repo, 'pw', [edit(n) for n in range(4)])


@pytest.fixture
def manage(chain, gui_env):
    import manage_backup_gui
    repo, epochs = chain
    gui = manage_backup_gui.GUI(gui_env.register, gui_env.unregister,
                                *repo.args, 'pw')
    yield gui, epochs
    gui.close()


def revisions(gui):
    return len(gui.gtkbuilder.get_object('treeview_revisions').get_model())


def open_screen(gui, gui_env):
    import prune_gui
    gui.open_prune()
    screen, = gui_env.find(prune_gui.GUI)
    return screen


def pick(screen, *indexes):
    for index in indexes:
        screen.toggled(None, str(index))


def test_prune_button_follows_export(manage):
    from gi.repository import Gtk
    gui, epochs = manage
    toolbar = gui.gtkbuilder.get_object('toolbar1')
    labels = [child.get_label() for child in toolbar.get_children()
              if isinstance(child, Gtk.ToolButton)]
    assert labels[labels.index('Export') + 1] == 'Prune'


def test_screen_lists_moments_and_enables_actions(manage, gui_env):
    gui, epochs = manage
    screen = open_screen(gui, gui_env)
    get = screen.gtkbuilder.get_object
    assert [row[4] for row in screen.model] == epochs
    assert [row[2] for row in screen.model] == [
        'full', 'incremental', 'incremental', 'incremental']
    assert not get('button_prune').get_sensitive()
    pick(screen, 1)
    assert get('button_prune').get_sensitive()
    assert not get('button_merge').get_sensitive()
    pick(screen, 3)
    assert not get('button_merge').get_sensitive()
    pick(screen, 2)
    assert get('button_merge').get_sensitive()
    pick(screen, 0)
    assert not get('button_prune').get_sensitive()
    assert '4 of 4' in get('label_summary').get_text()
    screen.close()


@pytest.mark.parametrize('action, indexes, remaining', [
    ('prune', [1, 2], 2), ('squash', [0, 1, 2], 2)])
def test_prune_and_merge_through_the_screen(manage, gui_env, action,
                                             indexes, remaining):
    from gi.repository import Gtk
    gui, epochs = manage
    screen = open_screen(gui, gui_env)
    pick(screen, *indexes)
    gui_env.dialog_response = Gtk.ResponseType.YES
    getattr(screen, action)()
    # estimate, rebuild, apply
    gui_env.wait_for_takedowns(3, timeout=300)
    assert revisions(gui) == remaining
    assert not merge.get_journal(screen.duplicity_dir)


def test_declining_the_second_confirmation_changes_nothing(manage, gui_env,
                                                          monkeypatch):
    from gi.repository import Gtk
    import util
    gui, epochs = manage
    answers = iter([Gtk.ResponseType.YES, Gtk.ResponseType.NO])
    monkeypatch.setattr(util, 'message_dialog', lambda *args: next(answers))
    screen = open_screen(gui, gui_env)
    files = sorted(os.listdir(screen.duplicity_dir))
    pick(screen, 1)
    screen.prune()
    gui_env.wait_for_takedowns(2, timeout=300)
    assert sorted(os.listdir(screen.duplicity_dir)) == files
    assert revisions(gui) == 4


def test_foreign_files_stop_before_anything_runs(manage, gui_env,
                                                 monkeypatch):
    import util
    gui, epochs = manage
    shown = []
    monkeypatch.setattr(util, 'message_dialog',
                        lambda *args: shown.append(args[2]))
    real = merge.estimate_rewrite
    monkeypatch.setattr(merge, 'estimate_rewrite', lambda *args: dict(
        real(*args), foreign_owned=3))
    screen = open_screen(gui, gui_env)
    pick(screen, 1)
    screen.prune()
    gui_env.wait_for_takedowns(1, timeout=120)
    assert shown == ['Prune or merge stopped']
    assert revisions(gui) == 4


def test_low_space_asks_before_deleting_first(manage, gui_env, monkeypatch):
    from gi.repository import Gtk
    gui, epochs = manage
    d = backup.get_backupPath(gui.uuid, gui.host, gui.path)
    real = merge.shutil.disk_usage
    monkeypatch.setattr(merge.shutil, 'disk_usage', lambda path: (
        real(path)._replace(free=0) if path == d else real(path)))
    screen = open_screen(gui, gui_env)
    pick(screen, 1)
    gui_env.dialog_response = Gtk.ResponseType.YES
    screen.prune()
    # estimate, rebuild, apply (no room), apply deleting first
    gui_env.wait_for_takedowns(4, timeout=300)
    assert revisions(gui) == 3


def test_interrupted_change_is_offered_on_open(chain, gui_env):
    import manage_backup_gui
    import prune_gui
    repo, epochs = chain
    d = backup.get_backupPath(*repo.args)
    merge.prepare_rewrite(merge.plan_prune(d, [epochs[1]]), 'pw')
    journal = merge.get_journal(d)
    journal['phase'] = 'commit'
    merge._write_journal(d, journal)
    gui_env.dialog_response = prune_gui.FINISH
    gui = manage_backup_gui.GUI(gui_env.register, gui_env.unregister,
                                *repo.args, 'pw')
    gui_env.wait_for_takedowns(1, timeout=300)
    assert not merge.get_journal(d)
    assert revisions(gui) == 3
    assert gui.gtkbuilder.get_object('toolbutton_backup').get_sensitive()
    gui.close()


def test_prepared_change_is_dropped_on_open(chain, gui_env):
    import manage_backup_gui
    repo, epochs = chain
    d = backup.get_backupPath(*repo.args)
    merge.prepare_rewrite(merge.plan_prune(d, [epochs[1]]), 'pw')
    gui = manage_backup_gui.GUI(gui_env.register, gui_env.unregister,
                                *repo.args, 'pw')
    assert not merge.get_journal(d)
    assert revisions(gui) == 4
    gui.close()


def test_postponed_full_backup_is_explained(manage, gui_env, monkeypatch):
    import util
    gui, epochs = manage
    shown = []
    monkeypatch.setattr(util, 'message_dialog',
                        lambda *args: shown.append(args[2]))
    monkeypatch.setattr(backup, 'full_backup_status',
                        lambda *args: (True, False))
    gui.start_backup()
    gui_env.wait_for_takedowns(1, timeout=120)
    assert shown == ['Full backup postponed']
