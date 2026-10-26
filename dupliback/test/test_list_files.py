# the fast listing of a moment from its signature files, checked against
# duplicity's own list-current-files
import io
import os
import shutil
import tarfile
import time

import pytest

import backup
import sigtar
from conftest import write

needs_duplicity = pytest.mark.skipif(shutil.which('duplicity') is None,
                                     reason='duplicity is not installed')

# moments at fixed epochs in a DST summer, so local time and UTC differ
BASE = 1784000000
LONG_NAME = 'deep/' + 'n' * 120 + '.txt'
LONG_TARGET = '/' + 't' * 150


def moments(repo, password, steps):
    # backs up repo.path once per step, step k at BASE + 100 * k
    backup.init_backup(*repo.args, password)
    epochs = []
    for k, step in enumerate(steps):
        step(repo.path)
        epoch = BASE + 100 * k
        operands = [repo.path, backup.get_backupUri(*repo.args),
                    '--allow-source-mismatch']
        assert backup.run_duplicity(
            password, ['--current-time', str(epoch)], operands) == 0
        epochs.append(epoch)
    return epochs


def fast(repo, epoch, password):
    found = []
    backup.list_files(*repo.args, str(epoch), password, found.append)
    return found


def slow(repo, epoch, password):
    found = []
    backup.get_files_for_revision(*repo.args, str(epoch), password,
                                  found.append)
    return found


def first(root):
    write(os.path.join(root, 'keep.txt'), 'k')
    write(os.path.join(root, 'gone.txt'), 'g')
    write(os.path.join(root, 'dir with spaces', 'ünïcode.txt'), 'u')
    write(os.path.join(root, LONG_NAME), 'long')
    os.makedirs(os.path.join(root, 'empty dir'))
    os.symlink('keep.txt', os.path.join(root, 'link'))
    os.symlink(LONG_TARGET, os.path.join(root, 'long link'))


def second(root):
    os.remove(os.path.join(root, 'gone.txt'))
    os.rename(os.path.join(root, 'keep.txt'), os.path.join(root, 'moved.txt'))
    write(os.path.join(root, 'new.txt'), 'n')
    os.remove(os.path.join(root, 'link'))
    os.symlink('moved.txt', os.path.join(root, 'link'))


def third(root):
    write(os.path.join(root, 'gone.txt'), 're-created')
    shutil.rmtree(os.path.join(root, 'dir with spaces'))
    write(os.path.join(root, 'new.txt'), 'changed')


STEPS = [first, second, third]


@pytest.fixture
def los_angeles(monkeypatch):
    # a zone with summer time, where the old zone-less --time was an hour off
    monkeypatch.setenv('TZ', 'America/Los_Angeles')
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


@needs_duplicity
@pytest.mark.parametrize('password', ['pw', None])
def test_matches_duplicity_for_every_moment(repo, password, los_angeles):
    for epoch in moments(repo, password, STEPS):
        assert fast(repo, epoch, password) == slow(repo, epoch, password)


@needs_duplicity
def test_moment_states(repo, los_angeles):
    one, two, three = moments(repo, 'pw', STEPS)
    names = lambda epoch: [name for name, date in fast(repo, epoch, 'pw')]
    assert names(one)[0] == '.'
    assert {'keep.txt', 'gone.txt', 'dir with spaces/ünïcode.txt', LONG_NAME,
            'empty dir', 'link', 'long link'} <= set(names(one))
    assert 'gone.txt' not in names(two) and 'moved.txt' in names(two)
    assert 'gone.txt' in names(three)
    assert not [n for n in names(three) if n.startswith('dir with spaces')]


@needs_duplicity
def test_revisions_have_exact_epochs(repo, los_angeles):
    epochs = moments(repo, 'pw', STEPS)
    revisions = backup.get_revisions(*repo.args)
    assert [rev['epoch'] for rev in revisions] == epochs
    assert [rev['type'] for rev in revisions] == [
        'Full', 'Incremental', 'Incremental']
    assert [backup.revision_id(rev) for rev in revisions] == [
        str(epoch) for epoch in epochs]
    # shown in local time, 7 hours behind UTC in the summer
    assert revisions[0]['time'] == time.strftime('%H:%M:%S',
                                                 time.localtime(BASE))


