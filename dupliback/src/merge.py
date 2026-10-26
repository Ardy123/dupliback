# Prune and squash: rewrite a backup's duplicity chains so they keep only the
# chosen moments, each with its original time and exact state. A kept moment
# that follows a dropped one is regenerated (restored, then re-diffed against
# its new predecessor by duplicity) and verified before the drive is touched.
import hashlib
import json
import os
import re
import shutil
import subprocess
import time

import backup

JOURNAL_FILE = backup.REWRITE_JOURNAL
TRASH_DIR = '.dupliback_trash'
TMP_SUFFIX = '.dupliback-tmp'
SUPPORTED_DUPLICITY_MAJOR = 3
# rough restore/verify speed from a USB drive through gpg and gunzip
READ_BYTES_PER_HOUR = 60e6 * 3600
SPACE_MARGIN = 1 << 30
_T = r'\d{8}T\d{6}Z'
NAME_RGX = re.compile(
    r'duplicity-(?:full\.(?P<full>{t})|inc\.(?P<start>{t})\.to\.(?P<end>{t})'
    r'|full-signatures\.(?P<sig_full>{t})'
    r'|new-signatures\.(?P<sig_start>{t})\.to\.(?P<sig_end>{t}))'
    r'\.(?P<part>vol\d+\.difftar|manifest|sigtar|jsonstat)'
    r'(?:\.gz|\.gpg)?(?P<partial>\.part)?$'.format(t=_T))


class MergeError(Exception):
    pass


class Moment(object):
    # one backup set: a full (start is None) or an incremental
    def __init__(self, start, end):
        self.start = start
        self.end = end
        self.files = []

    @property
    def full(self):
        return self.start is None

    def kinds(self):
        return {NAME_RGX.match(name).group('part').split('.')[-1]
                for name in self.files}


def get_chains(duplicity_dir):
    # the backup's chains, oldest first, each a list of Moments starting with
    # a full; refuses anything duplicity would not chain cleanly
    sets = {}
    for name in sorted(os.listdir(duplicity_dir)):
        if not name.startswith('duplicity-'):
            continue
        match = NAME_RGX.match(name)
        if not match or match.group('partial'):
            raise MergeError('unexpected file in the backup: %s' % name)
        times = match.groupdict()
        if times['full'] or times['sig_full']:
            key = (None, backup.utc_epoch(times['full'] or times['sig_full']))
        else:
            key = tuple(map(backup.utc_epoch,
                            (times['start'] or times['sig_start'],
                             times['end'] or times['sig_end'])))
        sets.setdefault(key, Moment(*key)).files.append(name)
    incs = {}
    for moment in sets.values():
        if not {'difftar', 'manifest', 'sigtar'} <= moment.kinds():
            raise MergeError('incomplete backup set ending %s'
                             % time.ctime(moment.end))
        if not moment.full:
            if moment.start in incs:
                raise MergeError('two backup sets start at %s'
                                 % time.ctime(moment.start))
            incs[moment.start] = moment
    chains = []
    for full in sorted((m for m in sets.values() if m.full),
                       key=lambda m: m.end):
        chain = [full]
        while chain[-1].end in incs:
            chain.append(incs.pop(chain[-1].end))
        chains.append(chain)
    if incs:
        raise MergeError('backup sets outside any chain, e.g. ending %s'
                         % time.ctime(min(m.end for m in incs.values())))
    return chains


def moments(chains):
    return [moment for chain in chains for moment in chain]


class Plan(object):
    # what rewriting chains to keep the moments ending at `keep` involves:
    # steps are (moment, action), action 'reuse', 'full', 'inc' or 'drop'
    def __init__(self, duplicity_dir, chains, keep):
        self.duplicity_dir = duplicity_dir
        self.chains = chains
        self.keep = set(keep)
        all_ends = {m.end for m in moments(chains)}
        if not self.keep or not self.keep <= all_ends:
            raise MergeError('at least one existing moment must be kept')
        if self.keep == all_ends:
            raise MergeError('nothing to delete or merge')
        self.steps = [list(self._chain_steps(chain)) for chain in chains]

    def _chain_steps(self, chain):
        previous = None
        for index, moment in enumerate(chain):
            if moment.end not in self.keep:
                yield moment, 'drop'
                continue
            if previous is None:
                action = 'reuse' if index == 0 else 'full'
            else:
                action = 'reuse' if previous == index - 1 else 'inc'
            previous = index
            yield moment, action

    def all_steps(self):
        return [step for chain in self.steps for step in chain]

    @property
    def regenerated(self):
        return [m for m, action in self.all_steps() if action in ('full',
                                                                  'inc')]

    @property
    def dropped(self):
        return [m for m, action in self.all_steps() if action == 'drop']

    def old_files(self):
        # files replaced or removed: dropped and regenerated moments'
        return [name for m, action in self.all_steps() if action != 'reuse'
                for name in m.files]

    def size_of(self, names):
        return sum(os.path.getsize(os.path.join(self.duplicity_dir, name))
                   for name in names)


