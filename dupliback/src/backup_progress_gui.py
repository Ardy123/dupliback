import threading
import util
import logging
from gi.repository import GLib


def run_with_progress(register_gui, unregister_gui, parentWnd, msg, work, on_done=None, after=None):
    # shows a progress dialog while work() runs on a worker thread, then on the gtk
    # thread calls on_done(result), takes the dialog down and calls after(result)
    progress = GUI(register_gui, unregister_gui, parentWnd, msg)
    def finish(result):
        if on_done:
            on_done(result)
        progress.takedownProgressBar()
        if after:
            after(result)
        return False
    # the dialog exists before the thread starts, so finish can always take it down
    threading.Thread(target=lambda: GLib.idle_add(finish, work())).start()
    return progress


class GUI(object):
    def takedownProgressBar(self):
        logging.debug('progress bar take down')
        GLib.source_remove(self.pulse_timer)
        self.unregister_gui(self)
        self.main_window.close()

    def pulse(self):
        self.progress_bar.pulse()
        return True

    def __init__(self, register_gui, unregister_gui, parentWnd, msg):
        self.unregister_gui = unregister_gui
        self.gtkbuilder = util.load_glade('backup_progress.glade')
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
        self.main_window.show()
        # start progress bar updates
        logging.debug('progress bar put up')
        self.pulse_timer = GLib.timeout_add(500, self.pulse)
