import datetime, gnome, gobject, gtk, gtk.glade, os, sys, tempfile, threading, time

import backup
import settings
import util
import backup_progress_gui

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
    treeview_files_model = self.xml.get_widget('treeview_files').get_model()
    treeview_files_model.clear()
    treeview_files_model.append( (util.pango_escape('loading files... (please wait)'),) )
    
    model, entry = a.get_selection().get_selected()
    if not entry:
      treeview_files_model.clear()
      return
    self.xml.get_widget('toolbutton_export').set_sensitive( True )
    self.xml.get_widget('toolbutton_explore').set_sensitive( True )
    rev = entry and model.get_value(entry, 1)
    
    icon = self.main_window.render_icon(gtk.STOCK_FIND, gtk.ICON_SIZE_MENU)
    running_tasks_model = self.xml.get_widget('running_tasks').get_model()
    i = running_tasks_model.append( ( icon, util.pango_escape('loading files for rev: '+self.path), datetime.datetime.now(), '' ) )
    gui = self
    
    class T(threading.Thread):
      def run(self):
        if rev not in gui.rev_files_map:
          gui.rev_files_map[rev] = backup.get_files_for_revision(gui.uuid, gui.host, gui.path, rev)
        gtk.gdk.threads_enter()
        if rev==gui.get_selected_revision():
          treeview_files_model.clear()
          for fn in gui.rev_files_map[rev]:
            treeview_files_model.append( (util.pango_escape(fn),) )
        running_tasks_model.remove(i)
        gtk.gdk.threads_leave()
    T().start()
  
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
          messageBox = backup_progress_gui.GUI(gui.register_gui, gui.unregister_gui )          
          backup.backup(gui.uuid, gui.host, gui.path)
          messageBox.takedownProgressBar()        
          gtk.gdk.threads_enter()
          gui.update_revisions()
          running_tasks_model.remove(i)
          gtk.gdk.threads_leave()
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
          fn = backup.export_revision( gui.uuid, gui.host, gui.path, rev, target_dir )
          util.open_file(fn)
          gtk.gdk.threads_enter()
          running_tasks_model.remove(i)
          gtk.gdk.threads_leave()
      T().start()
      
    elif response == gtk.RESPONSE_CANCEL:
      pass
    dialog.destroy()

  def start_explore(self):
    target_dir = tmp = tempfile.mkdtemp(suffix='_flyback')
    rev = self.get_selected_revision()
    
    icon = self.main_window.render_icon(gtk.STOCK_DIRECTORY, gtk.ICON_SIZE_MENU)
    running_tasks_model = self.xml.get_widget('running_tasks').get_model()
    i = running_tasks_model.append( ( icon, util.pango_escape('preparing folder for exploration: '+target_dir), datetime.datetime.now(), '' ) )
    gui = self
    
    class T(threading.Thread):
      def run(self):
        fn = backup.export_revision( gui.uuid, gui.host, gui.path, rev, target_dir )
        os.chdir(target_dir)
        os.system('tar -zxvf "%s"' % fn)
        os.remove(fn)
        os.chdir(util.RUN_FROM_DIR)
        util.open_file(target_dir)
        gtk.gdk.threads_enter()
        running_tasks_model.remove(i)
        gtk.gdk.threads_leave()
    T().start()

    
  def start_status(self):
    icon = self.main_window.render_icon(gtk.STOCK_FIND, gtk.ICON_SIZE_MENU)
    running_tasks_model = self.xml.get_widget('running_tasks').get_model()
    i = running_tasks_model.append( ( icon, util.pango_escape('retrieving folder status since last backup...'), datetime.datetime.now(), '' ) )
    import backup_status_gui
    gui2 = backup_status_gui.GUI(self.register_gui, self.unregister_gui, self.uuid, self.host, self.path)
    self.register_gui( gui2 )
    gui = self
    
    class T(threading.Thread):
      def run(self):
        added, modified, deleted = backup.get_status( gui.uuid, gui.host, gui.path )
        gtk.gdk.threads_enter()
        gui2.set_files(added, modified, deleted)
        running_tasks_model.remove(i)
        gtk.gdk.threads_leave()
    T().start()
    


  def __init__(self, register_gui, unregister_gui, uuid, host, path):

    self.register_gui = register_gui
    self.unregister_gui = unregister_gui
    self.uuid = uuid
    self.host = host
    self.path = path
    
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
    treeview_files_model = gtk.ListStore( str )
    renderer = gtk.CellRendererText()
    renderer.set_property('font','monospace')
    treeview_files_widget.append_column( gtk.TreeViewColumn('Files', renderer, markup=0) )
    treeview_files_widget.set_model(treeview_files_model)
    treeview_files_widget.set_property('rules-hint', True)
    treeview_files_model.append( (util.pango_escape('please select a revision to view... (on the left)'),) )

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
      s = 'Welcome to Flyback!'
      md = gtk.MessageDialog(None, gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_INFO, gtk.BUTTONS_CLOSE, s)
      md.format_secondary_markup('This is a brand new (and currently empty) backup repository.  To fill it with data, please click the "backup" button in the upper-left corner.')
      md.run()
      md.destroy()
    


