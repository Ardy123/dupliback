import os
import sys
import threading
import logging
import time
import dbus
import gi
from gi.repository import GObject
from dbus.mainloop.glib import DBusGMainLoop

gi.require_version('Gtk', '3.0')

RUN_FROM_DIR = os.path.abspath(os.path.dirname(sys.argv[0]))

def system_escape(string):
    message = "\ ".join(string.split(" "))    
    return message

def pango_escape(message):
    assert isinstance(message, str)
    message = "&amp;".join(message.split("&"))
    message = "&lt;".join(message.split("<"))
    message = "&gt;".join(message.split(">"))
    return message


def open_file(fn):
    os.system( 'xdg-open "%s"' % fn )
  
  
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
    seconds = int(td.seconds)
    if seconds < 60:
        return '%is' % seconds
    elif seconds < 60*60:
        return '%im %is' % (seconds//60, seconds%60)
    elif seconds < 60*60*24:
        return '%ih %.1fm' % (seconds//60//60, seconds/60)
    return '%id %.1fh' % (seconds//60//60//24, seconds/60/60)
  

class DeviceMonitor(threading.Thread):
    def __init__(self):
        super().__init__()
        DBusGMainLoop(set_as_default=True)
        self.device_add_callback = []
        self.device_rem_callback = []
        self.daemon = True

    def addCallback(self, device_add_callback, device_remove_callback):
        self.device_add_callback.append(device_add_callback)
        self.device_rem_callback.append(device_remove_callback)

    def dbus_object_add(self, *args):
        logging.info('dbus-monitor: device added')
        for callback in self.device_add_callback:
            callback()

    def dbus_object_rem(self, *args):
        logging.info('dbus-monitor: device removed')
        for callback in self.device_rem_callback:
            callback()

    def run(self):
        logging.info('starting dbus-monitor...')
        time.sleep(1)     # wait for x session connection to be established
        system_bus = dbus.SystemBus()
        system_bus.add_signal_receiver(self.dbus_object_add, 'InterfacesAdded', 'org.freedesktop.DBus.ObjectManager')
        system_bus.add_signal_receiver(self.dbus_object_rem, 'InterfacesRemoved', 'org.freedesktop.DBus.ObjectManager')
        loop = GObject.MainLoop()
        loop.run()

device_monitor_thread = DeviceMonitor()

def register_device_added_removed_callback(add_callback, rem_callback):
    device_monitor_thread.addCallback(add_callback, rem_callback)
    if not device_monitor_thread.is_alive():
        device_monitor_thread.start()
