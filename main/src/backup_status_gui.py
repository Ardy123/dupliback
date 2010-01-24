import gnome, gobject, gtk, gtk.glade, os, sys, tempfile, threading

import settings
import util


class GUI(object):

  def close(self, a=None, b=None):
    self.main_window.hide()
    self.unregister_gui(self)

  def set_files(self, added, modified, deleted):
    print added, modified, deleted
    model = self.xml.get_widget('treeview_filelist').get_model()
    model.clear()
    for fn in added:
      icon_added = self.main_window.render_icon(gtk.STOCK_ADD, gtk.ICON_SIZE_MENU)
      model.append( (icon_added, fn) )
    for fn in modified:
      icon_modified = self.main_window.render_icon(gtk.STOCK_EDIT, gtk.ICON_SIZE_MENU)
      model.append( (icon_modified, fn) )
    for fn in deleted:
      icon_deleted = self.main_window.render_icon(gtk.STOCK_DELETE, gtk.ICON_SIZE_MENU)
      model.append( (icon_deleted, fn) )
    

  def __init__(self, register_gui, unregister_gui, uuid, host, path):

    self.register_gui = register_gui
    self.unregister_gui = unregister_gui
    self.uuid = uuid
    self.host = host
    self.path = path
    
    self.xml = gtk.glade.XML( os.path.join( util.RUN_FROM_DIR, 'glade', 'backup_status.glade' ) )
    self.main_window = self.xml.get_widget('dialog')
    icon = self.main_window.render_icon(gtk.STOCK_HARDDISK, gtk.ICON_SIZE_BUTTON)
    self.main_window.set_icon(icon)
    self.main_window.set_title('%s v%s - Backup Status' % (settings.PROGRAM_NAME, settings.PROGRAM_VERSION))
    self.xml.get_widget('button_close').connect('clicked', self.close)

    treeview_files_widget = self.xml.get_widget('treeview_filelist')
    treeview_files_model = gtk.ListStore( gtk.gdk.Pixbuf, str )
    renderer = gtk.CellRendererPixbuf()
    renderer.set_property('xpad', 4)
    renderer.set_property('ypad', 4)
    treeview_files_widget.append_column( gtk.TreeViewColumn('', renderer, pixbuf=0) )
    renderer = gtk.CellRendererText()
    treeview_files_widget.append_column( gtk.TreeViewColumn('', renderer, markup=1) )
    treeview_files_widget.set_model(treeview_files_model)
    treeview_files_widget.set_headers_visible(False)
    treeview_files_widget.set_property('rules-hint', True)
    treeview_files_model.append( (None, 'Please wait...(loading list)') )
    
    self.main_window.show()

