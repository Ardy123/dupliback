import os
import pickle
import tempfile
import traceback
import hashlib
import hmac
import logging
import shutil
import socket
import re
import threading
import settings
import util
from gi.repository import Gtk, GObject, GdkPixbuf, GLib, Gdk
import subprocess
import error_dialog

PROPERTIES_FILE = 'dupliback_properties.pickle'
PREFERENCES_FILE = 'dupliback_preferences.pickle'
PASSWORD_HASH_ITERATIONS = 100000
# the command line interface turns this off since there is no gui to show errors in
SHOW_ERROR_DIALOGS = True


def get_known_backups():
    backups = []
    for uuid in get_mounted_devices():
        try:
            path = get_mount_point_for_uuid(uuid)
            if path:
                fbdbs = [ x for x in os.listdir(path) if x.startswith('.duplibackdb') ]
                for fbdb in fbdbs:
                    try:
                        f = open( os.path.join(path, fbdb, PROPERTIES_FILE), 'rb' )
                        o = pickle.load(f, encoding='utf-8')
                        f.close()
                        if 'password' not in o:
                            o['password'] = ''
                        backups.append(o)
                        logging.info('discovered backup: %s %s', uuid, path)
                    except Exception as e:
                        logging.debug(e)
                        logging.warning('failed to read: %s', os.path.join(path, fbdb, PROPERTIES_FILE))
        except Exception as outer_e:
            logging.debug(outer_e)
    return backups

def is_dev_present(uuid):
    return os.path.exists(os.path.join('/dev/disk/by-uuid/', uuid))

def get_device_type(uuid):
    if os.path.exists(os.path.join('/dev/disk/by-uuid/', uuid)):
        return 'local'
    return None

def get_hostname():
    return socket.gethostname()
  
def get_mounted_devices():
    return [os.path.basename(x) for x in os.listdir('/dev/disk/by-uuid/')]
  
def get_writable_devices():
    writable_uuids = []
    for uuid in get_mounted_devices():
        path = get_mount_point_for_uuid(uuid)
        if path:
            try:
                fn = os.path.join(path,'.dupliback_write_test.txt')
                f = open(fn, 'w')
                f.write('delete me!')
                f.close()
                os.remove(fn)
                writable_uuids.append(uuid)
            except:
                logging.info('could not write to: ' + str(path))
    return writable_uuids
  
def test_backup_assertions(uuid, host, path, test_exists=True):
    if not is_dev_present(uuid): 
        logging.error('not is_dev_present("%s")' % uuid)
        launch_error('not is_dev_present("%s")' % uuid)
        return False
    if not get_hostname() == host:
        logging.error('get_hostname()!="%s"' % host)
        launch_error('get_hostname()!="%s"' % host)
        return False
    if not os.path.exists(path):
        logging.error('not os.path.exists("%s")' % path)
        launch_error('not os.path.exists("%s")' % path)
        return False
    if test_exists and not os.path.exists(get_backupPath(uuid, host, path)):
        logging.error('not os.path.exists("%s")' % get_backupPath(uuid, host, path))
        launch_error('not os.path.exists("%s")' % get_backupPath(uuid, host, path))
        return False
    return True

def exec_subprocess_cmd(cmd, env=None):
    # cmd is an argument list and never goes through a shell, so paths and
    # passwords do not need escaping
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=1, universal_newlines=True, env=env) as proc:
        for line in proc.stdout:
            yield line

def run_subprocess_cmd(cmd, env=None):
    # runs cmd to completion, logging its output, and returns its exit code
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, universal_newlines=True, env=env) as proc:
        for line in proc.stdout:
            logging.debug(line)
    return proc.returncode

