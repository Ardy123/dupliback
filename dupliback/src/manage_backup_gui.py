import datetime
import os
# util first, it pins Gtk to 3.0
import util
from gi.repository import Gtk, GObject, GLib, GdkPixbuf
import backup
import manage_backup_preferences_gui
import backup_progress_gui
import backup_status_gui
import about_gui
import prune_gui


class FileTreeBuilder(object):
    # builds the tree from duplicity's listing; each path's parent is found by
    # matching its dirs, depth by depth, against the previous row's ancestors
    def __init__(self, model):
        self.model = model
        # [name, row] of the previous row and its ancestors; root has no row
        self.stack = [['', None]]

    def add(self, pathDateLst):
        *dirs, filename = pathDateLst[0].split('/')
        # keep the ancestors shared with the previous row
        depth = 1
        while (depth < len(self.stack) and depth <= len(dirs)
               and self.stack[depth][0] == dirs[depth - 1]):
            depth += 1
        del self.stack[depth:]
        # directories missing from the listing get an empty row
        for name in dirs[depth - 1:]:
            self.stack.append(
                [name, self.model.append(self.stack[-1][1], [name, ''])])
        self.stack.append(
            [filename,
             self.model.append(self.stack[-1][1], [filename, pathDateLst[1]])])


class GUI(object):

    def close(self, a=None, b=None):
        GLib.source_remove(self.status_bar_timer)
        self.unregister_gui(self)
        self.main_window.destroy()

    def run_task(self, stock_icon, task_text, progress_msg, work,
                 on_done=None, after=None, reports=False):
        # lists the task as running while work() runs; see run_with_progress
        tasks = self.gtkbuilder.get_object('running_tasks').get_model()
        row = tasks.append((
            self.main_window.render_icon(stock_icon, Gtk.IconSize.MENU),
            util.pango_escape(task_text), datetime.datetime.now(), ''))
        def done(result):
            if on_done:
                on_done(result)
            tasks.remove(row)
        backup_progress_gui.run_with_progress(
            self.register_gui, self.unregister_gui, self.main_window,
            progress_msg, work, done, after, reports)

    def update_toolbar(self):
        # backing up needs this host and drive, and no rewrite in progress
        can_backup = backup.test_backup_assertions(self.uuid, self.host,
                                                   self.path)
        for name in ('toolbutton_backup', 'toolbutton_status'):
            self.gtkbuilder.get_object(name).set_sensitive(can_backup)

    def update_revisions(self):
        self.update_toolbar()
        self.show_revisions(
            backup.get_revisions(self.uuid, self.host, self.path))

    def show_revisions(self, revisions):
        treeview = self.gtkbuilder.get_object('treeview_revisions')
        selected = self.get_selected_revision()
        # refilling moves the cursor through the rows, and each move would
        # list that moment's files
        with treeview.handler_block(self.revision_cursor_handler):
            self._fill_revisions(treeview.get_model(), revisions)
            rows = [row.path for row in treeview.get_model()
                    if row[1] == selected]
            if rows:
                treeview.set_cursor(rows[0], None, False)
        if selected and not rows:
            self.update_files(treeview)

    def _fill_revisions(self, treeview_revisions_model, revisions):
        treeview_revisions_model.clear()
        # no revisions yet: prompt the user to run a backup
        if not revisions:
            util.message_dialog(
                Gtk.MessageType.INFO, Gtk.ButtonsType.CLOSE,
                'Welcome to dupli.back!',
                'This is a brand new (and currently empty) backup '
                'repository.  To fill it with data, please click the '
                '"backup" button in the upper-left corner.')
        for n, rev in enumerate(revisions):
            date = "%s %s/%s/%s %s" % (rev['day'],rev['month'],rev['dayOfMo'],
                                       rev['year'], rev['time'])
            s = '[%s] %s\n<i>%s</i>' % ( 'epoch' if n == 0 else 'moment',
                                         util.pango_escape(date),
                                         util.pango_escape(rev['type']) )
            treeview_revisions_model.append((s, backup.revision_id(rev)))

    def update_files(self, treeview_revisions=None):
        treeview_files_view = self.gtkbuilder.get_object('treeview_files')
        treeview_files_model = treeview_files_view.get_model()
        treeview_files_model.clear()
        treeview_files_model.append(
            None, [('loading files... (please wait)'),('')] )
        # clear the old selection
        treeview_files_view.get_selection().unselect_all()
        # list the files of the selected revision
        model, entry = treeview_revisions.get_selection().get_selected()
        if not entry:
            treeview_files_model.clear()
            for name in ('toolbutton_export', 'toolbutton_restore',
                         'toolbutton_explore'):
                self.gtkbuilder.get_object(name).set_sensitive(False)
            return
        for name in ('toolbutton_export', 'toolbutton_restore',
                     'toolbutton_explore'):
            self.gtkbuilder.get_object(name).set_sensitive( True )
        rev = model.get_value(entry, 1)
        tree = FileTreeBuilder(Gtk.TreeStore( str, str ))
        self.run_task(Gtk.STOCK_FIND, 'loading files for rev: '+self.path,
                      'Retrieving File List, Please Wait',
                      lambda: backup.list_files(
                          self.uuid, self.host, self.path, rev, self.password,
                          tree.add),
                      lambda result: treeview_files_view.set_model(tree.model))

    def popup_menu(self, name, event, clicked):
        # the right-click menu name, for the rows clicked
        self.clicked = clicked
        self.gtkbuilder.get_object(name).popup_at_pointer(event)

    def fileview_mouse_notify(self, widget, event):
        if event.button != 3:
            return False
        selection = widget.get_selection().get_selected_rows()
        if not selection[1]:
            return False
        self.popup_menu('menu_files', event, selection)
        return True

    def revview_mouse_notify(self, widget, event):
        # a right-click only opens the moment's menu; selecting the moment
        # would start listing its files
        if event.button != 3:
            return False
        hit = widget.get_path_at_pos(int(event.x), int(event.y))
        if hit:
            self.popup_menu('menu_moment', event,
                            widget.get_model()[hit[0]][1])
        return True

    def prune_moment(self, rev):
        prune_gui.RewriteFlow(self).prune([int(rev)])

    def get_selected_revision(self):
        model, entry = self.gtkbuilder.get_object(
            'treeview_revisions').get_selection().get_selected()
        return model.get_value(entry, 1) if entry else None

    def open_prune(self):
        self.register_gui(prune_gui.GUI(self.register_gui, self.unregister_gui,
                                        self))

    def open_preferences(self):
        self.register_gui( manage_backup_preferences_gui.GUI(
            self.register_gui, self.unregister_gui, self.uuid, self.host,
            self.path) )

    def start_backup(self):
        notices = []
        def work():
            backup.backup(self.uuid, self.host, self.path, self.password,
                          report=notices.append)
            # listed here so duplicity does not block the gtk thread
            return backup.get_revisions(self.uuid, self.host, self.path)
        def show_notices(result):
            # the only notice: a due full backup was postponed
            if notices:
                util.run_message('dialog_full_postponed')
        self.run_task(Gtk.STOCK_SAVE, 'backing up: '+self.path,
                      'Backing Up, Please Wait', work, self.show_revisions,
                      after=show_notices)

    def start_restore(self, selection=None, rev=None):
        # restores rev, or the selected moment, whole or just selection
        rev = rev or self.get_selected_revision()
        def work():
            if selection is None:
                backup.restore_to_revision( self.uuid, self.host, self.path,
                                            rev, self.password)
                return
            model, tree_paths = selection
            for numericPath in tree_paths:
                # the row's path, from the names of the rows above it
                path = ''.join('/' + model.get_value(
                                   model.get_iter(numericPath[:depth]), 0)
                               for depth in range(1, len(numericPath) + 1))
                backup.restore_to_revision( self.uuid, self.host, self.path,
                                            rev, self.password, path )
        backup_progress_gui.run_with_progress(
            self.register_gui, self.unregister_gui, self.main_window,
            'Restoring, Please Wait', work)

    def start_export(self):
        dialog = Gtk.FileChooserDialog(
            title='Select folder to save archive to...',
            parent=None,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                     Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        if dialog.run() == Gtk.ResponseType.OK:
            target_dir = dialog.get_filename()
            rev = self.get_selected_revision()
            def work():
                fn, tmp_path = backup.export_revision(
                    self.uuid, self.host, self.path, rev, target_dir,
                    self.password )
                backup.rmdir(os.path.dirname(tmp_path))
                if fn:
                    util.open_file(fn)
                else:
                    backup.launch_error('Failed to export revision %s' % rev)
            self.run_task(Gtk.STOCK_FLOPPY,
                          'exporting selected revision to: '+target_dir,
                          'Exporting Backup, Please Wait', work)
        dialog.destroy()

    def start_explore(self):
        rev = self.get_selected_revision()
        def work():
            fn, tmp_path = backup.export_revision(
                self.uuid, self.host, self.path, rev, None, self.password )
            if os.path.isdir(tmp_path):
                util.open_file(tmp_path)
            else:
                backup.launch_error(
                    'Failed to restore revision %s for exploration' % rev)
        self.run_task(Gtk.STOCK_DIRECTORY,
                      'preparing folder for exploration of revision: '+rev,
                      'Exploring Backup, Please Wait', work)

    def start_status(self):
        def show_status(status):
            status_gui = backup_status_gui.GUI(
                self.register_gui, self.unregister_gui, self.uuid, self.host,
                self.path, self.main_window )
            self.register_gui(status_gui)
            status_gui.set_files(*status)
        self.run_task(Gtk.STOCK_FIND,
                      'retrieving folder status since last backup...',
                      'Retrieving Status, Please Wait',
                      lambda: backup.get_status( self.uuid, self.host,
                                                 self.path, self.password ),
                      after=show_status)

    def open_about(self):
        about_gui.GUI(self.register_gui, self.unregister_gui, self.main_window)

    def restore_button_notify(self, widget):
        selection = self.gtkbuilder.get_object(
            'treeview_files').get_selection().get_selected_rows()
        self.start_restore(selection if selection[1] else None)

    def update_task_times(self):
        now = datetime.datetime.now()
        for row in self.gtkbuilder.get_object('running_tasks').get_model():
            row[3] = util.humanize_time(now - row[2])
        return True

    def __init__(self, register_gui, unregister_gui, uuid, host, path,
                 password):

        self.register_gui = register_gui
        self.unregister_gui = unregister_gui
        self.uuid = uuid
        self.host = host
        self.path = path
        self.password = password

        self.gtkbuilder = util.load_glade('manage_backup.glade')
        get = self.gtkbuilder.get_object
        self.main_window = get('window')
        self.main_window.connect("delete-event", self.close)
        get('entry_drive_name').set_text( backup.get_drive_name(self.uuid) )
        get('entry_path').set_text( self.host +':'+ self.path )
        util.setup_window(self.main_window, 'Manage Backup')

        # toolbar
        self.update_toolbar()
        get('toolbutton_backup').connect(
            'clicked', lambda x: self.start_backup() )
        get('toolbutton_restore').connect(
            'clicked', self.restore_button_notify )
        get('toolbutton_status').connect(
            'clicked', lambda x: self.start_status() )
        get('toolbutton_export').connect(
            'clicked', lambda x: self.start_export() )
        get('toolbutton_explore').connect(
            'clicked', lambda x: self.start_explore() )
        get('toolbutton_preferences').connect(
            'clicked', lambda x: self.open_preferences() )
        get('toolbutton_about').connect('clicked', lambda x: self.open_about() )
        get('toolbutton_prune').connect('clicked', lambda x: self.open_prune())

        # right-click menus, attached so they show over their lists
        get('menu_files').attach_to_widget(get('treeview_files'), None)
        get('menu_moment').attach_to_widget(get('treeview_revisions'), None)
        get('menuitem_restore_selection').connect(
            'activate', lambda item: self.start_restore(self.clicked))
        get('menuitem_restore_moment').connect(
            'activate', lambda item: self.start_restore(rev=self.clicked))
        get('menuitem_prune_moment').connect(
            'activate', lambda item: self.prune_moment(self.clicked))

        # revision list
        treeview_revisions_widget = get('treeview_revisions')
        util.add_markup_column(treeview_revisions_widget, 0, 'History')
        treeview_revisions_widget.set_model(Gtk.ListStore( str, str ))
        self.revision_cursor_handler = treeview_revisions_widget.connect(
            'cursor-changed', self.update_files)
        treeview_revisions_widget.set_property('rules-hint', True)
        treeview_revisions_widget.connect("button_press_event",
                                          self.revview_mouse_notify)
        self.update_revisions()

        # file list
        treeview_files_widget = get('treeview_files')
        treeview_files_model = Gtk.TreeStore( str, str )
        renderer = Gtk.CellRendererText()
        renderer.set_property('font','arial')
        for column, title in enumerate(('Files', 'Date')):
            treeview_column = Gtk.TreeViewColumn(title, renderer, markup=column)
            treeview_column.set_resizable(True)
            treeview_files_widget.append_column( treeview_column )
        treeview_files_widget.set_model(treeview_files_model)
        treeview_files_widget.set_property('rules-hint', True)
        treeview_files_model.append(
            None,
            [('please select a revision to view... (on the left)'),('')] )
        treeview_files_widget.get_selection().set_mode(
            Gtk.SelectionMode.MULTIPLE)
        treeview_files_widget.connect("button_press_event",
                                      self.fileview_mouse_notify)

        # task list
        running_tasks_widget = get('running_tasks')
        util.add_icon_column(running_tasks_widget)
        util.add_markup_column(running_tasks_widget, 1)
        util.add_markup_column(running_tasks_widget, 3)
        running_tasks_widget.set_model(Gtk.ListStore(
            GdkPixbuf.Pixbuf, str, GObject.TYPE_PYOBJECT, str ))
        running_tasks_widget.set_headers_visible(False)
        running_tasks_widget.set_property('rules-hint', True)
        # status bar time update
        self.status_bar_timer = GLib.timeout_add(3000, self.update_task_times)
        self.main_window.show()
        prune_gui.offer_resume(self)
