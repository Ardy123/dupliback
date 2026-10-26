import calendar
import os
import pickle
import tempfile
import time
import traceback
import hashlib
import hmac
import logging
import shutil
import socket
import re
import threading
import settings
import sigtar
# unused, but pins Gtk to 3.0 before the import below
import util
from gi.repository import Gtk, GLib
import subprocess
import error_dialog

PROPERTIES_FILE = 'dupliback_properties.pickle'
PREFERENCES_FILE = 'dupliback_preferences.pickle'
PASSWORD_HASH_ITERATIONS = 100000
# the cli turns this off: it has no gui to show errors in
SHOW_ERROR_DIALOGS = True
DEV_BY_UUID = '/dev/disk/by-uuid/'

UDEVADM_RGX = re.compile(r'(N:|E: DEVLINKS=|E: DEVNAME=)\s*(.*)')
MOUNT_RGX = re.compile(r'\s*(\S*)\s*\S*\s*(\S*).*')
DF_RGX = re.compile(r'(?!(Filesystem|df:))(\s*\S*\s*(\S*)\s*\S*\s*(\S*).*)')
# a set in collection-status's machine log, e.g. ' inc 20260321T075513Z 3 enc'
REVISION_RGX = re.compile(r' (full|inc) (\d{8}T\d{6}Z) (\d+) ')
SIGNATURE_RGX = re.compile(
    r'duplicity-(?:full-signatures\.(?P<full>\d{8}T\d{6}Z)|new-signatures\.'
    r'(?P<start>\d{8}T\d{6}Z)\.to\.(?P<end>\d{8}T\d{6}Z))'
    r'\.sigtar\.(?:gz|gpg)$')
# a date like 'Sun Oct  5 23:32:44 2026', then a path that may contain spaces
FILE_LIST_RGX = re.compile(r'(\w{3}\s+\w{3}\s+\d+\s+[\d:]+\s+\d{4}) (.*)')
STATUS_RGX = re.compile(r'(DeletedFiles|ChangedFiles|NewFiles|'
                        r'NewFileSize|ChangedFileSize|DeletedFileSize)\s*(.*)')
# duplicity statistic -> (status line, text, appended rather than replacing)
STATUS_LINES = {
    'NewFiles': ('new', 'New Files: {}', False),
    'ChangedFiles': ('modified', 'Modified Files: {}', False),
    'DeletedFiles': ('deleted', 'Deleted Files: {}', False),
    'NewFileSize': ('new', '- Size of New Files: {} Bytes', True),
    'ChangedFileSize': ('modified', '- Size of Modified Files: {} Bytes', True),
    'DeletedFileSize': ('deleted', '- Size of Deleted Files: {} Bytes', True),
}


def get_known_backups():
    backups = []
    for uuid in get_mounted_devices():
        try:
            path = get_mount_point_for_uuid(uuid)
            if not path:
                continue
            for fbdb in (x for x in os.listdir(path)
                         if x.startswith('.duplibackdb')):
                fn = os.path.join(path, fbdb, PROPERTIES_FILE)
                try:
                    o = _read_pickle(fn)
                    o.setdefault('password', '')
                    backups.append(o)
                    logging.info('discovered backup: %s %s', uuid, path)
                except Exception as e:
                    logging.debug(e)
                    logging.warning('failed to read: %s', fn)
        except Exception as outer_e:
            logging.debug(outer_e)
    return backups

def is_dev_present(uuid):
    return os.path.exists(os.path.join(DEV_BY_UUID, uuid))

def get_device_type(uuid):
    return 'local' if is_dev_present(uuid) else None

def get_hostname():
    return socket.gethostname()

def get_mounted_devices():
    # containers and some VMs have no /dev/disk/by-uuid
    try:
        return os.listdir(DEV_BY_UUID)
    except FileNotFoundError:
        return []

def is_writable(path):
    if not path:
        return False
    try:
        fn = os.path.join(path, '.dupliback_write_test.txt')
        with open(fn, 'w') as f:
            f.write('delete me!')
        os.remove(fn)
        return True
    except:
        logging.info('could not write to: ' + str(path))
        return False

def get_writable_devices():
    return [uuid for uuid in get_mounted_devices()
            if is_writable(get_mount_point_for_uuid(uuid))]