def get_dev_paths_for_uuid(uuid):
    ret_paths= []
    dev_path = os.path.join('/dev/disk/by-uuid/', uuid)
    udevadm_cmd = ['udevadm', 'info', '-q', 'all', '-n', dev_path]
    udevadm_rgx = re.compile(r'(N:|E: DEVLINKS=|E: DEVNAME=)\s*(.*)')
    for line in exec_subprocess_cmd(udevadm_cmd):
        regex_groups = udevadm_rgx.match(line)
        if regex_groups:
            if 'N:' == regex_groups.group(1):
                ret_paths.append(os.path.join('/dev', regex_groups.group(2).strip()))
            elif 'E: DEVNAME=' == regex_groups.group(1):
                ret_paths.append(regex_groups.group(2).strip())
            elif 'E: DEVLINKS=' == regex_groups.group(1):
                ret_paths.extend(regex_groups.group(2).strip().split())
    return list(set(ret_paths))

def get_mount_point_for_uuid(uuid):
    dev_paths = get_dev_paths_for_uuid(uuid)
    mount_cmd = ['mount']
    mount_rgx = re.compile(r'\s*(\S*)\s*\S*\s*(\S*).*')
    for line in exec_subprocess_cmd(mount_cmd):
        regex_groups = mount_rgx.match(line)
        if regex_groups and regex_groups.group(1) in dev_paths:
            return regex_groups.group(2)

def get_drive_name(uuid):
    paths = get_dev_paths_for_uuid(uuid)
    drive_name = 'UUID: '+ uuid
    for path in paths:
        if 'disk/by-id' in path:
            drive_name = path[path.index('disk/by-id')+11:]
    return drive_name

def get_free_space(uuid):
    df_cmd = ['df', get_mount_point_for_uuid(uuid)]
    df_rgx = re.compile(r'(?!(Filesystem|df:))(\s*\S*\s*(\S*)\s*\S*\s*(\S*).*)')
    for line in exec_subprocess_cmd(df_cmd):
        regex_groups = df_rgx.match(line)
        if regex_groups and 0 == int(regex_groups.group(3)):  # unknown ammount of space
            return -1
        elif regex_groups:
            return int(regex_groups.group(4)) * 1024
    return -1

def get_git_db_name(uuid, host, path):
    s = ':'.join( (uuid, host, path) )
    logging.debug(s)
    return '.duplibackdb_%s' % hashlib.sha1(s.encode('utf-8')).hexdigest()
  
def get_backupPath(uuid, host, path):
    mount_point = get_mount_point_for_uuid(uuid)
    duplicity_db = get_git_db_name(uuid, host, path)    
    return os.path.join( mount_point, duplicity_db )
    
def get_backupUri(uuid, host, path):     
    return 'file://{}'.format(get_backupPath(uuid, host, path))

def gen_passwordCmd(password):
    # only password protected backups are encrypted
    return [] if password else ['--no-encryption']

def gen_duplicityEnv(password):
    env = dict(os.environ)
    # versions 0.3.0 - 0.4.0 inverted the encryption flag, which encrypted backups
    # without a password using the literal passphrase 'None'. duplicity decrypts
    # each volume as needed, so supplying it keeps those volumes readable.
    env['PASSPHRASE'] = password if password else 'None'
    return env

def gen_passwordEncrypt(password):
    if not password:
        return ''
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, PASSWORD_HASH_ITERATIONS)
    return 'pbkdf2_sha256$%d$%s$%s' % (PASSWORD_HASH_ITERATIONS, salt.hex(), digest.hex())

def check_password(password, password_hash):
    if not password or not password_hash:
        return False
    if password_hash.startswith('pbkdf2_sha256$'):
        _, iterations, salt, digest = password_hash.split('$')
        candidate = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), int(iterations)).hex()
        return hmac.compare_digest(candidate, digest)
    # backups created before this change stored an unsalted md5 hash
    return hmac.compare_digest(hashlib.md5(password.encode('utf-8')).hexdigest(), password_hash)

def get_file_size(filepath):
    try:
        return os.lstat(filepath).st_size
    except OSError as e:
        logging.debug(e)
        return -1

def get_large_files(path, max_bytes):
    # walks the tree lazily so a large source is never listed into memory at once
    filepaths = (os.path.join(dirpath, filename) for dirpath, dirnames, filenames in os.walk(path) for filename in filenames)
    return (filepath for filepath in filepaths if get_file_size(filepath) > max_bytes)

