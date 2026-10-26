# util first, it pins Gtk to 3.0
import util
from gi.repository import Gtk, GdkPixbuf

import backup
import create_backup_gui
import manage_backup_gui
import password_managment
import backup_progress_gui
import logging


class GUI(object):

    def close(self, a=None, b=None):
        util.unregister_device_added_removed_callback(
            self.refresh_device_list, self.refresh_device_list)
        self.unregister_gui(self)
        self.main_window.destroy()

    def selected_backup(self):
        # selected row's [uuid, host, path, password hash], all None for the
        # "create a new backup" row; None if no available row is selected
        model, entry = (self.gtkbuilder.get_object('treeview_backups')
                        .get_selection().get_selected())
        if entry and model.get_value(entry, 2):
            return [model.get_value(entry, column) for column in (3, 4, 5, 6)]
        return None

    def launchManageBackupGui(self, password=None):
        selected = self.selected_backup()
        if selected:
            uuid, host, path, _ = selected
            if password:
                backup.upgrade_password_hash(uuid, host, path, password)
            self.register_gui(manage_backup_gui.GUI(
                self.register_gui, self.unregister_gui, uuid, host, path,
                password))
        self.close()

    def passwordCancel(self):
        pass

    def open_backup(self,a=None,b=None,c=None):
        selected = self.selected_backup()
        if not selected:
            return
        uuid, host, path, pswd = selected
        if uuid and host and path:
            logging.info('opening... drive:%s path:%s', uuid, path)
            # check if a password is needed
            prefs = backup.get_preferences(uuid, host, path)
            if prefs['password_protect'] == True:
                passMgntGui = password_managment.GUI(self.register_gui,
                                                     self.unregister_gui)
                self.register_gui( passMgntGui )
                passMgntGui.passwordCheckDialog_show(
                    self.main_window, pswd, self.launchManageBackupGui,
                    self.passwordCancel)
            else:
                self.launchManageBackupGui()
        else:
            logging.info('creating a new archive...')
            self.register_gui(create_backup_gui.GUI(self.register_gui,
                                                    self.unregister_gui))
            self.close()

    def delete_backup(self,a=None,b=None,c=None):
        selected = self.selected_backup()
        if not selected:
            return
        uuid, host, path, _ = selected
        if not (uuid and host and path):
            return
        s = "Permanently delete the following backup repository?\n"
        s += "<b>Drive:</b> %s:%s\n<b>Source:</b> <i>%s</i>:%s\n" % (
            util.pango_escape(uuid),
            util.pango_escape(backup.get_mount_point_for_uuid(uuid)),
            util.pango_escape(host), util.pango_escape(path), )
        s += '\n<b>This action cannot be undone!</b>'
        if Gtk.ResponseType.YES == util.message_dialog(
                Gtk.MessageType.WARNING, Gtk.ButtonsType.YES_NO,
                'Delete Backup?', s):
            logging.info('deleting %s %s %s', uuid, host, path)
            backup_progress_gui.run_with_progress(
                self.register_gui, self.unregister_gui, self.main_window,
                'Deleting Backup, Please Wait',
                lambda: backup.delete_backup(uuid, host, path),
                lambda result: self.refresh_device_list())

    def update_buttons(self,a=None):
        model, entry = a.get_selection().get_selected()
        available = bool(entry and model.get_value(entry, 2))
        for name in ('button_open', 'button_delete'):
            self.gtkbuilder.get_object(name).set_sensitive(available)

    def refresh_device_list(self):
        treeview_backups_model = self.gtkbuilder.get_object(
            'treeview_backups').get_model()
        treeview_backups_model.clear()
        known_backups = backup.get_known_backups()
        hostname = backup.get_hostname()
        for t in known_backups:
            uuid = t['uuid']
            present = backup.is_dev_present(uuid)
            free_space = util.humanize_bytes(backup.get_free_space(uuid))
            drive_name = (backup.get_mount_point_for_uuid(uuid)
                          + ' (%s free)' % free_space)
            s = "<b>Drive:</b> %s\n<b>Source:</b> <i>%s</i>:%s\n" % (
                util.pango_escape(drive_name), util.pango_escape(t['host']),
                util.pango_escape(t['path']), )
            if present and hostname == t['host']:
                s += "<b>Status:</b> Drive is ready for backups"
            elif present:
                s += ("<b>Status:</b> Backup available for export only "
                      "(was created on another computer)")
            else:
                s += "<b>Status:</b> Drive is unavailable (please attach)"
            icon = util.device_icon(self.main_window,
                                    backup.get_device_type(uuid))
            treeview_backups_model.append( (icon, s, present, uuid, t['host'],
                                            t['path'], t['password']) )
        text = 'Double-click here to create a new backup...'
        if not known_backups:
            text = 'No existing backups found.\n' + text
        treeview_backups_model.append(
            (self.main_window.render_icon(Gtk.STOCK_ADD, Gtk.IconSize.DIALOG),
             text, True, None, None, None, None) )

    def __init__(self, register_gui, unregister_gui):
        self.register_gui = register_gui
        self.unregister_gui = unregister_gui
        self.gtkbuilder = util.load_glade('select_backup.glade')
        self.main_window = self.gtkbuilder.get_object('select_backup_gui')
        self.main_window.connect("delete-event", self.close)
        util.setup_window(self.main_window, 'Select Backup')
        # buttons
        self.gtkbuilder.get_object('button_cancel').connect(
            'clicked', self.close)
        self.gtkbuilder.get_object('button_open').connect(
            'clicked', self.open_backup)
        self.gtkbuilder.get_object('button_delete').connect(
            'clicked', self.delete_backup)
        # setup list
        treeview_backups_widget = self.gtkbuilder.get_object('treeview_backups')
        util.add_icon_column(treeview_backups_widget)
        util.add_markup_column(treeview_backups_widget, 1, pad=16)
        treeview_backups_widget.set_headers_visible(False)
        treeview_backups_widget.set_model(Gtk.ListStore(
            GdkPixbuf.Pixbuf, str, bool, str, str, str, str))
        treeview_backups_widget.connect( 'row-activated', self.open_backup )
        treeview_backups_widget.connect( 'cursor-changed', self.update_buttons )
        treeview_backups_widget.connect( 'move-cursor', self.update_buttons )
        util.register_device_added_removed_callback(
            self.refresh_device_list, self.refresh_device_list)
        self.refresh_device_list()

        self.main_window.show()
