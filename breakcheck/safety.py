"""Persistent, opt-in folder monitoring and bounded exact-content duplicate search."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
import time
from dataclasses import dataclass
from .core import scan, inside, SKIP_DIRS

MAX_FILES = 100_000
MAX_HASH_BYTES = 4 * 1024**3


def state_path():
    base = Path(os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share')
    return base / 'BreakCheck' / 'safety.sqlite3'


def encode_device(value):
    # Prefix prevents SQLite INTEGER affinity from coercing large numeric text
    # to an imprecise REAL in databases created by v0.4.0.
    return f'd:{value}'


def decode_device(value):
    if isinstance(value, str) and value.startswith('d:'):
        return int(value[2:])
    return int(value)  # Existing snapshots stored signed-64-bit integers.


def stamp(info):
    return info.st_size, info.st_mtime_ns, info.st_dev, info.st_ino, info.st_nlink


def inventory(root, excluded=None, max_files=MAX_FILES):
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Choose a folder to monitor.')
    rows = {}
    def fail(error):
        raise OSError(f'Incomplete inventory: {error}')
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=fail):
        folder = Path(directory)
        for name in dirs[:]:
            p = folder / name
            info = p.lstat()
            if (name in SKIP_DIRS or p == excluded or stat.S_ISLNK(info.st_mode)
                    or getattr(info, 'st_file_attributes', 0) & 0x400):
                dirs.remove(name)
        for name in files:
            path = folder / name
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                continue
            if len(rows) >= max_files:
                raise ValueError('File limit reached; choose a smaller folder. Previous snapshot preserved.')
            rows[path.relative_to(root).as_posix()] = stamp(info)
    return rows


@dataclass
class Snapshot:
    files: int
    bytes: int
    history: list
    alerts: list
    warnings: list


class SafetyIndex:
    def __init__(self, db=None):
        self.db = Path(db) if db is not None else state_path()

    def refresh(self, root):
        root = Path(root).resolve(strict=True)
        db_dir = self.db.resolve().parent
        if inside(root, db_dir) or inside(db_dir, root):
            raise ValueError('Choose a project folder that does not contain the BreakCheck data directory.')
        started = time.time_ns()
        current = inventory(root)
        index = scan(root, MAX_FILES)
        if any('File limit reached' in w for w in index.warnings):
            raise ValueError('Dependency scan incomplete; choose a smaller folder.')
        # Recheck metadata before committing: do not infer removals from an unstable walk.
        if inventory(root) != current:
            raise RuntimeError('Folder changed during scan; retry to obtain a consistent snapshot.')
        refs = {(r.source.relative_to(root).as_posix(), r.target.relative_to(root).as_posix())
                for r in index.references if r.source.relative_to(root).as_posix() in current}
        self.db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db, timeout=10)
        try:
            conn.executescript('''CREATE TABLE IF NOT EXISTS roots (root TEXT PRIMARY KEY, captured INTEGER);
              CREATE TABLE IF NOT EXISTS files (root TEXT, path TEXT, size INTEGER, mtime INTEGER, dev TEXT, ino TEXT, links INTEGER, PRIMARY KEY(root,path));
              CREATE TABLE IF NOT EXISTS refs (root TEXT, source TEXT, target TEXT, PRIMARY KEY(root,source,target));
              CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY, root TEXT, time INTEGER, action TEXT, path TEXT, detail TEXT);''')
            key = str(root)
            conn.execute('BEGIN IMMEDIATE')
            last = conn.execute('SELECT captured FROM roots WHERE root=?', (key,)).fetchone()
            if last and last[0] >= started:
                raise RuntimeError('A newer snapshot already exists; refresh again.')
            old = {p: (s, m, decode_device(d), int(i), n) for p,s,m,d,i,n in conn.execute('SELECT path,size,mtime,dev,ino,links FROM files WHERE root=?', (key,))}
            old_refs = set(conn.execute('SELECT source,target FROM refs WHERE root=?', (key,)))
            # Retain a previously observed link only while its source has not changed
            # and its target is genuinely missing. Edited sources must be re-parsed.
            alerts = []
            for source,target in sorted(old_refs - refs):
                if source in current and current[source] == old.get(source) and not os.path.lexists(root / target):
                    refs.add((source,target))
                    alerts.append((source,target))
            events = []
            if last:
                removed, added = set(old)-set(current), set(current)-set(old)
                before, after = defaultdict(list), defaultdict(list)
                for p in removed:
                    if old[p][3] and old[p][4] == 1:
                        before[old[p]].append(p)
                for p in added:
                    if current[p][3] and current[p][4] == 1:
                        after[current[p]].append(p)
                for identity in before.keys() & after.keys():
                    if len(before[identity]) == len(after[identity]) == 1:
                        a,b = before[identity][0],after[identity][0]
                        events.append(('Possible move',a,b)); removed.remove(a); added.remove(b)
                events += [('Removed',p,'') for p in sorted(removed)]
                events += [('Added',p,'') for p in sorted(added)]
                events += [('Changed',p,'') for p in sorted(old.keys() & current.keys()) if old[p] != current[p]]
            now = int(time.time())
            conn.executemany('INSERT INTO history(root,time,action,path,detail) VALUES(?,?,?,?,?)', [(key,now,*e) for e in events])
            conn.execute('DELETE FROM history WHERE root=? AND id NOT IN (SELECT id FROM history WHERE root=? ORDER BY id DESC LIMIT 1000)', (key,key))
            conn.execute('DELETE FROM files WHERE root=?', (key,))
            conn.executemany('INSERT INTO files VALUES(?,?,?,?,?,?,?)', [(key,p,s,m,encode_device(d),str(i),n) for p,(s,m,d,i,n) in current.items()])
            conn.execute('DELETE FROM refs WHERE root=?', (key,))
            conn.executemany('INSERT INTO refs VALUES(?,?,?)', [(key,s,t) for s,t in sorted(refs)])
            conn.execute('INSERT OR REPLACE INTO roots VALUES(?,?)', (key,started))
            history = list(conn.execute('SELECT time,action,path,detail FROM history WHERE root=? ORDER BY id DESC LIMIT 200', (key,)))
            conn.commit()
            return Snapshot(len(current),sum(s[0] for s in current.values()),history,alerts,index.warnings)
        finally:
            conn.close()


def duplicates(root, budget=MAX_HASH_BYTES):
    """Hash size-matched regular files; exclude hard links and changed files."""
    root = Path(root).resolve(strict=True)
    rows = inventory(root)
    sizes = defaultdict(list)
    for p,s in rows.items():
        if s[0] > 0 and s[4] == 1:
            sizes[s[0]].append(p)
    groups = defaultdict(list)
    skipped = 0
    remaining = budget
    for size, paths in sorted(sizes.items()):
        if len(paths) < 2:
            continue
        for relative in sorted(paths):
            if size > remaining:
                skipped += 1
                continue
            remaining -= size
            p = root / relative
            try:
                if p.resolve(strict=True) != p or stamp(p.lstat()) != rows[relative]:
                    raise OSError('File changed')
                digest = hashlib.sha256()
                with p.open('rb') as stream:
                    if stamp(os.fstat(stream.fileno())) != rows[relative]:
                        raise OSError('File changed')
                    left = size
                    while left:
                        chunk = stream.read(min(left, 1024**2))
                        if not chunk:
                            raise OSError('File shortened')
                        digest.update(chunk); left -= len(chunk)
                    if stream.read(1) or stamp(os.fstat(stream.fileno())) != rows[relative]:
                        raise OSError('File changed')
                if stamp(p.lstat()) != rows[relative]:
                    raise OSError('File changed')
                groups[size,digest.hexdigest()].append(relative)
            except OSError:
                skipped += 1
    results = []
    for (size,digest), paths in groups.items():
        stable = []
        for p in paths:
            try:
                if stamp((root/p).lstat()) == rows[p]:
                    stable.append(p)
                else:
                    skipped += 1
            except OSError:
                skipped += 1
        if len(stable) > 1:
            results.append((size,stable))
    return sorted(results,key=lambda r: (-r[0]*(len(r[1])-1),r[1])), skipped
