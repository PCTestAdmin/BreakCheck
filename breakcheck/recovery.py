"""Opt-in bounded local file versions. No automatic deletion or overwrite."""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import time

from .core import inside
from .safety import inventory, stamp, state_path

MIB = 1024 * 1024
DEFAULT_QUOTA = 256 * MIB
MAX_FILE = 16 * MIB
READ_BUDGET = 128 * MIB
MAX_VERSIONS = 20000


@dataclass
class Capture:
    saved: int = 0
    unchanged: int = 0
    skipped: int = 0
    used: int = 0
    quota: int = DEFAULT_QUOTA
    warnings: list | None = None


def safe_regular(path, expected):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400
            or stamp(info) != expected or path.resolve(strict=True) != path):
        raise OSError('File changed or is not a regular local file')


def read_stable(path, expected):
    safe_regular(path, expected)
    with path.open('rb') as stream:
        if stamp(os.fstat(stream.fileno())) != expected:
            raise OSError('File changed before read')
        data = stream.read(expected[0] + 1)
        if len(data) != expected[0] or stamp(os.fstat(stream.fileno())) != expected:
            raise OSError('File changed during read')
    safe_regular(path, expected)
    return data


class RecoveryStore:
    def __init__(self, db=None):
        self.db = Path(db) if db is not None else state_path().parent / 'recovery.sqlite3'

    def connect(self):
        self.db.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            fd = os.open(self.db, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            info = self.db.lstat()
            if not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('Recovery database must be a regular local file.')
            if os.name == 'posix' and info.st_mode & 0o077:
                raise PermissionError('Recovery database is not private; restrict its permissions to 0600.')
        else:
            os.close(fd)
        conn = sqlite3.connect(self.db, timeout=20)
        try:
            conn.execute('''CREATE TABLE IF NOT EXISTS versions (
                id INTEGER PRIMARY KEY, root TEXT NOT NULL, path TEXT NOT NULL,
                captured INTEGER NOT NULL, signature TEXT NOT NULL,
                size INTEGER NOT NULL, digest TEXT NOT NULL, data BLOB NOT NULL)''')
            conn.execute('CREATE INDEX IF NOT EXISTS versions_path ON versions(root,path,id)')
            conn.commit()
            return conn
        except BaseException:
            conn.close()
            raise

    def capture(self, root, quota=DEFAULT_QUOTA):
        root = Path(root).expanduser().resolve(strict=True)
        private = self.db.resolve().parent
        state = state_path().resolve().parent
        if (root == Path(root.anchor) or inside(root, private) or inside(private, root)
                or inside(root, state) or inside(state, root)):
            raise ValueError('Recovery requires a project folder outside application data.')
        if not 0 < quota <= 4096 * MIB:
            raise ValueError('Recovery quota must be between 1 byte and 4096 MiB.')
        rows = inventory(root)
        result = Capture(quota=quota, warnings=list(rows.warnings))
        if not rows.complete:
            result.warnings.append('Incomplete inventory: no versions captured.')
            if self.db.exists():
                with closing(self.connect()) as db:
                    result.used = db.execute('SELECT COALESCE(SUM(size),0) FROM versions').fetchone()[0]
            return result
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            count, used = db.execute('SELECT COUNT(*), COALESCE(SUM(size),0) FROM versions').fetchone()
            result.used = used
            latest = {p: (sig, digest) for p,sig,digest in db.execute(
                '''SELECT path,signature,digest FROM versions WHERE root=? AND id IN
                (SELECT MAX(id) FROM versions WHERE root=? GROUP BY path)''', (str(root),str(root)))}
            remaining = READ_BUDGET
            for relative, meta in sorted(rows.items()):
                size = meta[0]
                signature = json.dumps(meta, separators=(',', ':'))
                old = latest.get(relative)
                if old and old[0] == signature:
                    result.unchanged += 1
                    continue
                if (size > MAX_FILE or size > remaining or used + size > quota
                        or used >= quota or count >= MAX_VERSIONS):
                    result.skipped += 1
                    continue
                remaining -= size
                try:
                    data = read_stable(root / relative, meta)
                except OSError as exc:
                    result.skipped += 1
                    if len(result.warnings) < 100:
                        result.warnings.append(f'{relative}: {exc}')
                    continue
                digest = hashlib.sha256(data).hexdigest()
                if old and old[1] == digest:
                    # A metadata-only change does not create another content version.
                    result.unchanged += 1
                    db.execute('UPDATE versions SET signature=? WHERE id=(SELECT MAX(id) FROM versions WHERE root=? AND path=?)',
                               (signature,str(root),relative))
                    continue
                db.execute('INSERT INTO versions(root,path,captured,signature,size,digest,data) VALUES(?,?,?,?,?,?,?)',
                           (str(root),relative,time.time_ns(),signature,size,digest,data))
                count += 1
                used += size
                result.saved += 1
            result.used = used
            if result.skipped:
                result.warnings.append('Some files were skipped (size, read budget, quota, version limit or access). Older versions are never automatically removed.')
        return result

    def versions(self, root=None, limit=1000):
        if not 1 <= limit <= MAX_VERSIONS:
            raise ValueError('Invalid list limit.')
        if not self.db.exists():
            return []
        sql = 'SELECT id,root,path,captured,size,digest FROM versions'
        args = []
        if root is not None:
            sql += ' WHERE root=?'
            args.append(str(Path(root).expanduser().resolve()))
        sql += ' ORDER BY id DESC LIMIT ?'
        args.append(limit)
        with closing(self.connect()) as db:
            return [dict(zip(('id','root','path','captured','size','sha256'),row)) for row in db.execute(sql,args)]

    def restore(self, version, destination):
        if not self.db.exists():
            raise ValueError('No saved versions.')
        with closing(self.connect()) as db:
            row = db.execute('SELECT size,digest,data FROM versions WHERE id=?', (version,)).fetchone()
        if row is None:
            raise ValueError('Unknown version ID.')
        size, digest, data = row
        if size > MAX_FILE or len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Saved version failed integrity verification.')
        destination = Path(destination).expanduser().absolute()
        parent = destination.parent.resolve(strict=True)
        if parent != destination.parent or not parent.is_dir():
            raise ValueError('Choose an existing non-symlink destination directory.')
        if inside(destination, self.db.resolve().parent) or inside(destination, state_path().resolve().parent):
            raise ValueError('Cannot restore into application data.')
        if os.path.lexists(destination):
            raise FileExistsError('Destination exists. Choose a new filename; nothing was overwritten.')
        # Stage in the destination directory, then atomically publish without
        # replacing any file, even if a file appears after the existence check.
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(dir=parent, prefix='.breakcheck-restore-', delete=False) as stream:
                tmp = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(tmp, destination)
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
        return destination
