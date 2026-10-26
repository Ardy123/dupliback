#!/usr/bin/env bash
# Creates dupliback/.venv with everything needed to run and test dupli.back.
set -e
cd "$(dirname "$0")"
# PyGObject and dbus-python come from distro packages built for the distro's
# python, so the venv is based on it (override with PYTHON=...)
"${PYTHON:-/usr/bin/python3}" -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
if ! command -v Xvfb >/dev/null; then
    echo
    echo "warning: Xvfb is not installed, so the GUI tests will be" \
         "skipped (sudo apt-get install xvfb)"
fi
echo
echo "run the app:   .venv/bin/python src/dupliback.py"
echo "run the tests: .venv/bin/python -m pytest"
