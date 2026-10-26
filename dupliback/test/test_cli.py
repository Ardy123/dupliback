import os
import shutil
import subprocess
import sys

import pytest

import backup
import dupliback
from conftest import SRC_DIR, stored_hash, write, write_legacy_hash


def test_unknown_drive_is_skipped_without_dialogs():
    result = subprocess.run(
        [sys.executable, os.path.join(SRC_DIR, 'dupliback.py'),
         'NO-SUCH-UUID', '/tmp'],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        universal_newlines=True, timeout=60)
    assert 'skipped backup: NO-SUCH-UUID /tmp' in result.stdout


@pytest.mark.skipif(shutil.which('duplicity') is None,
                    reason='duplicity is not installed')
@pytest.mark.parametrize('passphrase, upgraded',
                         [('pw', True), ('nope', False)])
def test_cli_backup_checks_password_and_upgrades_hash(repo, monkeypatch,
                                                      passphrase, upgraded):
    write(os.path.join(repo.path, 'a'), 'a')
    backup.init_backup(*repo.args, 'pw')
    write_legacy_hash(repo, 'pw')
    monkeypatch.setenv('PASSPHRASE', passphrase)
    dupliback.run_backup(repo.uuid, repo.path, repo.host)
    stored = stored_hash(repo)
    assert stored.startswith('pbkdf2_sha256$') == upgraded
    assert bool(backup.get_revisions(*repo.args)) == upgraded
