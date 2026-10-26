# the version is set once, in settings.py, everything else must follow it
import os
import re
import subprocess
import sys
import types

import settings
from conftest import SRC_DIR, requires_display

ROOT = os.path.dirname(os.path.dirname(SRC_DIR))


def read(*path):
    with open(os.path.join(ROOT, *path)) as f:
        return f.read()


def print_version(**env):
    return subprocess.run(
        [sys.executable, os.path.join(SRC_DIR, 'settings.py')],
        env=dict(os.environ, **env), stdout=subprocess.PIPE,
        universal_newlines=True, check=True).stdout.strip()


def head_commit():
    return subprocess.run(['git', 'rev-parse', '--short', 'HEAD'],
                          cwd=SRC_DIR, stdout=subprocess.PIPE,
                          universal_newlines=True, check=True).stdout.strip()


def test_base_version_is_semver():
    assert re.fullmatch(r'\d+\.\d+\.\d+', settings.PROGRAM_BASE_VERSION)


def test_unreleased_version_carries_the_commit(monkeypatch):
    monkeypatch.delenv('DUPLIBACK_RELEASE', raising=False)
    assert settings.get_program_version() == '%s-%s' % (
        settings.PROGRAM_BASE_VERSION, head_commit())


def test_release_version_is_the_base_version(monkeypatch):
    monkeypatch.setenv('DUPLIBACK_RELEASE', '1')
    assert settings.get_program_version() == settings.PROGRAM_BASE_VERSION


def test_without_git_the_base_version_is_used(monkeypatch):
    monkeypatch.delenv('DUPLIBACK_RELEASE', raising=False)
    def no_git(*args, **kwargs):
        raise OSError('git not installed')
    monkeypatch.setattr(settings.subprocess, 'run', no_git)
    assert settings.get_program_version() == settings.PROGRAM_BASE_VERSION


def test_installed_packages_use_the_version_they_were_built_as(monkeypatch):
    monkeypatch.setitem(sys.modules, 'build_version',
                        types.SimpleNamespace(PROGRAM_VERSION='9.9.9-abc1234'))
    monkeypatch.setenv('DUPLIBACK_RELEASE', '1')
    assert settings.get_program_version() == '9.9.9-abc1234'


def test_build_scripts_get_the_version_from_settings():
    assert print_version(DUPLIBACK_RELEASE='') == '%s-%s' % (
        settings.PROGRAM_BASE_VERSION, head_commit())
    assert (print_version(DUPLIBACK_RELEASE='1')
            == settings.PROGRAM_BASE_VERSION)


def test_changelog_has_entry_for_the_version():
    assert re.search(r'^## \[%s\] - (Unreleased|\d{4}-\d{2}-\d{2})$'
                     % re.escape(settings.PROGRAM_BASE_VERSION),
                     read('CHANGELOG.md'), re.MULTILINE)


def test_package_metadata_does_not_hardcode_version():
    assert 'Version: @VERSION@' in read('packaging', 'deb', 'control')
    assert 'Version:        %{pkg_version}' in read('packaging', 'rpm',
                                                    'dupliback.spec')
    # Version= in a desktop file is the desktop entry spec version, not ours
    assert 'Version=1.0' in read('packaging', 'dupliback.desktop')
    assert '<property name="version">' not in read('dupliback', 'src',
                                                   'glade', 'about.glade')


@requires_display
def test_about_dialog_shows_version():
    import about_gui
    about = about_gui.GUI(lambda g: None, lambda g: None, None)
    assert about.main_window.get_version() == settings.PROGRAM_VERSION
    assert about.main_window.get_copyright() == '(c) 2026 QVXLabs LLC'
    about.closedButton(about.main_window, 0)
