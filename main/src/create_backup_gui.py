import gnome, gobject, gtk, gtk.glade, os, sys

import backup
import manage_backup_gui
import settings
import util

print util.RUN_FROM_DIR

def echo(*args):
  print 'echo', args

class GUI(object):

  def close(self, a=None, b=None):
    self.main_window.hide()
    self.unregister_gui(self)
    
  def init_backup(self,a=None,b=None,c=None):
    treeview_backups_widget = self.xml.get_widget('treeview_backups')
    model, entry = treeview_backups_widget.get_selection().get_selected()
    if entry:
      uuid = model.get_value(entry, 3)
      host = backup.get_hostname()
      path = self.xml.get_widget('filechooserbutton').get_current_folder()
      print 'opening... drive:%s'%uuid, 'host:%s'%host, 'path:%s'%path
      backup.init_backup(uuid, host, path)
      self.register_gui( manage_backup_gui.GUI(self.register_gui, self.unregister_gui, uuid, host, path) )
      self.close()
    else:
      s = 'No Drive Selected'
      md = gtk.MessageDialog(None, gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_WARNING, gtk.BUTTONS_CLOSE, s)
      md.format_secondary_markup('You must select a drive from the list...')
      md.run()
      md.destroy()

  def refresh_device_list(self):
    treeview_backups_model = self.xml.get_widget('treeview_backups').get_model()
    treeview_backups_model.clear()
    writable_devices = backup.get_writable_devices()
    for uuid in writable_devices:
      path = backup.get_mount_point_for_uuid(uuid)
      if backup.get_device_type(uuid)=='gvfs':
        icon = self.main_window.render_icon(gtk.STOCK_NETWORK, gtk.ICON_SIZE_DIALOG)
      elif backup.get_device_type(uuid)=='local':
        icon = self.main_window.render_icon(gtk.STOCK_HARDDISK, gtk.ICON_SIZE_DIALOG)
      else:
        icon = self.main_window.render_icon(gtk.STOCK_DIALOG_QUESTION, gtk.ICON_SIZE_DIALOG)
      free_space = util.humanize_bytes(backup.get_free_space(uuid))
      s = "<b>Drive:</b> %s\n<b>Mount Point:</b> %s\n<b>Free Space:</b> %s" % (util.pango_escape(uuid), util.pango_escape(path), util.pango_escape(free_space))
      treeview_backups_model.append( (icon, s, backup.is_dev_present(uuid), uuid) )
    if not writable_devices:
      icon = self.main_window.render_icon(gtk.STOCK_INFO, gtk.ICON_SIZE_DIALOG)
      s = 'In order to create a backup, Flyback needs a hard drive\nother than the one your computer boots from.\n(preferably external and removable)  Please plug one\ninto a free USB or eSATA port...'
      treeview_backups_model.append( (icon, s, False, None) )
      self.xml.get_widget('button_new').set_sensitive(False)
    else:
      self.xml.get_widget('button_new').set_sensitive(True)

  def __init__(self, register_gui, unregister_gui):
    print util.RUN_FROM_DIR

    self.register_gui = register_gui
    self.unregister_gui = unregister_gui
    self.xml = gtk.glade.XML( os.path.join( util.RUN_FROM_DIR, 'glade', 'create_backup.glade' ) )
    self.main_window = self.xml.get_widget('window')
    self.main_window.connect("delete-event", self.close )
    icon = self.main_window.render_icon(gtk.STOCK_HARDDISK, gtk.ICON_SIZE_BUTTON)
    self.main_window.set_icon(icon)
    self.main_window.set_title('%s v%s - Create Backup' % (settings.PROGRAM_NAME, settings.PROGRAM_VERSION))
    
    # buttons
    self.xml.get_widget('button_cancel').connect('clicked', self.close)
    self.xml.get_widget('button_new').connect('clicked', self.init_backup)
    
    # setup list
    treeview_backups_model = gtk.ListStore( gtk.gdk.Pixbuf, str, bool, str )
    treeview_backups_widget = self.xml.get_widget('treeview_backups')
    renderer = gtk.CellRendererPixbuf()
    renderer.set_property('xpad', 4)
    renderer.set_property('ypad', 4)
    treeview_backups_widget.append_column( gtk.TreeViewColumn('', renderer, pixbuf=0) )
    renderer = gtk.CellRendererText()
    renderer.set_property('xpad', 16)
    renderer.set_property('ypad', 16)
    treeview_backups_widget.append_column( gtk.TreeViewColumn('', renderer, markup=1) )
    treeview_backups_widget.set_headers_visible(False)
    treeview_backups_widget.set_model(treeview_backups_model)
    util.register_device_added_removed_callback(self.refresh_device_list)
    self.refresh_device_list()
    
    self.main_window.show()
    

