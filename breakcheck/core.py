"""Bounded, read-only dependency scanning and what-if analysis."""
from __future__ import annotations

import json
import os
import re
import stat
import zipfile
import zlib
from collections import defaultdict, deque
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree
from .adapters import EXTENSIONS, read_references

MAX_BYTES = 4 * 1024 * 1024
MAX_REL_TOTAL = 16 * 1024 * 1024
MAX_REL_ENTRIES = 1000
TEXT = {'.html', '.htm', '.css', '.md', '.markdown', '.json'}
OFFICE = {'.xlsx', '.docx', '.pptx', '.xlsm', '.docm', '.pptm'}
SKIP_DIRS = {'.git', '.venv', 'node_modules', '__pycache__'}
CSS = re.compile(r'''url\(\s*(?:"([^"\n]*)"|'([^'\n]*)'|([^\s)]+))\s*\)|@import\s+(?:"([^"\n]+)"|'([^'\n]+)')''', re.I)
MD = re.compile(r'''!?\[[^\]\n]*\]\(\s*(?:<([^>\n]+)>|([^\s)]+))|^\s*\[[^\]\n]+\]:\s*(?:<([^>\n]+)>|([^\s]+))''', re.M)
DRIVE = re.compile(r'^[a-zA-Z]:[\\/]')

@dataclass(frozen=True)
class Reference:
    source: Path
    target: Path
    raw: str
    kind: str
    line: int | None = None
    absolute: bool = False

@dataclass
class Scan:
    root: Path
    references: list[Reference] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    files_seen: int = 0
    files_parsed: int = 0
    unsupported: int = 0
    skipped: int = 0
    inventory: dict[Path, int] = field(default_factory=dict)

@dataclass(frozen=True)
class Impact:
    reference: Reference
    reason: str

@dataclass
class Report:
    operation: str
    target: Path
    destination: Path | None
    direct: list[Impact]
    indirect: list[Path]
    scan: Scan

    def as_dict(self):
        return {
            'operation': self.operation, 'target': str(self.target),
            'destination': str(self.destination) if self.destination else None,
            'direct': [{'source': str(i.reference.source), 'target': str(i.reference.target),
                        'reference': i.reference.raw, 'kind': i.reference.kind,
                        'line': i.reference.line, 'reason': i.reason} for i in self.direct],
            'indirect': list(map(str, self.indirect)),
            'coverage': {'root': str(self.scan.root), 'files_seen': self.scan.files_seen,
                         'files_parsed': self.scan.files_parsed, 'unsupported': self.scan.unsupported,
                         'skipped': self.scan.skipped, 'warnings': self.scan.warnings},
            'notice': 'Potential impacts only. No detected references does not prove safety.'}


def inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def local_path(raw: str, base: Path, kind: str) -> tuple[Path, bool] | None:
    raw = raw.strip()
    if not raw or raw.startswith(('#', '//')) or '\x00' in raw:
        return None
    if DRIVE.match(raw) or raw.startswith('\\\\'):
        if os.name != 'nt':
            return None
        path = Path(raw)
        return Path(os.path.abspath(path)), True
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return None
    if parsed.scheme and parsed.scheme.lower() != 'file':
        return None
    if parsed.netloc and parsed.netloc.lower() != 'localhost':
        return None
    if (kind == 'JSON' or kind.startswith('Wavefront') or kind.startswith('Premiere')) and not parsed.scheme:
        value = raw  # JSON paths may contain literal # and ? characters.
    else:
        value = unquote(parsed.path)
    if not value or '\x00' in value:
        return None
    if parsed.scheme == 'file' and os.name == 'nt' and re.match(r'^/[a-zA-Z]:', value):
        value = value[1:]
    # A leading slash in web content is server-root-relative, not a local file.
    if kind in {'HTML', 'CSS'} and value.startswith('/') and not parsed.scheme:
        return None
    path = Path(value)
    absolute = path.is_absolute()
    return Path(os.path.abspath(path if absolute else base / path)), absolute


class Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self.has_base = False

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if tag == 'base' and key == 'href' and value:
                self.has_base = True
            elif key in {'href', 'src', 'poster', 'data'} and value:
                self.items.append((value, self.getpos()[0]))


def strings(value):
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            yield item
        elif isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)


def extract(path: Path, warnings: list[str]):
    suffix = path.suffix.lower()
    if suffix in EXTENSIONS:
        yield from read_references(path, warnings)
        return
    if suffix in OFFICE:
        with zipfile.ZipFile(path) as archive:
            rels = [i for i in archive.infolist() if i.filename.endswith('.rels')]
            if (len(rels) > MAX_REL_ENTRIES or sum(i.file_size for i in rels) > MAX_REL_TOTAL
                    or any(i.file_size > MAX_BYTES for i in rels)):
                raise ValueError('Office relationship data exceeds scan limits')
            for info in rels:
                with archive.open(info) as entry:
                    data = entry.read(MAX_BYTES + 1)
                xml = data.decode('utf-8-sig')
                if len(data) > MAX_BYTES or '<!DOCTYPE' in xml.upper() or '<!ENTITY' in xml.upper():
                    raise ValueError('Unsupported or oversized XML relationship data')
                for node in ElementTree.fromstring(xml):
                    if node.get('TargetMode', '').lower() == 'external' and node.get('Target'):
                        yield node.get('Target'), 'Office external relationship', None
        return
    with path.open('rb') as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('Text file exceeds scan limit')
    text = data.decode('utf-8-sig')
    if suffix in {'.html', '.htm'}:
        parser = Links()
        parser.feed(text)
        parser.close()
        if parser.has_base:
            warnings.append(f'{path}: HTML base href is unsupported; relative references omitted')
        for raw, line in parser.items:
            if not parser.has_base or urlsplit(raw).scheme == 'file':
                yield raw, 'HTML', line
    elif suffix in {'.css', '.md', '.markdown'}:
        pattern = CSS if suffix == '.css' else MD
        kind = 'CSS' if suffix == '.css' else 'Markdown'
        previous, line = 0, 1
        for match in pattern.finditer(text):
            line += text.count('\n', previous, match.start())
            previous = match.start()
            raw = next((g for g in match.groups() if g is not None), '')
            yield raw, kind, line
    elif suffix == '.json':
        for raw in strings(json.loads(text)):
            yield raw, 'JSON', None


