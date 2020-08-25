import os, pickle, sys, tempfile, traceback, hashlib
import uuid as uuidlib
import settings
import util

UUID_GVFS = uuidlib.uuid5(uuidlib.NAMESPACE_DNS, 'gvfs.dupliback.org')
PROPERTIES_FILE = 'dupliback_properties.pickle'
PREFERENCES_FILE = 'dupliback_preferences.pickle'

def get_known_backups():
    backups = []
    for uuid in get_all_devices():
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
                    print('discovered backup:', uuid, path)
                except Exception as e:
                    print(e)
                    print('failed to read:', os.path.join(path, fbdb, PROPERTIES_FILE))
    return backups

  
def is_dev_present(uuid):  
    for x in get_gvfs_devices_and_paths():
        if uuid==x:
            return True
    return os.path.exists( os.path.join( '/dev/disk/by-uuid/', uuid ) )
  
def get_device_type(uuid):  
    for x in get_gvfs_devices_and_paths():
        if uuid==x:
            return 'gvfs'  
    if os.path.exists( os.path.join( '/dev/disk/by-uuid/', uuid ) ):
        return 'local'
    return None
  
def get_hostname():
    import socket
    return socket.gethostname()
  
def get_gvfs_devices():
    return [ x[0] for x in get_gvfs_devices_and_paths() ]
  
def get_gvfs_devices_and_paths():
    l = []
    gvfs_dir = os.path.join( os.path.expanduser('~'), '.gvfs')
    try:
        for x in os.listdir(gvfs_dir):
            mount_point = os.path.join( gvfs_dir, x )
            uuid = str(uuidlib.uuid5(UUID_GVFS, mount_point))
            l.append( (uuid, mount_point) )
    except OSError:
        os.mkdir( gvfs_dir )
        pass            
    return l
  
def get_local_devices():
    devices = [ os.path.basename(x) for x in os.listdir('/dev/disk/by-uuid/') ]
    return devices
  
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
                print('could not write to:', path)
    return writable_uuids
  
def test_backup_assertions(uuid, host, path, test_exists=True):
    if not is_dev_present(uuid): 
        print('not is_dev_present("%s")' % uuid)
        return False
    if not get_hostname() == host:
        print('get_hostname()!="%s"' % host)
        return False
    if not os.path.exists(path):
        print('not os.path.exists("%s")' % path)
        return False
    if test_exists:
        if not os.path.exists(get_backupPath(uuid, host, path)):
            print('not os.path.exists("%s")' % get_backupPath(uuid, host, path))
            return False
    return True


def get_dev_paths_for_uuid(uuid):
    dev_path = os.path.join( '/dev/disk/by-uuid/', uuid )
    f = os.popen('udevadm info -q all -n "%s"' % dev_path)
    s = f.read()
    f.close()
    dev_paths = set()
    for line in s.split('\n'):
        if line.startswith('N: '):
            dev_paths.add( os.path.join('/dev', line[line.index(' ')+1:].strip() ) )
        if line.startswith('E: DEVNAME='):
            dev_paths.add( line[line.index('=')+1:].strip() )
        if line.startswith('E: DEVLINKS='):
            for path in line[line.index('=')+1:].strip().split():
                dev_paths.add(path)
    return dev_paths

def get_mount_point_for_uuid(uuid):
    # handle gfvs
    for x,y in get_gvfs_devices_and_paths():
        if uuid==x:
            return y
    # handle local devices
    dev_paths = get_dev_paths_for_uuid(uuid)
    f = os.popen('mount')
    s = f.read()
    f.close()
    for line in s.split('\n'):
        x = line.strip().split()
        if x:
            dev_path = x[0]
            if dev_path in dev_paths:
                mount_path = x[2]
                return mount_path
      
def get_drive_name(uuid):
    paths = get_dev_paths_for_uuid(uuid)
    drive_name = 'UUID: '+ uuid
    for path in paths:
        if 'disk/by-id' in path:
            drive_name = path[path.index('disk/by-id')+11:]
    return drive_name

def get_free_space(uuid):
    path = get_mount_point_for_uuid(uuid)
    cmd = 'df "%s"' % path
    print('$', cmd)
    f = os.popen(cmd)
    s = f.read()
    f.close()
    line = s.split('\n')[1]
    x = line.strip().split()
    print(x)
    if int(x[1])==0: return -1 # unknown amount of space
    return int(x[-3])*1024
      
def get_git_db_name(uuid, host, path):
    s = ':'.join( (uuid, host, path) )
    print(s)
    return '.duplibackdb_%s' % hashlib.sha1(s.encode('utf-8')).hexdigest()
  
