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
- Password protected backups are encrypted again; since 0.3.0 they were
  written unencrypted. Existing backups stay readable, but volumes already
  written stay unencrypted until the backup is recreated.
- Passwords are stored as salted PBKDF2-SHA256 hashes instead of MD5. Existing
  passwords are upgraded the next time they are entered.
- Passwords no longer show up in the process list, and paths or passwords can
  no longer be used to run commands.

### Added
- **Prune and merge moments**: a new Prune button lists every moment with its
  size. Prune removes moments; Merge combines consecutive moments into the
  newest one selected. A single moment can also be pruned by right-clicking
  it. Moments are rebuilt and checked before anything on the drive changes,
  and an interrupted change can be finished or undone the next time the
  backup is opened. This frees space and makes listing files and backing up
  faster. Backups with other users' files ask for the administrator password.
- A new full backup is made once the last one is over a year old. If the
  drive may not have room for it, an incremental backup is made instead and
  you are asked to prune or merge old moments.
- Listing a moment's files is much faster (about 5 minutes instead of an hour
  on a large 14-year backup) and instant when the moment is viewed again. It
  also works on a new machine without duplicity's cache.
- Command line backups work with password protected backups, reading the
  password from `$PASSPHRASE` or asking for it.
- An RPM package for Fedora.

### Changed
- dupli.back's and duplicity's caches are never backed up.

### Fixed
- During summer time, restore, export and explore used a moment an hour off.
- Right-clicking a moment or a file crashed. Right-clicking a moment now only
  opens its menu (**Restore Moment**, **Prune Moment**) without listing its
  files.
- The Backup, Restore and Export toolbar icons were missing.
- The progress window could stay open after an error.
- Exclusion categories were applied even when switched off.
- The "exclude files over N GB" option could not be set and had no effect.
- Restoring single files failed with duplicity 2.0 and later, and restoring
  over existing files failed with duplicity 3.
- Paths with spaces were cut short in the file list and could not be
  restored.
- The Create Backup window crashed when opened.
- Random crashes.
- Creating a backup that already exists closed the application.
- Status swapped the new and deleted file counts and ignored exclusions.
- Exported archives held absolute paths and left temporary folders behind.
- Some drives were shown without their names.
- Installing the package now installs everything dupli.back needs.

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
