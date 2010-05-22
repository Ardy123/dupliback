import gtk.glade, os, util

class GUI(object):
    def closedButton(self, dialog, response_id, user=None):
        self.main_window.hide()
        return
    def __init__(self, register_gui, unregister_gui, parentWnd):
        self.register_gui = register_gui
        self.unregister_gui = unregister_gui          
        self.xml = gtk.glade.XML( os.path.join( util.RUN_FROM_DIR, 'glade', 'about.glade' ) )
        self.main_window = self.xml.get_widget('aboutdialog1')
        self.main_window.connect("response", self.closedButton)
        # force this window ontop
        self.main_window.set_transient_for( parentWnd )
        # running_tasks_thread.daemon = True
        self.main_window.show()               
        return     