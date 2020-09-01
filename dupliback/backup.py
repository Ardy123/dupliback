import os
import pickle
import tempfile
import traceback
import hashlib
import logging
import socket
import re
import uuid as uuidlib
import settings
import util
import error_dialog
from gi.repository import Gtk, GObject, GdkPixbuf, GLib, Gdk

UUID_GVFS = uuidlib.uuid5(uuidlib.NAMESPACE_DNS, 'gvfs.dupliback.org')
PROPERTIES_FILE = 'dupliback_properties.pickle'
PREFERENCES_FILE = 'dupliback_preferences.pickle'


def get_known_backups():
    backups = []
    for uuid in get_all_devices():
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
                        logging.info('discovered backup:', uuid, path)
                    except Exception as e:
                        logging.debug(e)
                        logging.warning('failed to read:', os.path.join(path, fbdb, PROPERTIES_FILE))
        except Exception as outer_e:
            logging.debug(outer_e)
    return backups

def is_dev_present(uuid):
    if uuid in get_gvfs_devices_and_paths():
        return True
    return os.path.exists(os.path.join('/dev/disk/by-uuid/', uuid))

def get_device_type(uuid):
    if uuid in get_gvfs_devices_and_paths():
        return 'gvfs'
    elif os.path.exists(os.path.join('/dev/disk/by-uuid/', uuid)):
        return 'local'
    return None

def get_hostname():
    return socket.gethostname()

def get_gvfs_devices():
    return [x[0] for x in get_gvfs_devices_and_paths()]

def get_gvfs_devices_and_paths():
    gvfs_device_lst= []
    gvfs_root_path = os.path.join(os.path.expanduser('~'), '.gvfs')
    try:
        for gvfs_dir in os.listdir(gvfs_root_path):
            mount_point = os.path.join(gvfs_root_path, gvfs_dir)
            uuid = str(uuidlib.uuid5(UUID_GVFS, mount_point))
            gvfs_device_lst.append((uuid, mount_point))
    except OSError:
        os.mkdir(gvfs_dir)
        pass
    return gvfs_device_lst
  
def get_local_devices():
    return [os.path.basename(x) for x in os.listdir('/dev/disk/by-uuid/')]
  
def get_all_devices():
    return get_local_devices() + get_gvfs_devices()
  
def get_writable_devices():
    writable_uuids = []
    for uuid in get_all_devices():
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


def get_dev_paths_for_uuid(uuid):
    ret_paths= []
    dev_path = os.path.join('/dev/disk/by-uuid/', uuid)
    udevadm_cmd = 'udevadm info -q all -n "{}"'.format(dev_path)
    udevadm_rgx = re.compile(r'(N:|E: DEVLINKS=|E: DEVNAME=)\s*(.*)')
    for line in os.popen(udevadm_cmd):
        regex_groups = udevadm_rgx.match(line)
        if regex_groups:
            if 'N:' == regex_groups.group(1):
                ret_paths.append(os.path.join('/dev', regex_groups.group(2).strip()))
            elif 'E: DEVNAME=' == regex_groups.group(1):
                ret_paths.append(regex_groups.group(2).strip())
            elif 'E: DEVLINKS=' == regex_groups.group(2):
                ret_paths.extend(regex_groups.group(2).strip().split())
    return list(set(ret_paths))

def get_mount_point_for_uuid(uuid):
    # handle gfvs
    for x,y in get_gvfs_devices_and_paths():
        if uuid==x:
            return y
    # handle local devices
    dev_paths = get_dev_paths_for_uuid(uuid)
    mount_cmd = 'mount'
    mount_rgx = re.compile(r'\s*(\S*)\s*\S*\s*(\S*).*')
    for line in os.popen(mount_cmd):
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
    df_cmd = 'df "{}"'.format(get_mount_point_for_uuid(uuid))
    df_rgx = re.compile(r'(?!(Filesystem|df:))(\s*\S*\s*(\S*)\s*\S*\s*(\S*).*)')
    for line in os.popen(df_cmd):
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
    return '--no-encryption' if password else ''

def gen_passwordEncrypt(password):
    return hashlib.md5(password.encode('utf-8')).hexdigest() if password else ''

def gen_exclusionCmd( preferences ):
    exclusion_list = []
    for preference, value in preferences.items():
        if preference and preference in settings.FILEEXT_EXCLUDE_MAP:
            for file_extension in settings.FILEEXT_EXCLUDE_MAP[preference]:
                exclusion_list.append('--exclude \'{}\''.format(file_extension))
    return " ".join(exclusion_list)


def rmdir(tmp):
    for line in os.popen('rm -Rf "%s"' % tmp):
        logging.debug(line)


