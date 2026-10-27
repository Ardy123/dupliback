# the Prune screen and its place in the manage window, on real duplicity
import os
import shutil

import pytest

import backup
import merge
from conftest import build_moments, wait_until, write

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
    # estimate, rebuild, apply; asked once, then told what was freed
    gui_env.wait_for_takedowns(3, timeout=300)
    assert revisions(gui) == remaining
    assert not merge.get_journal(screen.duplicity_dir)
    titles = [texts[0] for texts in gui_env.messages]
    assert titles == ['Prune or merge moments?',
                      'Pruning or merging finished']


def test_declining_the_confirmation_changes_nothing(manage, gui_env):
    from gi.repository import Gtk
    gui, epochs = manage
    gui_env.dialog_response = Gtk.ResponseType.NO
    screen = open_screen(gui, gui_env)
    files = sorted(os.listdir(screen.duplicity_dir))
    pick(screen, 1)
    screen.prune()
    gui_env.wait_for_takedowns(1, timeout=300)
    wait_until(lambda: True)
    assert len(gui_env.messages) == 1
    assert sorted(os.listdir(screen.duplicity_dir)) == files
    assert revisions(gui) == 4


def test_other_users_files_use_administrator_rights(manage, gui_env,
                                                    monkeypatch):
    from gi.repository import Gtk
    gui, epochs = manage
    gui_env.dialog_response = Gtk.ResponseType.YES
    real = merge.estimate_rewrite
    monkeypatch.setattr(merge, 'estimate_rewrite', lambda *args: dict(
        real(*args), foreign_owned=3))
    # as a normal user, and with the helper run without pkexec
    monkeypatch.setattr(merge.os, 'geteuid', lambda: 1000)
    monkeypatch.setattr(merge, 'ADMIN_COMMAND', [])
    used = []
    real_admin = merge.prepare_as_admin
    monkeypatch.setattr(merge, 'prepare_as_admin', lambda *args, **kwargs: (
        used.append(1) or real_admin(*args, **kwargs)))
    screen = open_screen(gui, gui_env)
    pick(screen, 1)
    screen.prune()
    gui_env.wait_for_takedowns(3, timeout=300)
    assert used == [1]
    assert 'administrator password' in ' '.join(gui_env.messages[0])
    assert revisions(gui) == 3


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
    gui, epochs = manage
    monkeypatch.setattr(backup, 'full_backup_status',
                        lambda *args: (True, False))
    gui.start_backup()
    gui_env.wait_for_takedowns(1, timeout=120)
    assert [texts[0] for texts in gui_env.messages] == [
        'Full backup postponed']


def test_prune_moment_from_the_right_click_menu(manage, gui_env):
    from gi.repository import Gtk
    from test_gui_manage import click_on_row
    gui, epochs = manage
    treeview = gui.gtkbuilder.get_object('treeview_revisions')
    gui.revview_mouse_notify(treeview, click_on_row(treeview, 1))
    menu, = gui_env.popups
    prune_item = menu.get_children()[1]
    assert prune_item.get_label() == 'Prune Moment'
    gui_env.dialog_response = Gtk.ResponseType.YES
    prune_item.activate()
    # estimate, rebuild, apply
    gui_env.wait_for_takedowns(3, timeout=300)
    assert [rev['epoch'] for rev in backup.get_revisions(gui.uuid, gui.host,
                                                         gui.path)] == [
        epochs[0]] + epochs[2:]
    assert revisions(gui) == 3


def test_pruning_the_only_moment_is_refused(repo, gui_env):
    import manage_backup_gui
    build_moments(repo, 'pw', [edit(0)])
    gui = manage_backup_gui.GUI(gui_env.register, gui_env.unregister,
                                *repo.args, 'pw')
    rev = gui.gtkbuilder.get_object('treeview_revisions').get_model()[0][1]
    gui.prune_moment(rev)
    assert [texts[0] for texts in gui_env.messages] == [
        'Prune or merge stopped']
    gui.close()


def test_little_temporary_space_is_a_warning_not_a_refusal(manage, gui_env,
                                                           monkeypatch):
    from gi.repository import Gtk
    gui, epochs = manage
    gui_env.dialog_response = Gtk.ResponseType.YES
    real = merge.estimate_rewrite
    monkeypatch.setattr(merge, 'estimate_rewrite', lambda *args: dict(
        real(*args), staging_free=1))
    screen = open_screen(gui, gui_env)
    pick(screen, 1)
    screen.prune()
    gui_env.wait_for_takedowns(3, timeout=300)
    confirm = ' '.join(gui_env.messages[0])
    assert 'temporary space' in confirm and '1B is free' in confirm
    assert 'administrator' not in confirm
    assert revisions(gui) == 3


def test_unexpected_errors_are_shown_and_end_the_task(manage, gui_env,
                                                      monkeypatch):
    gui, epochs = manage
    def broken(*args):
        raise RuntimeError('disk vanished')
    monkeypatch.setattr(merge, 'estimate_rewrite', broken)
    screen = open_screen(gui, gui_env)
    pick(screen, 1)
    screen.prune()
    gui_env.wait_for_takedowns(1, timeout=120)
    title, text = gui_env.messages[0]
    assert title == 'Prune or merge stopped'
    assert 'disk vanished' in text


def test_refreshing_the_history_lists_no_files(manage, gui_env, monkeypatch):
    # rebuilding the list after a prune or backup moved the cursor through
    # every row, listing each moment's files
    from gi.repository import Gtk
    gui, epochs = manage
    listed = []
    monkeypatch.setattr(backup, 'list_files',
                        lambda *args: listed.append(args[3]))
    treeview = gui.gtkbuilder.get_object('treeview_revisions')
    treeview.set_cursor(Gtk.TreePath.new_from_indices([1]), None, False)
    gui_env.wait_for_takedowns(1)
    gui.update_revisions()
    wait_until(lambda: True)
    assert len(listed) == 1
    model, entry = treeview.get_selection().get_selected()
    assert model[entry][1] == listed[0]


def test_a_pruned_selected_moment_clears_the_files(manage, gui_env,
                                                   monkeypatch):
    from gi.repository import Gtk
    gui, epochs = manage
    monkeypatch.setattr(backup, 'list_files', lambda *args: None)
    get = gui.gtkbuilder.get_object
    get('treeview_revisions').set_cursor(
        Gtk.TreePath.new_from_indices([1]), None, False)
    gui_env.wait_for_takedowns(1)
    assert get('toolbutton_restore').get_sensitive()
    revisions = backup.get_revisions(gui.uuid, gui.host, gui.path)
    gui.show_revisions(revisions[:1] + revisions[2:])
    assert len(get('treeview_files').get_model()) == 0
    assert not get('toolbutton_restore').get_sensitive()
