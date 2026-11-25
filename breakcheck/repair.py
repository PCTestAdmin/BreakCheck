"""Conservative link repair with preview tokens and a durable undo journal."""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from difflib import unified_diff
from html.parser import HTMLParser
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
import time
from urllib.parse import quote, urlsplit

from .core import inside, local_path, MAX_BYTES, SKIP_DIRS, excluded_system_dir
from .safety import stamp, state_path, missing_target
from .recovery import read_stable

MAX_JOURNAL = 128 * 1024**2
MAX_ENTRIES = 1000


def digest(data):
    return hashlib.sha256(data).hexdigest()


def project(root):
    root = Path(root).expanduser().resolve(strict=True)
    state = state_path().resolve().parent
    if not root.is_dir() or root == Path(root.anchor) or inside(state, root) or inside(root, state):
        raise ValueError('Select a project folder outside application data.')
    return root


def scoped(root, value):
    p = Path(os.path.abspath(root / Path(value)))
    if p == root or not inside(p, root) or any(x in SKIP_DIRS for x in p.relative_to(root).parts):
        raise ValueError('All paths must stay inside the selected project.')
    if any(excluded_system_dir(parent) for parent in (p, *p.parents)):
        raise ValueError('System directories are not supported.')
    # Reject symlinks and reparse points at every existing path component.
    for part in reversed((p, *[a for a in p.parents if inside(a, root)])):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Symbolic links and reparse points are not supported.')
    return p


def read_source(path):
    info = path.lstat()
    if info.st_size > MAX_BYTES or info.st_nlink != 1 or not info.st_mode & stat.S_IWUSR:
        raise ValueError('Repair supports writable, regular, single-link text files up to 4 MiB.')
    return read_stable(path, stamp(info)), stat.S_IMODE(info.st_mode)


# Tokenize a start tag sequentially instead of matching text inside another
# attribute value. Only literal, quoted link attributes are eligible.
TAG_NAME = re.compile(r'<[A-Za-z][^\s/>]*')
ATTR = re.compile(r'''\s+([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?''')
LINK_ATTRS = {'href', 'src', 'poster', 'data'}


class HtmlEdits(HTMLParser):
    def __init__(self, text, base, old, new):
        super().__init__(convert_charrefs=False)
        self.text, self.base, self.old, self.new = text, base, old, new
        self.offsets = [0]
        self.offsets.extend(m.end() for m in re.finditer('\n', text))
        self.edits = []
        self.has_base = False

    def handle_starttag(self, tag, attrs):
        if tag == 'base' and any(k == 'href' for k,v in attrs):
            self.has_base = True
        raw = self.get_starttag_text()
        match = TAG_NAME.match(raw)
        if not match:
            return
        offset = self.offsets[self.getpos()[0]-1] + self.getpos()[1]
        pos = match.end()
        while pos < len(raw):
            attr = ATTR.match(raw, pos)
            if not attr:
                break
            pos = attr.end()
            if attr.group(1).lower() not in LINK_ATTRS:
                continue
            group = 2 if attr.group(2) is not None else 3 if attr.group(3) is not None else None
            if group is None:
                continue
            value = attr.group(group)
            # Skip complex URLs, escapes and whitespace rather than rewriting
            # their meaning. Preserve query/fragment suffix verbatim.
            if '&' in value or value != value.strip():
                continue
            resolved = local_path(value, self.base, 'HTML')
            if resolved is None or resolved[0] != self.old:
                continue
            parsed = urlsplit(value)
            if parsed.scheme or resolved[1] or '\\' in value:
                continue
            suffix = value[len(re.split(r'[?#]', value, maxsplit=1)[0]):]
            new = quote(os.path.relpath(self.new, self.base).replace(os.sep, '/'), safe='/') + suffix
            self.edits.append((offset+attr.start(group), offset+attr.end(group), new))


def rewrite_html(text, source, old, new):
    parser = HtmlEdits(text, source.parent, old, new)
    parser.feed(text)
    parser.close()
    if parser.has_base:
        raise ValueError('HTML base href is not supported by automatic repair.')
    for start,end,value in reversed(parser.edits):
        text = text[:start] + value + text[end:]
    return text, len(parser.edits)


JSON_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')


def rewrite_json(text, source, old, new):
    json.loads(text)
    edits = []
    for match in JSON_STRING.finditer(text):
        # Object keys are never rewritten; values only.
        pos = match.end()
        while pos < len(text) and text[pos] in ' \t\r\n':
            pos += 1
        if pos < len(text) and text[pos] == ':':
            continue
        raw = json.loads(match.group())
        if not any(c in raw for c in ('/', '\\', '.')):
            continue
        resolved = local_path(raw, source.parent, 'JSON')
        if resolved is None or resolved[0] != old or resolved[1] or urlsplit(raw).scheme or '\\' in raw:
            continue
        replacement = os.path.relpath(new, source.parent).replace(os.sep, '/')
        edits.append((match.start(), match.end(), json.dumps(replacement, ensure_ascii=True)))
    for start,end,value in reversed(edits):
        text = text[:start]+value+text[end:]
    json.loads(text)
    return text, len(edits)


@dataclass(frozen=True)
class Plan:
    root: Path
    source: Path
    old: Path
    new: Path
    before: bytes
    after: bytes
    replacements: int
    mode: int

    @property
    def token(self):
        return digest(json.dumps([str(self.root),str(self.source),str(self.old),str(self.new),
                                  digest(self.before),digest(self.after),self.mode]).encode('utf-8'))

    def preview(self):
        return ''.join(unified_diff(self.before.decode('utf-8-sig').splitlines(keepends=True),
                                    self.after.decode('utf-8-sig').splitlines(keepends=True),
                                    fromfile='before', tofile='after'))