def scan(root: Path | str, max_files: int = 100_000) -> Scan:
    root = Path(root).expanduser().resolve(strict=True)
    if not root.is_dir() or max_files < 1:
        raise ValueError('Choose an existing directory and a positive file limit')
    result = Scan(root)
    seen = set()
    def warn_walk(error):
        result.skipped += 1
        result.warnings.append(str(error))
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=warn_walk):
        dirs.sort()
        files.sort()
        for name in dirs[:]:
            p = Path(directory) / name
            try:
                is_reparse = bool(getattr(p.lstat(), 'st_file_attributes', 0) & 0x400)
            except OSError as exc:
                warn_walk(exc)
                dirs.remove(name)
                continue
            if name in SKIP_DIRS or p.is_symlink() or is_reparse or getattr(p, 'is_junction', lambda: False)():
                dirs.remove(name)
                result.skipped += 1
        for name in files:
            if result.files_seen >= max_files:
                result.warnings.append(f'File limit reached ({max_files}); scan incomplete')
                return result
            result.files_seen += 1
            path = Path(directory) / name
            try:
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                    result.skipped += 1
                    continue
                result.inventory[path] = info.st_size
                if path.suffix.lower() not in TEXT | OFFICE | EXTENSIONS:
                    result.unsupported += 1
                    continue
                for raw, kind, line in extract(path, result.warnings):
                    resolved = local_path(raw, path.parent, kind)
                    if resolved is None:
                        continue
                    target, absolute = resolved
                    # Only index existing paths in the chosen root, without following
                    # links outside it. This also reduces JSON false positives.
                    if not inside(target, root) or not target.exists() or not inside(target.resolve(), root):
                        continue
                    if kind == 'JSON' and not any(c in raw for c in ('/', '\\', '.')):
                        continue
                    ref = Reference(path, target, raw, kind, line, absolute)
                    if ref not in seen:
                        seen.add(ref)
                        result.references.append(ref)
                result.files_parsed += 1
            except (OSError, EOFError, ValueError, RuntimeError, zipfile.BadZipFile, zlib.error, ElementTree.ParseError) as exc:
                result.skipped += 1
                result.warnings.append(f'{path}: {exc}')
    return result


def analyze(index: Scan, target: Path | str, operation: str = 'delete', destination: Path | str | None = None) -> Report:
    target = Path(os.path.abspath(Path(target).expanduser()))
    if not inside(target, index.root) or not target.exists():
        raise ValueError('Target must exist inside the scanned directory')
    if target.resolve() != target:
        raise ValueError('Symbolic-link targets are not supported')
    if operation not in {'delete', 'move', 'rename'}:
        raise ValueError('Unknown operation')
    dest = Path(os.path.abspath(Path(destination).expanduser())) if destination is not None else None
    if operation == 'delete' and dest is not None:
        raise ValueError('Delete simulation does not accept a destination')
    if operation != 'delete':
        if dest is None or os.path.lexists(dest) or inside(dest, target):
            raise ValueError('Choose a new destination outside the target')
        if operation == 'rename' and dest.parent != target.parent:
            raise ValueError('Rename must stay in the same directory; use move instead')
    def relocated(path):
        return dest / path.relative_to(target) if dest is not None and inside(path, target) else path
    direct = []
    for ref in index.references:
        source_inside = inside(ref.source, target)
        target_inside = inside(ref.target, target)
        if operation == 'delete':
            if target_inside and not source_inside:
                direct.append(Impact(ref, 'Referenced path would be removed'))
        elif source_inside or target_inside:
            new_source = relocated(ref.source)
            new_target = relocated(ref.target)
            resolved = local_path(ref.raw, new_source.parent, ref.kind)
            if resolved is None or resolved[0] != new_target:
                direct.append(Impact(ref, 'Reference would no longer point to the same file'))
    # Walk reverse references to identify potentially affected dependents.
    reverse = defaultdict(set)
    for ref in index.references:
        reverse[ref.target].add(ref.source)
        # Directory references can depend on content, too. For transitive
        # results use exact paths only to avoid unrelated directory fan-out.
    initial = {i.reference.source for i in direct}
    visited = set(initial)
    pending = deque(initial)
    while pending:
        for source in reverse[pending.popleft()]:
            if source in visited or (operation == 'delete' and inside(source, target)):
                continue
            visited.add(source)
            pending.append(source)
    direct.sort(key=lambda i: (str(i.reference.source), i.reference.line or 0, str(i.reference.target)))
    return Report(operation, target, dest, direct, sorted(visited - initial), index)
