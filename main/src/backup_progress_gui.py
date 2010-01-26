import datetime, gnome, gobject, gtk, gtk.glade, os, sys, tempfile, threading, time
import util

class GUI(object):
    def takedownProgressBar(self):
        self.progressUpdater.cancel()
        self.main_window.set_deletable(True)
        self.done_button.set_sensitive(True)          
        return
        
    def close(self, a=None, b=None):
        self.main_window.hide()
        self.unregister_gui(self)
        return
        
    def updateProgressBar(self):
        self.progress_bar.pulse()
        self.progressUpdater = threading.Timer(0.1, self.updateProgressBar );
        self.progressUpdater.start()
        return
    def __init__(self, register_gui, unregister_gui):
        self.register_gui = register_gui
        self.unregister_gui = unregister_gui          
        self.xml = gtk.glade.XML( os.path.join( util.RUN_FROM_DIR, 'glade', 'backup_progress.glade' ) )
        self.main_window = self.xml.get_widget('messagedialog1')
        self.done_button = self.xml.get_widget('done_button')
        self.progress_bar= self.xml.get_widget('progress_bar')
        # make the 'Done' button grayed out until completion
        self.done_button.set_sensitive(False)
        self.main_window.set_deletable(False)
        self.main_window.connect("delete-event", self.close )
        self.done_button.connect( "clicked", self.close )        
        # running_tasks_thread.daemon = True
        self.main_window.show()        
        # start progress bar updates
        self.updateProgressBar()         
        return     
    