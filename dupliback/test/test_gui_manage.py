# the manage window: toolbar actions run real duplicity on worker threads
import os
import shutil

import pytest

import backup
from conftest import pin_dir_mtimes, read, status_count, wait_until, write

pytestmark = pytest.mark.skipif(shutil.which('duplicity') is None,
                                reason='duplicity is not installed')


class FakeEvent(object):
    def __init__(self, button):
        self.button = button
        self.time = 0


def open_manage_window(repo, gui_env):
    import manage_backup_gui
    return manage_backup_gui.GUI(gui_env.register, gui_env.unregister,
                                 *repo.args, 'pw')


@pytest.fixture
def manage(protected, gui_env):
    gui = open_manage_window(protected, gui_env)
    yield gui
    gui.close()


@pytest.fixture
def empty_manage(repo, gui_env):
    # the window for a backup without revisions
    backup.init_backup(*repo.args, 'pw')
    gui = open_manage_window(repo, gui_env)
    yield gui
    gui.close()


def select_first_revision(gui, gui_env):
    from gi.repository import Gtk
    gui.gtkbuilder.get_object('treeview_revisions').set_cursor(
        Gtk.TreePath.new_first(), None, False)
    gui_env.wait_for_takedowns(1)


def file_tree(model, parent=None):
    # nested {name: children} view of the file tree model
    children = (model.iter_nth_child(parent, n)
                for n in range(model.iter_n_children(parent)))
    return {model.get_value(child, 0): file_tree(model, child)
            for child in children}


def find_row(model, *names, parent=None):
    children = (model.iter_nth_child(parent, n)
                for n in range(model.iter_n_children(parent)))
    match = next(child for child in children
                 if model.get_value(child, 0) == names[0])
    return find_row(model, *names[1:], parent=match) if names[1:] else match


def test_new_backup_shows_welcome_dialog(repo, gui_env):
    import manage_backup_gui
    backup.init_backup(*repo.args, None)
    gui = manage_backup_gui.GUI(gui_env.register, gui_env.unregister,
                                *repo.args, None)
    try:
        assert len(gui.gtkbuilder.get_object('treeview_revisions')
                   .get_model()) == 0
        assert gui_env.dialogs_run
    finally:
        gui.close()


def test_selecting_a_revision_lists_its_files(manage, gui_env):
    assert manage.get_selected_revision() is None
    select_first_revision(manage, gui_env)
    assert manage.get_selected_revision()
    tree = file_tree(
        manage.gtkbuilder.get_object('treeview_files').get_model())
    assert tree['my docs'] == {'file with spaces.txt': {}}
    assert 'small.bin' in tree
    assert manage.gtkbuilder.get_object('toolbutton_restore').get_sensitive()


def test_backup_button_adds_a_revision(manage, gui_env):
    write(os.path.join(manage.path, 'new.txt'), 'n')
    manage.start_backup()
    gui_env.wait_for_takedowns(1)
    assert len(manage.gtkbuilder.get_object('treeview_revisions')
               .get_model()) == 2
    assert len(manage.gtkbuilder.get_object('running_tasks')
               .get_model()) == 0


def test_restore_selected_file(manage, gui_env):
    select_first_revision(manage, gui_env)
    treeview = manage.gtkbuilder.get_object('treeview_files')
    treeview.get_selection().select_iter(
        find_row(treeview.get_model(), 'my docs', 'file with spaces.txt'))
    target = os.path.join(manage.path, 'my docs', 'file with spaces.txt')
    write(target, 'changed')
    manage.restore_button_notify(None)
    gui_env.wait_for_takedowns(2)
    assert read(target) == 'v1'


def test_restore_whole_revision_from_context_menu(manage, gui_env):
    select_first_revision(manage, gui_env)
    target = os.path.join(manage.path, 'small.bin')
    os.remove(target)
    revisions = manage.gtkbuilder.get_object('treeview_revisions')
    assert manage.revview_mouse_notify(revisions, FakeEvent(3))
    assert not manage.revview_mouse_notify(revisions, FakeEvent(1))
    manage.restore_selection(None, None)
    gui_env.wait_for_takedowns(2)
    assert os.path.isfile(target)


