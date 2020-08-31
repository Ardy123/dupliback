import os
from gi.repository import Gtk, GObject, Gdk, GLib, GdkPixbuf

import backup
import manage_backup_gui
import settings
import util
import password_managment
import logging


class GUI(object):

	def close(self, a=None, b=None):
		self.main_window.hide()
		self.unregister_gui(self)
		return
	
	def init_passwordSet(self,a=None,b=None,c=None):
		passMgntGui = password_managment.GUI(self.register_gui, self.unregister_gui)
		self.register_gui( passMgntGui )
		passMgntGui.newPasswordDialog_show( self.main_window, self.init_backup )		
		return
		
	def init_backup(self,password):
		treeview_backups_widget = self.gtkbuilder.get_object('treeview_backups')
		model, entry = treeview_backups_widget.get_selection().get_selected()
		if entry:
			chooserWidget = self.gtkbuilder.get_object('filechooserbutton')
			uuid = model.get_value(entry, 3)
			host = backup.get_hostname()			
			path = chooserWidget.get_preview_uri()
			# strang hack to work around bug with get_filename where it does not always return the correct value
			if path == None:
				path = chooserWidget.get_filename()
			else:
				path = path[7:]
			logging.debug('opening... drive:%s'%uuid, 'host:%s'%host, 'path:%s'%path)
			backup.init_backup(uuid, host, path, password)
			self.register_gui( manage_backup_gui.GUI(self.register_gui, self.unregister_gui, uuid, host, path, password) )
			self.close()
		else:
			s = 'No Drive Selected'
			md = Gtk.MessageDialog(None, Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.WARNING, Gtk.ButtonsType.CLOSE, s)
			md.format_secondary_markup('You must select a drive from the list...')
			md.run()
			md.destroy()

	def refresh_device_list(self):
		treeview_backups_model = self.gtkbuilder.get_object('treeview_backups').get_model()
		treeview_backups_model.clear()
		writable_devices = backup.get_writable_devices()
		for uuid in writable_devices:
			path = backup.get_mount_point_for_uuid(uuid)
			if backup.get_device_type(uuid)=='gvfs':
				icon = self.main_window.render_icon(Gtk.STOCK_NETWORK, Gtk.IconSize.DIALOG)
			elif backup.get_device_type(uuid)=='local':
				icon = self.main_window.render_icon(Gtk.STOCK_HARDDISK, Gtk.IconSize.DIALOG)
			else:
				icon = self.main_window.render_icon(Gtk.STOCK_DIALOG_QUESTION, Gtk.IconSize.DIALOG)
			free_space = util.humanize_bytes(backup.get_free_space(uuid))
			s = "<b>Drive:</b> %s\n<b>Mount Point:</b> %s\n<b>Free Space:</b> %s" % (util.pango_escape(uuid), util.pango_escape(path), util.pango_escape(free_space))
			treeview_backups_model.append( (icon, s, backup.is_dev_present(uuid), uuid) )
		if not writable_devices:
			icon = self.main_window.render_icon(Gtk.STOCK_INFO, Gtk.IconSize.DIALOG)
			s = 'In order to create a backup, dupli.back needs a hard drive\nother than the one your computer boots from.\n(preferably external and removable)	Please plug one\ninto a free USB or eSATA port...'
			treeview_backups_model.append( (icon, s, False, None) )
			self.gtkbuilder.get_object('button_new').set_sensitive(False)
		else:
			self.gtkbuilder.get_object('button_new').set_sensitive(True)

	def __init__(self, register_gui, unregister_gui):
		logging.debug(util.RUN_FROM_DIR)
		self.register_gui = register_gui
		self.unregister_gui = unregister_gui
		self.gtkbuilder = Gtk.Builder()
		self.gtkbuilder.add_from_file( os.path.join( util.RUN_FROM_DIR, 'glade', 'create_backup.glade' ) )
		self.main_window = self.gtkbuilder.get_object('window')
		self.main_window.connect("delete-event", self.close )
		icon = self.main_window.render_icon(Gtk.STOCK_HARDDISK, Gtk.IconSize.BUTTON)
		self.main_window.set_icon(icon)
		self.main_window.set_title('%s v%s - Create Backup' % (settings.PROGRAM_NAME, settings.PROGRAM_VERSION))
		
		# buttons
		self.gtkbuilder.get_object('button_cancel').connect('clicked', self.close)
		self.gtkbuilder.get_object('button_new').connect('clicked', self.init_passwordSet)
		
		# setup list
		treeview_backups_model = Gtk.ListStore( GdkPixbuf.Pixbuf, str, bool, str )
		treeview_backups_widget = self.gtkbuilder.get_object('treeview_backups')
		renderer = Gtk.CellRendererPixbuf()
		renderer.set_property('xpad', 4)
		renderer.set_property('ypad', 4)
		treeview_backups_widget.append_column( Gtk.TreeViewColumn('', renderer, pixbuf=0) )
		renderer = Gtk.CellRendererText()
		renderer.set_property('xpad', 16)
		renderer.set_property('ypad', 16)
		treeview_backups_widget.append_column( Gtk.TreeViewColumn('', renderer, markup=1) )
		treeview_backups_widget.set_headers_visible(False)
		treeview_backups_widget.set_model(treeview_backups_model)
		util.register_device_added_removed_callback(self.refresh_device_list)
		self.refresh_device_list()
		
		self.main_window.show()

