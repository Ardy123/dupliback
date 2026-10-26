# integration tests that run the real duplicity binary against a fake drive
import datetime
import os
import shutil
import subprocess
import tarfile

import pytest

import backup
from conftest import mark_modified, pin_dir_mtimes, read, status_count, write

pytestmark = pytest.mark.skipif(shutil.which('duplicity') is None,
                                reason='duplicity is not installed')


def volumes(repo):
    return [f for f in os.listdir(backup.get_backupPath(*repo.args))
            if '.difftar' in f]


def latest_revision(repo):
    rev = backup.get_revisions(*repo.args)[-1]
    return '%s-%02d-%02dT%s' % (rev['year'], rev['month'],
                                int(rev['dayOfMo']), rev['time'])


def list_files(repo, rev, password):
    files = []
    backup.get_files_for_revision(*repo.args, rev, password, files.append)
    return [name for name, date in files]


def test_init_backup_twice_reports_instead_of_exiting(protected):
    assert backup.init_backup(*protected.args, 'pw') is False


def test_password_protected_backup_is_encrypted(protected):
    assert volumes(protected) and all(v.endswith('.gpg')
                                      for v in volumes(protected))


def test_passwordless_backup_is_not_encrypted(repo):
    write(os.path.join(repo.path, 'a'), 'a')
    backup.init_backup(*repo.args, None)
    assert backup.backup(*repo.args, None) == 0
    assert volumes(repo) and all(v.endswith('.gz') for v in volumes(repo))


def test_backup_applies_exclusions(repo):
    write(os.path.join(repo.path, 'song.mp3'), 'mp3')
    write(os.path.join(repo.path, 'movie.mp4'), 'mp4')
    write(os.path.join(repo.path, 'big.bin'), 'x' * 4096)
    write(os.path.join(repo.path, 'small.bin'), 'x')
    backup.init_backup(*repo.args, None)
    backup.save_preferences(*repo.args, {
        'exclude_audio': True, 'exclude_video': False,
        'exclude_filesize': 2048 / 1024 ** 3})
    backup.backup(*repo.args, None)
    names = list_files(repo, latest_revision(repo), None)
    assert 'song.mp3' not in names and 'big.bin' not in names
    assert 'movie.mp4' in names and 'small.bin' in names


def test_listing_keeps_paths_with_spaces(protected):
    assert 'my docs/file with spaces.txt' in list_files(
        protected, latest_revision(protected), 'pw')


def test_status_reports_changes_with_correct_labels(protected):
    write(os.path.join(protected.path, 'new.txt'), 'n')
    modified_file = os.path.join(protected.path, 'my docs',
                                 'file with spaces.txt')
    write(modified_file, 'v2')
    mark_modified(modified_file)
    os.remove(os.path.join(protected.path, 'small.bin'))
    pin_dir_mtimes(protected.path)
    added, modified, deleted = backup.get_status(*protected.args, 'pw')
    assert status_count('New Files', added) == 1
    assert status_count('Modified Files', modified) == 1
    assert status_count('Deleted Files', deleted) == 1


def test_status_without_changes(protected):
    added, modified, deleted = backup.get_status(*protected.args, 'pw')
    assert [status_count('New Files', added),
            status_count('Modified Files', modified),
            status_count('Deleted Files', deleted)] == [0, 0, 0]


def test_restore_single_file_with_spaces(protected):
    rev = latest_revision(protected)
    target = os.path.join(protected.path, 'my docs', 'file with spaces.txt')
    write(target, 'changed')
    assert backup.restore_to_revision(*protected.args, rev, 'pw',
                                      '/my docs/file with spaces.txt') == 0
    assert read(target) == 'v1'


def test_restore_whole_revision_over_existing_source(protected):
    rev = latest_revision(protected)
    write(os.path.join(protected.path, 'my docs', 'file with spaces.txt'),
          'changed')
    os.remove(os.path.join(protected.path, 'small.bin'))
    assert backup.restore_to_revision(*protected.args, rev, 'pw') == 0
    assert read(os.path.join(protected.path, 'my docs',
                             'file with spaces.txt')) == 'v1'
    assert os.path.isfile(os.path.join(protected.path, 'small.bin'))
    assert not [d for d in os.listdir(protected.path)
                if d.startswith('.dupliback_restore_')]


def test_export_creates_tarball_with_relative_paths(protected, tmp_path):
    fn, tmp_dir = backup.export_revision(
        *protected.args, latest_revision(protected), str(tmp_path), 'pw')
    try:
        members = tarfile.open(fn).getnames()
        assert members and all(m.startswith('archive-') for m in members)
    finally:
        backup.rmdir(os.path.dirname(tmp_dir))
    assert not os.path.exists(os.path.dirname(tmp_dir))


def test_explore_restores_without_tarball(protected):
    fn, tmp_dir = backup.export_revision(
        *protected.args, latest_revision(protected), None, 'pw')
    try:
        assert fn is None
        assert os.path.isfile(os.path.join(tmp_dir, 'small.bin'))
    finally:
        backup.rmdir(os.path.dirname(tmp_dir))


def test_export_with_wrong_password_fails(protected, tmp_path):
    fn, tmp_dir = backup.export_revision(
        *protected.args, latest_revision(protected), str(tmp_path), 'wrong')
    backup.rmdir(os.path.dirname(tmp_dir))
    assert fn is None


def test_legacy_passwordless_backup_encrypted_with_none(repo):
    # 0.3.0 - 0.4.0 encrypted password-less backups with passphrase 'None'
    write(os.path.join(repo.path, 'old'), 'old')
    backup.init_backup(*repo.args, None)
    subprocess.run(['duplicity', repo.path, backup.get_backupUri(*repo.args)],
                   env=dict(os.environ, PASSPHRASE='None'),
                   stdout=subprocess.DEVNULL, check=True)
    write(os.path.join(repo.path, 'newer'), 'new')
    assert backup.backup(*repo.args, None) == 0
    rev = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    fn, tmp_dir = backup.export_revision(*repo.args, rev, None, None)
    try:
        assert os.path.isfile(os.path.join(tmp_dir, 'old'))
        assert os.path.isfile(os.path.join(tmp_dir, 'newer'))
    finally:
        backup.rmdir(os.path.dirname(tmp_dir))


def test_delete_backup(protected):
    backup.delete_backup(*protected.args)
    assert not os.path.exists(backup.get_backupPath(*protected.args))
