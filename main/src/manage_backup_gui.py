import datetime
import threading
import time
import tempfile
import os
import logging
from gi.repository import Gtk, GObject, Gdk, GLib, GdkPixbuf
import backup
import settings
import util
import backup_progress_gui
import backup_status_gui
import about_gui


class GUI(object):

    def close(self, a=None, b=None):
        self.main_window.hide()
        self.unregister_gui(self)
    
    def update_revisions(self):
        revisions = backup.get_revisions(self.uuid, self.host, self.path)
        treeview_revisions_widget = self.gtkbuilder.get_object('treeview_revisions')
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
        treeview_files_view = self.gtkbuilder.get_object('treeview_files')
        treeview_files_model = treeview_files_view.get_model()
        treeview_files_model.clear()        
        treeview_files_model.append( None, [('loading files... (please wait)'),('')] )
        #clear the old tree view selection
        treeview_files_view.get_selection().unselect_all()
        # get files based on the rev selection
        model, entry = a.get_selection().get_selected()
        if not entry:
            treeview_files_model.clear()
            return
        self.gtkbuilder.get_object('toolbutton_export').set_sensitive( True )
        self.gtkbuilder.get_object('toolbutton_restore').set_sensitive( True )
        self.gtkbuilder.get_object('toolbutton_explore').set_sensitive( True )
        rev = entry and model.get_value(entry, 1)
        
        icon = self.main_window.render_icon(Gtk.STOCK_FIND, Gtk.IconSize.MENU)
        running_tasks_model = self.gtkbuilder.get_object('running_tasks').get_model()
        i = running_tasks_model.append( ( icon, util.pango_escape('loading files for rev: '+self.path), datetime.datetime.now(), '' ) )
        replacmentModel = Gtk.TreeStore( str, str )
        gui = self
            
        class T:
            def splitPathFilename(self, filepath):
                # split out path from file 
                ndx = filepath.rfind('/')
                if ndx == -1:
                    return ('', filepath)
                else:
                    return (filepath[:ndx],filepath[ndx + 1:])                            
            def findPath(self, pathStr):
                # find the delta in the curr path and the desired path
                dirSplit = pathStr.split('/')
                if dirSplit[0] != '': dirSplit.insert( 0, '' )
                # unwind cached path until it matches desired path
                del self.currPath[len(dirSplit):]
                for ndx, dir in enumerate(dirSplit):
                    try:
                        if len(self.currPath) > ndx and self.currPath[ndx][0] != dir:
                            del self.currPath[ndx:]                                                          
                            break
                    except IndexError as e:
                        logging.debug(e)
                        break                 
                #find adjusted path - because path will always be the last added path just find the last path and add it
                itr = self.currPath[-1][1]
                if self.currPath[-1][0] != dir:                    
                    itr = replacmentModel.iter_nth_child( itr, replacmentModel.iter_n_children( itr ) - 1)
                    self.currPath.append([dir,itr]) 
                return itr
                
            def callback(self, pathDateLst):
                # split out path from file
                path, file = self.splitPathFilename(pathDateLst[0])
                # add item to tree
                insert_itr = replacmentModel.append(parent=self.findPath(path))
                replacmentModel[insert_itr] = [file, pathDateLst[1]]

            def run(self):
                self.currPath=[['',None]]
                backup.get_files_for_revision(gui.uuid, gui.host, gui.path, rev, gui.password, self.callback)
                def ui_update():
                    running_tasks_model.remove(i)
                    treeview_files_view.set_model(replacmentModel)
                    messageBox.takedownProgressBar()
                GLib.idle_add(ui_update)

        messageBox = backup_progress_gui.GUI(gui.register_gui, gui.unregister_gui, self.main_window, 'Retrieving File List, Please Wait' )
        messageBox.main_window.set_transient_for( self.main_window )
        def thread_func(): (T()).run()
        thread = threading.Thread(target = thread_func)
        thread.start()

    def restore_selection(self, widget, selection=None ):  
        self.start_restore(selection)
        return
    
    def fileview_mouse_notify(self, widget, event):
        if event.button == 3:            
            selection =  widget.get_selection().get_selected_rows()
            if selection[1] != []:
                # create menu
                menu = Gtk.Menu()  
                restoreSelection = Gtk.MenuItem("Restore Selection")
                restoreSelection.connect("activate", self.restore_selection, selection )
                menu.append( restoreSelection )                        
                # display menu
                restoreSelection.show()
                menu.popup( None, None, None, event.button, event.time )
                return True
        return False

    def revview_mouse_notify(self, widget, event):
        if event.button == 3:            
            selection =  widget.get_selection().get_selected_rows()
            if selection[1] != []:
                # create menu
                menu = Gtk.Menu()  
                restoreSelection = Gtk.MenuItem("Restore Moment(revision)")
                restoreSelection.connect("activate", self.restore_selection, None )
                menu.append( restoreSelection )                        
                # display menu
                restoreSelection.show()
                menu.popup( None, None, None, event.button, event.time )
                return True
        return False
    
    def get_selected_revision(self):
        model, entry = self.gtkbuilder.get_object('treeview_revisions').get_selection().get_selected()
        if not entry: return
        rev = entry and model.get_value(entry, 1)
        return rev
    
    def open_preferences(self):
        import manage_backup_preferences_gui
        self.register_gui( manage_backup_preferences_gui.GUI(self.register_gui, self.unregister_gui, self.uuid, self.host, self.path) )

    def start_backup(self):
        icon = self.main_window.render_icon(Gtk.STOCK_SAVE, Gtk.IconSize.MENU)
        running_tasks_model = self.gtkbuilder.get_object('running_tasks').get_model()
        i = running_tasks_model.append( ( icon, util.pango_escape('backing up: '+self.path), datetime.datetime.now(), '' ) )
        gui = self
        def thread_func():
            backup.backup(gui.uuid, gui.host, gui.path, gui.password)
            def ui_update():
                gui.update_revisions()
                running_tasks_model.remove(i)
                messageBox.takedownProgressBar()
            GLib.idle_add(ui_update)

        messageBox = backup_progress_gui.GUI(gui.register_gui, gui.unregister_gui, self.main_window, 'Backing Up, Please Wait' )
        thread = threading.Thread(target=thread_func)
        thread.start()

    def start_restore(self, selection=None ):  
        gui = self
        rev = self.get_selected_revision()
        def thread_func():
            if selection != None:
                for numericPath in selection[1]:
                    # construct a string path
                    path = ""
                    for ndx in range( 0, len(numericPath) ):
                        tpl = [] + numericPath[:ndx + 1]
                        itr = selection[0].get_iter( tpl )
                        path += ( "/"+ selection[0].get_value(itr,0) )
                    backup.restore_to_revision( gui.uuid, gui.host, gui.path, rev, gui.password, path )
            else:
                backup.restore_to_revision( gui.uuid, gui.host, gui.path, rev, gui.password)
            GLib.idle_add(messageBox.takedownProgressBar)

        messageBox = backup_progress_gui.GUI(gui.register_gui, gui.unregister_gui, self.main_window, 'Restoring, Please Wait' )
        thread = threading.Thread(target=thread_func)
        thread.start()
        return
        
    def start_export(self):
        dialog = Gtk.FileChooserDialog(title='Select folder to save archive to...',
                                       parent=None,
                                       action=Gtk.FileChooserAction.SELECT_FOLDER,
                                       buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            target_dir = dialog.get_filename()
            rev = self.get_selected_revision()
            icon = self.main_window.render_icon(Gtk.STOCK_FLOPPY, Gtk.IconSize.MENU)
            running_tasks_model = self.gtkbuilder.get_object('running_tasks').get_model()
            i = running_tasks_model.append( ( icon, util.pango_escape('exporting selected revision to: '+target_dir), datetime.datetime.now(), '' ) )
            gui = self
            def thread_func():
                fn, tmp_path = backup.export_revision( gui.uuid, gui.host, gui.path, rev, target_dir, gui.password )
                backup.rmdir(tmp_path)
                util.open_file(fn)
                def ui_task():
                    running_tasks_model.remove(i)
                    messageBox.takedownProgressBar()
                GLib.idle_add(ui_task)

            messageBox = backup_progress_gui.GUI(gui.register_gui, gui.unregister_gui, self.main_window, 'Exporting Backup, Please Wait' )
            thread = threading.Thread(target=thread_func)
            thread.start()
        
        elif response == Gtk.ResponseType.CANCEL: pass
        dialog.destroy()

    def start_explore(self):
        target_dir = tempfile.mkdtemp(suffix='_duplibackback')
        rev = self.get_selected_revision()
        icon = self.main_window.render_icon(Gtk.STOCK_DIRECTORY, Gtk.IconSize.MENU)
        running_tasks_model = self.gtkbuilder.get_object('running_tasks').get_model()
        i = running_tasks_model.append( ( icon, util.pango_escape('preparing folder for exploration: '+target_dir), datetime.datetime.now(), '' ) )
        gui = self
        def thread_func():
            fn, tmp_path = backup.export_revision( gui.uuid, gui.host, gui.path, rev, target_dir, gui.password )
            os.remove( fn )
            util.open_file(tmp_path)
            def ui_update():
                running_tasks_model.remove(i)
                messageBox.takedownProgressBar()
            GLib.idle_add(ui_update)

        messageBox = backup_progress_gui.GUI(gui.register_gui, gui.unregister_gui, self.main_window, 'Exploring Backup, Please Wait' )
        thread = threading.Thread(target=thread_func)
        thread.start()
    
    def start_status(self):
        icon = self.main_window.render_icon(Gtk.STOCK_FIND, Gtk.IconSize.MENU)
        running_tasks_model = self.gtkbuilder.get_object('running_tasks').get_model()
        i = running_tasks_model.append( ( icon, util.pango_escape('retrieving folder status since last backup...'), datetime.datetime.now(), '' ) )       
        gui = self
        def thread_func():
            added, modified, deleted = backup.get_status( gui.uuid, gui.host, gui.path, gui.password )
            def ui_update():
                running_tasks_model.remove(i)
                messageBox.takedownProgressBar()
                gui2 = backup_status_gui.GUI(gui.register_gui, gui.unregister_gui, gui.uuid, gui.host, gui.path, gui.main_window )
                gui.register_gui( gui2 )
                gui2.set_files(added, modified, deleted)
            GLib.idle_add(ui_update)
        messageBox = backup_progress_gui.GUI(gui.register_gui, gui.unregister_gui, self.main_window, 'Retrieving Status, Please Wait' )
        thread = threading.Thread(target=thread_func)
        thread.start()

    def open_about(self):
        about_dialoge = about_gui.GUI(self.register_gui, self.unregister_gui, self.main_window)
        
    def restore_button_notify(self, widget):
        treeview_files_widget = self.gtkbuilder.get_object('treeview_files')
        selection = treeview_files_widget.get_selection().get_selected_rows()
        if len(selection[1]) == 0: selection = None
        self.start_restore(selection)
          
    def __init__(self, register_gui, unregister_gui, uuid, host, path, password):

        self.register_gui = register_gui
        self.unregister_gui = unregister_gui
        self.uuid = uuid
        self.host = host
        self.path = path
        self.password = password
        
        self.rev_files_map = {}

        self.gtkbuilder = Gtk.Builder()
        self.gtkbuilder.add_from_file( os.path.join( util.RUN_FROM_DIR, 'glade', 'manage_backup.glade' ) )
        self.main_window = self.gtkbuilder.get_object('window')
        self.main_window.connect("delete-event", self.close )
        icon = self.main_window.render_icon(Gtk.STOCK_HARDDISK, Gtk.IconSize.BUTTON)
        self.main_window.set_icon(icon)
        self.gtkbuilder.get_object('entry_drive_name').set_text( backup.get_drive_name(self.uuid) )
        self.gtkbuilder.get_object('entry_path').set_text( self.host +':'+ self.path )
        self.main_window.set_title('%s v%s - Manage Backup' % (settings.PROGRAM_NAME, settings.PROGRAM_VERSION))
    
        # toolbar
        self.gtkbuilder.get_object('toolbutton_backup').set_sensitive( backup.test_backup_assertions(self.uuid, self.host, self.path) )
        self.gtkbuilder.get_object('toolbutton_backup').connect('clicked', lambda x: self.start_backup() )
        self.gtkbuilder.get_object('toolbutton_restore').connect('clicked', self.restore_button_notify )
        self.gtkbuilder.get_object('toolbutton_status').set_sensitive( backup.test_backup_assertions(self.uuid, self.host, self.path) )
        self.gtkbuilder.get_object('toolbutton_status').connect('clicked', lambda x: self.start_status() )
        self.gtkbuilder.get_object('toolbutton_export').connect('clicked', lambda x: self.start_export() )
        self.gtkbuilder.get_object('toolbutton_explore').connect('clicked', lambda x: self.start_explore() )
        self.gtkbuilder.get_object('toolbutton_preferences').connect('clicked', lambda x: self.open_preferences() )
        self.gtkbuilder.get_object('toolbutton_about').connect('clicked', lambda x: self.open_about() )
    
        # revision list
        treeview_revisions_model = Gtk.ListStore( str, str )
        treeview_revisions_widget = self.gtkbuilder.get_object('treeview_revisions')
        renderer = Gtk.CellRendererText()        
        treeview_revisions_widget.append_column( Gtk.TreeViewColumn('History', renderer, markup=0) )
        treeview_revisions_widget.set_model(treeview_revisions_model)
        treeview_revisions_widget.connect( 'cursor-changed', self.update_files )
        treeview_revisions_widget.set_property('rules-hint', True)
        treeview_revisions_widget.connect("button_press_event", self.revview_mouse_notify)
        self.update_revisions()
    
        # file list
        treeview_files_widget = self.gtkbuilder.get_object('treeview_files')
        treeview_files_model = Gtk.TreeStore( str, str )      
        renderer = Gtk.CellRendererText()
        renderer.set_property('font','arial')
        filesColumn = Gtk.TreeViewColumn('Files', renderer, markup=0)
        filesColumn.set_resizable(True)
        dateColumn = Gtk.TreeViewColumn('Date', renderer, markup=1)
        dateColumn.set_resizable(True)
        treeview_files_widget.append_column( filesColumn )
        treeview_files_widget.append_column( dateColumn )
        treeview_files_widget.set_model(treeview_files_model)
        treeview_files_widget.set_property('rules-hint', True)
        treeview_files_model.append( None, [('please select a revision to view... (on the left)'),('')] )
        treeview_files_widget.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        treeview_files_widget.connect("button_press_event", self.fileview_mouse_notify)

        # task list
        running_tasks_widget = self.gtkbuilder.get_object('running_tasks')
        running_tasks_model = Gtk.ListStore( GdkPixbuf.Pixbuf, str, GObject.TYPE_PYOBJECT, str )
        renderer = Gtk.CellRendererPixbuf()
        renderer.set_property('xpad', 4)
        renderer.set_property('ypad', 4)
        running_tasks_widget.append_column( Gtk.TreeViewColumn('', renderer, pixbuf=0) )
        renderer = Gtk.CellRendererText()
        running_tasks_widget.append_column( Gtk.TreeViewColumn('', renderer, markup=1) )
        renderer = Gtk.CellRendererText()
        running_tasks_widget.append_column( Gtk.TreeViewColumn('', renderer, markup=3) )
        running_tasks_widget.set_model(running_tasks_model)
        running_tasks_widget.set_headers_visible(False)
        running_tasks_widget.set_property('rules-hint', True)
        def thread_func():
            while True:
                tasks_running = False
                def ui_update():
                    for x in running_tasks_model:
                        print(x)
                        x[3] = util.humanize_time( datetime.datetime.now() - x[2] )
                GLib.idle_add(ui_update)
                if tasks_running: time.sleep(1)
                else: time.sleep(3)
        thread = threading.Thread(target=thread_func)
        thread.daemon = True
        thread.start()
        self.main_window.show()
    
        # if no revisions exist, prompt user to run backup
        if not backup.get_revisions(self.uuid, self.host, self.path):
            s = 'Welcome to dupli.back!'
            md = Gtk.MessageDialog(None, Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.INFO, Gtk.ButtonsType.CLOSE, s)
            md.format_secondary_markup('This is a brand new (and currently empty) backup repository.  To fill it with data, please click the "backup" button in the upper-left corner.')
            md.run()
            md.destroy()
    