@needs_duplicity
def test_reads_the_drive_without_duplicitys_cache(repo, monkeypatch):
    epochs = moments(repo, 'pw', STEPS)
    expected = slow(repo, epochs[-1], 'pw')
    shutil.rmtree(backup.duplicity_cache_dir(
        backup.get_backupPath(*repo.args)))
    monkeypatch.setattr(backup, 'get_files_for_revision', None)
    assert fast(repo, epochs[-1], 'pw') == expected


@needs_duplicity
def test_wrong_password_falls_back_to_duplicity(repo, monkeypatch):
    epochs = moments(repo, 'pw', STEPS)
    shutil.rmtree(backup.duplicity_cache_dir(
        backup.get_backupPath(*repo.args)))
    fallback = []
    monkeypatch.setattr(backup, 'get_files_for_revision',
                        lambda *args: fallback.append(args))
    fast(repo, epochs[-1], 'wrong')
    assert len(fallback) == 1


@needs_duplicity
def test_listing_is_cached(repo, monkeypatch):
    epochs = moments(repo, 'pw', STEPS)
    listed = fast(repo, epochs[1], 'pw')
    def no_replay(*args, **kwargs):
        raise AssertionError('the listing should come from the cache')
    monkeypatch.setattr(sigtar, 'replay', no_replay)
    assert fast(repo, epochs[1], 'pw') == listed
    backup.delete_backup(*repo.args)
    assert not os.path.exists(backup.listing_cache_dir(
        backup.get_backupPath(*repo.args)))


@needs_duplicity
def test_names_with_newlines(repo):
    epoch, = moments(repo, None, [
        lambda root: write(os.path.join(root, 'two\nlines'), 'x')])
    assert 'two\nlines' in [name for name, date in fast(repo, epoch, None)]


@needs_duplicity
def test_own_caches_are_never_backed_up(repo, monkeypatch):
    cache = os.path.join(repo.path, 'xdg cache')
    monkeypatch.setenv('XDG_CACHE_HOME', cache)
    write(os.path.join(cache, 'dupliback', 'x.list'), 'x')
    write(os.path.join(repo.path, 'data.txt'), 'd')
    backup.init_backup(*repo.args, None)
    backup.save_preferences(*repo.args, {'exclude_cache': False})
    assert backup.backup(*repo.args, None) == 0
    rev = backup.revision_id(backup.get_revisions(*repo.args)[-1])
    names = [name for name, date in fast(repo, rev, None)]
    assert 'data.txt' in names
    assert not [name for name in names if name.startswith('xdg cache/')]


def test_no_cache_exclusions_when_caches_are_elsewhere(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    assert backup.own_cache_exclusions(str(tmp_path / 'src')) == []


@pytest.mark.parametrize('epoch, expected', [
    (backup.utc_epoch('20200101T000000Z'), ['full-a']),
    (backup.utc_epoch('20200301T000000Z'), ['full-a', 'inc-1', 'inc-2']),
    (backup.utc_epoch('20210101T000000Z'), ['full-b']),
    (backup.utc_epoch('20200201T120000Z'), None),
    (backup.utc_epoch('20190101T000000Z'), None),
])
def test_signature_chain(epoch, expected):
    files = {
        'full-a': 'duplicity-full-signatures.20200101T000000Z.sigtar.gpg',
        'inc-1': 'duplicity-new-signatures.20200101T000000Z.to.'
                 '20200201T000000Z.sigtar.gpg',
        'inc-2': 'duplicity-new-signatures.20200201T000000Z.to.'
                 '20200301T000000Z.sigtar.gpg',
        'full-b': 'duplicity-full-signatures.20210101T000000Z.sigtar.gz',
    }
    listing = list(files.values()) + ['duplicity-full.x.manifest', 'other']
    chain = backup.signature_chain(listing, epoch)
    assert chain == (None if expected is None
                     else [files[key] for key in expected])


def test_revision_label():
    assert backup.revision_label('2026-03-21T07:55:13') == '2026-03-21T07.55.13'
    assert backup.revision_label(str(BASE)) == time.strftime(
        '%Y-%m-%dT%H.%M.%S', time.localtime(BASE))


# --- the tar reader itself

def tar_bytes(members, fmt=tarfile.GNU_FORMAT, compress=False):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w:gz' if compress else 'w',
                      format=fmt) as tar:
        for name, mtime in members:
            info = tarfile.TarInfo(name)
            info.mtime = mtime
            tar.addfile(info, io.BytesIO(b''))
    return data.getvalue()


