# prune and squash: every remaining moment must restore exactly as before
import collections
import hashlib
import os
import shutil
import stat
import sys
import time
import types

import pytest

import backup
import merge
from conftest import BASE, STEP, build_moments as build, status_count, write

pytestmark = pytest.mark.skipif(shutil.which('duplicity') is None,
                                reason='duplicity is not installed')

def snapshot(tree):
    # everything a restore must reproduce, per relative path
    found = {}
    for root, dirs, files in os.walk(tree):
        for name in dirs + files:
            path = os.path.join(root, name)
            info = os.lstat(path)
            rel = os.path.relpath(path, tree)
            mode = stat.S_IMODE(info.st_mode)
            if stat.S_ISLNK(info.st_mode):
                found[rel] = ('link', os.readlink(path))
            elif stat.S_ISREG(info.st_mode):
                with open(path, 'rb') as f:
                    digest = hashlib.sha256(f.read()).hexdigest()
                found[rel] = ('file', mode, int(info.st_mtime), info.st_size,
                              digest)
            else:
                found[rel] = (stat.S_IFMT(info.st_mode), mode,
                              int(info.st_mtime))
    return found


def restore_all(repo, password, epochs, tmp_path, label):
    states = {}
    for epoch in epochs:
        tree = str(tmp_path / ('%s-%d' % (label, epoch)))
        assert backup.run_duplicity(
            password, ['restore', '--time', str(epoch)],
            [backup.get_backupUri(*repo.args), tree]) == 0
        states[epoch] = snapshot(tree)
        shutil.rmtree(tree)
    return states


def drive_files(repo):
    d = backup.get_backupPath(*repo.args)
    return {name: hashlib.sha1(open(os.path.join(d, name), 'rb').read())
            .hexdigest() for name in os.listdir(d)}


# --- the chain every scenario starts from: five moments

def step0(root):
    write(os.path.join(root, 'a.txt'), 'aaaa')
    write(os.path.join(root, 'b.txt'), 'b')
    write(os.path.join(root, 'dir', 'inner.txt'), 'inner')
    write(os.path.join(root, 'odd name ünï\ncode'), 'odd')
    os.makedirs(os.path.join(root, 'empty'))
    os.symlink('a.txt', os.path.join(root, 'link'))
    os.mkfifo(os.path.join(root, 'fifo'))
    with open(os.path.join(root, 'big.bin'), 'wb') as f:
        f.write(os.urandom(3 << 20))


def step1(root):
    # same size, new content and mtime; delete; add; mode only
    write(os.path.join(root, 'a.txt'), 'AAAA')
    os.utime(os.path.join(root, 'a.txt'), (BASE + 50, BASE + 50))
    os.remove(os.path.join(root, 'b.txt'))
    write(os.path.join(root, 'c.txt'), 'c1')
    os.chmod(os.path.join(root, 'dir'), 0o700)


def pin(root, *names, when):
    # duplicity skips files whose mtime second and mode match its signature,
    # so edits made within a second of another moment's must not share it
    for name in names:
        os.utime(os.path.join(root, name), (when, when))


def step2(root):
    # re-add b, retarget the link, edit c
    write(os.path.join(root, 'b.txt'), 'b again')
    os.remove(os.path.join(root, 'link'))
    os.symlink('c.txt', os.path.join(root, 'link'))
    write(os.path.join(root, 'c.txt'), 'c2 longer')
    pin(root, 'b.txt', 'c.txt', when=BASE + 250)


def step3(root):
    # undo the step1 edit of a, change the big file
    write(os.path.join(root, 'a.txt'), 'aaaa')
    with open(os.path.join(root, 'big.bin'), 'r+b') as f:
        f.seek(1 << 20)
        f.write(os.urandom(1 << 16))
    pin(root, 'a.txt', 'big.bin', when=BASE + 350)


def step4(root):
    # a changes again, after any range ending at step3
    write(os.path.join(root, 'a.txt'), 'a after')
    write(os.path.join(root, 'dir', 'inner.txt'), 'inner changed')
    pin(root, 'a.txt', os.path.join('dir', 'inner.txt'), when=BASE + 450)


