import datetime
import os

import util


def test_glade_files_found_next_to_modules():
    assert os.path.isfile(os.path.join(util.RUN_FROM_DIR, 'glade',
                                       'select_backup.glade'))


def test_pango_escape():
    assert util.pango_escape('a & <b>') == 'a &amp; &lt;b&gt;'


def test_humanize_bytes():
    assert util.humanize_bytes(-1) == 'unknown'
    assert util.humanize_bytes(512) == '512B'
    assert util.humanize_bytes(1536) == '1.5KB'
    assert util.humanize_bytes(3 * 1024 ** 3) == '3.0GB'


def test_humanize_time():
    assert util.humanize_time(datetime.timedelta(seconds=42)) == '42s'
    assert util.humanize_time(datetime.timedelta(seconds=125)) == '2m 5s'
    assert util.humanize_time(datetime.timedelta(hours=3, minutes=2)) == '3h 2m'
    assert util.humanize_time(datetime.timedelta(days=2, hours=5)) == '2d 5h'


def test_device_callbacks_can_be_removed_twice():
    monitor = util.DeviceMonitor()
    callback = lambda: None
    monitor.addCallback(callback, callback)
    monitor.remCallback(callback, callback)
    monitor.remCallback(callback, callback)
    assert (monitor.device_add_callback == []
            and monitor.device_rem_callback == [])


def test_device_monitor_dispatches_to_callbacks():
    monitor = util.DeviceMonitor()
    added, removed = [], []
    monitor.addCallback(lambda: added.append(1), lambda: removed.append(1))
    monitor.dbus_object_add('/org/freedesktop/UDisks2/block_devices/sdb1', {})
    monitor.dbus_object_rem('/org/freedesktop/UDisks2/block_devices/sdb1', [])
    assert added == [1] and removed == [1]


def test_device_monitor_listens_on_the_system_bus_once(monkeypatch):
    receivers = []
    class FakeBus(object):
        def add_signal_receiver(self, handler, signal, interface):
            receivers.append(signal)
    monkeypatch.setattr(util.dbus, 'SystemBus', FakeBus)
    monitor = util.DeviceMonitor()
    monitor.start()
    monitor.start()
    assert monitor.started and receivers == ['InterfacesAdded',
                                             'InterfacesRemoved']


def test_device_monitor_without_system_bus(monkeypatch):
    def no_bus():
        raise util.dbus.exceptions.DBusException('no bus')
    monkeypatch.setattr(util.dbus, 'SystemBus', no_bus)
    monitor = util.DeviceMonitor()
    monitor.start()
    assert not monitor.started
