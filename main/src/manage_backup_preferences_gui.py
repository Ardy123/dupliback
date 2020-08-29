import os
import backup
import settings
import util
from gi.repository import Gtk, GObject, Gdk, GLib, GdkPixbuf
import logging

class GUI(object):

  def close(self, a=None, b=None):
    self.main_window.hide()
    self.unregister_gui(self)
  
  def save(self, a=None):
    preferences = {
      'exclude_audio': self.gtkbuilder.get_object('checkbutton_exclude_audio').get_active(),
      'exclude_video': self.gtkbuilder.get_object('checkbutton_exclude_video').get_active(),
      'exclude_trash': self.gtkbuilder.get_object('checkbutton_exclude_trash').get_active(),
      'exclude_cache': self.gtkbuilder.get_object('checkbutton_exclude_cache').get_active(),
      'exclude_vms': self.gtkbuilder.get_object('checkbutton_exclude_vms').get_active(),
      'exclude_iso': self.gtkbuilder.get_object('checkbutton_exclude_iso').get_active(),
    }
    if self.gtkbuilder.get_object('checkbutton_exclude_filesize').get_active():
      preferences['exclude_filesize'] = self.gtkbuilder.get_object('spinbutton_exclude_filesize_value').get_value()
    else:
      preferences['exclude_filesize'] = None
    
    backup.save_preferences(self.uuid, self.host, self.path, preferences)
    self.close()
    
  def __init__(self, register_gui, unregister_gui, uuid, host, path):

    self.register_gui = register_gui
    self.unregister_gui = unregister_gui
    self.uuid = uuid
    self.host = host
    self.path = path
    self.gtkbuilder = Gtk.Builder()
    self.gtkbuilder.add_from_file( os.path.join( util.RUN_FROM_DIR, 'glade', 'manage_backup_preferences.glade' ) )
    self.main_window = self.gtkbuilder.get_object('dialog')
    self.gtkbuilder.get_object('button_cancel').connect('clicked', self.close)
    self.gtkbuilder.get_object('button_ok').connect('clicked', self.save)
    icon = self.main_window.render_icon(Gtk.STOCK_HARDDISK, Gtk.IconSize.BUTTON)
    self.main_window.set_icon(icon)
    self.main_window.set_title('%s v%s - Backup Preferences' % (settings.PROGRAM_NAME, settings.PROGRAM_VERSION))
    
    self.preferences = backup.get_preferences(self.uuid, self.host, self.path)
    logging.debug(self.preferences)

    self.gtkbuilder.get_object('checkbutton_exclude_audio').set_active(self.preferences.get('exclude_audio'))
    self.gtkbuilder.get_object('checkbutton_exclude_video').set_active(self.preferences.get('exclude_video'))
    self.gtkbuilder.get_object('checkbutton_exclude_trash').set_active(self.preferences.get('exclude_trash'))
    self.gtkbuilder.get_object('checkbutton_exclude_cache').set_active(self.preferences.get('exclude_cache'))
    self.gtkbuilder.get_object('checkbutton_exclude_vms').set_active(self.preferences.get('exclude_vms'))
    self.gtkbuilder.get_object('checkbutton_exclude_iso').set_active(self.preferences.get('exclude_iso'))
    self.gtkbuilder.get_object('checkbutton_exclude_filesize').set_active(bool(self.preferences.get('exclude_filesize')))
    if self.preferences.get('exclude_filesize'):
      self.gtkbuilder.get_object('spinbutton_exclude_filesize_value').set_value(self.preferences.get('exclude_filesize'))
    else:
      self.gtkbuilder.get_object('spinbutton_exclude_filesize_value').set_value(0)

    self.main_window.show()
    

