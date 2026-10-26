# smoke tests that build the real windows, they need an X display
import os
import shutil

import backup

from conftest import requires_display, run_in_main_loop, stored_hash, write, write_legacy_hash

pytestmark = requires_display


def test_windows_build_and_close(repo, monkeypatch):
    import create_backup_gui, manage_backup_gui, select_backup_gui, backup_progress_gui
    # only the fake drive, not every device on the machine running the tests
    monkeypatch.setattr(backup, 'get_mounted_devices', lambda: [repo.uuid])
    write(os.path.join(repo.path, 'a'), 'a')
    backup.init_backup(*repo.args, 'pw')
    if shutil.which('duplicity'):
        backup.backup(*repo.args, 'pw')
    guis = set()
    def build():
        select = select_backup_gui.GUI(guis.add, guis.discard)
        create = create_backup_gui.GUI(guis.add, guis.discard)
        create.close()
        create.close()
        manage = manage_backup_gui.GUI(guis.add, guis.discard, *repo.args, 'pw')
        revisions = len(manage.gtkbuilder.get_object('treeview_revisions').get_model())
        progress = backup_progress_gui.GUI(guis.add, guis.discard, None, 'testing')
        assert progress.pulse() is True
        progress.takedownProgressBar()
        manage.close()
        select.close()
        return revisions
    revisions = run_in_main_loop(build)
    if shutil.which('duplicity'):
        assert revisions == 1


def test_password_dialog_checks_on_ok():
    import password_managment
    password_hash = backup.gen_passwordEncrypt('pw')
    def build():
        dialog = password_managment.GUI(set().add, lambda g: None)
        window = dialog.check_password_window
        accepted = []
        dialog.passwordCheckDialog_show(None, password_hash, accepted.append, lambda: None)
        state = {'error_hidden_initially': not window['pass_err_labl'].get_visible()}
        window['password_entry_question'].set_text('wrong')
        dialog.passwordCheck_okClicked()
        state['wrong_rejected'] = accepted == [] and window['pass_err_labl'].get_visible()
        window['password_entry_question'].set_text('pw')
        state['ok_enabled_after_typing'] = window['password_check_ok'].get_sensitive()
        dialog.passwordCheck_okClicked()
        state['right_accepted'] = accepted == ['pw']
        return state
    assert run_in_main_loop(build) == {'error_hidden_initially': True, 'wrong_rejected': True,
                                       'ok_enabled_after_typing': True, 'right_accepted': True}


def test_opening_backup_upgrades_legacy_hash(repo, monkeypatch):
    import select_backup_gui
    backup.init_backup(*repo.args, 'pw')
    legacy_hash = write_legacy_hash(repo, 'pw')
    opened = []
    monkeypatch.setattr(select_backup_gui.manage_backup_gui, 'GUI', lambda *args: opened.append(args) or object())
    def build():
        gui = select_backup_gui.GUI(set().add, lambda g: None)
        treeview = gui.gtkbuilder.get_object('treeview_backups')
        model = treeview.get_model()
        model.clear()
        treeview.get_selection().select_iter(model.append((None, 'test', True, *repo.args, legacy_hash)))
        gui.launchManageBackupGui('pw')
    run_in_main_loop(build)
    assert opened
    assert stored_hash(repo).startswith('pbkdf2_sha256$')
