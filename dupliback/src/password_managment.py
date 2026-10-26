import util
import backup

NEW_PASSWORD_WIDGETS = ('password_entry_label1', 'password_entry_label2',
                        'password_entry1', 'password_entry2',
                        'password_missing', 'password_mismatch',
                        'password_checkbutton', 'ok_button')
CHECK_PASSWORD_WIDGETS = ('password_entry_question', 'password_check_ok',
                          'password_check_cancel', 'pass_err_img',
                          'pass_err_labl')

class GUI(object):
    def newPassword_passwordCheckBox(self,button, a=None, b=None ):
        window = self.new_password_window
        no_password = button.get_active()
        for name in ('password_entry_label1', 'password_entry_label2',
                     'password_entry1', 'password_entry2'):
            window[name].set_sensitive(not no_password)
        if no_password:
            window['password_entry1'].set_text('')
            window['password_entry2'].set_text('')
            window['password_missing'].hide()
            window['password_mismatch'].hide()
        else:
            window['password_missing'].show()
        window['ok_button'].set_sensitive(no_password)
    
    def newPassword_okClicked(self, button,a=None, b=None):
        password = self.new_password_window['password_entry1'].get_text()
        if password == '': password = None
        self.new_password_window['okFunc']( password )
        self.close()
    
    def newPassword_textTyped(self, editable, a=None, b=None ):
        window = self.new_password_window
        if window['password_checkbutton'].get_active():
            return
        first, second = (window['password_entry1'].get_text(),
                         window['password_entry2'].get_text())
        if first != second:
            window['password_missing'].hide()
            window['password_mismatch'].show()
            window['ok_button'].set_sensitive(False)
        elif first == '':
            window['password_missing'].show()
            window['password_mismatch'].hide()
        else:
            window['password_missing'].hide()
            window['password_mismatch'].hide()
            window['ok_button'].set_sensitive(True)
    
    def newPasswordDialog_show(self, parentWnd, okFunc):
        # set up the new password window
        self.new_password_window['okFunc'] = okFunc
        self.new_password_window['main_window'].set_transient_for( parentWnd )
        self.new_password_window['password_entry1'].set_text('')
        self.new_password_window['password_entry2'].set_text('')
        self.new_password_window['ok_button'].set_sensitive(False)            
        self.new_password_window['password_mismatch'].hide()
        self.new_password_window['main_window'].show()
    
    def passwordCheck_okClicked(self, a=None, b=None):
        # hashing is slow on purpose, so check once on ok, not per keystroke
        password = (self.check_password_window['password_entry_question']
                    .get_text())
        if not backup.check_password(password,
                                     self.check_password_window['password']):
            self.check_password_window['pass_err_img'].show()
            self.check_password_window['pass_err_labl'].show()
            self.check_password_window['password_check_ok'].set_sensitive(False)
            return
        self.check_password_window['okFunc'](password)
        self.close()
    
    def passwordCheck_cancelClicked(self, a=None, b=None):
        self.check_password_window['cancelFunc']()
        self.close()
    
    def passwordCheck_textTyped(self, a=None, b=None):
        self.check_password_window['pass_err_img'].hide()
        self.check_password_window['pass_err_labl'].hide()
        self.check_password_window['password_check_ok'].set_sensitive(
            self.check_password_window['password_entry_question'].get_text()
            != '')
    
    def passwordCheckDialog_show(self, parentWnd, correctPassHash, okFunc,
                                 cancelFunc):
        # set up the password check window
        self.check_password_window['password'] = correctPassHash
        self.check_password_window['okFunc'] = okFunc
        self.check_password_window['cancelFunc'] = cancelFunc
        self.check_password_window['main_window'].set_transient_for( parentWnd )
        self.check_password_window['password_entry_question'].set_text('')
        self.check_password_window['password_check_ok'].set_sensitive(False)
        self.check_password_window['pass_err_img'].hide()
        self.check_password_window['pass_err_labl'].hide()
        self.check_password_window['main_window'].show()

    def close(self, a=None, b=None):
        self.new_password_window['main_window'].close()
        self.check_password_window['main_window'].close()
        self.unregister_gui(self)
    
    def __init__(self, register_gui, unregister_gui):
        self.unregister_gui = unregister_gui
        self.gtkbuilder = util.load_glade('password_entry.glade')
        get = self.gtkbuilder.get_object
        # new password window
        self.new_password_window = {'main_window': get('new_password'),
                                    **{name: get(name)
                                       for name in NEW_PASSWORD_WIDGETS}}
        self.new_password_window['main_window'].connect(
            "delete-event", self.close)
        self.new_password_window['main_window'].hide()
        # hook up its signals
        self.new_password_window['ok_button'].connect(
            'clicked', self.newPassword_okClicked)
        self.new_password_window['password_entry1'].connect(
            'changed', self.newPassword_textTyped)
        self.new_password_window['password_entry2'].connect(
            'changed', self.newPassword_textTyped)
        self.new_password_window['password_checkbutton'].connect(
            'toggled', self.newPassword_passwordCheckBox)
        # password check window
        self.check_password_window = {'main_window': get('password_check'),
                                      **{name: get(name)
                                         for name in CHECK_PASSWORD_WIDGETS}}
        self.check_password_window['main_window'].connect(
            "delete-event", self.close)
        self.check_password_window['main_window'].hide()
        # hook up its signals
        self.check_password_window['password_check_ok'].connect(
            'clicked', self.passwordCheck_okClicked)
        self.check_password_window['password_check_cancel'].connect(
            'clicked', self.passwordCheck_cancelClicked)
        self.check_password_window['password_entry_question'].connect(
            'changed', self.passwordCheck_textTyped)