def test_moment_context_menu_restores(manage, gui_env):
    select_first_revision(manage, gui_env)
    target = os.path.join(manage.path, 'small.bin')
    os.remove(target)
    revisions = manage.gtkbuilder.get_object('treeview_revisions')
    assert manage.revview_mouse_notify(revisions, FakeEvent(3))
    menu, = gui_env.popups
    item, = menu.get_children()
    assert item.get_label() == 'Restore Moment(revision)'
    item.activate()
    gui_env.wait_for_takedowns(2)
    assert os.path.isfile(target)


def test_file_context_menu_needs_a_selection(manage, gui_env):
    select_first_revision(manage, gui_env)
    treeview = manage.gtkbuilder.get_object('treeview_files')
    assert not manage.fileview_mouse_notify(treeview, FakeEvent(3))
    treeview.get_selection().select_iter(
        find_row(treeview.get_model(), 'small.bin'))
    assert manage.fileview_mouse_notify(treeview, FakeEvent(3))
    assert not manage.fileview_mouse_notify(treeview, FakeEvent(1))


def test_restore_button_without_file_selection_restores_everything(
        manage, gui_env):
    select_first_revision(manage, gui_env)
    os.remove(os.path.join(manage.path, 'small.bin'))
    manage.restore_button_notify(None)
    gui_env.wait_for_takedowns(2)
    assert os.path.isfile(os.path.join(manage.path, 'small.bin'))


def test_export_writes_tarball_and_opens_it(manage, gui_env, tmp_path):
    select_first_revision(manage, gui_env)
    gui_env.chosen_folder = str(tmp_path)
    manage.start_export()
    gui_env.wait_for_takedowns(2)
    assert len(gui_env.opened_files) == 1
    assert (gui_env.opened_files[0].startswith(str(tmp_path))
            and gui_env.opened_files[0].endswith('.tar.gz'))
    assert os.path.isfile(gui_env.opened_files[0])


def test_export_cancelled(manage, gui_env):
    from gi.repository import Gtk
    select_first_revision(manage, gui_env)
    gui_env.dialog_response = Gtk.ResponseType.CANCEL
    manage.start_export()
    assert gui_env.opened_files == []


def test_explore_opens_restored_folder(manage, gui_env):
    select_first_revision(manage, gui_env)
    manage.start_explore()
    gui_env.wait_for_takedowns(2)
    assert len(gui_env.opened_files) == 1
    assert os.path.isfile(os.path.join(gui_env.opened_files[0], 'small.bin'))
    backup.rmdir(os.path.dirname(gui_env.opened_files[0]))


def test_status_opens_status_window(manage, gui_env):
    import backup_status_gui
    write(os.path.join(manage.path, 'new.txt'), 'n')
    pin_dir_mtimes(manage.path)
    manage.start_status()
    gui_env.wait_for_takedowns(1)
    status, = gui_env.find(backup_status_gui.GUI)
    rows = [row[1]
            for row in status.gtkbuilder.get_object('treeview_filelist')
            .get_model()]
    assert [status_count('New Files', rows[0]),
            status_count('Modified Files', rows[1]),
            status_count('Deleted Files', rows[2])] == [1, 0, 0]
    status.close()
    assert not gui_env.find(backup_status_gui.GUI)


def test_preferences_and_about(empty_manage, gui_env):
    manage = empty_manage
    import about_gui
    import manage_backup_preferences_gui
    manage.open_preferences()
    preferences, = gui_env.find(manage_backup_preferences_gui.GUI)
    preferences.close()
    manage.open_about()
    about = about_gui.GUI(gui_env.register, gui_env.unregister,
                          manage.main_window)
    about.closedButton(about.main_window, 0)


def test_running_task_timer_updates_elapsed_time(empty_manage, gui_env):
    import datetime
    tasks = empty_manage.gtkbuilder.get_object('running_tasks').get_model()
    tasks.append((None, 'pretend task',
                  datetime.datetime.now() - datetime.timedelta(seconds=90),
                  ''))
    wait_until(lambda: tasks[0][3] != '', timeout=10)
    assert tasks[0][3].startswith('1m')