def gen_exclusionCmd( preferences, path ):
    patterns = [pattern for preference, value in preferences.items() if value and preference in settings.FILEEXT_EXCLUDE_MAP
                for pattern in settings.FILEEXT_EXCLUDE_MAP[preference]]
    # custom filters are separated by ':', a literal ':' is escaped as '\:'
    patterns += [file_filter.replace('\\:', ':') for file_filter in re.split(r'(?<!\\):', preferences['exclude_filters']) if file_filter]
    exclusion_list = [arg for pattern in patterns for arg in ('--exclude', pattern)]
    # duplicity has no file size filter, so exclude each large file by name
    if preferences['exclude_filesize']:
        max_bytes = preferences['exclude_filesize'] * 1024*1024*1024
        exclusion_list += [arg for filepath in get_large_files(path, max_bytes) for arg in ('--exclude-regexp', '^%s$' % re.escape(filepath))]
    return exclusion_list


def rmdir(tmp):
    shutil.rmtree(tmp, ignore_errors=True)


def init_backup(uuid, host, path, password):
    assert test_backup_assertions(uuid, host, path, test_exists=False)
    duplicity_dir = get_backupPath(uuid, host, path)
    if not os.path.isdir(duplicity_dir):
        os.mkdir(duplicity_dir)
    else:
        launch_error("Backup Already Exists!")
        return False
    # write config info
    o = {'uuid':uuid,
         'host':host,
         'path':path,
         'version':settings.PROGRAM_VERSION,
         'password': gen_passwordEncrypt(password)}
    save_properties(uuid, host, path, o)
    # save default preferences
    preferences = get_preferences(uuid, host, path)
    if not password:
        preferences['password_protect'] = False
    save_preferences(uuid, host, path, preferences)
    return True
  

def backup(uuid, host, path, password):
    assert test_backup_assertions(uuid, host, path)
    duplicity_dir = get_backupPath(uuid, host, path)
    duplicity_uri = get_backupUri(uuid, host, path)
    # check that dir exists & create it if it does not
    if not os.path.exists(duplicity_dir):
        init_backup(uuid, host, path, password)
    # start backup  
    password_cmd = gen_passwordCmd(password)
    preferences_cmd = gen_exclusionCmd(get_preferences(uuid, host, path), path)
    duplicity_cmd = ['duplicity'] + preferences_cmd + password_cmd + [path, duplicity_uri, '--allow-source-mismatch']
    return run_subprocess_cmd(duplicity_cmd, gen_duplicityEnv(password))
             

def get_properties(uuid, host, path):
    try:
        f = open( os.path.join(get_backupPath(uuid, host, path), PROPERTIES_FILE), 'rb' )
        o = pickle.load(f, encoding='utf-8')
        f.close()
    except Exception as e:
        logging.error(e)
        return {}
    return o


def save_properties(uuid, host, path, properties):
    # backups are only discovered through this file, so write it to a temporary
    # file first rather than risk truncating it if the drive is pulled mid write
    duplicity_dir = get_backupPath(uuid, host, path)
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


def upgrade_password_hash(uuid, host, path, password):
    # replace a legacy unsalted md5 hash once the user has proven they know the password
    properties = get_properties(uuid, host, path)
    password_hash = properties.get('password', '')
    if not password_hash or password_hash.startswith('pbkdf2_sha256$'):
        return False
    if not check_password(password, password_hash):
        return False
    properties['password'] = gen_passwordEncrypt(password)
    if not save_properties(uuid, host, path, properties):
        return False
    logging.info('upgraded password hash for %s', path)
    return True


def get_preferences(uuid, host, path):
    preferences = dict(settings.DEFAULT_PREFERENCES)
    duplicity_dir = get_backupPath(uuid, host, path)
    try:
        f = open( os.path.join(duplicity_dir, PREFERENCES_FILE), 'rb' )
        o = pickle.load(f, encoding='utf-8')
        f.close()
    except Exception as e:
        logging.error(e)
        return preferences
    # deal with a change in version numbers
    if o:
        # version 0.1.0 did not store a version number
        if 'app_version' not in o:
            o['app_version'] = settings.PROGRAM_VERSION
        # version 0.1.0 did not support password encrypted backups
        if 'password_protect' not in o:
            o['password_protect'] = False
        # version 0.2.0 did not support file size exclusions
        if 'exclude_filesize' not in o or o['exclude_filesize'] == None:
            o['exclude_filesize'] = 0
        # version 0.3.0 did not store additional exclusion filters
        if 'exclude_filters' not in o:
            o['exclude_filters'] = ''
        preferences.update(o)    
    #nothing to do right now
    return preferences


