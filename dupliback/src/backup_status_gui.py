import util
from gi.repository import Gtk, GdkPixbuf

class GUI(object):

    def close(self, a=None, b=None):
        self.unregister_gui(self)
        self.main_window.destroy()

    def set_files(self, added, modified, deleted):
        model = self.gtkbuilder.get_object('treeview_filelist').get_model()
        model.clear()
        for stock_icon, text in ((Gtk.STOCK_ADD, added), (Gtk.STOCK_EDIT, modified), (Gtk.STOCK_DELETE, deleted)):
            model.append((self.main_window.render_icon(stock_icon, Gtk.IconSize.MENU), text))
    
    def __init__(self, register_gui, unregister_gui, uuid, host, path, parentWindow ):
        self.unregister_gui = unregister_gui
        self.gtkbuilder = util.load_glade('backup_status.glade')
        self.main_window = self.gtkbuilder.get_object('dialog')
        self.main_window.connect("delete-event", self.close)
        util.setup_window(self.main_window, 'Backup Status')
        self.gtkbuilder.get_object('button_close').connect('clicked', self.close)
        treeview_files_widget = self.gtkbuilder.get_object('treeview_filelist')
        treeview_files_model = Gtk.ListStore( GdkPixbuf.Pixbuf, str )
        util.add_icon_column(treeview_files_widget)
        util.add_markup_column(treeview_files_widget, 1)
        treeview_files_widget.set_model(treeview_files_model)
        treeview_files_widget.set_headers_visible(False)
        treeview_files_widget.set_property('rules-hint', True)
        treeview_files_model.append( (None, 'Please wait...(loading list)') )    
        self.main_window.show()
        # force this window ontop
        self.main_window.set_transient_for( parentWindow )
    