def get_backup_assertion_error(uuid, host, path, test_exists=True):
    # the first reason a backup cannot be run, or None
    if not is_dev_present(uuid):
        return 'not is_dev_present("%s")' % uuid
    if get_hostname() != host:
        return 'get_hostname()!="%s"' % host
    if not os.path.exists(path):
        return 'not os.path.exists("%s")' % path
    if test_exists:
        backup_path = get_backupPath(uuid, host, path)
        if not os.path.exists(backup_path):
            return 'not os.path.exists("%s")' % backup_path
    return None

def test_backup_assertions(uuid, host, path, test_exists=True):
    error = get_backup_assertion_error(uuid, host, path, test_exists)
    if error:
        logging.error(error)
        launch_error(error)
        return False
    return True

def exec_subprocess_cmd(cmd, env=None):
    # cmd is an argument list run without a shell: paths and passwords need
    # no escaping
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=1,
                          universal_newlines=True, env=env) as proc:
        yield from proc.stdout

def run_subprocess_cmd(cmd, env=None):
    # runs cmd to completion, logging its output; returns its exit code
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          bufsize=1, universal_newlines=True, env=env) as proc:
        for line in proc.stdout:
            logging.debug(line)
    return proc.returncode

def get_dev_paths_for_uuid(uuid):
    ret_paths = set()
    udevadm_cmd = ['udevadm', 'info', '-q', 'all', '-n',
                   os.path.join(DEV_BY_UUID, uuid)]
    for regex_groups in filter(None, map(UDEVADM_RGX.match,
                                         exec_subprocess_cmd(udevadm_cmd))):
        key, value = regex_groups.group(1), regex_groups.group(2).strip()
        if key == 'N:':
            ret_paths.add(os.path.join('/dev', value))
        elif key == 'E: DEVNAME=':
            ret_paths.add(value)
        elif key == 'E: DEVLINKS=':
            ret_paths.update(value.split())
    return list(ret_paths)

def get_mount_point_for_uuid(uuid):
    dev_paths = get_dev_paths_for_uuid(uuid)
    for line in exec_subprocess_cmd(['mount']):
        regex_groups = MOUNT_RGX.match(line)
        if regex_groups and regex_groups.group(1) in dev_paths:
            return regex_groups.group(2)

def get_drive_name(uuid):
    # the last disk/by-id link wins
    by_id = (path for path in reversed(get_dev_paths_for_uuid(uuid))
             if 'disk/by-id' in path)
    return next((path[path.index('disk/by-id')+11:] for path in by_id),
                'UUID: ' + uuid)

def get_free_space(uuid):
    for line in exec_subprocess_cmd(['df', get_mount_point_for_uuid(uuid)]):
        regex_groups = DF_RGX.match(line)
        if regex_groups:
            # a size of 0 means the amount of space is unknown
            return (-1 if 0 == int(regex_groups.group(3))
                    else int(regex_groups.group(4)) * 1024)
    return -1

def get_git_db_name(uuid, host, path):
    s = ':'.join( (uuid, host, path) )
    logging.debug(s)
    return '.duplibackdb_%s' % hashlib.sha1(s.encode('utf-8')).hexdigest()

def get_backupPath(uuid, host, path):
    mount_point = get_mount_point_for_uuid(uuid)
    duplicity_db = get_git_db_name(uuid, host, path)
    return os.path.join( mount_point, duplicity_db )

def backup_uri(duplicity_dir):
    return 'file://{}'.format(duplicity_dir)

def get_backupUri(uuid, host, path):
    return backup_uri(get_backupPath(uuid, host, path))

def gen_passwordCmd(password):
    # only password protected backups are encrypted
    return [] if password else ['--no-encryption']

def gen_duplicityEnv(password):
    # 0.3.0 - 0.4.0 inverted the encryption flag, encrypting password-less
    # backups with the literal passphrase 'None'. duplicity decrypts each
    # volume as needed, so supplying it keeps those volumes readable.
    return dict(os.environ, PASSPHRASE=password or 'None')

def duplicity_cmd(password, options, operands):
    # the encryption flag must match gen_duplicityEnv's PASSPHRASE, so build
    # and run a backup's duplicity commands only through here
    return ['duplicity'] + options + gen_passwordCmd(password) + operands

