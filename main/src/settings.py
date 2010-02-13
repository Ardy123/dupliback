PROGRAM_NAME = 'dupli.back'
PROGRAM_VERSION = '0.2.0'

DEFAULT_PREFERENCES = {
    'app_version': PROGRAM_VERSION,
    'exclude_audio': True,
    'exclude_video': True,
    'exclude_trash': True,
    'exclude_cache': True,
    'exclude_vms': True,
    'exclude_iso': True,
    'exclude_filesize': 1,
    'password_protect': True,
}
FILEEXT_EXCLUDE_MAP = {
    'exclude_audio': ['*.mp3','*.aac','*.wma'],
    'exclude_video': ['*.mp4','*.avi','*.mpeg',],
    'exclude_trash': ['Trash/','.Trash*/',],
    'exclude_cache': ['Cache/','.cache/',],
    'exclude_vms': ['*.vmdk',],
    'exclude_iso': ['*.iso',],
}

if __name__=='__main__':
    print PROGRAM_VERSION