STEPS = [step0, step1, step2, step3, step4]


@pytest.fixture
def chain(repo, tmp_path):
    # (repo, epochs, states before any rewrite) for a password protected chain
    epochs = build(repo, 'pw', STEPS)
    return repo, epochs, restore_all(repo, 'pw', epochs, tmp_path, 'before')


def rewrite(repo, password, plan, **options):
    # moments are rebuilt in the staging folder; the source is never written
    source = snapshot(repo.path)
    journal = merge.prepare_rewrite(plan, password, **options)
    merge.commit_rewrite(backup.get_backupPath(*repo.args), password)
    assert snapshot(repo.path) == source
    return journal


def check_kept(repo, password, before, tmp_path, kept):
    revisions = backup.get_revisions(*repo.args)
    assert [rev['epoch'] for rev in revisions] == kept
    after = restore_all(repo, password, kept, tmp_path, 'after')
    for epoch in kept:
        assert after[epoch] == before[epoch], 'moment %d changed' % epoch
    assert not merge.get_journal(backup.get_backupPath(*repo.args))
    assert not os.path.exists(merge.staging_dir(
        backup.get_backupPath(*repo.args)))


@pytest.mark.parametrize('run, kept_indexes', [
    ([1, 2, 3], [0, 3, 4]),       # middle
    ([2, 3, 4], [0, 1, 4]),       # ending at the newest moment
    ([0, 1, 2], [2, 3, 4]),       # starting at the full backup
    ([0, 1, 2, 3, 4], [4]),       # the whole chain
])
def test_squash(chain, tmp_path, run, kept_indexes):
    repo, epochs, before = chain
    d = backup.get_backupPath(*repo.args)
    plan = merge.plan_squash(d, [epochs[i] for i in run])
    journal = merge.prepare_rewrite(plan, 'pw')
    freed = merge.freed_bytes(plan, journal)
    old_bytes = plan.size_of(plan.old_files())
    merge.commit_rewrite(d, 'pw')
    kept = [epochs[i] for i in kept_indexes]
    check_kept(repo, 'pw', before, tmp_path, kept)
    assert freed == old_bytes - sum(entry['size'] for entry in journal['new'])


@pytest.mark.parametrize('delete', [[4], [0], [1, 3], [1, 2]])
def test_prune(chain, tmp_path, delete):
    repo, epochs, before = chain
    d = backup.get_backupPath(*repo.args)
    plan = merge.plan_prune(d, [epochs[i] for i in delete])
    rewrite(repo, 'pw', plan)
    kept = [e for i, e in enumerate(epochs) if i not in delete]
    check_kept(repo, 'pw', before, tmp_path, kept)


def test_pruning_the_newest_regenerates_nothing(chain):
    repo, epochs, before = chain
    plan = merge.plan_prune(backup.get_backupPath(*repo.args), [epochs[-1]])
    assert plan.regenerated == []
    assert [m.end for m in plan.dropped] == [epochs[-1]]


def test_squash_into_newest_keeps_signatures_equivalent(chain):
    # a status check after rewriting the newest moment finds no changes
    repo, epochs, before = chain
    d = backup.get_backupPath(*repo.args)
    rewrite(repo, 'pw', merge.plan_squash(d, epochs[2:]))
    added, modified, deleted = backup.get_status(*repo.args, 'pw')
    assert [status_count('New Files', added),
            status_count('Modified Files', modified),
            status_count('Deleted Files', deleted)] == [0, 0, 0]


@pytest.mark.parametrize('password, legacy', [(None, False), (None, True)])
def test_unencrypted_and_legacy_chains(repo, tmp_path, password, legacy):
    epochs = build(repo, password, STEPS, legacy=legacy)
    before = restore_all(repo, password, epochs, tmp_path, 'before')
    d = backup.get_backupPath(*repo.args)
    rewrite(repo, password, merge.plan_squash(d, epochs[1:4]))
    check_kept(repo, password, before, tmp_path,
               [epochs[0], epochs[3], epochs[4]])


