# the Prune screen: prune moments, or merge consecutive ones into the newest
# util first, it pins Gtk to 3.0
import util
from gi.repository import Gtk, GObject
import os
import time

import backup
import merge

FINISH, UNDO = 1, 2


def _describe(epochs):
    return '\n'.join(' - ' + time.ctime(epoch) for epoch in epochs)


def _guarded(work):
    # a worker's result as ('ok', value) or ('error', message), so a failure
    # still reaches the gtk thread and takes the progress dialog down
    def run(*args):
        try:
            return 'ok', work(*args)
        except merge.MergeError as e:
            return 'error', str(e)
    return run


def _show_error(text):
    util.message_dialog(Gtk.MessageType.ERROR, Gtk.ButtonsType.CLOSE,
                        'Prune or merge stopped', text)


class GUI(object):

    def close(self, a=None, b=None):
        self.main_window.destroy()
        self.unregister_gui(self)

    def __init__(self, register_gui, unregister_gui, manage):
        self.unregister_gui = unregister_gui
        self.manage = manage
        self.duplicity_dir = backup.get_backupPath(manage.uuid, manage.host,
                                                   manage.path)
        self.gtkbuilder = util.load_glade('prune.glade')
        get = self.gtkbuilder.get_object
        self.main_window = get('dialog')
        self.main_window.connect('delete-event', self.close)
        self.main_window.set_transient_for(manage.main_window)
        util.setup_window(self.main_window, 'Prune or Merge Moments')
        get('button_cancel').connect('clicked', self.close)
        get('button_prune').connect('clicked', lambda b: self.prune())
        get('button_merge').connect('clicked', lambda b: self.squash())
        # picked, date, type, size, end epoch
        self.model = Gtk.ListStore(bool, str, str, str, GObject.TYPE_INT64)
        treeview = get('treeview_moments')
        toggle = Gtk.CellRendererToggle()
        toggle.connect('toggled', self.toggled)
        treeview.append_column(Gtk.TreeViewColumn('', toggle, active=0))
        for column, title in ((1, 'Moment'), (2, 'Type'), (3, 'Size')):
            util.add_markup_column(treeview, column, title)
        treeview.set_model(self.model)
        for moment in merge.moments(merge.get_chains(self.duplicity_dir)):
            size = sum(os.path.getsize(os.path.join(self.duplicity_dir, name))
                       for name in moment.files)
            self.model.append((
                False, util.pango_escape(time.ctime(moment.end)),
                'full' if moment.full else 'incremental',
                util.humanize_bytes(size), moment.end))
        self.update()
        self.main_window.show()

    def picked(self):
        return [row[4] for row in self.model if row[0]]

    def toggled(self, renderer, path):
        self.model[path][0] = not self.model[path][0]
        self.update()

    def update(self):
        get = self.gtkbuilder.get_object
        picked = self.picked()
        ends = [row[4] for row in self.model]
        indexes = [ends.index(end) for end in picked]
        consecutive = indexes == list(range(indexes[0], indexes[-1] + 1)
                                      ) if indexes else False
        get('button_prune').set_sensitive(0 < len(picked) < len(ends))
        get('button_merge').set_sensitive(len(picked) >= 2 and consecutive)
        get('label_summary').set_text(
            '%d of %d moments selected.' % (len(picked), len(ends))
            if picked else 'No moments selected.')

    def prune(self):
        self.start(merge.plan_prune(self.duplicity_dir, self.picked()))

    def squash(self):
        self.start(merge.plan_squash(self.duplicity_dir, self.picked()))

    def start(self, plan):
        thorough = self.gtkbuilder.get_object('check_thorough').get_active()
        self.close()
        RewriteFlow(self.manage).start(plan, thorough)

