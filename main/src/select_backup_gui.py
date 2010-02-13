import gnome, gobject, gtk, gtk.glade, os, sys, threading

import backup
import create_backup_gui
import manage_backup_gui
import password_managment
import backup_progress_gui
import settings
import util

  
def echo(*args):
    print 'echo', args

class GUI(object):

    def close(self, a=None, b=None):
        self.main_window.hide()
        self.unregister_gui(self)
        return
    
    def launchManageBackupGui(self, password=None):
        treeview_backups_widget = self.xml.get_widget('treeview_backups')
        model, entry = treeview_backups_widget.get_selection().get_selected()
        if entry and model.get_value(entry, 2):        
            uuid = model.get_value(entry, 3)
            host = model.get_value(entry, 4)
            path = model.get_value(entry, 5)
            self.register_gui( manage_backup_gui.GUI(self.register_gui, self.unregister_gui, uuid, host, path, password ) )
        return
    def passwordCancel(self):
        return 
    def launchCreateBackupGui(self, password=None):

        return
    
    def open_backup(self,a=None,b=None,c=None):
        treeview_backups_widget = self.xml.get_widget('treeview_backups')
        model, entry = treeview_backups_widget.get_selection().get_selected()
        if entry and model.get_value(entry, 2):        
            uuid = model.get_value(entry, 3)
            host = model.get_value(entry, 4)
            path = model.get_value(entry, 5)
            pswd = model.get_value(entry, 6)
            if uuid and host and path:
                print 'opening... drive:%s'%uuid, 'path:%s'%path
                # check if a password is needed
                prefs = backup.get_preferences(uuid, host, path)
                if prefs['password_protect'] == True:
                    passMgntGui = password_managment.GUI(self.register_gui, self.unregister_gui)                    
                    self.register_gui( passMgntGui )
                    passMgntGui.passwordCheckDialog_show( self.main_window, pswd, self.launchManageBackupGui, self.passwordCancel )
                else:
                    self.launchManageBackupGui()       
            else:
                print 'creating a new archive...'
                self.register_gui( create_backup_gui.GUI(self.register_gui, self.unregister_gui) )
                self.close()
        return 

    def delete_backup(self,a=None,b=None,c=None):
        treeview_backups_widget = self.xml.get_widget('treeview_backups')
        model, entry = treeview_backups_widget.get_selection().get_selected()
        if entry and model.get_value(entry, 2):
            uuid = model.get_value(entry, 3)
            host = model.get_value(entry, 4)
            path = model.get_value(entry, 5)
            if uuid and host and path:
                title = 'Delete Backup?'
                s = "Permanently delete the following backup repository?\n"
                s += "<b>Drive:</b> %s:%s\n<b>Source:</b> <i>%s</i>:%s\n" % (util.pango_escape(uuid), util.pango_escape(backup.get_mount_point_for_uuid(uuid)), util.pango_escape(host), util.pango_escape(path), )
                s += '\n<b>This action cannot be undone!</b>'
                md = gtk.MessageDialog(None, gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_WARNING, gtk.BUTTONS_YES_NO, util.pango_escape(title))
                md.format_secondary_markup(s)
                if gtk.RESPONSE_YES==md.run():
                    print 'deleting',uuid,host,path
                    gui = self
                    class T(threading.Thread):
                        def run(self):
                            backup.delete_backup(uuid, host, path)
                            gtk.gdk.threads_enter()                            
                            gui.refresh_device_list()
                            messageBox.takedownProgressBar()
                            gtk.gdk.threads_leave()
                    messageBox = backup_progress_gui.GUI(gui.register_gui, gui.unregister_gui, self.main_window, 'Retrieving Status, Please Wait' )
                    T().start()
                md.destroy()
        return

    def update_buttons(self,a=None):
        model, entry = a.get_selection().get_selected()
        available = entry and model.get_value(entry, 2)
        if available:
            self.xml.get_widget('button_open').set_sensitive(True)
            self.xml.get_widget('button_delete').set_sensitive(True)
        else:
            self.xml.get_widget('button_open').set_sensitive(False)
            self.xml.get_widget('button_delete').set_sensitive(False)
        return

    def refresh_device_list(self):
        treeview_backups_model = self.xml.get_widget('treeview_backups').get_model()
        treeview_backups_model.clear()
        known_backups = backup.get_known_backups()
        for t in known_backups:
            uuid = t['uuid']
            paths = backup.get_dev_paths_for_uuid(t['uuid'])
            drive_name = 'UUID: '+ t['uuid']
            for path in paths:
                if 'disk/by-id' in path:
                    drive_name = path[path.index('disk/by-id')+11:]
            free_space = util.humanize_bytes(backup.get_free_space(t['uuid']))
            drive_name = backup.get_mount_point_for_uuid(t['uuid']) + ' (%s free)' % free_space
            s = "<b>Drive:</b> %s\n<b>Source:</b> <i>%s</i>:%s\n" % (util.pango_escape(drive_name), util.pango_escape(t['host']), util.pango_escape(t['path']), )
            if backup.is_dev_present(t['uuid']) and backup.get_hostname()==t['host']:
                s += "<b>Status:</b> Drive is ready for backups"
            else:
                if backup.is_dev_present(t['uuid']) and backup.get_hostname()!=t['host']:
                    s += "<b>Status:</b> Backup available for export only (was created on another computer)"
                else:
                    s += "<b>Status:</b> Drive is unavailable (please attach)"
            if backup.get_device_type(uuid)=='gvfs':
                icon = self.main_window.render_icon(gtk.STOCK_NETWORK, gtk.ICON_SIZE_DIALOG)
            elif backup.get_device_type(uuid)=='local':
                icon = self.main_window.render_icon(gtk.STOCK_HARDDISK, gtk.ICON_SIZE_DIALOG)
            else:
                icon = self.main_window.render_icon(gtk.STOCK_DIALOG_QUESTION, gtk.ICON_SIZE_DIALOG)
            treeview_backups_model.append( (icon, s, backup.is_dev_present(t['uuid']), t['uuid'], t['host'], t['path'], t['password']) )
        if known_backups:
            treeview_backups_model.append( (self.main_window.render_icon(gtk.STOCK_ADD, gtk.ICON_SIZE_DIALOG), 'Double-click here to create a new backup...', True, None, None, None, None) )
        else:
            treeview_backups_model.append( (self.main_window.render_icon(gtk.STOCK_ADD, gtk.ICON_SIZE_DIALOG), 'No existing backups found.\nDouble-click here to create a new backup...', True, None, None, None, None) )

    def __init__(self, register_gui, unregister_gui):
        self.register_gui = register_gui
        self.unregister_gui = unregister_gui
        self.xml = gtk.glade.XML( os.path.join( util.RUN_FROM_DIR, 'glade', 'select_backup.glade' ) )
        self.main_window = self.xml.get_widget('select_backup_gui')
        self.main_window.connect("delete-event", self.close )
        icon = self.main_window.render_icon(gtk.STOCK_HARDDISK, gtk.ICON_SIZE_BUTTON)
        self.main_window.set_icon(icon)
        self.main_window.set_title('%s v%s - Select Backup' % (settings.PROGRAM_NAME, settings.PROGRAM_VERSION))
        # buttons
        self.xml.get_widget('button_cancel').connect('clicked', self.close)
        self.xml.get_widget('button_open').connect('clicked', self.open_backup)
        self.xml.get_widget('button_delete').connect('clicked', self.delete_backup)
        # setup list
        treeview_backups_model = gtk.ListStore( gtk.gdk.Pixbuf, str, bool, str, str, str, str )
        treeview_backups_widget = self.xml.get_widget('treeview_backups')
        renderer = gtk.CellRendererPixbuf()
        renderer.set_property('xpad', 4)
        renderer.set_property('ypad', 4)
        treeview_backups_widget.append_column( gtk.TreeViewColumn('', renderer, pixbuf=0) )
        renderer = gtk.CellRendererText()
        renderer.set_property('xpad', 16)
        renderer.set_property('ypad', 16)
        treeview_backups_widget.append_column( gtk.TreeViewColumn('', renderer, markup=1) )
        treeview_backups_widget.set_headers_visible(False)
        treeview_backups_widget.set_model(treeview_backups_model)
        treeview_backups_widget.connect( 'row-activated', self.open_backup )
        treeview_backups_widget.connect( 'cursor-changed', self.update_buttons )
        treeview_backups_widget.connect( 'move-cursor', self.update_buttons )
        util.register_device_added_removed_callback(self.refresh_device_list)
        self.refresh_device_list()
            
        self.main_window.show()
    