def run_duplicity(password, options, operands):
    return run_subprocess_cmd(duplicity_cmd(password, options, operands),
                              gen_duplicityEnv(password))

def stream_duplicity(password, options, operands):
    return exec_subprocess_cmd(duplicity_cmd(password, options, operands),
                               gen_duplicityEnv(password))

def gen_passwordEncrypt(password):
    if not password:
        return ''
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt,
                                 PASSWORD_HASH_ITERATIONS)
    return 'pbkdf2_sha256$%d$%s$%s' % (PASSWORD_HASH_ITERATIONS, salt.hex(),
                                       digest.hex())

def check_password(password, password_hash):
    if not password or not password_hash:
        return False
    if password_hash.startswith('pbkdf2_sha256$'):
        _, iterations, salt, digest = password_hash.split('$')
        candidate = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'),
                                        bytes.fromhex(salt),
                                        int(iterations)).hex()
        return hmac.compare_digest(candidate, digest)
    # older backups stored an unsalted md5 hash
    return hmac.compare_digest(
        hashlib.md5(password.encode('utf-8')).hexdigest(), password_hash)

def get_file_size(filepath):
    try:
        return os.lstat(filepath).st_size
    except OSError as e:
        logging.debug(e)
        return -1

def get_large_files(path, max_bytes):
    # lazy, so a large source is never listed into memory at once
    filepaths = (os.path.join(dirpath, filename)
                 for dirpath, dirnames, filenames in os.walk(path)
                 for filename in filenames)
    return (filepath for filepath in filepaths
            if get_file_size(filepath) > max_bytes)

def gen_exclusionCmd( preferences, path ):
    patterns = [pattern for preference, value in preferences.items()
                if value and preference in settings.FILEEXT_EXCLUDE_MAP
                for pattern in settings.FILEEXT_EXCLUDE_MAP[preference]]
    # custom filters are ':' separated; a literal ':' is escaped as '\:'
    patterns += [file_filter.replace('\\:', ':')
                 for file_filter in re.split(r'(?<!\\):',
                                             preferences['exclude_filters'])
                 if file_filter]
    exclusion_list = [arg for pattern in patterns
                      for arg in ('--exclude', pattern)]
    # duplicity has no file size filter, so exclude each large file by name
    if preferences['exclude_filesize']:
        max_bytes = preferences['exclude_filesize'] * 1024*1024*1024
        exclusion_list += [arg for filepath in get_large_files(path, max_bytes)
                           for arg in ('--exclude-regexp',
                                       '^%s$' % re.escape(filepath))]
    return exclusion_list


def rmdir(tmp):
    shutil.rmtree(tmp, ignore_errors=True)


def _read_pickle(fn):
    with open(fn, 'rb') as f:
        return pickle.load(f, encoding='utf-8')


def init_backup(uuid, host, path, password):
    assert test_backup_assertions(uuid, host, path, test_exists=False)
    duplicity_dir = get_backupPath(uuid, host, path)
    if os.path.isdir(duplicity_dir):
        launch_error("Backup Already Exists!")
        return False
    os.mkdir(duplicity_dir)
    # write config info
    _write_properties(duplicity_dir, {
        'uuid':uuid,
        'host':host,
        'path':path,
        'version':settings.PROGRAM_VERSION,
        'password': gen_passwordEncrypt(password)})
    # save default preferences
    preferences = dict(settings.DEFAULT_PREFERENCES)
    if not password:
        preferences['password_protect'] = False
    _write_preferences(duplicity_dir, preferences)
    return True


def own_cache_exclusions(path):
    # never back up duplicity's or the app's caches when they are in path
    source = os.path.realpath(path)
    caches = (os.path.relpath(os.path.realpath(cache), source)
              for cache in own_cache_dirs())
    return [arg for cache in caches if not cache.startswith('..')
            for arg in ('--exclude-regexp',
                        '^%s(/|$)' % re.escape(os.path.join(path, cache)))]


def _backup_args(duplicity_dir, path):
    # the options and operands shared by a backup and its dry run
    exclusions = (own_cache_exclusions(path)
                  + gen_exclusionCmd(_read_preferences(duplicity_dir), path))
    return exclusions, [path, backup_uri(duplicity_dir),
                        '--allow-source-mismatch']