def get_backupPath(uuid, host, path):
    mount_point = get_mount_point_for_uuid(uuid)
    duplicity_db = get_git_db_name(uuid, host, path)    
    return os.path.join( mount_point, duplicity_db )
    
def get_backupUri(uuid, host, path):     
    return 'file://%s' % get_backupPath(uuid, host, path)
  
def gen_passwordCmd(password):
    if password:
        passwordLine = ''
    else:
        passwordLine = '--no-encryption'    
    return passwordLine
  
def gen_passwordEncrypt(password):
    if password:
        md5 = hashlib.md5()
        md5.update(password)
        hashStr = md5.hexdigest()
    else:
        hashStr = ''
    return hashStr

def gen_exclusionCmd( preferences ):
    excludeCmd = ''
    for prefItem, prefValue in preferences.iteritems():
        if prefValue == True:
            excludeSubCmd = ''
            if ( settings.FILEEXT_EXCLUDE_MAP.has_key(prefItem)):
                for fileExt in settings.FILEEXT_EXCLUDE_MAP[prefItem]:
                    excludeSubCmd += '--exclude \'' + fileExt + '\' '
            excludeCmd += excludeSubCmd
    return excludeCmd
    
def rmdir(tmp):
    f = os.popen('rm -Rf "%s"' % tmp)
    s = f.read().strip()
    f.close()
    if s:  print(s)


def init_backup(uuid, host, path, password):
    assert test_backup_assertions(uuid, host, path, test_exists=False)
    duplicity_dir = get_backupPath(uuid, host, path)
    os.mkdir(duplicity_dir)
    # write config info
    f = open( os.path.join(duplicity_dir, PROPERTIES_FILE), 'w' )
    o = {
		'uuid':uuid,
		'host':host,
		'path':path,
		'version':settings.PROGRAM_VERSION,
        'password': gen_passwordEncrypt(password)
	}
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
    f = os.popen(duplicity_cmd)
    output = f.read()
    if settings.PROGRAM_DEBUG:        
            sys.stdout.write(output)
    f.close()
    return
             

def get_preferences(uuid, host, path):
    preferences = dict(settings.DEFAULT_PREFERENCES)
    duplicity_dir = get_backupPath(uuid, host, path)
    try:
        f = open( os.path.join(duplicity_dir, PREFERENCES_FILE), 'r' )
        o = pickle.load(f)
        f.close()
    except:
        return preferences
    #deal with a change in version numbers
    if o:
        # version 0.1.0 did not store a version number
        if not o.has_key('app_version'):                                       
            o['app_version'] = '0.1.0'
        # version 0.1.0 did not support password encrypted backups
        if not o.has_key('password_protect'):
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
        f = open( os.path.join(duplicity_dir, PREFERENCES_FILE), 'w' )
        pickle.dump(pref, f)
        f.close()
    except:
        print(traceback.print_exc())
    return
  


def get_revisions(uuid, host, path):
    duplicity_uri = get_backupUri(uuid, host, path)
    duplicity_cmd = 'duplicity collection-status %s' % (duplicity_uri)  
    f = os.popen(duplicity_cmd)
    s = []
    for line in f:
        s.append(line)
    f.close()
    s = ''.join(s)
    log = []
    if s:
        MonthTbl = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,"Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12 }
        entry = None
        for line in s.split('\n'):
            line = line.strip().expandtabs(1)
            # check if a backup has ever occured
            if line == 'Last full backup date: none': 
                break
            # check if there are backups lets fill the dictionary
            if line.startswith('Full') or line.startswith('Incremental'):
                entry = {}
                for column in line.split(' '):
                    if column != '':
                        if column.lower() == 'full' or column.lower() == 'incremental':
                            entry['type'] = column
                        elif 'type' in entry and 'day' not in entry:
                            entry['day'] = column
                        elif 'day' in entry and 'month'not in entry:
                            entry['month'] = MonthTbl[ column ]
                        elif 'month' in entry and 'dayOfMo' not in entry:
                            entry['dayOfMo'] = column
                        elif 'dayOfMo' in entry and 'time' not in entry:
                            entry['time'] = column
                        elif 'time' in entry and 'year' not in entry:
                            entry['year'] = column
                        elif 'year' in entry and 'nVolumes' not in entry:
                            entry['nVolumes'] = column                            
                if entry:
                    log.append(entry)                    
    print('log', log)
    return log