def test_metadata_only_change_is_refused(repo, tmp_path):
    # content changes in the run but its metadata ends equal to the moment
    # before: duplicity would skip it, so the verify must stop the rewrite
    trap = os.path.join(repo.path, 'trap.txt')
    def first(root):
        write(trap, 'AAAA')
        os.utime(trap, (BASE, BASE))
    def changed(root):
        write(trap, 'BBBB')
        os.utime(trap, (BASE + 5, BASE + 5))
    def metadata_reset(root):
        os.utime(trap, (BASE, BASE))
    epochs = build(repo, 'pw', [first, changed, metadata_reset])
    before = drive_files(repo)
    d = backup.get_backupPath(*repo.args)
    with pytest.raises(merge.MergeError):
        merge.prepare_rewrite(merge.plan_squash(d, epochs[1:]), 'pw')
    assert drive_files(repo) == before
    assert not merge.get_journal(d)


def record_steps(monkeypatch, fail=None):
    # (step, start, end) of each duplicity run; fail names one to break
    steps = []
    real = merge._run_step
    def run(password, options, operands, log_file):
        step = os.path.basename(log_file).split('-')[0]
        if step == 'verify':
            step = '-'.join(os.path.basename(log_file).split('-')[:2])
        start = time.monotonic()
        try:
            if step == fail:
                raise merge.MergeError('%s failed' % step)
            return real(password, options, operands, log_file)
        finally:
            steps.append((step, start, time.monotonic()))
    monkeypatch.setattr(merge, '_run_step', run)
    return steps


def test_original_is_checked_while_saving(chain, monkeypatch):
    repo, epochs, before = chain
    d = backup.get_backupPath(*repo.args)
    steps = record_steps(monkeypatch)
    merge.prepare_rewrite(merge.plan_prune(d, [epochs[1]]), 'pw')
    times = {step: (start, end) for step, start, end in steps}
    assert times['verify-old'][0] < times['backup'][1]
    assert times['restore'][1] <= times['verify-old'][0]
    merge.undo_rewrite(d)


def test_quick_rebuild_skips_the_original(chain, monkeypatch):
    repo, epochs, before = chain
    d = backup.get_backupPath(*repo.args)
    steps = record_steps(monkeypatch)
    merge.prepare_rewrite(merge.plan_prune(d, [epochs[1]]), 'pw',
                          thorough=False)
    assert 'verify-old' not in [step for step, start, end in steps]
    merge.undo_rewrite(d)


def test_failed_original_check_stops_the_rewrite(chain, monkeypatch):
    repo, epochs, before = chain
    d = backup.get_backupPath(*repo.args)
    files = drive_files(repo)
    steps = record_steps(monkeypatch, fail='verify-old')
    with pytest.raises(merge.MergeError, match='verify-old failed'):
        merge.prepare_rewrite(merge.plan_prune(d, [epochs[1]]), 'pw')
    # the save and its check still ran to the end, and nothing changed
    assert 'verify-new' in [step for step, start, end in steps]
    assert drive_files(repo) == files
    assert not merge.get_journal(d)


def test_failed_prepare_leaves_the_drive_unchanged(chain, monkeypatch):
    repo, epochs, before = chain
    d = backup.get_backupPath(*repo.args)
    files = drive_files(repo)
    def broken_verify(*args):
        raise merge.MergeError('verify failed')
    monkeypatch.setattr(merge, '_check_chain', broken_verify)
    with pytest.raises(merge.MergeError):
        merge.prepare_rewrite(merge.plan_squash(d, epochs[1:3]), 'pw')
    assert drive_files(repo) == files
    assert not merge.get_journal(d)


@pytest.fixture
def prepared(chain):
    repo, epochs, before = chain
    d = backup.get_backupPath(*repo.args)
    merge.prepare_rewrite(merge.plan_squash(d, epochs[1:4]), 'pw')
    return repo, epochs, before, d