def plan_rewrite(duplicity_dir, keep):
    return Plan(duplicity_dir, get_chains(duplicity_dir), keep)


def plan_prune(duplicity_dir, delete):
    # keep every moment except those ending at the epochs in delete
    chains = get_chains(duplicity_dir)
    keep = {m.end for m in moments(chains)} - set(delete)
    return Plan(duplicity_dir, chains, keep)


def plan_squash(duplicity_dir, run):
    # merge the contiguous moments ending at the epochs in run into the newest
    chains = get_chains(duplicity_dir)
    ends = [m.end for m in moments(chains)]
    picked = sorted(ends.index(end) for end in run)
    if len(picked) < 2 or picked != list(range(picked[0], picked[-1] + 1)):
        raise MergeError('squash needs two or more consecutive moments')
    keep = set(ends) - set(ends[picked[0]:picked[-1]])
    return Plan(duplicity_dir, chains, keep)


def _chain_read_bytes(plan, moment):
    # volume bytes duplicity reads to restore a moment: its chain up to it
    for chain in plan.chains:
        if moment in chain:
            upto = chain[:chain.index(moment) + 1]
            return plan.size_of([name for m in upto for name in m.files
                                 if '.difftar' in name])
    return 0


def _source_scan(path):
    # (bytes, files owned by another user or a group we are not in)
    groups = set(os.getgroups()) | {os.getgid()}
    uid = os.getuid()
    stats = (os.lstat(os.path.join(root, name))
             for root, dirs, files in os.walk(path) for name in dirs + files)
    total = foreign = 0
    for stat in stats:
        total += stat.st_size
        foreign += stat.st_uid != uid or stat.st_gid not in groups
    return total, foreign


def staging_dir(duplicity_dir):
    return os.path.join(backup.cache_home(), 'dupliback', 'rewrite',
                        os.path.basename(duplicity_dir))


def estimate_rewrite(plan, source_path, thorough=True):
    source_bytes, foreign = _source_scan(source_path)
    reads = sum(_chain_read_bytes(plan, m) for m in plan.regenerated)
    staging = staging_dir(plan.duplicity_dir)
    os.makedirs(os.path.dirname(staging), exist_ok=True)
    return {
        'dropped': [m.end for m in plan.dropped],
        'regenerated': [m.end for m in plan.regenerated],
        'max_freed': plan.size_of(plan.old_files()),
        'staging_needed': source_bytes if plan.regenerated else 0,
        'staging_free': shutil.disk_usage(os.path.dirname(staging)).free,
        'drive_free': shutil.disk_usage(plan.duplicity_dir).free,
        'hours': reads * (3 if thorough else 2) / READ_BYTES_PER_HOUR,
        'foreign_owned': foreign,
    }


# --- journal: written on the drive so every app sees a rewrite in progress

def get_journal(duplicity_dir):
    try:
        with open(os.path.join(duplicity_dir, JOURNAL_FILE)) as journal:
            return json.load(journal)
    except FileNotFoundError:
        return None


def _write_journal(duplicity_dir, journal):
    backup.write_atomic(os.path.join(duplicity_dir, JOURNAL_FILE),
                        json.dumps(journal, indent=1).encode())


def _remove_journal(duplicity_dir):
    os.remove(os.path.join(duplicity_dir, JOURNAL_FILE))


# --- running duplicity

def _run_step(password, options, operands, log_file):
    # a duplicity step that must succeed cleanly: restores and verifies only
    # warn about skipped files, so any warning fails the rewrite
    returncode = backup.run_duplicity(
        password, options + ['--log-file', log_file], operands)
    with open(log_file) as log:
        warnings = [line.strip() for line in log
                    if line.startswith(('WARNING', 'ERROR'))]
    if returncode != 0 or warnings:
        raise MergeError('duplicity %s failed (exit %d)%s; see %s' % (
            options[0], returncode,
            ': ' + warnings[0] if warnings else '', log_file))


