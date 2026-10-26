#!/usr/bin/python3

import getpass
import os
import sys
import traceback
import backup
from gi.repository import Gtk
import select_backup_gui

GUIS = set()


def register_gui(gui):
  GUIS.add(gui)
  
def unregister_gui(gui):
  GUIS.discard(gui)
  if not GUIS:
    Gtk.main_quit()

def run_all_backups():
  for t in backup.get_known_backups():
    run_backup(t['uuid'], t['path'], t['host'])
  
def run_backup(uuid, path, host=None):
  if host is None:
    host = backup.get_hostname()
  if not backup.test_backup_assertions(uuid, host, path):
    print('---=== skipped backup:', uuid, path, '===---')
    return
  password = None
  if backup.get_preferences(uuid, host, path)['password_protect']:
    # password protected backups take their password from $PASSPHRASE, or prompt for it
    password = os.environ.get('PASSPHRASE')
    if password is None and sys.stdin.isatty():
      password = getpass.getpass('password for %s: ' % path)
    if not backup.check_password(password, backup.get_properties(uuid, host, path).get('password', '')):
      print('---=== skipped backup (wrong or missing password):', uuid, path, '===---')
      return
    backup.upgrade_password_hash(uuid, host, path, password)
  print('---=== starting backup:', uuid, path, '===---')
  try: backup.backup(uuid, host, path, password)
  except: traceback.print_exc()
  
def launch_select_backup_gui():
  register_gui(select_backup_gui.GUI(register_gui, unregister_gui))

if __name__=='__main__':
  args = sys.argv[1:]
  if len(args):
    print()
    print("------------------------------------------")
    print(" dupliBack - Backup for Linux")
    print("------------------------------------------")
    print()
    backup.SHOW_ERROR_DIALOGS = False
    if args[0] in ('-b','--backup-all'):
      run_all_backups()
    elif len(args)==2:
      run_backup(args[0], args[1])
    else:
      print(' to launch the graphical interface:')
      print(' $ python dupliback.py')
      print(' to backup all detected repositories:')
      print(' $ python dupliback.py [-b|--backup-all]')
      print(' to backup a specific repository:')
      print(' $ python dupliback.py <drive_uuid> <path>')
      print(' password protected backups read their password from $PASSPHRASE,')
      print(' or prompt for it when run from a terminal')
      print()
  else:
    launch_select_backup_gui()
    Gtk.main()