def save_preferences(uuid, host, path, preferences):  
    # delta the difference with the old preferences
    pref = get_preferences( uuid, host, path )
    pref.update( preferences )
    duplicity_dir = get_backupPath(uuid, host, path)
    try:
        f = open( os.path.join(duplicity_dir, PREFERENCES_FILE), 'wb' )
        pickle.dump(pref, f)
        f.close()
    except:
        logging.error(traceback.print_exc())
    return


def get_revisions(uuid, host, path):
    duplicity_uri = get_backupUri(uuid, host, path)
    duplicity_cmd = ['duplicity', 'collection-status', duplicity_uri]
    duplicity_rgx = re.compile(r'\s*(Full|Incremental)\s*(\S*)\s*(\S*)\s*(\S*)\s*(\S*)\s*(\S*)\s*(\S*)')
    month_tbl_map = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
                     "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}
    revision_history = []
    for line in exec_subprocess_cmd(duplicity_cmd):
        regex_groups = duplicity_rgx.match(line)
        logging.debug(line)
        if regex_groups:
            try:
                entry = {}
                entry['type'] = regex_groups.group(1)
                entry['day'] = regex_groups.group(2)
                entry['month'] = month_tbl_map[regex_groups.group(3)]
                entry['dayOfMo'] = regex_groups.group(4)
                entry['time'] = regex_groups.group(5)
                entry['year'] = regex_groups.group(6)
                entry['nVolumes'] = regex_groups.group(7)
                revision_history.append(entry)
            except Exception as e:
                logging.debug(e)
    return revision_history


def get_files_for_revision(uuid, host, path, rev, password, callback):
    duplicity_uri = get_backupUri(uuid, host, path)
    password_cmd = gen_passwordCmd(password)
    duplicity_cmd = ['duplicity', 'list-current-files', '--time', rev] + password_cmd + [duplicity_uri]
    # each line is a date such as 'Sun Oct  5 23:32:44 2026' followed by a path, which may contain spaces
    duplicity_rgx = re.compile(r'(\w{3}\s+\w{3}\s+\d+\s+[\d:]+\s+\d{4}) (.*)')
    for line in exec_subprocess_cmd(duplicity_cmd, gen_duplicityEnv(password)):
        regex_groups = duplicity_rgx.match(line.rstrip('\n'))
        if regex_groups:
            try:
                date = regex_groups.group(1)
                path = regex_groups.group(2)
                callback([path, date])
            except Exception as e:
                logging.debug(e)
    return


def export_revision(uuid, host, path, rev, target_path, password):
    # restores rev into a temporary directory and, if target_path is given, archives it there
    prety_rev= rev.replace(":",".")
    tmp_dir = os.path.join(tempfile.mkdtemp(suffix='_dupliback'), 'archive-%s' % (prety_rev))
    duplicity_uri = get_backupUri(uuid, host, path)
    password_cmd = gen_passwordCmd(password)
    duplicity_cmd = ['duplicity', 'restore', '--time', rev] + password_cmd + [duplicity_uri, tmp_dir]
    if run_subprocess_cmd(duplicity_cmd, gen_duplicityEnv(password)) != 0:
        logging.error('failed to restore revision %s', rev)
        return None, tmp_dir
    fn = None
    if target_path:
        fn = os.path.join(target_path, 'dupliback-archive_r%s.tar.gz' % (prety_rev))
        run_subprocess_cmd(['tar', '-czf', fn, '-C', os.path.dirname(tmp_dir), os.path.basename(tmp_dir)])
    return fn, tmp_dir