def backup(uuid, host, path, password):
    assert test_backup_assertions(uuid, host, path)
    duplicity_dir = get_backupPath(uuid, host, path)
    # create the backup dir if missing
    if not os.path.exists(duplicity_dir):
        init_backup(uuid, host, path, password)
    exclusions, operands = _backup_args(duplicity_dir, path)
    return run_duplicity(password, exclusions, operands)


def _read_properties(duplicity_dir):
    try:
        return _read_pickle(os.path.join(duplicity_dir, PROPERTIES_FILE))
    except Exception as e:
        logging.error(e)
        return {}


def get_properties(uuid, host, path):
    return _read_properties(get_backupPath(uuid, host, path))


def _write_properties(duplicity_dir, properties):
    # backups are only discovered through this file, so write a temp file
    # first rather than risk truncating it if the drive is pulled mid write
    tmp_fn = os.path.join(duplicity_dir, PROPERTIES_FILE + '.tmp')
    try:
        with open(tmp_fn, 'wb') as f:
            pickle.dump(properties, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_fn, os.path.join(duplicity_dir, PROPERTIES_FILE))
    except Exception as e:
        logging.error(e)
        return False
    return True


def save_properties(uuid, host, path, properties):
    return _write_properties(get_backupPath(uuid, host, path), properties)


def upgrade_password_hash(uuid, host, path, password):
    # replace a legacy unsalted md5 hash once the password is proven
    duplicity_dir = get_backupPath(uuid, host, path)
    properties = _read_properties(duplicity_dir)
    password_hash = properties.get('password', '')
    if not password_hash or password_hash.startswith('pbkdf2_sha256$'):
        return False
    if not check_password(password, password_hash):
        return False
    properties['password'] = gen_passwordEncrypt(password)
    if not _write_properties(duplicity_dir, properties):
        return False
    logging.info('upgraded password hash for %s', path)
    return True


def _read_preferences(duplicity_dir):
    preferences = dict(settings.DEFAULT_PREFERENCES)
    try:
        o = _read_pickle(os.path.join(duplicity_dir, PREFERENCES_FILE))
    except Exception as e:
        logging.error(e)
        return preferences
    # fill in what older versions did not store
    if o:
        # version 0.1.0 did not store a version number
        o.setdefault('app_version', settings.PROGRAM_VERSION)
        # version 0.1.0 did not support password encrypted backups
        o.setdefault('password_protect', False)
        # version 0.2.0 did not support file size exclusions
        if o.get('exclude_filesize') is None:
            o['exclude_filesize'] = 0
        # version 0.3.0 did not store additional exclusion filters
        o.setdefault('exclude_filters', '')
        preferences.update(o)
    return preferences


def get_preferences(uuid, host, path):
    return _read_preferences(get_backupPath(uuid, host, path))


def _write_preferences(duplicity_dir, preferences):
    try:
        with open(os.path.join(duplicity_dir, PREFERENCES_FILE), 'wb') as f:
            pickle.dump(preferences, f)
    except:
        logging.error(traceback.print_exc())


def save_preferences(uuid, host, path, preferences):
    # merge into the stored preferences
    duplicity_dir = get_backupPath(uuid, host, path)
    pref = _read_preferences(duplicity_dir)
    pref.update( preferences )
    _write_preferences(duplicity_dir, pref)


def utc_epoch(timestring):
    # duplicity's '20260321T075513Z' times are UTC
    return calendar.timegm(time.strptime(timestring, '%Y%m%dT%H%M%SZ'))


def _revision(kind, timestring, volumes):
    epoch = utc_epoch(timestring)
    local = time.localtime(epoch)
    return {'type': 'Full' if kind == 'full' else 'Incremental',
            'epoch': epoch, 'day': time.asctime(local)[:3],
            'month': local.tm_mon, 'dayOfMo': str(local.tm_mday),
            'time': time.strftime('%H:%M:%S', local),
            'year': str(local.tm_year), 'nVolumes': volumes}


def get_revisions(uuid, host, path):
    # moments from collection-status's machine log, which has exact UTC times
    # (the printed table is in local time, ambiguous when clocks go back)
    with tempfile.NamedTemporaryFile('r', suffix='.log') as log_file:
        for line in exec_subprocess_cmd(['duplicity', 'collection-status',
                                         '--log-file', log_file.name,
                                         get_backupUri(uuid, host, path)]):
            logging.debug(line)
        return [_revision(*match.groups())
                for match in map(REVISION_RGX.match, log_file) if match]


