# the Prune screen: prune moments, or merge consecutive ones into the newest
# util first, it pins Gtk to 3.0
import util
from gi.repository import Gtk
import logging
import os
import time

import backup
import merge

# the resume dialog's responses, as set in messages.glade
FINISH, UNDO = 1, 2

PROGRESS_STEPS = ('ready', 'unpack', 'save', 'check_new', 'check_old',
                  'check_history')


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
        except Exception as e:
            logging.exception('prune or merge failed')
            return 'error', 'unexpected error: %s' % e
    return run


def _show_error(text):
    util.run_message('dialog_error', error=text)


def _task(manage, icon, name, work, after, reports=False):
    # runs work under the texts text_<name>_task and text_<name>
    manage.run_task(icon, util.text('text_%s_task' % name),
                    util.text('text_' + name), work, after=after,
                    reports=reports)


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
        util.setup_window(self.main_window, self.main_window.get_title())
        get('button_cancel').connect('clicked', self.close)
        get('button_prune').connect('clicked', lambda b: self.prune())
        get('button_merge').connect('clicked', lambda b: self.squash())
        get('toggle_picked').connect('toggled', self.toggled)
        self.model = get('liststore_moments')
        kinds = {True: util.text('text_full'),
                 False: util.text('text_incremental')}
        for moment in merge.moments(merge.get_chains(self.duplicity_dir)):
            size = sum(os.path.getsize(os.path.join(self.duplicity_dir, name))
                       for name in moment.files)
            self.model.append((False, time.ctime(moment.end),
                               kinds[moment.full], util.humanize_bytes(size),
                               moment.end))
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
            util.text('text_selected').format(picked=len(picked),
                                              total=len(ends))
            if picked else util.text('text_none_selected'))

    def prune(self):
        self.start(merge.plan_prune(self.duplicity_dir, self.picked()),
                   'pruning')

    def squash(self):
        self.start(merge.plan_squash(self.duplicity_dir, self.picked()),
                   'merging')

    def start(self, plan, doing):
        thorough = self.gtkbuilder.get_object('check_thorough').get_active()
        self.close()
        RewriteFlow(self.manage, doing).start(plan, thorough)


class RewriteFlow(object):
    # estimate, confirm, rebuild and apply a prune or squash for the manage
    # window, from the Prune screen or a moment's right-click menu
    def __init__(self, manage, doing='pruning'):
        self.manage = manage
        # 'pruning' or 'merging', naming the progress window's texts
        self.doing = doing
        self.duplicity_dir = backup.get_backupPath(manage.uuid, manage.host,
                                                   manage.path)

    def prune(self, epochs):
        try:
            plan = merge.plan_prune(self.duplicity_dir, epochs)
        except merge.MergeError as e:
            return _show_error(str(e))
        self.start(plan)

    def start(self, plan, thorough=True):
        _task(self.manage, Gtk.STOCK_FIND, 'estimating',
              _guarded(lambda: merge.estimate_rewrite(plan, self.manage.path,
                                                      thorough)),
              lambda result: self.confirm(plan, result, thorough))

    def confirm(self, plan, result, thorough):
        status, estimate = result
        if status == 'error':
            return _show_error(estimate)
        rebuilds = bool(estimate['regenerated'])
        # other users' files can only be restored with their owners by root
        as_admin = (rebuilds and bool(estimate['foreign_owned'])
                    and os.geteuid() != 0)
        show = ['label_space'] * rebuilds + ['label_admin'] * as_admin
        if Gtk.ResponseType.YES != util.run_message(
                'dialog_confirm', show,
                dropped=_describe(estimate['dropped']),
                freed=util.humanize_bytes(estimate['max_freed']),
                rebuilt=len(estimate['regenerated']),
                hours=estimate['hours'],
                needed=util.humanize_bytes(estimate['staging_needed']),
                staging=merge.staging_dir(self.duplicity_dir),
                free=util.humanize_bytes(estimate['staging_free']),
                foreign=estimate['foreign_owned']):
            return
        prepare = merge.prepare_as_admin if as_admin else merge.prepare_rewrite
        password = self.manage.password
        # read here, on the gtk thread; the worker reports the steps
        texts = {step: util.text('progress_' + step)
                 for step in PROGRESS_STEPS}
        def work(report):
            return prepare(plan, password, lambda step, **fields: report(
                texts[step].format(**fields)), thorough)
        _task(self.manage, Gtk.STOCK_FIND, self.doing, _guarded(work),
              lambda result: self.confirm_commit(plan, result), reports=True)

    def confirm_commit(self, plan, result):
        status, journal = result
        if status == 'error':
            return _show_error(journal)
        if Gtk.ResponseType.YES != util.run_message(
                'dialog_apply',
                freed=util.humanize_bytes(merge.freed_bytes(plan, journal))):
            merge.undo_rewrite(self.duplicity_dir)
            return
        self.commit(False)

    def commit(self, delete_first):
        _task(self.manage, Gtk.STOCK_DELETE, 'applying',
              lambda: self._commit(delete_first), self.committed)

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
            if Gtk.ResponseType.YES == util.run_message(
                    'dialog_delete_first', needed=util.humanize_bytes(value),
                    staging=merge.staging_dir(self.duplicity_dir)):
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
    if util.run_message('dialog_resume') == UNDO:
        work = lambda: merge.undo_rewrite(duplicity_dir)
    else:
        work = lambda: merge.resume_rewrite(duplicity_dir, manage.password)
    _task(manage, Gtk.STOCK_DELETE, 'finishing', _guarded(work),
          lambda result: (_show_error(result[1]) if result[0] == 'error'
                          else manage.update_revisions()))
