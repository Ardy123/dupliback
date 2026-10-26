from gi.repository import Gtk, GdkPixbuf

import backup
import manage_backup_gui
import util
import password_managment
import logging


class GUI(object):

	def close(self, a=None, b=None):
		util.unregister_device_added_removed_callback(self.refresh_device_list, self.refresh_device_list)
		self.main_window.close()
		self.unregister_gui(self)

	def init_passwordSet(self,a=None,b=None,c=None):
		passMgntGui = password_managment.GUI(self.register_gui, self.unregister_gui)
		self.register_gui( passMgntGui )
		passMgntGui.newPasswordDialog_show( self.main_window, self.init_backup )

	def init_backup(self,password):
		model, entry = self.gtkbuilder.get_object('treeview_backups').get_selection().get_selected()
		if not entry:
			util.message_dialog(Gtk.MessageType.WARNING, Gtk.ButtonsType.CLOSE, 'No Drive Selected', 'You must select a drive from the list...')
			return
		chooserWidget = self.gtkbuilder.get_object('filechooserbutton')
		uuid = model.get_value(entry, 3)
		host = backup.get_hostname()
		path = chooserWidget.get_preview_uri()
		# strang hack to work around bug with get_filename where it does not always return the correct value
		if path is None:
			path = chooserWidget.get_filename()
		else:
			path = path[7:]
		logging.debug('opening... drive:%s host:%s path:%s', uuid, host, path)
		if not backup.init_backup(uuid, host, path, password):
			return
		self.register_gui( manage_backup_gui.GUI(self.register_gui, self.unregister_gui, uuid, host, path, password) )
		self.close()

	def refresh_device_list(self):
		treeview_backups_model = self.gtkbuilder.get_object('treeview_backups').get_model()
		treeview_backups_model.clear()
		writable_devices = backup.get_writable_devices()
		for uuid in writable_devices:
			path = backup.get_mount_point_for_uuid(uuid)
			icon = util.device_icon(self.main_window, backup.get_device_type(uuid))
			free_space = util.humanize_bytes(backup.get_free_space(uuid))
			s = "<b>Drive:</b> %s\n<b>Mount Point:</b> %s\n<b>Free Space:</b> %s" % (util.pango_escape(uuid), util.pango_escape(path), util.pango_escape(free_space))
			treeview_backups_model.append( (icon, s, backup.is_dev_present(uuid), uuid) )
		if not writable_devices:
			icon = self.main_window.render_icon(Gtk.STOCK_INFO, Gtk.IconSize.DIALOG)
			s = 'In order to create a backup, dupli.back needs a hard drive\nother than the one your computer boots from.\n(preferably external and removable)	Please plug one\ninto a free USB or eSATA port...'
			treeview_backups_model.append( (icon, s, False, None) )
		self.gtkbuilder.get_object('button_new').set_sensitive(bool(writable_devices))

	def __init__(self, register_gui, unregister_gui):
		logging.debug(util.RUN_FROM_DIR)
		self.register_gui = register_gui
		self.unregister_gui = unregister_gui
		self.gtkbuilder = util.load_glade('create_backup.glade')
		self.main_window = self.gtkbuilder.get_object('window')
		self.main_window.connect("delete-event", self.close )
		util.setup_window(self.main_window, 'Create Backup')

		# buttons
		self.gtkbuilder.get_object('button_cancel').connect('clicked', self.close)
		self.gtkbuilder.get_object('button_new').connect('clicked', self.init_passwordSet)

		# setup list
		treeview_backups_widget = self.gtkbuilder.get_object('treeview_backups')
		util.add_icon_column(treeview_backups_widget)
		util.add_markup_column(treeview_backups_widget, 1, pad=16)
		treeview_backups_widget.set_headers_visible(False)
		treeview_backups_widget.set_model(Gtk.ListStore( GdkPixbuf.Pixbuf, str, bool, str ))
		util.register_device_added_removed_callback(self.refresh_device_list, self.refresh_device_list)
		self.refresh_device_list()

		self.main_window.show()