class RewriteFlow(object):
    # estimate, confirm, rebuild and apply a prune or squash for the manage
    # window, from the Prune screen or a moment's right-click menu
    def __init__(self, manage):
        self.manage = manage
        self.duplicity_dir = backup.get_backupPath(manage.uuid, manage.host,
                                                   manage.path)

    def prune(self, epochs):
        try:
            plan = merge.plan_prune(self.duplicity_dir, epochs)
        except merge.MergeError as e:
            return _show_error(str(e))
        self.start(plan)

    def start(self, plan, thorough=True):
        self.manage.run_task(
            Gtk.STOCK_FIND, 'estimating the space freed',
            'Estimating, Please Wait',
            _guarded(lambda: merge.estimate_rewrite(plan, self.manage.path,
                                                    thorough)),
            after=lambda result: self.confirm(plan, result, thorough))

    def confirm(self, plan, result, thorough):
        status, estimate = result
        if status == 'error':
            return _show_error(estimate)
        if estimate['foreign_owned']:
            return _show_error(
                '%d files in %s belong to another user. Rebuilding moments '
                'restores them without root, which would lose their '
                'permissions, so this backup cannot be changed.'
                % (estimate['foreign_owned'], self.manage.path))
        if estimate['staging_needed'] > estimate['staging_free']:
            return _show_error(
                'Rebuilding needs about %s free in %s; only %s is free.' % (
                    util.humanize_bytes(estimate['staging_needed']),
                    merge.staging_dir(self.duplicity_dir),
                    util.humanize_bytes(estimate['staging_free'])))
        text = ('These moments will no longer be restorable:\n%s\n\n'
                'Up to %s can be freed. %d moment(s) will be rebuilt and '
                'checked, which takes about %.1f hours and %s of temporary '
                'space. The backup stays unchanged until you confirm again.'
                % (util.pango_escape(_describe(estimate['dropped'])),
                   util.humanize_bytes(estimate['max_freed']),
                   len(estimate['regenerated']), estimate['hours'],
                   util.humanize_bytes(estimate['staging_needed'])))
        if Gtk.ResponseType.YES != util.message_dialog(
                Gtk.MessageType.WARNING, Gtk.ButtonsType.YES_NO,
                'Prune or merge moments?', text):
            return
        self.manage.run_task(
            Gtk.STOCK_FIND, 'rebuilding moments', 'Rebuilding, Please Wait',
            _guarded(lambda report: merge.prepare_rewrite(
                plan, self.manage.password, report, thorough)),
            after=lambda result: self.confirm_commit(plan, result),
            reports=True)

    def confirm_commit(self, plan, result):
        status, journal = result
        if status == 'error':
            return _show_error(journal)
        text = ('The rewritten moments are rebuilt and checked. Applying them '
                'frees %s on the drive.'
                % util.humanize_bytes(merge.freed_bytes(plan, journal)))
        if Gtk.ResponseType.YES != util.message_dialog(
                Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO,
                'Apply the changes?', text):
            merge.undo_rewrite(self.duplicity_dir)
            return
        self.commit(False)

    def commit(self, delete_first):
        self.manage.run_task(
            Gtk.STOCK_DELETE, 'applying the changes', 'Applying, Please Wait',
            lambda: self._commit(delete_first), after=self.committed)

    def _commit(self, delete_first):
        try:
            merge.commit_rewrite(self.duplicity_dir, self.manage.password,
                                 delete_first)
            return 'ok', None
        except merge.NotEnoughSpace as e:
            return 'space', e.needed
        except merge.MergeError as e:
            return 'error', str(e)

    def committed(self, result):
        status, value = result
        if status == 'space':
            text = ('The drive does not have room for the rebuilt moments '
                    '(%s) next to the old ones. They can be applied by '
                    'deleting the old moments first; until that finishes the '
                    'only copy of the changed moments is in %s.'
                    % (util.humanize_bytes(value),
                       merge.staging_dir(self.duplicity_dir)))
            if Gtk.ResponseType.YES == util.message_dialog(
                    Gtk.MessageType.WARNING, Gtk.ButtonsType.YES_NO,
                    'Remove the old moments first?', text):
                return self.commit(True)
            merge.undo_rewrite(self.duplicity_dir)
            return
        if status == 'error':
            return _show_error(value)
        self.manage.update_revisions()


def offer_resume(manage):
    # after an interrupted rewrite: one still being prepared never touched the
    # drive and is dropped; one being applied is finished or undone
    duplicity_dir = backup.get_backupPath(manage.uuid, manage.host, manage.path)
    journal = merge.get_journal(duplicity_dir)
    if not journal:
        return
    if journal['phase'] != 'commit':
        merge.undo_rewrite(duplicity_dir)
        return
    dialog = Gtk.MessageDialog(None, Gtk.DialogFlags.DESTROY_WITH_PARENT,
                               Gtk.MessageType.WARNING, Gtk.ButtonsType.NONE,
                               'Deleting or merging moments was interrupted')
    dialog.format_secondary_text(
        'The backup was being changed when dupli.back stopped. Finish the '
        'change, or undo it to put the backup back as it was.')
    dialog.add_buttons('Undo', UNDO, 'Finish', FINISH)
    response = dialog.run()
    dialog.destroy()
    if response == UNDO:
        work = lambda: merge.undo_rewrite(duplicity_dir)
    else:
        work = lambda: merge.resume_rewrite(duplicity_dir, manage.password)
    manage.run_task(Gtk.STOCK_DELETE, 'finishing an interrupted change',
                    'Finishing, Please Wait', _guarded(work),
                    after=lambda result: (
                        _show_error(result[1]) if result[0] == 'error'
                        else manage.update_revisions()))
