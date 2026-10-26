import hashlib
import os

import pytest

import backup
from conftest import PRODUCTION_HASH_ITERATIONS, stored_hash, write_legacy_hash


def test_production_hashing_is_slow_enough():
    # the tests lower the count, the shipped value must stay high
    assert PRODUCTION_HASH_ITERATIONS >= 100000


def test_hash_is_salted_pbkdf2():
    first, second = (backup.gen_passwordEncrypt('s3cret'),
                     backup.gen_passwordEncrypt('s3cret'))
    assert first.startswith('pbkdf2_sha256$')
    assert first != second


def test_check_password_pbkdf2():
    password_hash = backup.gen_passwordEncrypt('s3cret')
    assert backup.check_password('s3cret', password_hash)
    assert not backup.check_password('nope', password_hash)


def test_check_password_legacy_md5():
    legacy = hashlib.md5(b's3cret').hexdigest()
    assert backup.check_password('s3cret', legacy)
    assert not backup.check_password('nope', legacy)


@pytest.mark.parametrize('password', ['', None])
def test_empty_password_or_hash_never_matches(password):
    assert not backup.check_password(password, '')
    assert not backup.check_password('s3cret', '')


def test_init_backup_stores_pbkdf2_hash(repo):
    assert backup.init_backup(*repo.args, 'pw')
    assert stored_hash(repo).startswith('pbkdf2_sha256$')


def test_upgrade_legacy_hash(repo):
    backup.init_backup(*repo.args, 'pw')
    before = backup.get_properties(*repo.args)
    write_legacy_hash(repo, 'pw')
    assert backup.upgrade_password_hash(*repo.args, 'pw')
    upgraded = stored_hash(repo)
    assert upgraded.startswith('pbkdf2_sha256$')
    assert backup.check_password('pw', upgraded)
    after = backup.get_properties(*repo.args)
    assert ({k: v for k, v in after.items() if k != 'password'}
            == {k: v for k, v in before.items() if k != 'password'})
    assert not [f for f in os.listdir(backup.get_backupPath(*repo.args))
                if f.endswith('.tmp')]


def test_upgrade_with_wrong_password_keeps_legacy_hash(repo):
    backup.init_backup(*repo.args, 'pw')
    write_legacy_hash(repo, 'pw')
    legacy = stored_hash(repo)
    assert not backup.upgrade_password_hash(*repo.args, 'nope')
    assert stored_hash(repo) == legacy


def test_upgrade_is_a_noop_for_pbkdf2_hashes(repo):
    backup.init_backup(*repo.args, 'pw')
    current = stored_hash(repo)
    assert not backup.upgrade_password_hash(*repo.args, 'pw')
    assert stored_hash(repo) == current


@pytest.mark.skipif(os.geteuid() == 0,
                    reason='root can write to read-only directories')
def test_upgrade_on_read_only_drive_keeps_legacy_hash(repo):
    backup.init_backup(*repo.args, 'pw')
    write_legacy_hash(repo, 'pw')
    db_dir = backup.get_backupPath(*repo.args)
    os.chmod(db_dir, 0o555)
    try:
        assert not backup.upgrade_password_hash(*repo.args, 'pw')
    finally:
        os.chmod(db_dir, 0o755)
    assert stored_hash(repo) == hashlib.md5(b'pw').hexdigest()