def _duplicity_major():
    output = subprocess.run(['duplicity', '--version'], stdout=subprocess.PIPE,
                            universal_newlines=True).stdout
    match = re.search(r'(\d+)\.\d+', output)
    return int(match.group(1)) if match else 0


def _self_test(work):
    # --current-time is a hidden testing option; check it still stamps sets
    if _duplicity_major() != SUPPORTED_DUPLICITY_MAJOR:
        raise MergeError('prune and squash support duplicity %d.x only'
                         % SUPPORTED_DUPLICITY_MAJOR)
    test = os.path.join(work, 'selftest')
    os.makedirs(os.path.join(test, 'tree'))
    with open(os.path.join(test, 'tree', 'f'), 'w') as f:
        f.write('f')
    _run_step(None, ['full', '--current-time', '1000000000',
                     '--archive-dir', os.path.join(test, 'cache'),
                     '--name', 'selftest'],
              [os.path.join(test, 'tree'),
               backup.backup_uri(os.path.join(test, 'target'))],
              os.path.join(test, 'log'))
    if not os.path.exists(os.path.join(
            test, 'target', 'duplicity-full.20010909T014640Z.manifest')):
        raise MergeError('this duplicity ignores --current-time')
    backup.rmdir(test)


def _local_name(remote_name):
    # name of a set's manifest or signature in duplicity's cache
    name = re.sub(r'\.gpg$', '', remote_name)
    return name + '.gz' if name.endswith('.sigtar') else name


def _link(source, target):
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def _seed_cache(duplicity_dir, cache, moment):
    # reuse duplicity's decrypted copies rather than decrypt them again
    real = backup.duplicity_cache_dir(duplicity_dir)
    for name in moment.files:
        local = _local_name(name)
        if '.difftar' not in name and os.path.exists(
                os.path.join(real, local)):
            _link(os.path.join(real, local), os.path.join(cache, local))


def _set_times(log_file):
    with open(log_file) as log:
        return [backup.utc_epoch(match.group(2)) for match in
                map(backup.REVISION_RGX.match, log) if match]


def _check_chain(password, uri, archive, name, log_file, expected):
    # collection-status must show one complete chain of exactly the expected
    # moments, nothing orphaned or incomplete
    _run_step(password, ['collection-status', '--archive-dir', archive,
                         '--name', name], [uri], log_file)
    with open(log_file) as log:
        text = log.read()
    found = _set_times(log_file)
    if (found != expected or 'orphaned-sets-num 0' not in text
            or 'incomplete-sets-num 0' not in text):
        raise MergeError('the rewritten chain is not what was planned; '
                         'see %s' % log_file)


def _regenerate(plan, k, moment, action, previous_end, work, password,
                thorough, report):
    d = plan.duplicity_dir
    target = os.path.join(work, 'target%d' % k)
    archive = os.path.join(work, 'cache')
    tree = os.path.join(work, 'tree')
    tmp = os.path.join(work, 'tmp')
    logs = os.path.join(work, 'log')
    when = time.ctime(moment.end)
    label = '%d-%d' % (k, moment.end)
    backup.rmdir(tree)
    report('Restoring the moment of %s' % when)
    _run_step(password, ['restore', '--time', str(moment.end),
                         '--tempdir', tmp],
              [backup.backup_uri(d), tree],
              os.path.join(logs, 'restore-%s.log' % label))
    before = set(os.listdir(target))
    report('Rebuilding the moment of %s' % when)
    options = [{'full': 'full', 'inc': 'incremental'}[action],
               '--current-time', str(moment.end),
               '--archive-dir', archive, '--name', 'chain%d' % k,
               '--tempdir', tmp]
    if action == 'inc':
        options.append('--allow-source-mismatch')
    _run_step(password, options, [tree, backup.backup_uri(target)],
              os.path.join(logs, 'backup-%s.log' % label))
    stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(moment.end))
    if action == 'full':
        prefixes = ('duplicity-full.%s.' % stamp,
                    'duplicity-full-signatures.%s.' % stamp)
    else:
        start = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(previous_end))
        prefixes = ('duplicity-inc.%s.to.%s.' % (start, stamp),
                    'duplicity-new-signatures.%s.to.%s.' % (start, stamp))
    added = set(os.listdir(target)) - before
    if not added or not all(name.startswith(prefixes) for name in added):
        raise MergeError('duplicity wrote unexpected files: %s'
                         % ', '.join(sorted(added)))
    report('Checking the rebuilt moment of %s' % when)
    _run_step(password, ['verify', '--compare-data', '--time',
                         str(moment.end), '--archive-dir', archive,
                         '--name', 'chain%d' % k, '--tempdir', tmp],
              [backup.backup_uri(target), tree],
              os.path.join(logs, 'verify-new-%s.log' % label))
    if thorough:
        report('Checking the original moment of %s' % when)
        _run_step(password, ['verify', '--compare-data', '--time',
                             str(moment.end), '--tempdir', tmp],
                  [backup.backup_uri(d), tree],
                  os.path.join(logs, 'verify-old-%s.log' % label))
    backup.rmdir(tree)
    return sorted(added)


