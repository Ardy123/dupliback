# the file tree built from duplicity's listing of a revision
import pytest

# imported first, it pins Gtk to 3.0
from manage_backup_gui import FileTreeBuilder
from gi.repository import Gtk


class ReferenceTreeBuilder(object):
    # the previous algorithm, which walked each parent's children; the new one
    # must build the same tree for well-formed listings
    def __init__(self, model):
        self.model = model
        self.currPath = [['', None]]

    def findPath(self, pathStr):
        dirSplit = pathStr.split('/')
        if dirSplit[0] != '': dirSplit.insert( 0, '' )
        del self.currPath[len(dirSplit):]
        for ndx, name in enumerate(dirSplit):
            if len(self.currPath) > ndx and self.currPath[ndx][0] != name:
                del self.currPath[ndx:]
                break
        itr = self.currPath[-1][1]
        if self.currPath[-1][0] != name:
            itr = self.model.iter_nth_child(
                itr, self.model.iter_n_children( itr ) - 1)
            self.currPath.append([name, itr])
        return itr

    def add(self, pathDateLst):
        path, _, filename = pathDateLst[0].rpartition('/')
        insert_itr = self.model.append(parent=self.findPath(path))
        self.model[insert_itr] = [filename, pathDateLst[1]]


class CountingTreeStore(Gtk.TreeStore):
    # counts the calls that walk a row's children
    def __init__(self):
        super().__init__(str, str)
        self.child_walks = 0

    def iter_nth_child(self, *args):
        self.child_walks += 1
        return super().iter_nth_child(*args)

    def iter_n_children(self, *args):
        self.child_walks += 1
        return super().iter_n_children(*args)


def listing(tree, prefix=''):
    # paths in duplicity's order, each directory just before its contents
    for name in sorted(tree):
        yield prefix + name
        if tree[name]:
            yield from listing(tree[name], prefix + name + '/')


def build(builder_class, paths, model=None):
    builder = builder_class(model if model is not None
                            else Gtk.TreeStore(str, str))
    for n, path in enumerate(paths):
        builder.add([path, 'date %d' % n])
    return builder.model


def dump(model, parent=None):
    # nested (name, date, children) tuples of the whole tree
    children = (model.iter_nth_child(parent, n)
                for n in range(model.iter_n_children(parent)))
    return [(model.get_value(child, 0), model.get_value(child, 1),
             dump(model, child))
            for child in children]


NESTED = {'my docs': {'file with spaces.txt': None,
                      'photos': {'a.jpg': None, 'b.jpg': None},
                      'z.txt': None},
          'small.bin': None, 'empty dir': {}}
DEEP = {'a': {'b': {'c': {'d': {'e': {'deep.txt': None}}, 'c.txt': None}},
              'a.txt': None},
        'top.txt': None}
WIDE = {'wide': {'dir%04d' % n: {'file.txt': None, 'sub': {'leaf': None}}
                 for n in range(300)},
        'after.txt': None}

CASES = {
    'duplicity sample': ['.', 'my docs', 'my docs/file with spaces.txt',
                         'small.bin'],
    'nested': ['.'] + list(listing(NESTED)),
    'deep then back to the root': list(listing(DEEP)),
    'wide directory': list(listing(WIDE)),
}


@pytest.mark.parametrize('paths', CASES.values(), ids=list(CASES))
def test_builds_the_same_tree_as_before(paths):
    assert dump(build(FileTreeBuilder, paths)) == dump(
        build(ReferenceTreeBuilder, paths))


def test_tree_shape():
    model = build(FileTreeBuilder, ['.', 'my docs',
                                    'my docs/file with spaces.txt',
                                    'my docs/photos', 'my docs/photos/a.jpg',
                                    'small.bin'])
    assert dump(model) == [
        ('.', 'date 0', []),
        ('my docs', 'date 1', [
            ('file with spaces.txt', 'date 2', []),
            ('photos', 'date 3', [('a.jpg', 'date 4', [])]),
        ]),
        ('small.bin', 'date 5', []),
    ]


def test_repeated_directory_names():
    # the previous algorithm put x next to a/a instead of inside it
    assert dump(build(FileTreeBuilder, ['a', 'a/a', 'a/a/x', 'a/b'])) == [
        ('a', 'date 0', [('a', 'date 1', [('x', 'date 2', [])]),
                         ('b', 'date 3', [])]),
    ]


def test_same_name_at_different_depths():
    assert dump(build(FileTreeBuilder, ['x', 'x/y', 'x/y/x', 'y'])) == [
        ('x', 'date 0', [('y', 'date 1', [('x', 'date 2', [])])]),
        ('y', 'date 3', []),
    ]


def test_directories_missing_from_the_listing_are_added():
    # the previous algorithm dropped b and c and put x at the top
    assert dump(build(FileTreeBuilder, ['b/c/x', 'b/c/y', 'b/d'])) == [
        ('b', '', [('c', '', [('x', 'date 0', []), ('y', 'date 1', [])]),
                   ('d', 'date 2', [])]),
    ]


def test_entering_directories_does_not_walk_siblings():
    paths = list(listing(WIDE))
    reference = CountingTreeStore()
    build(ReferenceTreeBuilder, paths, reference)
    model = CountingTreeStore()
    build(FileTreeBuilder, paths, model)
    # the old algorithm walked the parent's children for all 600 directories
    assert reference.child_walks >= 1200
    assert model.child_walks == 0
