import settings
import util

class GUI(object):
    def closedButton(self, dialog, response_id, user=None):
        self.main_window.close()
        self.unregister_gui(self)

    def __init__(self, register_gui, unregister_gui, parentWnd):
        self.unregister_gui = unregister_gui
        self.gtkbuilder = util.load_glade('about.glade')
        self.main_window = self.gtkbuilder.get_object('aboutdialog1')
        self.main_window.set_version(settings.PROGRAM_VERSION)
        self.main_window.connect("response", self.closedButton)
        # force this window ontop
        self.main_window.set_transient_for( parentWnd )
        self.main_window.show()