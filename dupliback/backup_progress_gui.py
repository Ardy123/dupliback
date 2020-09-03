import os
import util
import logging
from gi.repository import Gtk
import repeat_timer

class GUI(object):
    def takedownProgressBar(self):
        logging.debug('progress bar take down')
        self.progress_thread.cancel()
        self.unregister_gui(self)
        self.main_window.close()
    
    def __init__(self, register_gui, unregister_gui, parentWnd, msg):
        self.register_gui = register_gui
        self.unregister_gui = unregister_gui
        self.gtkbuilder = Gtk.Builder()
        self.gtkbuilder.add_from_file(os.path.join(util.RUN_FROM_DIR, 'glade', 'backup_progress.glade'))
        self.main_window = self.gtkbuilder.get_object('messagedialog1')
        self.progress_bar= self.gtkbuilder.get_object('progress_bar')
        self.message = self.gtkbuilder.get_object('progress_messasge')
        # set the progress message
        if msg:
            self.message.set_label(msg)
        # prevent the window from being closed
        self.main_window.set_deletable(False)
        # force this window ontop
        self.main_window.set_transient_for( parentWnd )
        # running_tasks_thread.daemon = True
        self.main_window.show()        
        # start progress bar updates
        logging.debug('progress bar put up')
        self.progress_thread = repeat_timer.RepeatTimer(0.5, self.progress_bar.pulse)
        self.progress_thread.start()
    