def get_files_for_revision(uuid, host, path, rev, password, callback):
    duplicity_uri = get_backupUri(uuid, host, path)
    password_cmd = gen_passwordCmd(password)
    duplicity_cmd = 'PASSPHRASE=%s duplicity list-current-files --time %s %s %s' % ( password, rev, password_cmd, duplicity_uri)
    f = os.popen(duplicity_cmd)    
    for line in f:       
        lineSplit = line.split( ' ', 5 )
        if lineSplit[0] != 'Last' and lineSplit[0] != 'Local':
            # remove blank entries from the list
            nBlankLines = lineSplit.count('')
            if nBlankLines:
                tmpList = lineSplit[-1].split( ' ', nBlankLines )
                lineSplit.pop()
                lineSplit.extend( tmpList)
            # search for path portion and separate out the date from the path
            path = lineSplit[-1].strip('\n')
            date = ' '.join(lineSplit[:-1])
            callback([ (path), (date) ] )                                                    
    f.close()
    return


def export_revision(uuid, host, path, rev, target_path, password):
    prety_rev= rev.replace(":",".")
    tmp_dir = (tempfile.mkdtemp(suffix='_dupliback') + 'archive-%s' % (prety_rev)).replace(":",".")
    duplicity_uri = get_backupUri(uuid, host, path)
    password_cmd = gen_passwordCmd(password)
    duplicity_cmd = 'PASSPHRASE=%s duplicity restore --time %s %s %s %s' % ( password, rev, password_cmd, duplicity_uri,tmp_dir)
    fn = '%s/dupliback-archive_r%s.tar.gz' % (target_path, prety_rev)
    cmd = duplicity_cmd + ' && tar -czvf %s %s' % (fn, tmp_dir)
    f = os.popen(cmd)
    output = f.read()
    if settings.PROGRAM_DEBUG:        
            sys.stdout.write(output)
    f.close();
    return fn, tmp_dir

def restore_to_revision( uuid, host, path, rev, password, restorePath=None):
    duplicity_uri = get_backupUri(uuid, host, path)
    password_cmd = gen_passwordCmd(password)
    if restorePath == None:
        dst_dir = path;
        duplicity_cmd = 'PASSPHRASE=%s duplicity restore --force --time %s %s %s %s' % ( password, rev, password_cmd, duplicity_uri,dst_dir)
    else:
        dst_dir = path + util.system_escape(restorePath)
        duplicity_cmd = 'PASSPHRASE=%s duplicity restore --force --time %s %s --file-to-restore %s %s %s' % ( password, rev, password_cmd, util.system_escape(restorePath[1:]), duplicity_uri, dst_dir )
    f = os.popen(duplicity_cmd)
    output = f.read()
    if settings.PROGRAM_DEBUG:        
            sys.stdout.write(output)
    f.close()    
    return

def get_status(uuid, host, path, password):
    assert test_backup_assertions(uuid, host, path)
    added = []
    modified = []
    deleted = []
    duplicity_uri = get_backupUri(uuid, host, path)
    password_cmd = gen_passwordCmd(password)
    duplicity_cmd = 'PASSPHRASE=%s duplicity %s --dry-run %s %s' % (password, password_cmd, path, duplicity_uri)
    print('$', duplicity_cmd)
    f = os.popen(duplicity_cmd)    
    for line in f:
        if settings.PROGRAM_DEBUG: 
            sys.stdout.write(line)            
        if line.startswith('DeletedFiles'):
            deleted.append( 'Deleted Files: %s' % (line.split(' ')[1] ) )
        elif line.startswith('ChangedFiles'):
            modified.append( 'Modified Files: %s' % (line.split(' ')[1] ) )
        elif line.startswith('NewFiles'):
            added.append( 'New Files: %s' % (line.split(' ')[1] ) )
        elif line.startswith( 'NewFileSize' ):
            added[0] = added[0] + ' - Size of New Files: %s Bytes' % (line.split(' ')[1] )
        elif line.startswith('ChangedFileSize'):
            modified[0] = modified[0] + ' - Size of Modified Files: %s Bytes' % (line.split(' ')[1] )
        elif line.startswith('DeletedFileSize'):
            deleted[0] = deleted[0] + ( ' - Size of Deleted Files: %s Bytes' % (line.split(' ')[1] ) )
    f.close()
    return added, modified, deleted


def delete_backup(uuid, host, path):
    backup_dir = get_backupPath(uuid, host, path)
    cmd = 'rm -Rf "%s"' % backup_dir
    print('$', cmd)
    f = os.popen(cmd)
    output = f.read()
    if settings.PROGRAM_DEBUG:        
            sys.stdout.write(output)
    f.close()
  

