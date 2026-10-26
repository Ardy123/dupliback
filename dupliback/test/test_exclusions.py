import os

import backup
import settings


def preferences(**overrides):
    prefs = dict(settings.DEFAULT_PREFERENCES)
    prefs.update({key: False for key in settings.FILEEXT_EXCLUDE_MAP})
    prefs.update(overrides)
    return prefs


def test_disabled_categories_add_no_excludes(source_dir):
    assert backup.gen_exclusionCmd(preferences(), source_dir) == []


def test_only_enabled_categories_are_excluded(source_dir):
    cmd = backup.gen_exclusionCmd(preferences(exclude_audio=True), source_dir)
    assert cmd == [arg for ext in settings.FILEEXT_EXCLUDE_MAP['exclude_audio']
                   for arg in ('--exclude', ext)]
    assert '**.mp4' not in cmd


def test_custom_filters_split_on_unescaped_colons(source_dir):
    cmd = backup.gen_exclusionCmd(
        preferences(exclude_filters=r'**/a\:b:**/tmp/'), source_dir)
    assert cmd == ['--exclude', '**/a:b', '--exclude', '**/tmp/']


def test_empty_custom_filter_adds_nothing(source_dir):
    assert backup.gen_exclusionCmd(preferences(exclude_filters=''),
                                   source_dir) == []


def test_files_over_size_limit_are_excluded(source_dir):
    big = os.path.join(source_dir, 'big file.bin')
    with open(big, 'w') as f:
        f.write('x' * 4096)
    with open(os.path.join(source_dir, 'small.bin'), 'w') as f:
        f.write('x')
    cmd = backup.gen_exclusionCmd(
        preferences(exclude_filesize=2048 / 1024 ** 3), source_dir)
    assert len(cmd) == 2 and cmd[0] == '--exclude-regexp'
    assert cmd[1].startswith('^') and 'big' in cmd[1] and cmd[1].endswith('$')
