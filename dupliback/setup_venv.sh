#!/usr/bin/env bash
# Creates dupliback/.venv with everything needed to run and test dupli.back.
set -e
cd "$(dirname "$0")"
# PyGObject and dbus-python come from the distro packages, which are only built for
# the distro's python, so base the venv on it (override with PYTHON=...)
"${PYTHON:-/usr/bin/python3}" -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
echo
echo "run the app:   .venv/bin/python src/dupliback.py"
echo "run the tests: .venv/bin/python -m pytest"
