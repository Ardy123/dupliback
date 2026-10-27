import os
import subprocess
import sys

PROGRAM_NAME = 'dupli.back'
# the only place the version is set. releases use it exactly; afterwards it
# is bumped by hand to the next one.
PROGRAM_BASE_VERSION = '0.5.0'
# the oldest duplicity known to work (Debian 13's, tested in CI). It must
# not exceed what the current Ubuntu LTS installs (26.04: 3.0.6). Packages
# depend on it through the build scripts; requirements.txt repeats it (a test
# checks).
MIN_DUPLICITY_VERSION = '3.0.4'
PROGRAM_DEBUG = False


def get_program_version():
    # packages record the exact version they were built as
    try:
        from build_version import PROGRAM_VERSION as built_version
        return built_version
    except ImportError:
        pass
    if os.environ.get('DUPLIBACK_RELEASE'):
        return PROGRAM_BASE_VERSION
    # unreleased builds carry the commit they were built from
    try:
        commit = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            universal_newlines=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return PROGRAM_BASE_VERSION
    return '%s-%s' % (PROGRAM_BASE_VERSION, commit)


PROGRAM_VERSION = get_program_version()

DEFAULT_PREFERENCES = {
    'app_version': PROGRAM_VERSION,
    'exclude_audio': True,
    'exclude_video': True,
    'exclude_trash': True,
    'exclude_cache': True,
    'exclude_vms': True,
    'exclude_iso': True,
    'exclude_filesize': 0,
    'exclude_filters': '',
    'password_protect': True,
}
FILEEXT_EXCLUDE_MAP = {
    'exclude_audio': ['**.mp3','**.aac','**.wma'],
    'exclude_video': ['**.mp4','**.avi','**.mpeg',],
    'exclude_trash': ['**/Trash/','**/.Trash*/',],
    'exclude_cache': ['**/Cache/','**/.cache/',],
    'exclude_vms': ['**.vmdk',],
    'exclude_iso': ['**.iso',],
}

if __name__=='__main__':
    # the build scripts read both versions from here
    print(MIN_DUPLICITY_VERSION if sys.argv[1:] == ['--min-duplicity']
          else PROGRAM_VERSION)
