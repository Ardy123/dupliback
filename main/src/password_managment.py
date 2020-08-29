import os
from gi.repository import Gtk
import util
import backup

class GUI(object):
    def newPassword_passwordCheckBox(self,button, a=None, b=None ):
        if button.get_active():
            self.new_password_window['password_entry_label1'].set_sensitive(False)
            self.new_password_window['password_entry_label2'].set_sensitive(False)
            self.new_password_window['password_entry1'].set_sensitive(False)
            self.new_password_window['password_entry1'].set_text('')
            self.new_password_window['password_entry2'].set_sensitive(False)
            self.new_password_window['password_entry2'].set_text('')
            self.new_password_window['password_missing'].hide()
            self.new_password_window['password_mismatch'].hide()
            self.new_password_window['ok_button'].set_sensitive(True)
        else:
            self.new_password_window['password_entry_label1'].set_sensitive(True)
            self.new_password_window['password_entry_label2'].set_sensitive(True)
            self.new_password_window['password_entry1'].set_sensitive(True)
            self.new_password_window['password_entry2'].set_sensitive(True)            
            self.new_password_window['password_missing'].show()
            self.new_password_window['ok_button'].set_sensitive(False)                                
        return
    
    def newPassword_okClicked(self, button,a=None, b=None):
        password = self.new_password_window['password_entry1'].get_text()
        if password == '':
            password = None
        self.new_password_window['main_window'].hide()
        self.new_password_window['okFunc']( password )
        return
    
    def newPassword_textTyped(self, editable, a=None, b=None ):
        if not self.new_password_window['password_checkbutton'].get_active():
            if self.new_password_window['password_entry1'].get_text() != self.new_password_window['password_entry2'].get_text():
                self.new_password_window['password_missing'].hide()
                self.new_password_window['password_mismatch'].show()
                self.new_password_window['ok_button'].set_sensitive(False)
            elif self.new_password_window['password_entry1'].get_text() == '':
                self.new_password_window['password_missing'].show()
                self.new_password_window['password_mismatch'].hide()
            else:
                self.new_password_window['password_missing'].hide()
                self.new_password_window['password_mismatch'].hide()
                self.new_password_window['ok_button'].set_sensitive(True)        
        return
    
    def newPasswordDialog_show(self, parentWnd, okFunc):
        # Setup NewPassword window
        self.new_password_window['okFunc'] = okFunc
        self.new_password_window['main_window'].set_transient_for( parentWnd )
        self.new_password_window['password_entry1'].set_text('')
        self.new_password_window['password_entry2'].set_text('')
        self.new_password_window['ok_button'].set_sensitive(False)            
        self.new_password_window['password_mismatch'].hide()
        self.new_password_window['main_window'].show()
        return
    
    def passwordCheck_okClicked(self, a=None, b=None):
        self.check_password_window['main_window'].hide()
        self.check_password_window['okFunc']( self.check_password_window['password_entry_question'].get_text() )
        return
    
    def passwordCheck_cancelClicked(self, a=None, b=None):
        self.check_password_window['main_window'].hide()
        self.check_password_window['cancelFunc']()
        return
    
    def passwordCheck_textTyped(self, a=None, b=None):
        hashPswd = backup.gen_passwordEncrypt( self.check_password_window['password_entry_question'].get_text().encode('utf-8') )
        if hashPswd == self.check_password_window['password']:
            self.check_password_window['pass_err_img'].hide()
            self.check_password_window['pass_err_labl'].hide()
            self.check_password_window['password_check_ok'].set_sensitive(True)
        else:
            self.check_password_window['pass_err_img'].show()
            self.check_password_window['pass_err_labl'].show()
            self.check_password_window['password_check_ok'].set_sensitive(False)
        return
    
    def passwordCheckDialog_show(self, parentWnd, correctPassHash, okFunc, cancelFunc):
        # Setup password entry window
        self.check_password_window['password'] = correctPassHash
        self.check_password_window['okFunc'] = okFunc
        self.check_password_window['cancelFunc'] = cancelFunc
        self.check_password_window['main_window'].set_transient_for( parentWnd )
        self.check_password_window['password_entry_question'].set_text('')
        self.check_password_window['password_check_ok'].set_sensitive(False)
        self.check_password_window['main_window'].show()
        return
    
    def __init__(self, register_gui, unregister_gui):
        self.register_gui = register_gui
        self.unregister_gui = unregister_gui
        self.gtkbuilder = Gtk.Builder()
        self.gtkbuilder.add_from_file( os.path.join( util.RUN_FROM_DIR, 'glade', 'password_entry.glade' ) )
        # Setup New Password Window
        self.new_password_window = {}
        self.new_password_window['main_window'] = self.gtkbuilder.get_object('new_password')
        self.new_password_window['password_entry_label1'] = self.gtkbuilder.get_object('password_entry_label1')
        self.new_password_window['password_entry_label2'] = self.gtkbuilder.get_object('password_entry_label2')
        self.new_password_window['password_entry1'] = self.gtkbuilder.get_object('password_entry1')
        self.new_password_window['password_entry2'] = self.gtkbuilder.get_object('password_entry2')
        self.new_password_window['password_missing'] = self.gtkbuilder.get_object('password_missing')
        self.new_password_window['password_mismatch'] = self.gtkbuilder.get_object('password_mismatch')
        self.new_password_window['password_checkbutton'] = self.gtkbuilder.get_object('password_checkbutton')
        self.new_password_window['ok_button'] = self.gtkbuilder.get_object('ok_button')
        self.new_password_window['main_window'].hide()
        #hook up signals for New Password Window
        self.new_password_window['ok_button'].connect('clicked', self.newPassword_okClicked)
        self.new_password_window['password_entry1'].connect('changed', self.newPassword_textTyped)
        self.new_password_window['password_entry2'].connect('changed', self.newPassword_textTyped)   
        self.new_password_window['password_checkbutton'].connect('toggled', self.newPassword_passwordCheckBox)
        # Setup Password Check Window 
        self.check_password_window = {}
        self.check_password_window['main_window'] = self.gtkbuilder.get_object('password_check')
        self.check_password_window['password_entry_question'] = self.gtkbuilder.get_object('password_entry_question')
        self.check_password_window['password_check_ok'] = self.gtkbuilder.get_object('password_check_ok')
        self.check_password_window['password_check_cancel'] = self.gtkbuilder.get_object('password_check_cancel')
        self.check_password_window['pass_err_img'] = self.gtkbuilder.get_object('pass_err_img')
        self.check_password_window['pass_err_labl'] = self.gtkbuilder.get_object('pass_err_labl')
        self.check_password_window['main_window'].hide()
        #hook up signals for check Password Window
        self.check_password_window['password_check_ok'].connect('clicked', self.passwordCheck_okClicked)
        self.check_password_window['password_check_cancel'].connect('clicked', self.passwordCheck_cancelClicked)
        self.check_password_window['password_entry_question'].connect('changed', self.passwordCheck_textTyped)
        return