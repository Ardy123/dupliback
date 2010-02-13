import gtk.glade, os, threading
import util

class GUI(object):
    def takedownProgressBar(self):
        print 'progress bar take down'
        self.progressUpdater.cancel()
        self.main_window.hide()
        gtk.gdk.flush()
        self.unregister_gui(self)        
        return
                
    def updateProgressBar(self):
        self.progress_bar.pulse()
        self.progressUpdater = threading.Timer(0.1, self.updateProgressBar );
        self.progressUpdater.start()
        return
    
    def __init__(self, register_gui, unregister_gui, parentWnd, msg):
        print 'progress bar put up'
        self.register_gui = register_gui
        self.unregister_gui = unregister_gui          
        self.xml = gtk.glade.XML( os.path.join( util.RUN_FROM_DIR, 'glade', 'backup_progress.glade' ) )
        self.main_window = self.xml.get_widget('messagedialog1')
        self.progress_bar= self.xml.get_widget('progress_bar')
        self.message = self.xml.get_widget('progress_messasge')
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
        self.updateProgressBar()         
        return     
    