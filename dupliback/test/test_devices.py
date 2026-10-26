# backend helpers that parse udevadm / mount / df output, driven with canned output
import os
import pickle
import threading

import pytest

import backup
import settings

UDEVADM_OUTPUT = [
    'P: /devices/pci0000:00/usb1/1-1/host6/block/sdb/sdb1\n',
    'N: sdb1\n',
    'S: disk/by-id/usb-Foo_Bar-0:0-part1\n',
    'E: DEVNAME=/dev/sdb1\n',
    'E: DEVLINKS=/dev/disk/by-id/usb-Foo_Bar-0:0-part1 /dev/disk/by-uuid/1234-ABCD\n',
]
MOUNT_OUTPUT = [
    '/dev/sda2 on / type ext4 (rw,relatime)\n',
    '/dev/sdb1 on /media/usb type vfat (rw,nosuid)\n',
]


def fake_command_output(monkeypatch, outputs):
    # outputs maps the command name to the lines it prints
    monkeypatch.setattr(backup, 'exec_subprocess_cmd', lambda cmd, env=None: iter(outputs[cmd[0]]))


def test_dev_paths_include_devname_and_devlinks(monkeypatch):
    fake_command_output(monkeypatch, {'udevadm': UDEVADM_OUTPUT})
    assert set(backup.get_dev_paths_for_uuid('1234-ABCD')) == {
        '/dev/sdb1', '/dev/disk/by-id/usb-Foo_Bar-0:0-part1', '/dev/disk/by-uuid/1234-ABCD'}


def test_mount_point_for_uuid(monkeypatch):
    fake_command_output(monkeypatch, {'udevadm': UDEVADM_OUTPUT, 'mount': MOUNT_OUTPUT})
    assert backup.get_mount_point_for_uuid('1234-ABCD') == '/media/usb'


def test_mount_point_for_unmounted_uuid(monkeypatch):
    fake_command_output(monkeypatch, {'udevadm': [], 'mount': MOUNT_OUTPUT})
    assert backup.get_mount_point_for_uuid('1234-ABCD') is None


def test_drive_name_uses_by_id_link(monkeypatch):
    fake_command_output(monkeypatch, {'udevadm': UDEVADM_OUTPUT})
    assert backup.get_drive_name('1234-ABCD') == 'usb-Foo_Bar-0:0-part1'


def test_drive_name_falls_back_to_uuid(monkeypatch):
    fake_command_output(monkeypatch, {'udevadm': []})
    assert backup.get_drive_name('1234-ABCD') == 'UUID: 1234-ABCD'


@pytest.mark.parametrize('df_line, expected', [
    ('/dev/sdb1  1000  10  990  1% /media/usb\n', 990 * 1024),
    ('/dev/sdb1  0  0  0  -  /media/usb\n', -1),
])
def test_free_space(monkeypatch, df_line, expected):
    monkeypatch.setattr(backup, 'get_mount_point_for_uuid', lambda uuid: '/media/usb')
    fake_command_output(monkeypatch, {'df': ['Filesystem 1K-blocks Used Available Use% Mounted on\n', df_line]})
    assert backup.get_free_space('1234-ABCD') == expected


def test_free_space_without_output(monkeypatch):
    monkeypatch.setattr(backup, 'get_mount_point_for_uuid', lambda uuid: '/media/usb')
    fake_command_output(monkeypatch, {'df': []})
    assert backup.get_free_space('1234-ABCD') == -1


def test_real_commands_run():
    # exercises the real subprocess helpers against harmless commands
    assert [line.strip() for line in backup.exec_subprocess_cmd(['echo', 'hello'])] == ['hello']
    assert backup.run_subprocess_cmd(['true']) == 0
    assert backup.run_subprocess_cmd(['false']) != 0


def test_unknown_uuid_is_not_present():
    assert not backup.is_dev_present('NO-SUCH-UUID')
    assert backup.get_device_type('NO-SUCH-UUID') is None
    assert isinstance(backup.get_mounted_devices(), list)


def test_known_device_type_is_local(monkeypatch):
    monkeypatch.setattr(backup.os.path, 'exists', lambda path: True)
    assert backup.get_device_type('ANY') == 'local'