def test_prepared_rewrite_blocks_backups_and_can_be_dropped(prepared):
    repo, epochs, before, d = prepared
    files = drive_files(repo)
    del files[merge.JOURNAL_FILE]
    assert 'in progress' in backup.get_backup_assertion_error(*repo.args)
    with pytest.raises(merge.MergeError):
        merge.prepare_rewrite(merge.plan_prune(d, [epochs[4]]), 'pw')
    assert merge.resume_rewrite(d, 'pw') == 'dropped'
    assert drive_files(repo) == files
    assert backup.get_backup_assertion_error(*repo.args) is None


def crash_after(patch, operation, count):
    # patch is a monkeypatch.context(), so undoing it keeps the fake drive
    real = getattr(os, operation)
    calls = collections.Counter()
    def flaky(*args, **kwargs):
        calls[operation] += 1
        if calls[operation] > count:
            raise OSError('simulated power loss')
        return real(*args, **kwargs)
    patch.setattr(merge.os, operation, flaky)


@pytest.mark.parametrize('operation, count', [('replace', 1), ('rename', 2)])
def test_commit_resumes_after_a_crash(prepared, tmp_path, monkeypatch,
                                      operation, count):
    repo, epochs, before, d = prepared
    with monkeypatch.context() as patch:
        crash_after(patch, operation, count)
        with pytest.raises(OSError):
            merge.commit_rewrite(d, 'pw')
    assert 'in progress' in backup.get_backup_assertion_error(*repo.args)
    assert merge.resume_rewrite(d, 'pw') == 'finished'
    check_kept(repo, 'pw', before, tmp_path, [epochs[0]] + epochs[3:])


def test_commit_can_be_undone_after_a_crash(prepared, tmp_path, monkeypatch):
    repo, epochs, before, d = prepared
    with monkeypatch.context() as patch:
        crash_after(patch, 'rename', 2)
        with pytest.raises(OSError):
            merge.commit_rewrite(d, 'pw')
    merge.undo_rewrite(d)
    check_kept(repo, 'pw', before, tmp_path, epochs)


def test_low_space_needs_consent_to_delete_first(prepared, tmp_path,
                                                 monkeypatch):
    repo, epochs, before, d = prepared
    usage = shutil.disk_usage(d)
    with monkeypatch.context() as patch:
        patch.setattr(merge.shutil, 'disk_usage',
                      lambda path: usage._replace(free=0))
        with pytest.raises(merge.NotEnoughSpace):
            merge.commit_rewrite(d, 'pw')
        assert merge.get_journal(d)['phase'] == 'prepared'
        merge.commit_rewrite(d, 'pw', allow_delete_first=True)
    check_kept(repo, 'pw', before, tmp_path, [epochs[0]] + epochs[3:])


def test_missing_duplicity_cache_is_rebuilt(chain, tmp_path):
    repo, epochs, before = chain
    d = backup.get_backupPath(*repo.args)
    shutil.rmtree(backup.duplicity_cache_dir(d))
    rewrite(repo, 'pw', merge.plan_squash(d, epochs[1:3]))
    check_kept(repo, 'pw', before, tmp_path,
               [epochs[0]] + epochs[2:])


def test_listing_cache_of_dropped_moments_is_removed(chain):
    repo, epochs, before = chain
    d = backup.get_backupPath(*repo.args)
    for epoch in epochs:
        backup.list_files(*repo.args, str(epoch), 'pw', lambda item: None)
    rewrite(repo, 'pw', merge.plan_prune(d, [epochs[2]]))
    cached = sorted(os.listdir(backup.listing_cache_dir(d)))
    assert cached == sorted('%d.list' % e for e in epochs if e != epochs[2])


def test_two_chains(repo, tmp_path):
    # a yearly full backup starts a second chain; rewrites cross it
    epochs = build(repo, 'pw', STEPS[:3])
    full = BASE + STEP * 10
    step3(repo.path)
    assert backup.run_duplicity(
        'pw', ['full', '--current-time', str(full)],
        [repo.path, backup.get_backupUri(*repo.args)]) == 0
    step4(repo.path)
    inc = full + STEP
    assert backup.run_duplicity(
        'pw', ['--current-time', str(inc)],
        [repo.path, backup.get_backupUri(*repo.args),
         '--allow-source-mismatch']) == 0
    epochs += [full, inc]
    before = restore_all(repo, 'pw', epochs, tmp_path, 'before')
    d = backup.get_backupPath(*repo.args)
    assert [len(c) for c in merge.get_chains(d)] == [3, 2]
    rewrite(repo, 'pw', merge.plan_squash(d, epochs[1:4]))
    check_kept(repo, 'pw', before, tmp_path, [epochs[0], full, inc])