def plan_repair(root, source, old, new):
    root = project(root)
    source, old, new = [scoped(root, p) for p in (source,old,new)]
    if source in (old,new) or not missing_target(old):
        raise ValueError('The old link target must be missing and different from the source.')
    info = new.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('The replacement must be an existing regular file.')
    before, mode = read_source(source)
    text = before.decode('utf-8-sig')
    if source.suffix.lower() in {'.html','.htm'}:
        updated,count = rewrite_html(text,source,old,new)
    elif source.suffix.lower() == '.json':
        updated,count = rewrite_json(text,source,old,new)
    else:
        raise ValueError('Repair currently supports UTF-8 HTML and JSON only.')
    after = updated.encode('utf-8-sig' if before.startswith(b'\xef\xbb\xbf') else 'utf-8')
    if not count or before == after:
        raise ValueError('No eligible literal relative links matched the missing target.')
    if len(after) > MAX_BYTES:
        raise ValueError('Repaired file would exceed the size limit.')
    return Plan(root,source,old,new,before,after,count,mode)


def suggestions(root, db=None):
    """Historical move hints, not proof of identity or current link validity."""
    root = project(root)
    db = Path(db) if db is not None else state_path()
    if not db.is_file():
        return []
    with closing(sqlite3.connect(db.resolve().as_uri()+'?mode=ro', uri=True)) as conn:
        rows = conn.execute('SELECT source,target FROM refs WHERE root=? ORDER BY source,target LIMIT 20000', (str(root),)).fetchall()
        moves = {}
        for old,new in conn.execute("SELECT path,detail FROM history WHERE root=? AND action='Possible move' ORDER BY id DESC",(str(root),)):
            moves.setdefault(old,new)
    result = []
    for source,old in rows:
        if old not in moves:
            continue
        try:
            plan = plan_repair(root,source,old,moves[old])
        except (OSError,ValueError):
            continue
        result.append({'source':source,'old':old,'new':moves[old],'replacements':plan.replacements})
        if len(result) >= 200:
            break
    return result


def replace_checked(root, source, expected, data, mode):
    source = scoped(root, source)
    current, current_mode = read_source(source)
    if current != expected or current_mode != mode:
        raise ValueError('Source changed since preview. No replacement made.')
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=source.parent,prefix='.breakcheck-repair-',delete=False) as stream:
            temp = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, mode)
        # This is not a filesystem compare-and-swap: close external editors.
        if read_source(scoped(root,source)) != (expected,mode):
            raise ValueError('Source changed while staging repair.')
        os.replace(temp,source)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


class RepairJournal:
    def __init__(self, db=None):
        self.db = Path(db) if db is not None else state_path().parent / 'repairs.sqlite3'

    def connect(self):
        self.db.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        try:
            fd = os.open(self.db,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        except FileExistsError:
            info = self.db.lstat()
            if not stat.S_ISREG(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
                raise ValueError('Repair journal must be a regular local file.')
            if os.name == 'posix' and info.st_mode & 0o077:
                raise PermissionError('Repair journal must have private permissions (0600).')
        else:
            os.close(fd)
        db = sqlite3.connect(self.db,timeout=20)
        try:
            db.execute('''CREATE TABLE IF NOT EXISTS repairs (id INTEGER PRIMARY KEY, root TEXT,
                source TEXT, before BLOB, after BLOB, mode INTEGER, created INTEGER, status TEXT)''')
            db.commit()
            return db
        except BaseException:
            db.close()
            raise

    def apply(self, plan, token):
        # Rebuild instead of accepting caller-supplied replacement bytes.
        fresh = plan_repair(plan.root,plan.source,plan.old,plan.new)
        if fresh.token != token or plan.token != token:
            raise ValueError('Preview is stale. Generate a new preview.')
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            count,used = db.execute('SELECT COUNT(*),COALESCE(SUM(length(before)+length(after)),0) FROM repairs').fetchone()
            if count >= MAX_ENTRIES or used+len(fresh.before)+len(fresh.after)>MAX_JOURNAL:
                raise ValueError('Repair journal is full. No file changed.')
            ident = db.execute('INSERT INTO repairs(root,source,before,after,mode,created,status) VALUES(?,?,?,?,?,?,?)',
                (str(fresh.root),str(fresh.source),fresh.before,fresh.after,fresh.mode,time.time_ns(),'prepared')).lastrowid
            db.commit()  # durable undo bytes before touching source
            db.execute('BEGIN IMMEDIATE')
            verified = plan_repair(fresh.root,fresh.source,fresh.old,fresh.new)
            if verified.token != token:
                raise ValueError('Preview changed while preparing journal. No replacement made.')
            replace_checked(fresh.root,fresh.source,fresh.before,fresh.after,fresh.mode)
            db.execute("UPDATE repairs SET status='applied' WHERE id=?",(ident,))
        return ident

    def entries(self):
        if not self.db.is_file():
            return []
        with closing(self.connect()) as db:
            return [dict(zip(('id','root','source','created','status'),row)) for row in db.execute(
                'SELECT id,root,source,created,status FROM repairs ORDER BY id DESC LIMIT 1000')]

    def undo(self, ident):
        if not self.db.is_file():
            raise ValueError('No repair journal.')
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT root,source,before,after,mode,status FROM repairs WHERE id=?',(ident,)).fetchone()
            if row is None or row[-1] not in ('prepared','applied'):
                raise ValueError('Repair is not available for undo.')
            root,source,before,after,mode,status = row
            root = project(root)
            source = scoped(root,source)
            # A prepared entry may survive a crash after atomic replacement.
            # Only the exact repaired bytes may be reverted.
            replace_checked(root,source,after,before,mode)
            db.execute("UPDATE repairs SET status='undone' WHERE id=?",(ident,))
        return source
