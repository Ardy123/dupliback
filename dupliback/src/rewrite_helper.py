#!/usr/bin/python3
# The prepare step of a prune or merge, run as root via pkexec when moments
# hold other users' files; uses the user's caches and hands back what it makes.
# usage: rewrite_helper.py <backup dir> --cache-home <dir>
#        --owner <uid>:<gid> (--thorough|--quick) <kept epoch>...
# Reads the password from stdin; prints 'progress: <json [step, fields]>'
# and 'error: ...' lines.
import json
import os
import pwd
import sys


def parse(args):
    duplicity_dir = args[0]
    rest = args[1:]
    options = dict(zip(rest[0:4:2], rest[1:4:2]))
    thorough = rest[4] == '--thorough'
    uid, gid = map(int, options['--owner'].split(':'))
    # pkexec says who asked; trust that over the command line
    if 'PKEXEC_UID' in os.environ:
        uid = int(os.environ['PKEXEC_UID'])
        gid = pwd.getpwuid(uid).pw_gid
    return (duplicity_dir, options['--cache-home'], uid, gid, thorough,
            [int(end) for end in rest[5:]])


def main(args):
    duplicity_dir, cache_home, uid, gid, thorough, keep = parse(args)
    # set before the backend runs, so it and duplicity use the user's caches
    os.environ['XDG_CACHE_HOME'] = cache_home
    import backup
    import merge
    backup.SHOW_ERROR_DIALOGS = False
    password = sys.stdin.readline().rstrip('\n') or None
    report = lambda step, **fields: print(
        'progress: ' + json.dumps([step, fields]), flush=True)
    try:
        merge.prepare_rewrite(merge.plan_rewrite(duplicity_dir, keep),
                              password, report, thorough)
        return 0
    except Exception as e:
        print('error: ' + str(e).replace('\n', ' '), flush=True)
        return 1
    finally:
        if os.geteuid() == 0:
            merge.hand_back(duplicity_dir, uid, gid)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
