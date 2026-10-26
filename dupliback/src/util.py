import os
import subprocess
import logging
import dbus
import gi
from dbus.mainloop.glib import DBusGMainLoop

gi.require_version('Gtk', '3.0')

# glade/ and images/ live next to the modules, both in src/ and once installed
RUN_FROM_DIR = os.path.abspath(os.path.dirname(__file__))

def pango_escape(message):
    assert isinstance(message, str)
    message = "&amp;".join(message.split("&"))
    message = "&lt;".join(message.split("<"))
    message = "&gt;".join(message.split(">"))
    return message


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
    # dbus signals are delivered through the default glib main loop that Gtk.main()
    # runs, so callbacks run on the gtk thread. Running a second main loop on its own
    # thread made that thread dispatch gtk callbacks too, which crashed gtk.
    def __init__(self):
        self.device_add_callback = []
        self.device_rem_callback = []
        self.started = False

    def addCallback(self, device_add_callback, device_remove_callback):
        self.device_add_callback.append(device_add_callback)
        self.device_rem_callback.append(device_remove_callback)

    def remCallback(self, device_add_callback, device_remove_callback):
        # windows may be closed more than once, so ignore callbacks that are already gone
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
            logging.warning('no system bus, drive changes will not be detected: %s', e)
            return
        system_bus.add_signal_receiver(self.dbus_object_add, 'InterfacesAdded', 'org.freedesktop.DBus.ObjectManager')
        system_bus.add_signal_receiver(self.dbus_object_rem, 'InterfacesRemoved', 'org.freedesktop.DBus.ObjectManager')
        self.started = True

device_monitor = DeviceMonitor()

def register_device_added_removed_callback(add_callback, rem_callback):
    device_monitor.addCallback(add_callback, rem_callback)
    device_monitor.start()

def unregister_device_added_removed_callback(add_callback, rem_callback):
    device_monitor.remCallback(add_callback, rem_callback)
