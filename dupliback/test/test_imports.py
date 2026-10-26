# every module must get Gtk 3 when imported alone, even if Gtk 4 is installed
import glob
import os
import subprocess
import sys

import pytest

from conftest import SRC_DIR

MODULES = sorted(os.path.basename(path)[:-3]
                 for path in glob.glob(os.path.join(SRC_DIR, '*.py')))


@pytest.mark.parametrize('module', MODULES)
def test_module_imports_gtk3(module):
    # a fresh interpreter, so nothing else has loaded Gtk first
    check = ('import sys; sys.path.insert(0, %r); import %s; '
             'gtk = sys.modules.get("gi.repository.Gtk"); '
             'print(gtk.get_major_version() if gtk else "no gtk")'
             % (SRC_DIR, module))
    result = subprocess.run([sys.executable, '-c', check],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            universal_newlines=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] in ('3', 'no gtk')
