import backup
import settings
import util
import logging

class GUI(object):

    def close(self, a=None, b=None):
        self.main_window.close()
        self.unregister_gui(self)

    def save(self, a=None):
        get = self.gtkbuilder.get_object
        # one checkbutton_<key> per exclusion category
        preferences = {key: get('checkbutton_' + key).get_active()
                       for key in settings.FILEEXT_EXCLUDE_MAP}
        preferences['exclude_filesize'] = (
            get('spinbutton_exclude_filesize_value').get_value()
            if get('checkbutton_exclude_filesize').get_active() else 0)
        preferences['exclude_filters'] = (
            get('custom_exclude_filter_value').get_text()
            if get('checkbox_custom_filter_list').get_active() else '')
        backup.save_preferences(self.uuid, self.host, self.path, preferences)
        self.close()

    def __init__(self, register_gui, unregister_gui, uuid, host, path):

        self.unregister_gui = unregister_gui
        self.uuid = uuid
        self.host = host
        self.path = path
        self.gtkbuilder = util.load_glade('manage_backup_preferences.glade')
        get = self.gtkbuilder.get_object
        self.main_window = get('dialog')
        self.main_window.connect("delete-event", self.close)
        get('button_cancel').connect('clicked', self.close)
        get('button_ok').connect('clicked', self.save)
        util.setup_window(self.main_window, 'Backup Preferences')

        preferences = backup.get_preferences(self.uuid, self.host, self.path)
        logging.debug(preferences)

        for key in settings.FILEEXT_EXCLUDE_MAP:
            get('checkbutton_' + key).set_active(preferences.get(key))
        get('checkbutton_exclude_filesize').set_active(
            bool(preferences.get('exclude_filesize')))
        get('spinbutton_exclude_filesize_value').set_value(
            preferences.get('exclude_filesize'))
        has_filters = bool(preferences.get('exclude_filters'))
        get('checkbox_custom_filter_list').set_active(has_filters)
        self.set_filters_editable(has_filters)
        get('custom_exclude_filter_value').set_text(
            preferences.get('exclude_filters'))
        get('checkbox_custom_filter_list').connect(
            'clicked', lambda x: self.onClickCustomFilters())
        self.main_window.show()

    def set_filters_editable(self, editable):
        textbox = self.gtkbuilder.get_object('custom_exclude_filter_value')
        textbox.set_editable(editable)
        textbox.set_can_focus(editable)

    def onClickCustomFilters(self):
        checkbox_activated = self.gtkbuilder.get_object(
            'checkbox_custom_filter_list').get_active()
        self.set_filters_editable(checkbox_activated)
        textbox = self.gtkbuilder.get_object('custom_exclude_filter_value')
        if checkbox_activated:
            textbox.grab_focus_without_selecting()
        else:
            textbox.set_text('')
