# select / create backup windows and the smaller dialogs
import os

import pytest

import backup


@pytest.fixture
def recorded_windows(monkeypatch):
    # replaces windows opened from other windows with recorders
    import create_backup_gui, select_backup_gui
    class Opened(list):
        pass
    opened = Opened()
    def recorder(name):
        return lambda *args: opened.append((name, args)) or object()
    monkeypatch.setattr(select_backup_gui.manage_backup_gui, 'GUI', recorder('manage'))
    monkeypatch.setattr(create_backup_gui.manage_backup_gui, 'GUI', recorder('manage'))
    opened.record_create = lambda: monkeypatch.setattr(create_backup_gui, 'GUI', recorder('create'))
    return opened


@pytest.fixture
def known_drive(repo, monkeypatch):
    # makes the fake drive look like a real attached usb drive
    monkeypatch.setattr(backup, 'get_dev_paths_for_uuid', lambda uuid: ['/dev/sdb1', '/dev/disk/by-id/usb-Test_Drive-0:0'])
    monkeypatch.setattr(backup, 'get_free_space', lambda uuid: 5 * 1024 ** 3)
    monkeypatch.setattr(backup, 'get_device_type', lambda uuid: 'local')
    return repo


def select_window(gui_env, known_backups, monkeypatch):
    import select_backup_gui
    monkeypatch.setattr(backup, 'get_known_backups', lambda: known_backups)
    return select_backup_gui.GUI(gui_env.register, gui_env.unregister)


def rows(gui):
    return [list(row) for row in gui.gtkbuilder.get_object('treeview_backups').get_model()]


def select_row(gui, n):
    from gi.repository import Gtk
    treeview = gui.gtkbuilder.get_object('treeview_backups')
    treeview.get_selection().select_path(Gtk.TreePath.new_from_indices([n]))
    return treeview


def properties(repo):
    return backup.get_properties(*repo.args)


# --- select backup window

def test_select_without_backups_offers_to_create_one(gui_env, monkeypatch, recorded_windows):
    recorded_windows.record_create()
    gui = select_window(gui_env, [], monkeypatch)
    assert [row[1] for row in rows(gui)] == ['No existing backups found.\nDouble-click here to create a new backup...']
    select_row(gui, 0)
    gui.open_backup()
    assert [name for name, args in recorded_windows] == ['create']


def test_select_lists_backup_status_for_each_drive(known_drive, gui_env, monkeypatch):
    backup.init_backup(*known_drive.args, None)
    other_host = dict(properties(known_drive), host='another-computer')
    missing_drive = dict(properties(known_drive), uuid='MISSING')
    monkeypatch.setattr(backup, 'is_dev_present', lambda uuid: uuid != 'MISSING')
    types = iter(['local', 'gvfs', None])
    monkeypatch.setattr(backup, 'get_device_type', lambda uuid: next(types))
    gui = select_window(gui_env, [properties(known_drive), other_host, missing_drive], monkeypatch)
    texts = [row[1] for row in rows(gui)]
    assert 'Drive is ready for backups' in texts[0] and '5.0GB free' in texts[0]
    assert 'export only' in texts[1]
    assert 'Drive is unavailable' in texts[2]
    assert texts[3].startswith('Double-click here')
    gui.close()


def test_select_buttons_follow_selection(known_drive, gui_env, monkeypatch):
    backup.init_backup(*known_drive.args, None)
    gui = select_window(gui_env, [properties(known_drive)], monkeypatch)
    treeview = gui.gtkbuilder.get_object('treeview_backups')
    treeview.get_selection().unselect_all()
    gui.update_buttons(treeview)
    assert not gui.gtkbuilder.get_object('button_open').get_sensitive()
    select_row(gui, 0)
    gui.update_buttons(treeview)
    assert gui.gtkbuilder.get_object('button_open').get_sensitive()
    assert gui.gtkbuilder.get_object('button_delete').get_sensitive()
    gui.close()


def test_open_unprotected_backup(known_drive, gui_env, monkeypatch, recorded_windows):
    backup.init_backup(*known_drive.args, None)
    gui = select_window(gui_env, [properties(known_drive)], monkeypatch)
    select_row(gui, 0)
    gui.open_backup()
    assert recorded_windows == [('manage', (gui_env.register, gui_env.unregister, *known_drive.args, None))]