def _sha1(path):
    digest = hashlib.sha1()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_rewrite(plan, password, report=lambda text: None, thorough=True):
    # builds and verifies the rewritten chains in a staging dir; the drive is
    # not changed. Returns the journal that commit_rewrite applies.
    d = plan.duplicity_dir
    if get_journal(d):
        raise MergeError('a prune or squash is already in progress')
    work = staging_dir(d)
    backup.rmdir(work)
    for sub in ('cache', 'tmp', 'log'):
        os.makedirs(os.path.join(work, sub))
    journal = {'version': 1, 'phase': 'prepare', 'staging': work,
               'keep': sorted(plan.keep), 'old': plan.old_files(),
               'new': [], 'delete_first': False}
    _write_journal(d, journal)
    try:
        report('Checking duplicity')
        _self_test(work)
        new = []
        for k, steps in enumerate(plan.steps):
            kept = [m.end for m, action in steps if action != 'drop']
            if not kept:
                continue
            target = os.path.join(work, 'target%d' % k)
            archive = os.path.join(work, 'cache', 'chain%d' % k)
            os.makedirs(target)
            os.makedirs(archive)
            previous_end = None
            for moment, action in steps:
                if action == 'reuse':
                    for name in moment.files:
                        os.symlink(os.path.join(d, name),
                                   os.path.join(target, name))
                    _seed_cache(d, archive, moment)
                elif action != 'drop':
                    new += [(k, name) for name in _regenerate(
                        plan, k, moment, action, previous_end, work,
                        password, thorough, report)]
                if action != 'drop':
                    previous_end = moment.end
            report('Checking the rewritten history')
            _check_chain(password, backup.backup_uri(target),
                         os.path.join(work, 'cache'), 'chain%d' % k,
                         os.path.join(work, 'log', 'status-%d.log' % k),
                         kept)
        journal['new'] = [
            {'name': name, 'chain': k,
             'size': os.path.getsize(os.path.join(work, 'target%d' % k, name)),
             'sha1': _sha1(os.path.join(work, 'target%d' % k, name))}
            for k, name in new]
        journal['phase'] = 'prepared'
        _write_journal(d, journal)
        return journal
    except BaseException:
        _roll_back_prepare(d, work)
        raise


def freed_bytes(plan, journal):
    return plan.size_of(plan.old_files()) - sum(entry['size']
                                                for entry in journal['new'])


def _roll_back_prepare(duplicity_dir, work):
    backup.rmdir(work)
    if get_journal(duplicity_dir):
        _remove_journal(duplicity_dir)


def _copy_in(work, d, entry):
    # copies a new file onto the drive, durably, if not already there
    target = os.path.join(d, entry['name'])
    if os.path.exists(target) and _sha1(target) == entry['sha1']:
        return
    source = os.path.join(work, 'target%d' % entry['chain'], entry['name'])
    if not os.path.exists(source):
        raise MergeError('the staged copy of %s is gone' % entry['name'])
    tmp = target + TMP_SUFFIX
    with open(source, 'rb') as src, open(tmp, 'wb') as dst:
        shutil.copyfileobj(src, dst, 1 << 20)
        dst.flush()
        os.fsync(dst.fileno())
    os.replace(tmp, target)
    if _sha1(target) != entry['sha1']:
        raise MergeError('%s did not copy correctly' % entry['name'])