def revision_id(rev):
    # what --time is given for a moment: its UTC epoch
    return str(rev['epoch'])


def revision_label(rev_id):
    # a file name friendly local time for a moment id
    if str(rev_id).isdigit():
        return time.strftime('%Y-%m-%dT%H.%M.%S',
                             time.localtime(int(rev_id)))
    return str(rev_id).replace(':', '.')


def cache_home():
    return os.environ.get('XDG_CACHE_HOME') or os.path.expanduser('~/.cache')


def duplicity_cache_dir(duplicity_dir):
    # duplicity's default archive dir for a backup is named by its url's md5
    url_hash = hashlib.md5(backup_uri(duplicity_dir).encode()).hexdigest()
    return os.path.join(cache_home(), 'duplicity', url_hash)


def listing_cache_dir(duplicity_dir):
    return os.path.join(cache_home(), 'dupliback',
                        os.path.basename(duplicity_dir))


def own_cache_dirs():
    # caches the app and duplicity keep, which are never backed up
    return [os.path.join(cache_home(), name)
            for name in ('duplicity', 'dupliback')]


def signature_chain(names, epoch):
    # the signature files to replay, oldest first, for the moment at epoch;
    # None unless names hold a complete chain ending exactly there
    fulls, incs = {}, {}
    for match in filter(None, map(SIGNATURE_RGX.match, names)):
        if match.group('full'):
            fulls[utc_epoch(match.group('full'))] = match.group(0)
        else:
            incs[utc_epoch(match.group('start'))] = (
                utc_epoch(match.group('end')), match.group(0))
    starts = [t for t in fulls if t <= epoch]
    if not starts:
        return None
    t = max(starts)
    chain = [fulls[t]]
    while t < epoch and t in incs:
        t, name = incs[t]
        chain.append(name)
    return chain if t == epoch else None


def _replay_signatures(duplicity_dir, epoch, password):
    # {name: mtime} for the moment, from duplicity's cache or, without it
    # (e.g. restoring on a new machine), the backup's own signature files
    for source in (duplicity_cache_dir(duplicity_dir), duplicity_dir):
        try:
            chain = signature_chain(os.listdir(source), epoch)
        except OSError:
            continue
        if not chain:
            continue
        try:
            # password-less backups by 0.3.0 - 0.4.0 used the passphrase 'None'
            return sigtar.replay([os.path.join(source, name)
                                  for name in chain], password or 'None')
        except sigtar.FormatError as e:
            logging.warning('could not read signatures in %s: %s', source, e)
    return None


def _read_listing(listing_file):
    # streams (name, mtime) records written by _write_listing
    with open(listing_file, 'rb') as listing:
        rest = b''
        for chunk in iter(lambda: listing.read(1 << 20), b''):
            *records, rest = (rest + chunk).split(b'\0')
            for record in records:
                mtime, _, name = record.partition(b'\t')
                yield os.fsdecode(name), int(mtime)


def _write_listing(listing_file, items):
    # passes items through while saving them; kept only if all were seen
    os.makedirs(os.path.dirname(listing_file), exist_ok=True)
    tmp_file = listing_file + '.tmp'
    try:
        with open(tmp_file, 'wb') as listing:
            for name, mtime in items:
                listing.write(b'%d\t%s\0' % (mtime, os.fsencode(name)))
                yield name, mtime
        os.replace(tmp_file, listing_file)
    finally:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)


def list_files(uuid, host, path, rev, password, callback):
    # lists a moment from its signature files, much faster than duplicity,
    # and caches the result; falls back to duplicity if they can't be read
    duplicity_dir = get_backupPath(uuid, host, path)
    epoch = int(rev)
    listing_file = os.path.join(listing_cache_dir(duplicity_dir),
                                '%d.list' % epoch)
    if os.path.exists(listing_file):
        items = _read_listing(listing_file)
    else:
        state = _replay_signatures(duplicity_dir, epoch, password)
        if state is None:
            return get_files_for_revision(uuid, host, path, rev, password,
                                          callback)
        items = _write_listing(listing_file, sigtar.listing(state))
    for name, mtime in items:
        try:
            callback([name, time.asctime(time.localtime(mtime))])
        except Exception as e:
            logging.debug(e)


