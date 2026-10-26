# Fast reader for duplicity's signature files, listing the files of a moment
# without duplicity's per-entry overhead. Reads the cache's .sigtar.gz copies
# or the backup's own .sigtar.gz / .sigtar.gpg files. No Gtk imports: worker
# processes run this file as a script.
import os
import subprocess
import sys
import tempfile
import zlib

BLOCK = 512
GZIP_MAGIC = b'\x1f\x8b'
# passphrase for .gpg files, passed to workers in the environment, not argv
PASSPHRASE_ENV = 'DUPLIBACK_PASSPHRASE'
KINDS = {b'signature': b's', b'snapshot': b's', b'deleted': b'd'}


class FormatError(Exception):
    pass


def _number(field):
    # tar numbers are octal text, or base-256 when the high bit is set
    if field[0] & 0x80:
        return int.from_bytes(field, 'big') & ~(0x80 << (8 * len(field) - 8))
    text = bytes(field).strip(b'\0 ')
    return int(text, 8) if text else 0


def _pax_records(data):
    # the 'length key=value\n' records of a pax extended header
    records = {}
    while data:
        length, _, rest = data.partition(b' ')
        size = int(length)
        key, _, value = rest[:size - len(length) - 2].partition(b'=')
        records[key] = value
        data = data[size:]
    return records


class _Blocks(object):
    # buffered reader over a plain or gzip'd tar stream
    def __init__(self, raw, path):
        self.raw = raw
        self.path = path
        self.pending = raw.read(len(GZIP_MAGIC))
        self.unzip = (zlib.decompressobj(16 + zlib.MAX_WBITS)
                      if self.pending == GZIP_MAGIC else None)
        self.buf = bytearray()
        self.pos = 0

    def fill(self, need):
        while len(self.buf) - self.pos < need:
            chunk = self.pending + self.raw.read(1 << 20)
            self.pending = b''
            data = chunk
            if self.unzip:
                data = (self.unzip.decompress(chunk) if chunk
                        else self.unzip.flush())
            if not chunk and not data:
                return False
            del self.buf[:self.pos]
            self.pos = 0
            self.buf += data
        return True

    def block(self):
        if not self.fill(BLOCK):
            return None
        block = bytes(self.buf[self.pos:self.pos + BLOCK])
        self.pos += BLOCK
        return block

    def take(self, size):
        # the data of an entry; entries are padded to whole blocks
        padded = (size + BLOCK - 1) & ~(BLOCK - 1)
        if not self.fill(padded):
            raise FormatError('truncated tar data in %s' % self.path)
        data = bytes(self.buf[self.pos:self.pos + size])
        self.pos += padded
        return data

    def skip(self, size):
        left = (size + BLOCK - 1) & ~(BLOCK - 1)
        while left:
            if not self.fill(1):
                raise FormatError('truncated tar data in %s' % self.path)
            step = min(left, len(self.buf) - self.pos)
            self.pos += step
            left -= step


def read_headers(raw, path=''):
    # yields (name, mtime) for every entry of the tar stream raw, skipping data
    blocks = _Blocks(raw, path)
    long_name = pax = None
    while True:
        block = blocks.block()
        if block is None or not any(block):
            break
        size = _number(block[124:136])
        typeflag = block[156:157]
        if typeflag == b'L':
            long_name = blocks.take(size).rstrip(b'\0')
        elif typeflag == b'x':
            pax = _pax_records(blocks.take(size))
        elif typeflag in (b'K', b'g'):
            # a long link target or global pax header; not needed for listing
            blocks.skip(size)
        else:
            name = block[0:100].split(b'\0', 1)[0]
            prefix = block[345:500].split(b'\0', 1)[0]
            if prefix and block[257:262] == b'ustar':
                name = prefix + b'/' + name
            mtime = _number(block[136:148])
            if pax:
                name = pax.get(b'path', name)
                mtime = int(float(pax.get(b'mtime', mtime)))
            if long_name is not None:
                name = long_name
            long_name = pax = None
            yield name, mtime
            blocks.skip(size)
    if long_name is not None or pax is not None:
        raise FormatError('header without an entry in %s' % path)


def entries(raw, path=''):
    # yields (kind, mtime, name): kind b's' for present, b'd' for deleted, and
    # name the path relative to the backup source (b'' for its root)
    for name, mtime in read_headers(raw, path):
        kind_name, _, rest = name.partition(b'/')
        kind = KINDS.get(kind_name)
        if kind is None:
            raise FormatError('unexpected entry %r in %s' % (name, path))
        yield kind, mtime, rest.rstrip(b'/')


def _open_source(path):
    # a .gpg signature file is decrypted by gpg, with the passphrase on a pipe
    if not path.endswith('.gpg'):
        return open(path, 'rb'), None
    gpg = subprocess.Popen(
        ['gpg', '--batch', '--quiet', '--no-tty', '--pinentry-mode',
         'loopback', '--passphrase-fd', '0', '--decrypt', path],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    gpg.stdin.write(os.environ.get(PASSPHRASE_ENV, '').encode() + b'\n')
    gpg.stdin.close()
    return gpg.stdout, gpg


def dump(path, out_path):
    # writes the entries of one signature file as 'kind mtime\tname\0' records
    raw, gpg = _open_source(path)
    with raw, open(out_path, 'wb') as out:
        out.writelines(b'%s%d\t%s\0' % (kind, mtime, name)
                       for kind, mtime, name in entries(raw, path))
    if gpg and gpg.wait() != 0:
        raise FormatError('gpg could not decrypt %s: %s' % (
            path, gpg.stderr.read().decode(errors='replace').strip()))


def _read_dump(out_path):
    # streams the records back in 1 MB chunks
    with open(out_path, 'rb') as dumped:
        rest = b''
        for chunk in iter(lambda: dumped.read(1 << 20), b''):
            *records, rest = (rest + chunk).split(b'\0')
            for record in records:
                head, _, name = record.partition(b'\t')
                yield head[:1], int(head[1:]), name


def replay(signature_files, passphrase=None, workers=None):
    # {name: mtime} of the files present after applying the signature files in
    # order; each file is parsed by its own worker process
    workers = workers or os.cpu_count() or 1
    env = dict(os.environ, **{PASSPHRASE_ENV: passphrase or ''})
    state = {}
    with tempfile.TemporaryDirectory(prefix='dupliback-sigtar-') as tmp:
        jobs = [(path, os.path.join(tmp, '%d' % n))
                for n, path in enumerate(signature_files)]
        running = []
        for _, out in list(jobs):
            while jobs and len(running) < workers:
                path, job_out = jobs.pop(0)
                running.append(subprocess.Popen(
                    [sys.executable, os.path.abspath(__file__), path,
                     job_out], env=env, stderr=subprocess.PIPE))
            worker = running.pop(0)
            _, error = worker.communicate()
            if worker.returncode != 0:
                for other in running:
                    other.kill()
                    other.wait()
                raise FormatError(error.decode(errors='replace').strip())
            for kind, mtime, name in _read_dump(out):
                if kind == b'd':
                    state.pop(name, None)
                else:
                    state[name] = mtime
            os.remove(out)
    return state


def listing(state):
    # (relative path, mtime) in duplicity's order: by path components, '.' first
    by_components = lambda name: name.split(b'/') if name else []
    for name in sorted(state, key=by_components):
        yield (os.fsdecode(name) if name else '.'), state[name]


if __name__ == '__main__':
    try:
        dump(sys.argv[1], sys.argv[2])
    except (FormatError, OSError, zlib.error) as e:
        sys.exit(str(e))