@pytest.mark.parametrize('fmt', [tarfile.GNU_FORMAT, tarfile.PAX_FORMAT,
                                 tarfile.USTAR_FORMAT])
@pytest.mark.parametrize('compress', [True, False])
def test_reader_formats(fmt, compress):
    members = [('snapshot/', 1), ('signature/a/b.txt', 2),
               ('deleted/' + 'x' * 90 + '/' + 'y' * 60, 3)]
    found = list(sigtar.entries(io.BytesIO(tar_bytes(members, fmt, compress))))
    assert found == [(b's', 1, b''), (b's', 2, b'a/b.txt'),
                     (b'd', 3, ('x' * 90 + '/' + 'y' * 60).encode())]


def test_reader_large_mtime_uses_base256():
    found = list(sigtar.entries(io.BytesIO(
        tar_bytes([('signature/f', 8 ** 12)]))))
    assert found == [(b's', 8 ** 12, b'f')]


def test_reader_rejects_unknown_entries():
    with pytest.raises(sigtar.FormatError):
        list(sigtar.entries(io.BytesIO(tar_bytes([('other/f', 1)]))))


def test_reader_rejects_truncated_long_names():
    long_name = tar_bytes([('signature/' + 'z' * 200, 1)])
    with pytest.raises(sigtar.FormatError):
        list(sigtar.entries(io.BytesIO(long_name[:512 + 100])))


def test_reader_stops_at_end_without_end_blocks():
    # duplicity's files end with zero blocks; a missing end is still readable
    one_entry = tar_bytes([('signature/f', 1)])[:512]
    assert list(sigtar.entries(io.BytesIO(one_entry))) == [(b's', 1, b'f')]


def test_replay_applies_files_in_order(tmp_path):
    first_file = tmp_path / 'a.sigtar.gz'
    second_file = tmp_path / 'b.sigtar.gz'
    first_file.write_bytes(tar_bytes(
        [('snapshot/', 1), ('signature/x', 2), ('signature/y', 3)],
        compress=True))
    second_file.write_bytes(tar_bytes(
        [('deleted/x', 4), ('signature/y', 5), ('snapshot/z', 6)],
        compress=True))
    state = sigtar.replay([str(first_file), str(second_file)], workers=2)
    assert list(sigtar.listing(state)) == [('.', 1), ('y', 5), ('z', 6)]


def test_replay_reports_unreadable_files(tmp_path):
    bad = tmp_path / 'bad.sigtar.gz'
    bad.write_bytes(b'\x1f\x8bnot really gzip')
    good = tmp_path / 'good.sigtar.gz'
    good.write_bytes(tar_bytes([('snapshot/', 1)], compress=True))
    with pytest.raises(sigtar.FormatError):
        sigtar.replay([str(bad), str(good)], workers=2)


@pytest.mark.skipif(shutil.which('gpg') is None, reason='gpg is not installed')
def test_replay_decrypts_gpg_files(tmp_path, monkeypatch):
    import subprocess
    plain = tmp_path / 'sig.tar'
    plain.write_bytes(tar_bytes([('snapshot/', 1), ('signature/f', 2)]))
    encrypted = str(tmp_path / 'sig.sigtar.gpg')
    monkeypatch.setenv('GNUPGHOME', str(tmp_path / 'gnupg'))
    os.makedirs(str(tmp_path / 'gnupg'), mode=0o700)
    subprocess.run(['gpg', '--batch', '--quiet', '--pinentry-mode', 'loopback',
                    '--passphrase', 'pw', '--symmetric', '--output', encrypted,
                    str(plain)], check=True)
    assert list(sigtar.listing(sigtar.replay([encrypted], 'pw'))) == [
        ('.', 1), ('f', 2)]
    with pytest.raises(sigtar.FormatError):
        sigtar.replay([encrypted], 'wrong')