def test_estimate(chain):
    repo, epochs, before = chain
    d = backup.get_backupPath(*repo.args)
    plan = merge.plan_squash(d, epochs[1:4])
    estimate = merge.estimate_rewrite(plan, repo.path)
    assert estimate['dropped'] == epochs[1:3]
    assert estimate['regenerated'] == [epochs[3]]
    assert estimate['max_freed'] == plan.size_of(plan.old_files()) > 0
    assert estimate['staging_needed'] > 0 and estimate['hours'] > 0
    assert estimate['foreign_owned'] == 0


def test_plan_validation(chain):
    repo, epochs, before = chain
    d = backup.get_backupPath(*repo.args)
    for bad in ([epochs[1]], [epochs[1], epochs[3]]):
        with pytest.raises(merge.MergeError):
            merge.plan_squash(d, bad)
    with pytest.raises(merge.MergeError):
        merge.plan_prune(d, epochs)
    with pytest.raises(merge.MergeError):
        merge.plan_prune(d, [])


@pytest.mark.parametrize('damage', ['part', 'orphan', 'no manifest'])
def test_unusual_backups_are_refused(chain, damage):
    repo, epochs, before = chain
    d = backup.get_backupPath(*repo.args)
    names = sorted(os.listdir(d))
    if damage == 'part':
        write(os.path.join(d, 'duplicity-inc.20230101T000000Z.to.'
                              '20230102T000000Z.manifest.part'), 'x')
    elif damage == 'orphan':
        # without the second moment, the later ones belong to no chain
        stamp = backup.time.strftime('%Y%m%dT%H%M%SZ',
                                     backup.time.gmtime(epochs[1]))
        for name in names:
            if '.to.%s.' % stamp in name:
                os.remove(os.path.join(d, name))
    else:
        os.remove(os.path.join(d, [n for n in names if '.manifest' in n][-1]))
    with pytest.raises(merge.MergeError):
        merge.get_chains(d)


def test_unsupported_duplicity_is_refused(chain, monkeypatch):
    repo, epochs, before = chain
    d = backup.get_backupPath(*repo.args)
    monkeypatch.setattr(merge, '_duplicity_major', lambda: 99)
    with pytest.raises(merge.MergeError):
        merge.prepare_rewrite(merge.plan_squash(d, epochs[1:3]), 'pw')
    assert not merge.get_journal(d)


# --- yearly full backups (issue #19)

def test_full_backup_when_the_last_is_a_year_old(repo):
    write(os.path.join(repo.path, 'f.txt'), 'f')
    backup.init_backup(*repo.args, 'pw')
    old = int(backup.time.time()) - 400 * 24 * 3600
    assert backup.run_duplicity(
        'pw', ['--current-time', str(old)],
        [repo.path, backup.get_backupUri(*repo.args)]) == 0
    assert backup.full_backup_status(*repo.args) == (True, True)
    assert backup.backup(*repo.args, 'pw') == 0
    types = [rev['type'] for rev in backup.get_revisions(*repo.args)]
    assert types == ['Full', 'Full']
    assert backup.full_backup_status(*repo.args) == (False, True)


def test_due_full_backup_that_does_not_fit_is_incremental(repo, monkeypatch):
    write(os.path.join(repo.path, 'f.txt'), 'f')
    backup.init_backup(*repo.args, 'pw')
    old = int(backup.time.time()) - 400 * 24 * 3600
    assert backup.run_duplicity(
        'pw', ['--current-time', str(old)],
        [repo.path, backup.get_backupUri(*repo.args)]) == 0
    usage = shutil.disk_usage(repo.path)
    monkeypatch.setattr(backup.shutil, 'disk_usage',
                        lambda path: usage._replace(free=0))
    messages = []
    assert backup.backup(*repo.args, 'pw', report=messages.append) == 0
    types = [rev['type'] for rev in backup.get_revisions(*repo.args)]
    assert types == ['Full', 'Incremental']
    assert messages and 'may not fit' in messages[0]


