import os
import subprocess
import logging
import dbus
import gi
from dbus.mainloop.glib import DBusGMainLoop

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
import settings

# glade/ and images/ live next to the modules, both in src/ and once installed
RUN_FROM_DIR = os.path.abspath(os.path.dirname(__file__))
DEVICE_ICONS = {'gvfs': Gtk.STOCK_NETWORK, 'local': Gtk.STOCK_HARDDISK}

def pango_escape(message):
    assert isinstance(message, str)
    return (message.replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;'))


def load_glade(name):
    builder = Gtk.Builder()
    builder.add_from_file(os.path.join(RUN_FROM_DIR, 'glade', name))
    return builder


def setup_window(window, title):
    # the icon and "dupli.back v<version> - <title>" shared by the main windows
    window.set_icon(window.render_icon(Gtk.STOCK_HARDDISK,
                                       Gtk.IconSize.BUTTON))
    window.set_title('%s v%s - %s' % (settings.PROGRAM_NAME,
                                      settings.PROGRAM_VERSION, title))


def add_icon_column(treeview, column=0):
    renderer = Gtk.CellRendererPixbuf()
    renderer.set_property('xpad', 4)
    renderer.set_property('ypad', 4)
    treeview.append_column(Gtk.TreeViewColumn('', renderer, pixbuf=column))


def add_markup_column(treeview, column, title='', pad=None):
    renderer = Gtk.CellRendererText()
    if pad:
        renderer.set_property('xpad', pad)
        renderer.set_property('ypad', pad)
    treeview.append_column(Gtk.TreeViewColumn(title, renderer, markup=column))


def device_icon(window, device_type):
    return window.render_icon(
        DEVICE_ICONS.get(device_type, Gtk.STOCK_DIALOG_QUESTION),
        Gtk.IconSize.DIALOG)


def message_dialog(message_type, buttons, text, secondary_markup):
    # runs a modal message dialog and returns the response
    dialog = Gtk.MessageDialog(None, Gtk.DialogFlags.DESTROY_WITH_PARENT,
                               message_type, buttons, text)
    dialog.format_secondary_markup(secondary_markup)
    response = dialog.run()
    dialog.destroy()
    return response


def open_file(fn):
    subprocess.Popen(['xdg-open', fn])
  
  
def humanize_bytes(bytes):
    if bytes < 0:
        return 'unknown'
    elif bytes < 1024:
        return '%dB' % bytes
    elif bytes < 1024*1024:
        return '%.1fKB' % (bytes/1024)
    elif bytes < 1024*1024*1024:
        return '%.1fMB' % (bytes/1024/1024)
    elif bytes < 1024*1024*1024*1024:
        return '%.1fGB' % (bytes/1024/1024/1024)
    return '%.1fTB' % (bytes/1024/1024/1024/1024)


def humanize_time(td):
    seconds = int(td.total_seconds())
    if seconds < 60:
        return '%is' % seconds
    elif seconds < 60*60:
        return '%im %is' % (seconds//60, seconds%60)
    elif seconds < 60*60*24:
        return '%ih %im' % (seconds//60//60, seconds//60%60)
    return '%id %ih' % (seconds//60//60//24, seconds//60//60%24)
  

class DeviceMonitor(object):
    # dbus signals arrive via the default glib main loop Gtk.main() runs, so
    # callbacks run on the gtk thread. a second main loop on its own thread
    # made that thread dispatch gtk callbacks too, which crashed gtk.
    def __init__(self):
        self.device_add_callback = []
        self.device_rem_callback = []
        self.started = False

    def addCallback(self, device_add_callback, device_remove_callback):
        self.device_add_callback.append(device_add_callback)
        self.device_rem_callback.append(device_remove_callback)

    def remCallback(self, device_add_callback, device_remove_callback):
        # windows may be closed more than once; ignore callbacks already gone
        if device_add_callback in self.device_add_callback:
            self.device_add_callback.remove(device_add_callback)
        if device_remove_callback in self.device_rem_callback:
            self.device_rem_callback.remove(device_remove_callback)

    def dbus_object_add(self, *args):
        logging.info('dbus-monitor: device added')
        # copy, a callback may unregister itself
        for callback in list(self.device_add_callback):
            callback()

    def dbus_object_rem(self, *args):
        logging.info('dbus-monitor: device removed')
        for callback in list(self.device_rem_callback):
            callback()

    def start(self):
        if self.started:
            return
        logging.info('starting dbus-monitor...')
        DBusGMainLoop(set_as_default=True)
        try:
            system_bus = dbus.SystemBus()
        except dbus.exceptions.DBusException as e:
            logging.warning('no system bus, drive changes will not be '
                            'detected: %s', e)
            return
        system_bus.add_signal_receiver(
            self.dbus_object_add, 'InterfacesAdded',
            'org.freedesktop.DBus.ObjectManager')
        system_bus.add_signal_receiver(
            self.dbus_object_rem, 'InterfacesRemoved',
            'org.freedesktop.DBus.ObjectManager')
        self.started = True

device_monitor = DeviceMonitor()

def register_device_added_removed_callback(add_callback, rem_callback):
    device_monitor.addCallback(add_callback, rem_callback)
    device_monitor.start()

def unregister_device_added_removed_callback(add_callback, rem_callback):
    device_monitor.remCallback(add_callback, rem_callback)
