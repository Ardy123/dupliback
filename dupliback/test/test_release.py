# packaging/start_next_version.py, run by the release workflow after a
# release to open a pull request starting the next version
import os
import re
import subprocess
import sys

from conftest import SRC_DIR

ROOT = os.path.dirname(os.path.dirname(SRC_DIR))
SCRIPT = os.path.join(ROOT, 'packaging', 'start_next_version.py')
URL = 'https://github.com/Ardy123/dupliback/compare'


def read(path):
    with open(path) as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(text)


def released_tree(tmp_path, version, base_version):
    # a copy of the repo's settings.py and CHANGELOG.md just after version
    # was released, with settings.py at base_version
    settings = re.sub(r"^PROGRAM_BASE_VERSION = '[^']*'$",
                      "PROGRAM_BASE_VERSION = '%s'" % base_version,
                      read(os.path.join(SRC_DIR, 'settings.py')),
                      flags=re.MULTILINE)
    write(str(tmp_path / 'dupliback' / 'src' / 'settings.py'), settings)
    changelog = read(os.path.join(ROOT, 'CHANGELOG.md'))
    first = re.search(r'^## \[[^\]]+\] - .*$', changelog, re.MULTILINE)
    # drop the versions after the one being released, then date it
    changelog = (changelog[:first.start()]
                 + changelog[changelog.index('## [%s]' % version):])
    changelog = re.sub(r'^## \[%s\] - Unreleased$' % re.escape(version),
                       '## [%s] - 2026-11-30' % version, changelog,
                       flags=re.MULTILINE)
    links = re.search(r'^\[\d', changelog, re.MULTILINE)
    changelog = (changelog[:links.start()]
                 + changelog[changelog.index('[%s]: ' % version):])
    write(str(tmp_path / 'CHANGELOG.md'), changelog)
    return tmp_path


def start_next_version(root, released):
    return subprocess.run(
        [sys.executable, SCRIPT, released, str(root)],
        stdout=subprocess.PIPE, universal_newlines=True,
        check=True).stdout.strip()


def test_starts_the_next_minor_version(tmp_path):
    root = released_tree(tmp_path, '0.6.0', '0.6.0')
    assert start_next_version(root, '0.6.0') == '0.7.0'
    assert ("PROGRAM_BASE_VERSION = '0.7.0'"
            in read(str(root / 'dupliback' / 'src' / 'settings.py')))
    changelog = read(str(root / 'CHANGELOG.md'))
    headings = re.findall(r'^## \[.*$', changelog, re.MULTILINE)
    assert headings[:2] == ['## [0.7.0] - Unreleased',
                            '## [0.6.0] - 2026-11-30']
    assert '[0.7.0]: %s/v0.6.0...HEAD\n' % URL in changelog
    assert '[0.6.0]: %s/v0.5.0...v0.6.0\n' % URL in changelog
    assert changelog.index('[0.7.0]: ') < changelog.index('[0.6.0]: ')


def test_released_link_already_ending_at_its_tag(tmp_path):
    root = released_tree(tmp_path, '0.6.0', '0.6.0')
    path = root / 'CHANGELOG.md'
    write(str(path), read(str(path)).replace('v0.5.0...HEAD',
                                             'v0.5.0...v0.6.0'))
    assert start_next_version(root, '0.6.0') == '0.7.0'
    changelog = read(str(path))
    assert '[0.7.0]: %s/v0.6.0...HEAD\n' % URL in changelog
    assert changelog.count('[0.6.0]: %s/v0.5.0...v0.6.0\n' % URL) == 1


def test_does_nothing_once_master_has_moved_on(tmp_path):
    root = released_tree(tmp_path, '0.6.0', '0.7.0')
    before = [read(str(root / 'CHANGELOG.md')),
              read(str(root / 'dupliback' / 'src' / 'settings.py'))]
    assert start_next_version(root, '0.6.0') == ''
    assert before == [read(str(root / 'CHANGELOG.md')),
                      read(str(root / 'dupliback' / 'src' / 'settings.py'))]


def test_minor_version_rolls_over_past_nine(tmp_path):
    root = released_tree(tmp_path, '0.6.0', '0.6.0')
    for path in (root / 'CHANGELOG.md',
                 root / 'dupliback' / 'src' / 'settings.py'):
        write(str(path), read(str(path)).replace('0.6.0', '1.9.3'))
    assert start_next_version(root, '1.9.3') == '1.10.0'