def test_open_protected_backup_asks_for_password(known_drive, gui_env, monkeypatch, recorded_windows):
    import password_managment
    backup.init_backup(*known_drive.args, 'pw')
    gui = select_window(gui_env, [properties(known_drive)], monkeypatch)
    select_row(gui, 0)
    gui.open_backup()
    dialog, = gui_env.find(password_managment.GUI)
    assert dialog.check_password_window['main_window'].get_visible()
    dialog.check_password_window['password_entry_question'].set_text('pw')
    dialog.passwordCheck_okClicked()
    assert recorded_windows == [('manage', (gui_env.register, gui_env.unregister, *known_drive.args, 'pw'))]
    gui.passwordCancel()


def test_delete_backup_after_confirmation(known_drive, gui_env, monkeypatch):
    from gi.repository import Gtk
    backup.init_backup(*known_drive.args, None)
    gui = select_window(gui_env, [properties(known_drive)], monkeypatch)
    select_row(gui, 0)
    gui_env.dialog_response = Gtk.ResponseType.NO
    gui.delete_backup()
    assert os.path.isdir(backup.get_backupPath(*known_drive.args))
    gui_env.dialog_response = Gtk.ResponseType.YES
    gui.delete_backup()
    gui_env.wait_for_takedowns(1)
    assert not os.path.exists(backup.get_backupPath(*known_drive.args))
    gui.close()


# --- create backup window

def create_window(gui_env, monkeypatch, devices):
    import create_backup_gui
    monkeypatch.setattr(backup, 'get_writable_devices', lambda: devices)
    return create_backup_gui.GUI(gui_env.register, gui_env.unregister)


def choose_folder(monkeypatch, preview_uri, filename):
    from gi.repository import Gtk
    monkeypatch.setattr(Gtk.FileChooserButton, 'get_preview_uri', lambda self: preview_uri)
    monkeypatch.setattr(Gtk.FileChooserButton, 'get_filename', lambda self: filename)


def test_create_without_writable_drives(gui_env, monkeypatch):
    gui = create_window(gui_env, monkeypatch, [])
    assert 'needs a hard drive' in rows(gui)[0][1]
    assert not gui.gtkbuilder.get_object('button_new').get_sensitive()
    gui.close()


def test_create_lists_drives_by_type(known_drive, gui_env, monkeypatch):
    types = iter(['gvfs', None, 'local'])
    monkeypatch.setattr(backup, 'get_device_type', lambda uuid: next(types))
    gui = create_window(gui_env, monkeypatch, ['A', 'B', 'C'])
    assert len(rows(gui)) == 3 and all('Free Space:</b> 5.0GB' in row[1] for row in rows(gui))
    assert gui.gtkbuilder.get_object('button_new').get_sensitive()
    gui.close()


def test_create_needs_a_selected_drive(known_drive, gui_env, monkeypatch, recorded_windows):
    gui = create_window(gui_env, monkeypatch, [known_drive.uuid])
    gui.init_backup('pw')
    assert gui_env.dialogs_run and recorded_windows == []
    gui.close()


@pytest.mark.parametrize('use_preview_uri', [True, False])
def test_create_backup_for_chosen_folder(known_drive, gui_env, monkeypatch, recorded_windows, use_preview_uri):
    gui = create_window(gui_env, monkeypatch, [known_drive.uuid])
    choose_folder(monkeypatch, 'file://' + known_drive.path if use_preview_uri else None, known_drive.path)
    select_row(gui, 0)
    gui.init_backup('pw')
    assert backup.check_password('pw', backup.get_properties(*known_drive.args)['password'])
    assert recorded_windows == [('manage', (gui_env.register, gui_env.unregister, *known_drive.args, 'pw'))]


def test_create_existing_backup_does_not_open_it(known_drive, gui_env, monkeypatch, recorded_windows):
    backup.init_backup(*known_drive.args, 'pw')
    gui = create_window(gui_env, monkeypatch, [known_drive.uuid])
    choose_folder(monkeypatch, None, known_drive.path)
    select_row(gui, 0)
    gui.init_backup('pw')
    assert recorded_windows == []
    gui.close()