# --- the administrator step, for moments with other users' files

def test_hand_back_only_touches_the_apps_own_files(prepared, monkeypatch):
    repo, epochs, before, d = prepared
    handed = []
    real_lstat = os.lstat
    with monkeypatch.context() as patch:
        # pretend root created everything
        patch.setattr(merge.os, 'lstat', lambda path: types.SimpleNamespace(
            st_uid=0, st_mode=real_lstat(path).st_mode))
        patch.setattr(merge.os, 'lchown', lambda path, uid, gid: handed.append(
            (path, uid, gid)))
        merge.hand_back(d, 1234, 5678)
    paths = [path for path, uid, gid in handed]
    assert {(uid, gid) for path, uid, gid in handed} == {(1234, 5678)}
    assert os.path.join(d, merge.JOURNAL_FILE) in paths
    assert merge.staging_dir(d) in paths
    assert backup.duplicity_cache_dir(d) in paths
    # nothing of the backup itself, or of the source
    assert not [p for p in paths if p.startswith(d + os.sep)
                and not p.endswith(merge.JOURNAL_FILE)]
    assert not [p for p in paths if p.startswith(repo.path)]


@pytest.fixture
def no_pkexec(monkeypatch):
    # the helper runs as this user instead of through pkexec
    monkeypatch.setattr(merge, 'ADMIN_COMMAND', [])


def test_prepare_as_admin_runs_the_helper(chain, tmp_path, no_pkexec):
    repo, epochs, before = chain
    d = backup.get_backupPath(*repo.args)
    progress = []
    plan = merge.plan_squash(d, epochs[1:4])
    journal = merge.prepare_as_admin(plan, 'pw', report=lambda step, **fields:
                                     progress.append((step, fields)))
    assert journal['phase'] == 'prepared'
    assert ('check_new_and_old', {'moment': 1, 'of': 1,
                          'when': time.ctime(epochs[3])}) in progress
    merge.commit_rewrite(d, 'pw')
    check_kept(repo, 'pw', before, tmp_path, [epochs[0]] + epochs[3:])


def test_prepare_as_admin_reports_errors(chain, no_pkexec):
    repo, epochs, before = chain
    d = backup.get_backupPath(*repo.args)
    files = drive_files(repo)
    with pytest.raises(merge.MergeError) as error:
        merge.prepare_as_admin(merge.plan_squash(d, epochs[1:3]), 'wrong')
    assert 'restore failed' in str(error.value)
    assert drive_files(repo) == files


def test_refused_admin_rights(chain, monkeypatch):
    repo, epochs, before = chain
    d = backup.get_backupPath(*repo.args)
    files = drive_files(repo)
    monkeypatch.setattr(merge, 'ADMIN_COMMAND', [
        sys.executable, '-c', 'import sys; sys.exit(126)'])
    with pytest.raises(merge.MergeError, match='not granted'):
        merge.prepare_as_admin(merge.plan_squash(d, epochs[1:3]), 'pw')
    assert drive_files(repo) == files


def test_source_scan_counts_allocated_space_and_skips_own_caches(
        tmp_path, monkeypatch):
    source = tmp_path / 'source'
    write(str(source / 'small.txt'), 'x' * 10)
    with open(str(source / 'sparse.img'), 'wb') as f:
        f.truncate(1 << 30)
    monkeypatch.setenv('XDG_CACHE_HOME', str(source / 'cache'))
    with open(str(source / 'big.bin'), 'wb') as f:
        f.write(os.urandom(1 << 20))
    write(str(source / 'cache' / 'duplicity' / 'x' / 'sig'), 'y' * (1 << 20))
    total, foreign = merge._source_scan(str(source))
    assert (1 << 20) <= total < 3 << 20
    assert foreign == 0
