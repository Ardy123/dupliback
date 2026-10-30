#!/usr/bin/env python3
# Starts the version after a release: bumps PROGRAM_BASE_VERSION to the next
# minor version and opens its "Unreleased" section in CHANGELOG.md. Prints
# the new version, or nothing when the version has already moved on.
#
#   start_next_version.py RELEASED_VERSION [REPO_ROOT]
import os
import re
import sys

SETTINGS = os.path.join('dupliback', 'src', 'settings.py')
VERSION_RGX = re.compile(r"^PROGRAM_BASE_VERSION = '([^']*)'$", re.MULTILINE)


def next_minor(version):
    major, minor, _ = map(int, version.split('.'))
    return '%d.%d.0' % (major, minor + 1)


def start_changelog(changelog, released, upcoming):
    heading = re.search(r'^## \[%s\] - ' % re.escape(released), changelog,
                        re.MULTILINE)
    if not heading:
        raise SystemExit('CHANGELOG.md has no entry for %s' % released)
    changelog = (changelog[:heading.start()]
                 + '## [%s] - Unreleased\n\n' % upcoming
                 + changelog[heading.start():])
    # the released compare link ends at its tag (it may already, if edited
    # for the release); the new one at HEAD
    link = re.search(r'^\[%s\]: (\S+/compare/)(\S+)\.\.\.(?:HEAD|v%s)$'
                     % (re.escape(released), re.escape(released)),
                     changelog, re.MULTILINE)
    if link:
        url, since = link.groups()
        changelog = (changelog[:link.start()]
                     + '[%s]: %sv%s...HEAD\n' % (upcoming, url, released)
                     + '[%s]: %s%s...v%s' % (released, url, since, released)
                     + changelog[link.end():])
    return changelog


def main(released, root='.'):
    settings_path = os.path.join(root, SETTINGS)
    changelog_path = os.path.join(root, 'CHANGELOG.md')
    with open(settings_path) as f:
        settings = f.read()
    if VERSION_RGX.search(settings).group(1) != released:
        return
    upcoming = next_minor(released)
    with open(changelog_path) as f:
        changelog = start_changelog(f.read(), released, upcoming)
    with open(changelog_path, 'w') as f:
        f.write(changelog)
    with open(settings_path, 'w') as f:
        f.write(VERSION_RGX.sub(
            "PROGRAM_BASE_VERSION = '%s'" % upcoming, settings))
    print(upcoming)


if __name__ == '__main__':
    main(*sys.argv[1:])
