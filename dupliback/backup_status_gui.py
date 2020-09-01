import os
import settings
import util
import logging
from gi.repository import Gtk, GdkPixbuf

class GUI(object):

    def close(self, a=None, b=None):
        self.main_window.hide()
        self.unregister_gui(self)

    def set_files(self, added, modified, deleted):
        icon_added = self.main_window.render_icon(Gtk.STOCK_ADD, Gtk.IconSize.MENU)
        icon_modified = self.main_window.render_icon(Gtk.STOCK_EDIT, Gtk.IconSize.MENU)
        icon_deleted = self.main_window.render_icon(Gtk.STOCK_DELETE, Gtk.IconSize.MENU)
        model = self.gtkbuilder.get_object('treeview_filelist').get_model()
        model.clear()
        model.append((icon_added, added))
        model.append((icon_modified, modified))
        model.append((icon_deleted, deleted))
    
    def __init__(self, register_gui, unregister_gui, uuid, host, path, parentWindow ):
        self.register_gui = register_gui
        self.unregister_gui = unregister_gui
        self.uuid = uuid
        self.host = host
        self.path = path
        self.gtkbuilder = Gtk.Builder()
        self.gtkbuilder.add_from_file( os.path.join( util.RUN_FROM_DIR, 'glade', 'backup_status.glade' ) )
        self.main_window = self.gtkbuilder.get_object('dialog')
        icon = self.main_window.render_icon(Gtk.STOCK_HARDDISK, Gtk.IconSize.BUTTON)
        self.main_window.set_icon(icon)
        self.main_window.set_title('%s v%s - Backup Status' % (settings.PROGRAM_NAME, settings.PROGRAM_VERSION))
        self.gtkbuilder.get_object('button_close').connect('clicked', self.close)
        treeview_files_widget = self.gtkbuilder.get_object('treeview_filelist')
        treeview_files_model = Gtk.ListStore( GdkPixbuf.Pixbuf, str )
        renderer = Gtk.CellRendererPixbuf()
        renderer.set_property('xpad', 4)
        renderer.set_property('ypad', 4)
        treeview_files_widget.append_column( Gtk.TreeViewColumn('', renderer, pixbuf=0) )
        renderer = Gtk.CellRendererText()
        treeview_files_widget.append_column( Gtk.TreeViewColumn('', renderer, markup=1) )
        treeview_files_widget.set_model(treeview_files_model)
        treeview_files_widget.set_headers_visible(False)
        treeview_files_widget.set_property('rules-hint', True)
        treeview_files_model.append( (None, 'Please wait...(loading list)') )    
        self.main_window.show()
        # force this window ontop
        self.main_window.set_transient_for( parentWindow )
    