def init_backup(uuid, host, path, password):
    assert test_backup_assertions(uuid, host, path, test_exists=False)
    duplicity_dir = get_backupPath(uuid, host, path)
    if not os.path.isdir(duplicity_dir):
        os.mkdir(duplicity_dir)
    else:
        launch_error("Backup Already Exists!")
        exit(-1)
        return
    # write config info
    f = open(os.path.join(duplicity_dir, PROPERTIES_FILE), 'wb')
    o = {'uuid':uuid,
         'host':host,
         'path':path,
         'version':settings.PROGRAM_VERSION,
         'password': gen_passwordEncrypt(password)}
    pickle.dump(o,f)
    f.close()
    # save default preferences
    preferences = get_preferences(uuid, host, path)
    if not password:
        preferences['password_protect'] = False
    save_preferences(uuid, host, path, preferences)
    return
  

def backup(uuid, host, path, password):
    assert test_backup_assertions(uuid, host, path)
    duplicity_dir = get_backupPath(uuid, host, path)
    duplicity_uri = get_backupUri(uuid, host, path)
    # check that dir exists & create it if it does not
    if not os.path.exists(duplicity_dir):
        init_backup(uuid, host, path)
    # start backup  
    password_cmd = gen_passwordCmd(password)
    preferences_cmd = gen_exclusionCmd(get_preferences(uuid, host, path))
    duplicity_cmd = 'PASSPHRASE=%s duplicity %s %s %s %s --allow-source-mismatch' % (password, preferences_cmd, password_cmd, path, duplicity_uri,)       
    for line in os.popen(duplicity_cmd):
        logging.debug(line)
    return
             

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
    duplicity_cmd = 'duplicity collection-status {}'.format(duplicity_uri)
    duplicity_rgx = re.compile(r'\s*(Full|Incremental)\s*(\S*)\s*(\S*)\s*(\S*)\s*(\S*)\s*(\S*)\s*(\S*)')
    month_tbl_map = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
                     "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}
    revision_history = []
    for line in os.popen(duplicity_cmd):
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
    duplicity_cmd = 'PASSPHRASE={} duplicity list-current-files --time {} {} {}'.format(password, rev, password_cmd, duplicity_uri)
    duplicity_rgx = re.compile(r'(?!(Local|Last))(\S*\s*\S*\s*\S*\s*\S*\s*\S*)\s*(\S*)')
    for line in os.popen(duplicity_cmd):
        regex_groups = duplicity_rgx.match(line)
        if regex_groups:
            try:
                date = regex_groups.group(2)
                path = regex_groups.group(3)
                callback([path, date])
            except Exception as e:
                logging.debug(e)
    return


def export_revision(uuid, host, path, rev, target_path, password):
    prety_rev= rev.replace(":",".")
    tmp_dir = (tempfile.mkdtemp(suffix='_dupliback') + 'archive-%s' % (prety_rev)).replace(":",".")
    duplicity_uri = get_backupUri(uuid, host, path)
    password_cmd = gen_passwordCmd(password)
    duplicity_cmd = 'PASSPHRASE=%s duplicity restore --time %s %s %s %s' % ( password, rev, password_cmd, duplicity_uri,tmp_dir)
    fn = '%s/dupliback-archive_r%s.tar.gz' % (target_path, prety_rev)
    cmd = duplicity_cmd + ' && tar -czvf %s %s' % (fn, tmp_dir)
    for line in os.popen(cmd):
        logging.debug(line)
    return fn, tmp_dir

def restore_to_revision( uuid, host, path, rev, password, restorePath=None):
    duplicity_uri = get_backupUri(uuid, host, path)
    password_cmd = gen_passwordCmd(password)
    if restorePath == None:
        dst_dir = path
        duplicity_cmd = 'PASSPHRASE=%s duplicity restore --force --time %s %s %s %s' % ( password, rev, password_cmd, duplicity_uri,dst_dir)
    else:
        dst_dir = path + util.system_escape(restorePath)
        duplicity_cmd = 'PASSPHRASE=%s duplicity restore --force --time %s %s --file-to-restore %s %s %s' % ( password, rev, password_cmd, util.system_escape(restorePath[1:]), duplicity_uri, dst_dir )
    for line in os.popen(duplicity_cmd):
        logging.debug(line)


def get_status(uuid, host, path, password):
    assert test_backup_assertions(uuid, host, path)
    backup_status = {'new': ['Deleted Files: 0'], 'modified': ['Modified Files: 0'], 'deleted': ['New Files: 0']}
    duplicity_uri = get_backupUri(uuid, host, path)
    password_cmd = gen_passwordCmd(password)
    duplicity_cmd = 'PASSPHRASE={} duplicity {} --dry-run {} {}'.format(password, password_cmd, path, duplicity_uri)
    duplicity_rgx = re.compile(r'(DeletedFiles|ChangedFiles|NewFiles|NewFileSize|ChangedFileSize|DeletedFileSize)\s*(.*)')
    for line in os.popen(duplicity_cmd):
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
    rm_cmd = 'rm -Rf "{}"'.format(get_backupPath(uuid, host, path))
    for line in os.popen(rm_cmd):
        logging.debug(line)

def launch_error(error_msg):
    err_dialog= error_dialog.ErrorDialog(error_msg, None)
    if err_dialog.run() == Gtk.ResponseType.OK:
        logging.debug("error dialog ok was pressed")
        err_dialog.destroy()
