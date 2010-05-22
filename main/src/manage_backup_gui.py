import datetime, gobject, gtk.glade, gtk.gdk, os,tempfile, threading, time

import backup
import settings
import util
import backup_progress_gui
import backup_status_gui


def echo(*args):
    print 'echo', args

class GUI(object):

    def close(self, a=None, b=None):
        self.main_window.hide()
        self.unregister_gui(self)
    
    def update_revisions(self):
        revisions = backup.get_revisions(self.uuid, self.host, self.path)
        treeview_revisions_widget = self.xml.get_widget('treeview_revisions')
        treeview_revisions_model = treeview_revisions_widget.get_model()
        treeview_revisions_model.clear()
        for rev in revisions:
            date = "%s %s/%s/%s %s" % (rev['day'],rev['month'],rev['dayOfMo'],rev['year'], rev['time'])
            isoTime = "%s-%02d-%02dT%s" % (rev['year'],rev['month'],int(rev['dayOfMo']),rev['time'])
            if rev == revisions[0] : type = 'epoch'
            else: type = 'moment'
            s = '[%s] %s\n<i>%s</i>' % ( type, util.pango_escape(date), util.pango_escape(rev['type']) )
            treeview_revisions_model.append((s,isoTime))
        return

    def update_files(self,a=None):
        treeview_files_view = self.xml.get_widget('treeview_files')
        treeview_files_model = treeview_files_view.get_model()
        treeview_files_model.clear()        
        treeview_files_model.append( None, [('loading files... (please wait)'),('')] )
    
        model, entry = a.get_selection().get_selected()
        if not entry:
            treeview_files_model.clear()
            return
        self.xml.get_widget('toolbutton_export').set_sensitive( True )
        self.xml.get_widget('toolbutton_restore').set_sensitive( True )
        self.xml.get_widget('toolbutton_explore').set_sensitive( True )
        rev = entry and model.get_value(entry, 1)
        
        icon = self.main_window.render_icon(gtk.STOCK_FIND, gtk.ICON_SIZE_MENU)
        running_tasks_model = self.xml.get_widget('running_tasks').get_model()
        i = running_tasks_model.append( ( icon, util.pango_escape('loading files for rev: '+self.path), datetime.datetime.now(), '' ) )
        replacmentModel = gtk.TreeStore( str, str )
        replacmentModel.set_default_sort_func(None)
        gui = self
            
        class T(threading.Thread):
            def splitPathFilename(self, filepath):
                # split out path from file 
                ndx = filepath.rfind('/')
                if ndx == -1:
                    return ('', filepath)
                else:
                    return (filepath[:ndx],filepath[ndx + 1:])                            
            def findPath(self, pathStr):
                #find the delta in the curr path and the desired path
                dirSplit = pathStr.split('/')
                if dirSplit[0] != '': dirSplit.insert( 0, '' )
                #unwind cached path until it matches desired path
                del self.currPath[len(dirSplit):]
                for ndx, dir in enumerate(dirSplit):
                    try:
                        if self.currPath[ndx][0] != dir:
                            del self.currPath[ndx:]                                                          
                            break
                    except IndexError:
                        break                 
                #find adjusted path - because path will always be the last added path just find the last path and add it              
                itr = self.currPath[-1][1]
                if self.currPath[-1][0] != dir:                    
                    itr = replacmentModel.iter_nth_child( itr, replacmentModel.iter_n_children( itr ) - 1)
                    self.currPath.append([dir,itr]) 
                return itr
                
            def callback(self, pathDateLst ):
                gtk.gdk.threads_enter()                
                # split out path from file
                path, file = self.splitPathFilename(pathDateLst[0])
                # get model iterator 
                itr =  self.findPath(path)
                #add item                        
                replacmentModel.append( itr, [(file),(pathDateLst[1])] )
                gtk.gdk.threads_leave()
                return                            
            def run(self):
                self.currPath=[['',None]]
                backup.get_files_for_revision(gui.uuid, gui.host, gui.path, rev, gui.password, self.callback)
                gtk.gdk.threads_enter()                
                running_tasks_model.remove(i)
                messageBox.takedownProgressBar()                
                treeview_files_view.set_model(replacmentModel)
                treeview_files_model = replacmentModel
                gtk.gdk.threads_leave()
                                
        messageBox = backup_progress_gui.GUI(gui.register_gui, gui.unregister_gui, self.main_window, 'Retrieving File List, Please Wait' )
        messageBox.main_window.set_transient_for( self.main_window )
        T().start()        

    def restore_selection(self, widget, selection=None ):  
        gui = self
        rev = self.get_selected_revision()
        class T(threading.Thread):
            def run(self):         
                for numericPath in selection[1]:
                    # construct a string path
                    path = ""
                    for ndx in xrange( 0, len(numericPath) ):
                        tpl = () + numericPath[:ndx + 1]
                        itr = selection[0].get_iter( tpl )
                        path += ( "/"+ selection[0].get_value(itr,0) )
                    backup.restore_to_revision( gui.uuid, gui.host, gui.path, rev, gui.password, path )
                messageBox.takedownProgressBar()
        messageBox = backup_progress_gui.GUI(gui.register_gui, gui.unregister_gui, self.main_window, 'Backing Up, Please Wait' )
        T().start()                            
        return
    
    def treeview_mouse_notify(self, widget, event):
        if event.button == 3:            
            selection =  widget.get_selection().get_selected_rows()
            if selection[1] != []:
                # create menu
                menu = gtk.Menu()  
                restoreSelection = gtk.MenuItem("Restore Selection")
                restoreSelection.connect("activate", self.restore_selection, selection )
                menu.append( restoreSelection )                        
                # display menu
                restoreSelection.show()
                menu.popup( None, None, None, event.button, event.time )
                return True
        return False
    
    def get_selected_revision(self):
        model, entry = self.xml.get_widget('treeview_revisions').get_selection().get_selected()
        if not entry: return
        rev = entry and model.get_value(entry, 1)
        return rev
    
    def open_preferences(self):
        import manage_backup_preferences_gui
        self.register_gui( manage_backup_preferences_gui.GUI(self.register_gui, self.unregister_gui, self.uuid, self.host, self.path) )

    def start_backup(self):
        icon = self.main_window.render_icon(gtk.STOCK_SAVE, gtk.ICON_SIZE_MENU)
        running_tasks_model = self.xml.get_widget('running_tasks').get_model()
        i = running_tasks_model.append( ( icon, util.pango_escape('backing up: '+self.path), datetime.datetime.now(), '' ) )
        gui = self
        class T(threading.Thread):
            def run(self):
                backup.backup(gui.uuid, gui.host, gui.path, gui.password)
                gtk.gdk.threads_enter()                                
                gui.update_revisions()
                running_tasks_model.remove(i)
                messageBox.takedownProgressBar()
                gtk.gdk.threads_leave()
        messageBox = backup_progress_gui.GUI(gui.register_gui, gui.unregister_gui, self.main_window, 'Backing Up, Please Wait' )
        T().start()
                
    def start_restore(self):        
        rev = self.get_selected_revision()
        gui = self
        class T(threading.Thread):
            def run(self):
                backup.restore_to_revision( gui.uuid, gui.host, gui.path, rev, gui.password)                
                gtk.gdk.threads_enter()
                messageBox.takedownProgressBar()
                gtk.gdk.threads_leave()
        messageBox = backup_progress_gui.GUI(gui.register_gui, gui.unregister_gui, self.main_window, 'Exporting Backup, Please Wait' )
        T().start()            
        
    def start_export(self):
        dialog = gtk.FileChooserDialog(title='Select folder to save archive to...', parent=None, action=gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER, buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OPEN, gtk.RESPONSE_OK), backend=None)
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            target_dir = dialog.get_filename()
            rev = self.get_selected_revision()
            icon = self.main_window.render_icon(gtk.STOCK_FLOPPY, gtk.ICON_SIZE_MENU)
            running_tasks_model = self.xml.get_widget('running_tasks').get_model()
            i = running_tasks_model.append( ( icon, util.pango_escape('exporting selected revision to: '+target_dir), datetime.datetime.now(), '' ) )
            gui = self
            class T(threading.Thread):
                def run(self):
                    fn, tmp_path = backup.export_revision( gui.uuid, gui.host, gui.path, rev, target_dir, gui.password )                         
                    backup.rmdir(tmp_path)               
                    util.open_file(fn)
                    gtk.gdk.threads_enter()
                    running_tasks_model.remove(i)
                    messageBox.takedownProgressBar()
                    gtk.gdk.threads_leave()
            messageBox = backup_progress_gui.GUI(gui.register_gui, gui.unregister_gui, self.main_window, 'Exporting Backup, Please Wait' )
            T().start()            
        
        elif response == gtk.RESPONSE_CANCEL: pass
        dialog.destroy()

    def start_explore(self):
        target_dir = tempfile.mkdtemp(suffix='_flyback')
        rev = self.get_selected_revision()
        icon = self.main_window.render_icon(gtk.STOCK_DIRECTORY, gtk.ICON_SIZE_MENU)
        running_tasks_model = self.xml.get_widget('running_tasks').get_model()
        i = running_tasks_model.append( ( icon, util.pango_escape('preparing folder for exploration: '+target_dir), datetime.datetime.now(), '' ) )
        gui = self

        class T(threading.Thread):
            def run(self):
                fn, tmp_path = backup.export_revision( gui.uuid, gui.host, gui.path, rev, target_dir, gui.password )
                os.remove( fn )
                os.system( 'xdg-open ' + tmp_path + " &" )                
                gtk.gdk.threads_enter()
                running_tasks_model.remove(i)
                messageBox.takedownProgressBar()
                gtk.gdk.threads_leave()
        messageBox = backup_progress_gui.GUI(gui.register_gui, gui.unregister_gui, self.main_window, 'Exploring Backup, Please Wait' )                
        T().start()                           
    
    def start_status(self):
        icon = self.main_window.render_icon(gtk.STOCK_FIND, gtk.ICON_SIZE_MENU)
        running_tasks_model = self.xml.get_widget('running_tasks').get_model()
        i = running_tasks_model.append( ( icon, util.pango_escape('retrieving folder status since last backup...'), datetime.datetime.now(), '' ) )       
        gui = self  
        class T(threading.Thread):
            def run(self):
                added, modified, deleted = backup.get_status( gui.uuid, gui.host, gui.path, gui.password )
                gtk.gdk.threads_enter()                                                
                running_tasks_model.remove(i)
                messageBox.takedownProgressBar() 
                gui2 = backup_status_gui.GUI(gui.register_gui, gui.unregister_gui, gui.uuid, gui.host, gui.path, gui.main_window )               
                gui.register_gui( gui2 )
                gui2.set_files(added, modified, deleted)
                gtk.gdk.threads_leave()                
        messageBox = backup_progress_gui.GUI(gui.register_gui, gui.unregister_gui, self.main_window, 'Retrieving Status, Please Wait' )
        T().start()        


    def __init__(self, register_gui, unregister_gui, uuid, host, path, password):

        self.register_gui = register_gui
        self.unregister_gui = unregister_gui
        self.uuid = uuid
        self.host = host
        self.path = path
        self.password = password
        
        self.rev_files_map = {}
  
        self.xml = gtk.glade.XML( os.path.join( util.RUN_FROM_DIR, 'glade', 'manage_backup.glade' ) )
        self.main_window = self.xml.get_widget('window')
        self.main_window.connect("delete-event", self.close )
        icon = self.main_window.render_icon(gtk.STOCK_HARDDISK, gtk.ICON_SIZE_BUTTON)
        self.main_window.set_icon(icon)
        self.xml.get_widget('entry_drive_name').set_text( backup.get_drive_name(self.uuid) )
        self.xml.get_widget('entry_path').set_text( self.host +':'+ self.path )
        self.main_window.set_title('%s v%s - Manage Backup' % (settings.PROGRAM_NAME, settings.PROGRAM_VERSION))
    
        # toolbar
        self.xml.get_widget('toolbutton_backup').set_sensitive( backup.test_backup_assertions(self.uuid, self.host, self.path) )
        self.xml.get_widget('toolbutton_backup').connect('clicked', lambda x: self.start_backup() )
        self.xml.get_widget('toolbutton_restore').connect('clicked', lambda x: self.start_restore() )        
        self.xml.get_widget('toolbutton_status').set_sensitive( backup.test_backup_assertions(self.uuid, self.host, self.path) )
        self.xml.get_widget('toolbutton_status').connect('clicked', lambda x: self.start_status() )
        self.xml.get_widget('toolbutton_export').connect('clicked', lambda x: self.start_export() )
        self.xml.get_widget('toolbutton_explore').connect('clicked', lambda x: self.start_explore() )
        self.xml.get_widget('toolbutton_preferences').connect('clicked', lambda x: self.open_preferences() )
    
        # revision list
        treeview_revisions_model = gtk.ListStore( str, str )
        treeview_revisions_widget = self.xml.get_widget('treeview_revisions')
        renderer = gtk.CellRendererText()        
        treeview_revisions_widget.append_column( gtk.TreeViewColumn('History', renderer, markup=0) )
        treeview_revisions_widget.set_model(treeview_revisions_model)
        treeview_revisions_widget.connect( 'cursor-changed', self.update_files )
        treeview_revisions_widget.set_property('rules-hint', True)
        self.update_revisions()
    
        # file list
        treeview_files_widget = self.xml.get_widget('treeview_files')
        treeview_files_model = gtk.TreeStore( str, str )      
        renderer = gtk.CellRendererText()
        renderer.set_property('font','monospace')
        filesColumn = gtk.TreeViewColumn('Files', renderer, markup=0)
        filesColumn.set_resizable(True)
        dateColumn = gtk.TreeViewColumn('Date', renderer, markup=1)
        dateColumn.set_resizable(True)
        treeview_files_widget.append_column( filesColumn )
        treeview_files_widget.append_column( dateColumn )
        treeview_files_widget.set_model(treeview_files_model)
        treeview_files_widget.set_property('rules-hint', True)
        treeview_files_model.append( None, [('please select a revision to view... (on the left)'),('')] )
        treeview_files_widget.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        treeview_files_widget.connect("button_press_event", self.treeview_mouse_notify)

        # task list
        running_tasks_widget = self.xml.get_widget('running_tasks')
        running_tasks_model = gtk.ListStore( gtk.gdk.Pixbuf, str, gobject.TYPE_PYOBJECT, str )
        renderer = gtk.CellRendererPixbuf()
        renderer.set_property('xpad', 4)
        renderer.set_property('ypad', 4)
        running_tasks_widget.append_column( gtk.TreeViewColumn('', renderer, pixbuf=0) )
        renderer = gtk.CellRendererText()
        running_tasks_widget.append_column( gtk.TreeViewColumn('', renderer, markup=1) )
        renderer = gtk.CellRendererText()
        running_tasks_widget.append_column( gtk.TreeViewColumn('', renderer, markup=3) )
        running_tasks_widget.set_model(running_tasks_model)
        running_tasks_widget.set_headers_visible(False)
        running_tasks_widget.set_property('rules-hint', True)
        class T(threading.Thread):
            def run(self):
                while True:
                    tasks_running = False
                    gtk.gdk.threads_enter()
                    for x in running_tasks_model:
                        x[3] = util.humanize_time( datetime.datetime.now() - x[2] )
                    gtk.gdk.threads_leave()
                    if tasks_running: time.sleep(1)
                    else: time.sleep(10)
        running_tasks_thread = T() 
        running_tasks_thread.daemon = True
        running_tasks_thread.start()
        self.main_window.show()
    
        # if no revisions exist, prompt user to run backup
        if not backup.get_revisions(self.uuid, self.host, self.path):
            s = 'Welcome to dupli.back!'
            md = gtk.MessageDialog(None, gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_INFO, gtk.BUTTONS_CLOSE, s)
            md.format_secondary_markup('This is a brand new (and currently empty) backup repository.  To fill it with data, please click the "backup" button in the upper-left corner.')
            md.run()
            md.destroy()
    


