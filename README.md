# dupli.back

Originally based on 'flyback', dupli.back, is a full featured backup application
built on top of the duplicity command line backup tool. The projects goals are
to support the following features.

  * Support password encrypted backup
  * Support backing up on remote servers via ssh
  * Support backing up on Amazon Cloud S3 service
  * Support backing up on local and removable disks
  * Keep a nice & clean user interface, which was originally based on Apple's
    'Time Machine'
  * Fix many of the outstanding bugs in 'flyback'
  

## Running from source

dupli.back needs Python 3, PyGObject with GTK 3, dbus-python and duplicity. On
Debian/Ubuntu:

    sudo apt-get install python3-venv python3-gi python3-dbus gir1.2-gtk-3.0 duplicity xvfb

Then create the development environment in `dupliback/.venv` and start the app:

    dupliback/setup_venv.sh
    dupliback/.venv/bin/python dupliback/src/dupliback.py

The venv is created with `--system-site-packages` so it uses the distro's PyGObject
and dbus-python, which need system libraries to build.

## Tests

    cd dupliback
    .venv/bin/python -m pytest
    .venv/bin/python -m pytest --cov        # fails below 80% coverage

The GUI tests open and close hundreds of windows, so they run on a private Xvfb
display that the test suite starts itself; nothing appears on your desktop. Without
Xvfb (the `xvfb` package) they are skipped and coverage falls below 80%. Set
`DUPLIBACK_GUI_TESTS_ON_DESKTOP=1` only if you really want them on your own display.
Tests that run duplicity use a temporary fake drive and never touch real backups.

## Packages

    ./build_deb.sh -b     # dupli.back-<version>-<commit>.deb
    ./build_rpm.sh -b     # dupli.back-<version>-<commit>.noarch.rpm (needs rpmbuild)

Add `-r` before `-b` to build a release, which drops the commit from the version.

## Releasing

The version is set only by `PROGRAM_BASE_VERSION` in `dupliback/src/settings.py`.
While a version is in development, builds show it as `<version>-<short commit>`
(for example `0.5.0-1a2b3c4`); a release is exactly `<version>`. To release 0.5.0:

1. In `CHANGELOG.md`, change `## [0.5.0] - Unreleased` to the release date.
2. Publish a GitHub release tagged `v0.5.0`. The release workflow runs the tests,
   checks the tag matches the version and has a dated changelog entry, then builds
   the release `.deb` and `.rpm` and attaches them to the release.
3. Bump `PROGRAM_BASE_VERSION` to `0.6.0` and add a `## [0.6.0] - Unreleased`
   section to `CHANGELOG.md`.