def get_files_for_revision(uuid, host, path, rev, password, callback):
    lines = stream_duplicity(password, ['list-current-files', '--time', rev],
                             [get_backupUri(uuid, host, path)])
    for regex_groups in filter(None, (FILE_LIST_RGX.match(line.rstrip('\n'))
                                      for line in lines)):
        try:
            callback([regex_groups.group(2), regex_groups.group(1)])
        except Exception as e:
            logging.debug(e)


def export_revision(uuid, host, path, rev, target_path, password):
    # restores rev to a temp dir, then archives it into target_path if given
    prety_rev = revision_label(rev)
    tmp_dir = os.path.join(tempfile.mkdtemp(suffix='_dupliback'),
                           'archive-%s' % (prety_rev))
    if run_duplicity(password, ['restore', '--time', rev],
                     [get_backupUri(uuid, host, path), tmp_dir]) != 0:
        logging.error('failed to restore revision %s', rev)
        return None, tmp_dir
    fn = None
    if target_path:
        fn = os.path.join(target_path,
                          'dupliback-archive_r%s.tar.gz' % (prety_rev))
        run_subprocess_cmd(['tar', '-czf', fn, '-C', os.path.dirname(tmp_dir),
                            os.path.basename(tmp_dir)])
    return fn, tmp_dir

def restore_to_revision( uuid, host, path, rev, password, restorePath=None):
    duplicity_uri = get_backupUri(uuid, host, path)
    # duplicity 3 will not restore over an existing path even with --force,
    # so restore into a scratch dir on the same filesystem and copy it over
    tmp_dir = tempfile.mkdtemp(prefix='.dupliback_restore_', dir=path)
    restored = os.path.join(tmp_dir, 'restored')
    if restorePath is None:
        dst_dir = path
        operands = []
    else:
        dst_dir = path + restorePath
        # '-r': --file-to-restore before duplicity 2.0, --path-to-restore after
        operands = ['-r', restorePath[1:]]
    returncode = run_duplicity(password, ['restore', '--force', '--time', rev],
                               operands + [duplicity_uri, restored])
    try:
        if returncode == 0:
            if os.path.isdir(restored) and not os.path.islink(restored):
                shutil.copytree(restored, dst_dir, symlinks=True,
                                dirs_exist_ok=True)
            else:
                os.makedirs(os.path.dirname(dst_dir), exist_ok=True)
                os.replace(restored, dst_dir)
    finally:
        rmdir(tmp_dir)
    return returncode


def get_status(uuid, host, path, password):
    assert test_backup_assertions(uuid, host, path)
    backup_status = {'new': ['New Files: 0'],
                     'modified': ['Modified Files: 0'],
                     'deleted': ['Deleted Files: 0']}
    # a real backup's exclusions, so the counts match what it would back up
    exclusions, operands = _backup_args(get_backupPath(uuid, host, path), path)
    for line in stream_duplicity(password, ['--dry-run'] + exclusions,
                                 operands):
        regex_groups = STATUS_RGX.match(line)
        if regex_groups:
            key, text, added = STATUS_LINES[regex_groups.group(1)]
            text = text.format(regex_groups.group(2).split()[0])
            if added:
                backup_status[key].append(text)
            else:
                backup_status[key] = [text]
        logging.debug(line)
    return tuple(' '.join(backup_status[key])
                 for key in ('new', 'modified', 'deleted'))


def delete_backup(uuid, host, path):
    duplicity_dir = get_backupPath(uuid, host, path)
    rmdir(listing_cache_dir(duplicity_dir))
    rmdir(duplicity_dir)

def show_error_dialog(error_msg):
    err_dialog= error_dialog.ErrorDialog(error_msg, None)
    if err_dialog.run() == Gtk.ResponseType.OK:
        logging.debug("error dialog ok was pressed")
    err_dialog.destroy()
    return False

def launch_error(error_msg):
    if not SHOW_ERROR_DIALOGS:
        return
    # gtk is main thread only; backups run on worker threads
    if threading.current_thread() is threading.main_thread():
        show_error_dialog(error_msg)
    else:
        GLib.idle_add(show_error_dialog, error_msg)