def test_known_backups_are_discovered(tmp_path, monkeypatch):
    good = tmp_path / '.duplibackdb_good'
    good.mkdir()
    with open(good / backup.PROPERTIES_FILE, 'wb') as f:
        pickle.dump({'uuid': 'U', 'host': 'h', 'path': '/src'}, f)
    (tmp_path / '.duplibackdb_broken').mkdir()
    monkeypatch.setattr(backup, 'get_mounted_devices', lambda: ['U', 'UNMOUNTED', 'ERROR'])
    def mount_point(uuid):
        if uuid == 'ERROR':
            raise OSError('udevadm failed')
        return str(tmp_path) if uuid == 'U' else None
    monkeypatch.setattr(backup, 'get_mount_point_for_uuid', mount_point)
    assert backup.get_known_backups() == [{'uuid': 'U', 'host': 'h', 'path': '/src', 'password': ''}]


def test_writable_devices(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, 'get_mounted_devices', lambda: ['WRITABLE', 'MISSING', 'UNMOUNTED'])
    paths = {'WRITABLE': str(tmp_path), 'MISSING': str(tmp_path / 'missing'), 'UNMOUNTED': None}
    monkeypatch.setattr(backup, 'get_mount_point_for_uuid', paths.get)
    assert backup.get_writable_devices() == ['WRITABLE']
    assert os.listdir(tmp_path) == []


def test_backup_assertions_pass(repo):
    backup.init_backup(*repo.args, None)
    assert backup.test_backup_assertions(*repo.args)


def test_backup_assertions_fail_when_drive_missing(repo, monkeypatch):
    monkeypatch.setattr(backup, 'is_dev_present', lambda uuid: False)
    assert not backup.test_backup_assertions(*repo.args)


def test_backup_assertions_fail_for_other_host(repo):
    assert not backup.test_backup_assertions(repo.uuid, 'some-other-host', repo.path)


def test_backup_assertions_fail_for_missing_source(repo):
    assert not backup.test_backup_assertions(repo.uuid, repo.host, repo.path + '-missing')


def test_backup_assertions_fail_without_backup_dir(repo):
    assert not backup.test_backup_assertions(*repo.args)
    assert backup.test_backup_assertions(*repo.args, test_exists=False)


def test_preferences_default_without_backup(repo):
    assert backup.get_preferences(*repo.args) == settings.DEFAULT_PREFERENCES


def test_preferences_from_old_versions_are_migrated(repo):
    backup.init_backup(*repo.args, None)
    with open(os.path.join(backup.get_backupPath(*repo.args), backup.PREFERENCES_FILE), 'wb') as f:
        pickle.dump({'exclude_audio': False, 'exclude_filesize': None}, f)
    preferences = backup.get_preferences(*repo.args)
    assert preferences['exclude_audio'] is False
    assert preferences['exclude_filesize'] == 0
    assert preferences['exclude_filters'] == ''
    assert preferences['password_protect'] is False
    assert preferences['app_version'] == settings.PROGRAM_VERSION


def test_save_preferences_merges(repo):
    backup.init_backup(*repo.args, None)
    backup.save_preferences(*repo.args, {'exclude_iso': False})
    preferences = backup.get_preferences(*repo.args)
    assert preferences['exclude_iso'] is False and preferences['exclude_audio'] is True


def test_save_preferences_without_backup_dir_does_not_raise(repo):
    backup.save_preferences(*repo.args, {'exclude_iso': False})


def test_properties_missing(repo):
    assert backup.get_properties(*repo.args) == {}
    assert not backup.save_properties(*repo.args, {'password': ''})


def test_backup_db_name_is_stable():
    name = backup.get_git_db_name('U', 'h', '/src')
    assert name.startswith('.duplibackdb_') and name == backup.get_git_db_name('U', 'h', '/src')
    assert name != backup.get_git_db_name('U', 'h', '/other')


def test_launch_error_is_silent_when_disabled(monkeypatch):
    shown = []
    monkeypatch.setattr(backup, 'show_error_dialog', shown.append)
    backup.launch_error('nope')
    assert shown == []


def test_launch_error_from_worker_thread_goes_through_main_loop(monkeypatch):
    shown, queued = [], []
    monkeypatch.setattr(backup, 'SHOW_ERROR_DIALOGS', True)
    monkeypatch.setattr(backup, 'show_error_dialog', shown.append)
    monkeypatch.setattr(backup.GLib, 'idle_add', lambda func, *args: queued.append((func, args)))
    thread = threading.Thread(target=backup.launch_error, args=('from a thread',))
    thread.start()
    thread.join()
    backup.launch_error('from the main thread')
    assert queued == [(shown.append, ('from a thread',))]
    assert shown == ['from the main thread']
