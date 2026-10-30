# Security policy

## Supported versions

Only the latest release gets security fixes. Fixes ship in a new release;
older versions are not patched.

## Reporting a vulnerability

Please don't open a public issue. Report it privately through
[Report a vulnerability][report] on the repository's Security tab.

Include the dupli.back version (shown by the About button in a backup's
window), your distribution and its duplicity version, and steps to
reproduce.

dupli.back is maintained by one person, so expect an acknowledgement
within a week. Once a fix is released, the advisory is published and you
are credited unless you'd rather not be.

## Scope

Especially relevant:

- `rewrite_helper.py`, which runs as root through pkexec for prune and
  merge
- how backup encryption passwords are handled and passed to duplicity
- restoring or exporting files outside the intended location

Bugs in duplicity, GPG or GTK themselves should go to those projects.

[report]: https://github.com/QVXLabs/dupliback/security/advisories/new