def _fsync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def commit_rewrite(duplicity_dir, password, allow_delete_first=False):
    # applies a prepared rewrite to the drive; safe to run again after a crash
    d = duplicity_dir
    journal = get_journal(d)
    if not journal or journal['phase'] not in ('prepared', 'commit'):
        raise MergeError('no prepared prune or squash to apply')
    work = journal['staging']
    trash = os.path.join(d, TRASH_DIR)
    new_bytes = sum(entry['size'] for entry in journal['new'])
    if journal['phase'] == 'prepared':
        if shutil.disk_usage(d).free < new_bytes + SPACE_MARGIN:
            if not allow_delete_first:
                raise NotEnoughSpace(new_bytes)
            journal['delete_first'] = True
        journal['phase'] = 'commit'
        _write_journal(d, journal)
    old = [name for name in journal['old']
           if os.path.exists(os.path.join(d, name))]
    if journal['delete_first']:
        for name in old:
            os.remove(os.path.join(d, name))
        old = []
    # manifests last, so a set is never complete before all its files are in
    for entry in sorted(journal['new'],
                        key=lambda entry: '.manifest' in entry['name']):
        _copy_in(work, d, entry)
    _fsync_dir(d)
    os.makedirs(trash, exist_ok=True)
    for name in old:
        os.rename(os.path.join(d, name), os.path.join(trash, name))
    _fsync_dir(d)
    expected = sorted(journal['keep'])
    found = _set_times_of(d, password, work)
    if found != expected:
        undo_rewrite(d)
        raise MergeError('the rewritten backup did not check out, so it was '
                         'put back as it was')
    _fix_duplicity_cache(d, journal)
    for end in set(_old_ends(journal)) - set(expected):
        listing = os.path.join(backup.listing_cache_dir(d), '%d.list' % end)
        if os.path.exists(listing):
            os.remove(listing)
    backup.rmdir(trash)
    backup.rmdir(work)
    _remove_journal(d)


class NotEnoughSpace(MergeError):
    def __init__(self, needed):
        MergeError.__init__(self, 'the drive needs %d more bytes free for the '
                                  'rewritten moments' % needed)
        self.needed = needed


def _old_ends(journal):
    return [backup.utc_epoch(times[-1]) for times in
            (re.findall(_T, name) for name in journal['old']) if times]


def _set_times_of(duplicity_dir, password, work):
    log_file = os.path.join(work, 'log', 'commit-status.log')
    if os.path.exists(log_file):
        os.remove(log_file)
    backup.run_duplicity(password, ['collection-status', '--log-file',
                                    log_file],
                         [backup.backup_uri(duplicity_dir)])
    return sorted(_set_times(log_file)) if os.path.exists(log_file) else []


def _fix_duplicity_cache(duplicity_dir, journal):
    # drop cached copies of removed sets, add those of the new ones
    real = backup.duplicity_cache_dir(duplicity_dir)
    if not os.path.isdir(real):
        return
    for name in journal['old']:
        local = os.path.join(real, _local_name(name))
        if os.path.exists(local):
            os.remove(local)
    for entry in journal['new']:
        local = _local_name(entry['name'])
        staged = os.path.join(journal['staging'], 'cache',
                              'chain%d' % entry['chain'], local)
        if '.difftar' not in local and os.path.exists(staged):
            _link(staged, os.path.join(real, local))


def undo_rewrite(duplicity_dir):
    # puts the drive back as it was before commit_rewrite (or drops a
    # prepared rewrite); impossible once old moments were deleted first
    d = duplicity_dir
    journal = get_journal(d)
    if not journal:
        return
    if journal['phase'] in ('prepare', 'prepared'):
        _roll_back_prepare(d, journal['staging'])
        return
    trash = os.path.join(d, TRASH_DIR)
    missing = [name for name in journal['old']
               if not os.path.exists(os.path.join(d, name))
               and not os.path.exists(os.path.join(trash, name))]
    if missing:
        raise MergeError('the old moments were already deleted; finish the '
                         'prune or squash instead')
    for entry in journal['new']:
        for path in (os.path.join(d, entry['name']),
                     os.path.join(d, entry['name'] + TMP_SUFFIX)):
            if os.path.exists(path):
                os.remove(path)
    for name in journal['old']:
        if os.path.exists(os.path.join(trash, name)):
            os.rename(os.path.join(trash, name), os.path.join(d, name))
    _fsync_dir(d)
    backup.rmdir(trash)
    backup.rmdir(journal['staging'])
    _remove_journal(d)


def resume_rewrite(duplicity_dir, password):
    # after a crash: a rewrite that never reached the drive is dropped, one
    # that did is finished
    journal = get_journal(duplicity_dir)
    if not journal:
        return None
    if journal['phase'] in ('prepare', 'prepared'):
        undo_rewrite(duplicity_dir)
        return 'dropped'
    commit_rewrite(duplicity_dir, password, allow_delete_first=True)
    return 'finished'
