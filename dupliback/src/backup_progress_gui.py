import threading
import util
import logging
from gi.repository import GLib


def run_with_progress(register_gui, unregister_gui, parentWnd, msg, work,
                      on_done=None, after=None, reports=False, on_failed=None):
    # shows a progress dialog while work() runs on a thread, then on the gtk
    # thread calls on_done(result), takes the dialog down, calls after(result).
    # With reports, work(report) can update the dialog's message. If work
    # raises, the dialog still comes down, on_failed() runs and it is shown.
    progress = GUI(register_gui, unregister_gui, parentWnd, msg)
    if reports:
        task = work
        work = lambda: task(progress.report)
    def finish(result):
        if on_done:
            on_done(result)
        progress.takedownProgressBar()
        if after:
            after(result)
        return False
    def failed(error):
        if on_failed:
            on_failed()
        progress.takedownProgressBar()
        util.run_message('dialog_task_failed', error=error)
        return False
    def run():
        try:
            result = work()
        except Exception as e:
            logging.exception('task failed')
            GLib.idle_add(failed, str(e))
            return
        GLib.idle_add(finish, result)
    # dialog is up before the thread starts, so finish can always take it down
    threading.Thread(target=run).start()
    return progress


class GUI(object):
    def takedownProgressBar(self):
        logging.debug('progress bar take down')
        GLib.source_remove(self.pulse_timer)
        self.unregister_gui(self)
        # close() is ignored while another dialog is modal
        self.main_window.destroy()

    def set_message(self, text):
        self.message.set_label(text)
        return False

    def report(self, text):
        # callable from any thread
        GLib.idle_add(self.set_message, text)

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