def test_create_asks_for_new_password(known_drive, gui_env, monkeypatch):
    import password_managment
    gui = create_window(gui_env, monkeypatch, [known_drive.uuid])
    gui.init_passwordSet()
    dialog, = gui_env.find(password_managment.GUI)
    assert dialog.new_password_window['main_window'].get_visible()
    dialog.close()
    gui.close()


# --- new password dialog

@pytest.fixture
def new_password(gui_env):
    import password_managment
    chosen = []
    dialog = password_managment.GUI(gui_env.register, gui_env.unregister)
    dialog.newPasswordDialog_show(None, chosen.append)
    return dialog, dialog.new_password_window, chosen


def test_new_password_must_match(new_password):
    dialog, window, chosen = new_password
    window['password_entry1'].set_text('one')
    window['password_entry2'].set_text('two')
    assert window['password_mismatch'].get_visible() and not window['ok_button'].get_sensitive()
    window['password_entry2'].set_text('one')
    assert not window['password_mismatch'].get_visible() and window['ok_button'].get_sensitive()
    dialog.newPassword_okClicked(None)
    assert chosen == ['one']


def test_new_password_cannot_be_empty(new_password):
    dialog, window, chosen = new_password
    window['password_entry1'].set_text('a')
    window['password_entry1'].set_text('')
    assert window['password_missing'].get_visible()


def test_new_password_can_be_skipped(new_password):
    dialog, window, chosen = new_password
    window['password_checkbutton'].set_active(True)
    assert not window['password_entry1'].get_sensitive() and window['ok_button'].get_sensitive()
    window['password_checkbutton'].set_active(False)
    assert window['password_entry1'].get_sensitive() and not window['ok_button'].get_sensitive()
    window['password_checkbutton'].set_active(True)
    dialog.newPassword_okClicked(None)
    assert chosen == [None]


def test_password_check_cancel(gui_env):
    import password_managment
    cancelled = []
    dialog = password_managment.GUI(gui_env.register, gui_env.unregister)
    dialog.passwordCheckDialog_show(None, backup.gen_passwordEncrypt('pw'), lambda p: None, lambda: cancelled.append(1))
    dialog.passwordCheck_cancelClicked()
    assert cancelled == [1]


# --- preferences dialog

def test_preferences_round_trip(repo, gui_env):
    import manage_backup_preferences_gui
    backup.init_backup(*repo.args, None)
    backup.save_preferences(*repo.args, {'exclude_filters': '**/tmp/', 'exclude_filesize': 2})
    gui = manage_backup_preferences_gui.GUI(gui_env.register, gui_env.unregister, *repo.args)
    get = gui.gtkbuilder.get_object
    assert get('custom_exclude_filter_value').get_text() == '**/tmp/'
    assert get('checkbutton_exclude_filesize').get_active()
    get('checkbutton_exclude_audio').set_active(False)
    get('custom_exclude_filter_value').set_text('**/build/')
    gui.save()
    preferences = backup.get_preferences(*repo.args)
    assert preferences['exclude_audio'] is False
    assert preferences['exclude_filters'] == '**/build/'
    assert preferences['exclude_filesize'] == 2


def test_preferences_unchecked_options_are_cleared(repo, gui_env):
    import manage_backup_preferences_gui
    backup.init_backup(*repo.args, None)
    backup.save_preferences(*repo.args, {'exclude_filters': '**/tmp/', 'exclude_filesize': 2})
    gui = manage_backup_preferences_gui.GUI(gui_env.register, gui_env.unregister, *repo.args)
    get = gui.gtkbuilder.get_object
    get('checkbox_custom_filter_list').set_active(False)
    assert get('custom_exclude_filter_value').get_text() == ''
    get('checkbox_custom_filter_list').set_active(True)
    assert get('custom_exclude_filter_value').get_editable()
    get('checkbox_custom_filter_list').set_active(False)
    get('checkbutton_exclude_filesize').set_active(False)
    gui.save()
    preferences = backup.get_preferences(*repo.args)
    assert preferences['exclude_filters'] == '' and preferences['exclude_filesize'] == 0


# --- error dialog

def test_error_dialog_is_shown_on_the_main_thread(gui_env, monkeypatch):
    import error_dialog
    monkeypatch.setattr(backup, 'SHOW_ERROR_DIALOGS', True)
    backup.launch_error('something broke')
    dialog, = gui_env.dialogs_run
    assert isinstance(dialog, error_dialog.ErrorDialog)
