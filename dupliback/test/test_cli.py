import hashlib
import os
import pickle
import shutil
import subprocess
import sys

import pytest

import backup
import dupliback
from conftest import SRC_DIR


def test_unknown_drive_is_skipped_without_dialogs():
    result = subprocess.run([sys.executable, os.path.join(SRC_DIR, 'dupliback.py'), 'NO-SUCH-UUID', '/tmp'],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True, timeout=60)
    assert 'skipped backup: NO-SUCH-UUID /tmp' in result.stdout


@pytest.mark.skipif(shutil.which('duplicity') is None, reason='duplicity is not installed')
@pytest.mark.parametrize('passphrase, upgraded', [('pw', True), ('nope', False)])
def test_cli_backup_checks_password_and_upgrades_hash(repo, monkeypatch, passphrase, upgraded):
    with open(os.path.join(repo.path, 'a'), 'w') as f:
        f.write('a')
    backup.init_backup(*repo.args, 'pw')
    properties = backup.get_properties(*repo.args)
    properties['password'] = hashlib.md5(b'pw').hexdigest()
    with open(os.path.join(backup.get_backupPath(*repo.args), backup.PROPERTIES_FILE), 'wb') as f:
        pickle.dump(properties, f)
    monkeypatch.setenv('PASSPHRASE', passphrase)
    dupliback.run_backup(repo.uuid, repo.path, repo.host)
    stored = backup.get_properties(*repo.args)['password']
    assert stored.startswith('pbkdf2_sha256$') == upgraded
    assert bool(backup.get_revisions(*repo.args)) == upgraded
