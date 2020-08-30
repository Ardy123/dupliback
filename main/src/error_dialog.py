
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class ErrorDialog(Gtk.Dialog):
    def __init__(self, error_message, parent):
        Gtk.Dialog.__init__(self, title="ERROR", transient_for=parent, flags=0)
        self.add_buttons(Gtk.STOCK_OK, Gtk.ResponseType.OK)
        self.set_default_size(150, 100)
        label = Gtk.Label(label=error_message)
        box = self.get_content_area()
        box.add(label)
        self.show_all()
