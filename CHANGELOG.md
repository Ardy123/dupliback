# Changelog

All notable changes to dupli.back are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[Semantic Versioning](https://semver.org/). The version is set in one place,
`PROGRAM_BASE_VERSION` in `dupliback/src/settings.py`; packages, window titles and
the about dialog all read it from there. Builds of an unreleased version are
labelled `X.Y.Z-<short commit>`, releases are exactly `X.Y.Z` and are tagged
`vX.Y.Z`. The version being worked on is listed as "Unreleased" until its release.

## [0.5.0] - Unreleased

### Security
- Password protected backups are encrypted again. Since 0.3.0 the encryption flag
  was inverted, so protected backups were written unencrypted and password-less
  backups were encrypted with the literal passphrase `None`. Existing backups stay
  readable; volumes already written unencrypted stay unencrypted until the backup
  is recreated.
- Passwords are stored as salted PBKDF2-SHA256 hashes instead of unsalted MD5.
  Existing MD5 hashes still work and are upgraded the first time the correct
  password is entered.
- duplicity and other tools are run without a shell and the passphrase is passed
  through the environment, so paths and passwords cannot inject commands or show
  up in the process list.

### Added
- Test suite under `dupliback/test` with 80%+ coverage, a `requirements.txt` and
  `setup_venv.sh` for a `.venv` development environment.
- RPM package build (`build_rpm.sh`, `packaging/rpm/dupliback.spec`).
- GitHub Actions: tests and package builds run on every pull request, and
  publishing a release attaches the `.deb` and `.rpm` to it.
- The command line backup (`dupliback.py <uuid> <path>` and `--backup-all`) reads
  the password of protected backups from `$PASSPHRASE` or prompts for it.
- Unreleased builds show their version as `X.Y.Z-<short commit>`; `build_deb.sh`
  and `build_rpm.sh` take `-r` to build a release.
- Listing a moment's files reads the signature files directly instead of
  running `duplicity list-current-files`: about 5 minutes instead of about an
  hour on a 14-year, 67-moment backup, and instant when the same moment is
  viewed again. It works without duplicity's cache (e.g. on a new machine) and
  falls back to duplicity if the signatures can't be read.

### Changed
- duplicity 3.0.6 or newer is required (what Kubuntu/Ubuntu 26.04 ships; also
  Fedora 43+ and Debian unstable). The packages depend on it, and CI runs the
  tests on Ubuntu 26.04. Backups made by older duplicity versions stay
  readable.
- Sources moved to `dupliback/src`.
- The version is defined only in `dupliback/src/settings.py` instead of being
  repeated in the deb control file, the about dialog and the desktop files.
- About dialog copyright updated to 2026.
- Drive change notifications are handled on the GTK main loop instead of a second
  main loop on its own thread.
- Duplicity's cache and the app's own cache are never backed up, whatever the
  "exclude cache" preference says.

### Fixed
- Moments are selected by their exact UTC time. The previous time strings had
  no time zone, so during summer time restore, export and explore resolved
  them an hour off.
- Exclusion categories were always applied, even when switched off, and empty
  custom filters added an empty exclusion.
- The "exclude files over N GB" option could not be set (its spin button had no
  range) and was never passed to duplicity.
- Restoring single files failed on duplicity 2.0 and later, and restoring onto
  existing files failed on duplicity 3.
- Paths containing spaces were cut short in the file list and could not be
  restored.
- The Create Backup window crashed when opened.
- Random GTK crashes caused by GTK being used from worker threads.
- Creating a backup that already exists closed the whole application.
- Status showed the new and deleted file counts under each other's labels and
  ignored the exclusions.
- Exporting a revision put absolute paths in the archive and left temporary
  directories behind.
- Drive names from udev links were not shown.
- The packages now depend on everything the app uses: `python3-dbus`, the GTK
  and GdkPixbuf typelibs, `udev` (drive detection), `mount` and `xdg-utils`
  (opening exports); the RPM requires the commands by path. The deb's
  section, priority and homepage are corrected, and its version always
  matches the application version.

## [0.4.0] - 2023-02-09

### Added
- Custom exclusion filters: a `:` separated list of duplicity patterns in the
  backup preferences.

## [0.3.0] - 2020-09-03

### Changed
- Ported to Python 3 and GTK 3 (PyGObject), with the UI layouts converted to
  GtkBuilder.
- Restructured the project and the deb build for Ubuntu 20.04 LTS.
- duplicity output is parsed with regular expressions, and commands run through
  `subprocess.Popen`.
- Error messages go through the `logging` module.

### Fixed
- The Select Backup window did not close after a backup was chosen.
- The password prompt was shown for backups without a password.
- A backup could be created over an existing one.
- No error was shown when the hostname did not match the one stored in the
  backup.
- Building the tree of backed up files.
- The application hung on exit.
- The drive list did not update on D-Bus drive notifications.
- Package dependencies in the deb control file.

## [0.2.4] - 2010-07-09

### Added
- Debug flag that prints duplicity's output to stdout.

### Fixed
- Exclusion preferences were not honoured (issue 14).
- Unrelated duplicity output was shown as a file in the file list.
- duplicity output is no longer printed to the terminal.
- duplicity thought the hostname had changed on Kubuntu 10.10.

## [0.2.3] - 2010-05-22

**Backups from earlier versions are not compatible with this version.**

### Added
- New icons, an application icon and a Restore button.
- Restore a whole moment (revision) from its right-click menu.

### Fixed
- Exported archives are opened once the export finishes.
- The About menu.
- Creating a new backup.
- Restoring a complete moment.
- The Restore button ignored the selection in the right-hand pane (issue 15).

## [0.2.2] - 2010-02-21

### Added
- Restore of individual files.

### Changed
- The revision file list is a tree instead of one flat list, and is built
  asynchronously.

## [0.2.1] - 2010-02-17

### Fixed
- Passwords longer than 5 characters did not work.
- Backups without a password could not be opened.
- Some removable USB disks were not discovered.
- "flyback" was shown instead of dupli.back.

## [0.2.0] - 2010-02-13

### Added
- Password protected (encrypted) backups.

## [0.1.0] - 2010-01-24

First release, forked from flyback and rebuilt on top of duplicity.

### Added
- Backups to local and removable disks, with a Time Machine style interface.
- deb packaging.

### Fixed
- The progress pop-up sometimes stayed up, was not tied to the main window, and
  was not shown for every long running operation.
- Status results appeared before the progress pop-up.
- Exploring a backup revision.
- Remaining references to flyback, including "welcome to flyback" on first run
  (issue 2).
- deb build script problems (issues 6 and 7).

[0.5.0]: https://github.com/Ardy123/dupliback/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/Ardy123/dupliback/releases/tag/v0.3.0
