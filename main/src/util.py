from __future__ import division
import datetime, os, sys, threading, time


RUN_FROM_DIR = os.path.abspath(os.path.dirname(sys.argv[0]))

def system_escape(string):
    message = "\ ".join(string.split(" "))    
    return message

def pango_escape(message):
    assert isinstance(message, basestring)
    message = "&amp;".join(message.split("&"))
    message = "&lt;".join(message.split("<"))
    message = "&gt;".join(message.split(">"))
    return message


def open_file(fn):
    import os
    os.system( 'xdg-open "%s"' % fn )
  
  
def humanize_bytes(bytes):
  if bytes < 0:
    return 'unknown'
  if bytes < 1024:
    return '%dB' % bytes
  if bytes < 1024*1024:
    return '%.1fKB' % (bytes/1024)
  if bytes < 1024*1024*1024:
    return '%.1fMB' % (bytes/1024/1024)
  if bytes < 1024*1024*1024*1024:
    return '%.1fGB' % (bytes/1024/1024/1024)
  return '%.1fTB' % (bytes/1024/1024/1024/1024)


def humanize_time(td):
  seconds = int(td.seconds)
  if seconds < 60:
    return '%is' % seconds
  if seconds < 60*60:
    return '%im %is' % (seconds//60, seconds%60)
  if seconds < 60*60*24:
    return '%ih %.1fm' % (seconds//60//60, seconds/60)
  return '%id %.1fh' % (seconds//60//60//24, seconds/60/60)
  

class DeviceMonitorThread(threading.Thread):
  def run(self):
    import gtk
    print 'starting dbus-monitor...'
    self.add_callbacks = []
    self.remove_callbacks = []
    f = os.popen('dbus-monitor --system "interface=org.freedesktop.Hal.Manager"')
    while True:
      line = f.readline()
      #print line
      if 'member=DeviceRemoved' in line:
        time.sleep(.5)
        print 'device removed'
        for callback in self.remove_callbacks:
          gtk.gdk.threads_enter()
          callback()
          gtk.gdk.threads_leave()
      if 'member=DeviceAdded' in line:
        time.sleep(.5)
        print 'device added'
        for callback in self.add_callbacks:
          gtk.gdk.threads_enter()
          callback()
          gtk.gdk.threads_leave()
        
        
device_monitor_thread = DeviceMonitorThread()
device_monitor_thread.daemon = True

def register_device_added_removed_callback(callback):
  if not device_monitor_thread.is_alive():
    device_monitor_thread.start()
    time.sleep(.5)
  device_monitor_thread.add_callbacks.append(callback)
  device_monitor_thread.remove_callbacks.append(callback)


def SDBMHash32(key):
    hash = 0
    for i in range(len(key)):
        hash = ord(key[i]) + (hash << 6) + (hash << 16) - hash;
    return hash & 0xFFFFFFFF

