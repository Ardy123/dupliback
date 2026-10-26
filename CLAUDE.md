# dupli.back

GTK3 desktop backup app for Linux, a front end for the `duplicity` command
line tool.

## Layout

- `dupliback/src/` - application modules plus `glade/` and `images/`; run
  with `python3 dupliback/src/dupliback.py`
- `dupliback/test/` - pytest suite (`conftest.py` provides a fake drive and
  GUI helpers)
- `dupliback/requirements.txt`, `dupliback/setup_venv.sh` - creates
  `dupliback/.venv` (with system site packages, for PyGObject and dbus-python)
- `build_deb.sh`, `build_rpm.sh`, `packaging/` - package builds

## Commands

```
cd dupliback
./setup_venv.sh
.venv/bin/python -m pytest              # GUI tests need Xvfb installed
.venv/bin/python -m pytest --cov --cov-report=term-missing
```

## Versioning

`PROGRAM_BASE_VERSION` in `dupliback/src/settings.py` is the only place the
version is written; never hard-code it anywhere else. Unreleased builds report
`<version>-<short commit>`, releases (`build_*.sh -r`) exactly `<version>`.
Record changes under the version's `Unreleased` heading in `CHANGELOG.md`.

## Testing

- The test suite is expected to keep **80%+ line coverage** of
  `dupliback/src/`. Add or update tests with every change so coverage does not
  drop below that; `.coveragerc` sets `fail_under = 80`, so a `--cov` run fails
  if it does.
- GUI tests run on a private Xvfb display started by `conftest.py`, never on
  the real desktop (running them there crashed KWin). Xvfb must be installed
  for them to run, and coverage is only meaningful when they do. Never set
  `DUPLIBACK_GUI_TESTS_ON_DESKTOP` when running tests on someone's machine.
- Tests that run duplicity use the `fake_drive`/`repo` fixtures and keep
  duplicity's cache in a temp directory; GUI tests use `gui_env`, which
  answers modal dialogs and stubs `xdg-open` so nothing touches the desktop.

## Coding style

1. Prefer list comprehensions and `map`/`filter`/`any`/`all`/`sum` (and
   generator expressions) over small `for` loops that only build up a list,
   set, dict or value, e.g.

   ```python
   # preferred
   large = [p for p in paths if os.lstat(p).st_size > limit]
   # avoid
   large = []
   for p in paths:
       if os.lstat(p).st_size > limit:
           large.append(p)
   ```

   Keep an explicit loop when the body has side effects or real control flow.

2. Favour streaming designs over ones that copy data into large buffers and
   then process it: iterate over subprocess output line by line, use
   generators and iterators to pass data between stages, and process files
   incrementally rather than reading them whole. Only materialise a full list
   when the caller truly needs random access or a length.

3. Keep comments concise: say why, or what the code cannot show, in one short
   line where possible. Don't restate the code or narrate history.

4. Keep every line, code and comments, at most 80 columns. Indent with 4
   spaces, never tabs. Wrap inside brackets at natural break points, and split
   long strings into adjacent literals rather than exceeding the limit.

5. Define UI elements (windows, dialogs, menus, labels) and user-facing text
   in the Glade XML files in `dupliback/src/glade/`, marked
   `translatable="yes"`, never in Python, so the UI can be edited and
   translated in one place. Code loads them with `util.load_glade`, fills in
   values (e.g. `{size}` placeholders) and connects signals.