def restore_to_revision( uuid, host, path, rev, password, restorePath=None):
    duplicity_uri = get_backupUri(uuid, host, path)
    password_cmd = gen_passwordCmd(password)
    # duplicity 3 will not restore over an existing path even with --force, so restore
    # into a scratch directory on the same filesystem and copy the result into place
    tmp_dir = tempfile.mkdtemp(prefix='.dupliback_restore_', dir=path)
    restored = os.path.join(tmp_dir, 'restored')
    duplicity_cmd = ['duplicity', 'restore', '--force', '--time', rev] + password_cmd
    if restorePath == None:
        dst_dir = path
    else:
        dst_dir = path + restorePath
        # '-r' is --file-to-restore before duplicity 2.0 and --path-to-restore after
        duplicity_cmd += ['-r', restorePath[1:]]
    duplicity_cmd += [duplicity_uri, restored]
    returncode = run_subprocess_cmd(duplicity_cmd, gen_duplicityEnv(password))
    try:
        if returncode == 0:
            if os.path.isdir(restored) and not os.path.islink(restored):
                shutil.copytree(restored, dst_dir, symlinks=True, dirs_exist_ok=True)
            else:
                os.makedirs(os.path.dirname(dst_dir), exist_ok=True)
                os.replace(restored, dst_dir)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return returncode


def get_status(uuid, host, path, password):
    assert test_backup_assertions(uuid, host, path)
    backup_status = {'new': ['New Files: 0'], 'modified': ['Modified Files: 0'], 'deleted': ['Deleted Files: 0']}
    duplicity_uri = get_backupUri(uuid, host, path)
    password_cmd = gen_passwordCmd(password)
    # use the same exclusions as a real backup so the counts match what would be backed up
    preferences_cmd = gen_exclusionCmd(get_preferences(uuid, host, path), path)
    duplicity_cmd = ['duplicity', '--dry-run'] + preferences_cmd + password_cmd + [path, duplicity_uri, '--allow-source-mismatch']
    duplicity_rgx = re.compile(r'(DeletedFiles|ChangedFiles|NewFiles|NewFileSize|ChangedFileSize|DeletedFileSize)\s*(.*)')
    for line in exec_subprocess_cmd(duplicity_cmd, gen_duplicityEnv(password)):
        regex_groups = duplicity_rgx.match(line)
        if regex_groups:
            status_type = regex_groups.group(1)
            status_data = regex_groups.group(2).split()[0]
            if 'DeletedFiles' == status_type:
                backup_status['deleted'] = ['Deleted Files: {}'.format(status_data)]
            elif 'ChangedFiles' == status_type:
                backup_status['modified'] = ['Modified Files: {}'.format(status_data)]
            elif 'NewFiles' == status_type:
                backup_status['new'] = ['New Files: {}'.format(status_data)]
            elif 'DeletedFileSize' == status_type:
                backup_status['deleted'].append('- Size of Deleted Files: {} Bytes'.format(status_data))
            elif 'ChangedFileSize' == status_type:
                backup_status['modified'].append('- Size of Modified Files: {} Bytes'.format(status_data))
            elif 'NewFileSize' == status_type:
                backup_status['new'].append('- Size of New Files: {} Bytes'.format(status_data))
        logging.debug(line)
    return ' '.join(backup_status['new']), ' '.join(backup_status['modified']), ' '.join(backup_status['deleted'])


def delete_backup(uuid, host, path):
    shutil.rmtree(get_backupPath(uuid, host, path), ignore_errors=True)

def show_error_dialog(error_msg):
    err_dialog= error_dialog.ErrorDialog(error_msg, None)
    if err_dialog.run() == Gtk.ResponseType.OK:
        logging.debug("error dialog ok was pressed")
    err_dialog.destroy()
    return False

def launch_error(error_msg):
    if not SHOW_ERROR_DIALOGS:
        return
    # gtk may only be used from the main thread, backups run on worker threads
    if threading.current_thread() is threading.main_thread():
        show_error_dialog(error_msg)
    else:
        GLib.idle_add(show_error_dialog, error_msg)
