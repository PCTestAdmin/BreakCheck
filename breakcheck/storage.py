"""Bounded metadata-only storage analysis; no cleanup or content changes."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, asdict
import os
from pathlib import Path
import shutil
import stat
import time

from .core import inside, SKIP_DIRS, excluded_system_dir
from .safety import state_path

MAX_ENTRIES = 500_000
DAY = 86400
MIB = 1024**2
ARCHIVES = {'.zip','.7z','.rar','.tar','.gz','.xz','.bz2','.iso'}
MEDIA = {'.mp4','.mkv','.mov','.avi','.webm','.mp3','.wav','.flac','.jpg','.jpeg','.png','.tiff','.raw','.webp'}
DOCUMENTS = {'.pdf','.docx','.xlsx','.pptx','.txt','.md','.odt','.ods','.csv'}
INSTALLERS = {'.exe','.msi','.deb','.rpm','.appimage','.dmg'}
CATEGORIES = ('Media','Archives','Documents','Installers','Other')
AGES = ('0–30 days','31–90 days','91–365 days','Over 365 days')


def category(path):
    ext = path.suffix.lower()
    for label, extensions in zip(CATEGORIES, (MEDIA,ARCHIVES,DOCUMENTS,INSTALLERS)):
        if ext in extensions:
            return label
    return 'Other'


def age_bucket(days):
    return AGES[0] if days <= 30 else AGES[1] if days <= 90 else AGES[2] if days <= 365 else AGES[3]


def human_size(size):
    value = float(size)
    for unit in ('B','KiB','MiB','GiB','TiB','PiB'):
        if value < 1024 or unit == 'PiB':
            return f'{value:,.1f} {unit}' if unit != 'B' else f'{int(value):,} B'
        value /= 1024


@dataclass
class StorageReport:
    root: str
    files: int
    logical_bytes: int
    entries: int
    skipped: int
    complete: bool
    cancelled: bool
    warnings: list
    folders: list
    categories: list
    ages: list
    largest: list
    review: list
    volume: dict | None

    def as_dict(self):
        return asdict(self)


def analyze_storage(root, max_entries=MAX_ENTRIES, older_days=180, min_bytes=100*MIB,
                    stop=None, progress=None, now=None):
    """One metadata pass, capped by *all* directory entries, not file count."""
    root = Path(root).expanduser().resolve(strict=True)
    private = state_path().resolve().parent
    if not root.is_dir() or inside(root,private):
        raise ValueError('Choose a directory outside BreakCheck application data.')
    if not 1 <= max_entries <= 2_000_000 or older_days < 0 or min_bytes < 0:
        raise ValueError('Invalid scan limit or review filters.')
    now = time.time() if now is None else now
    device = root.stat().st_dev
    folders = defaultdict(lambda:[0,0])
    categories = {name:[0,0] for name in CATEGORIES}
    ages = {name:[0,0] for name in AGES}
    largest, review, warnings = [], [], []
    files = total = entries = skipped = 0
    complete = True
    cancelled = False
    capped = False
    # Keep only the top 200 rows in each file list to bound memory.
    import heapq
    def top(heap, item):
        if len(heap) < 200:
            heapq.heappush(heap,item)
        elif item > heap[0]:
            heapq.heapreplace(heap,item)

    def warn(message):
        nonlocal skipped, complete
        skipped += 1
        complete = False
        if len(warnings) < 100:
            warnings.append(str(message))

    stack = [root]
    last_progress = time.monotonic()
    while stack:
        if stop is not None and stop.is_set():
            cancelled = True
            break
        folder = stack.pop()
        try:
            # Recheck queued directories before opening them.
            info = folder.lstat()
            if (folder.resolve(strict=True) != folder or not stat.S_ISDIR(info.st_mode)
                    or getattr(info,'st_file_attributes',0)&0x400 or info.st_dev != device):
                warn(f'Excluded linked or other-volume directory: {folder}')
                continue
            with os.scandir(folder) as children:
                for entry in children:
                    if stop is not None and stop.is_set():
                        cancelled = True
                        break
                    if entries >= max_entries:
                        complete = False
                        capped = True
                        warnings.append(f'Entry limit reached ({max_entries:,}); results are partial.')
                        stack.clear()
                        break
                    entries += 1
                    path = Path(entry.path)
                    try:
                        # Windows DirEntry.stat may report zero st_dev/st_ino;
                        # use lstat for reliable volume and hard-link metadata.
                        info = path.lstat() if os.name == 'nt' else entry.stat(follow_symlinks=False)
                        if (stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400
                                or info.st_dev != device):
                            warn(f'Excluded linked or other-volume entry: {path}')
                            continue
                        if stat.S_ISDIR(info.st_mode):
                            if path == private or excluded_system_dir(path) or path.name in SKIP_DIRS:
                                warn(f'Excluded directory: {path}')
                            else:
                                stack.append(path)
                            continue
                        if not stat.S_ISREG(info.st_mode):
                            warn(f'Excluded special file: {path}')
                            continue
                        relative = path.relative_to(root)
                        first = (relative.parts[0], True) if len(relative.parts)>1 else ('(root files)', False)
                        size = info.st_size
                        # Logical per-path bytes, not allocated disk blocks.
                        days = max(0,int((now-info.st_mtime)/DAY))
                        files += 1
                        total += size
                        for bucket in (folders[first],categories[category(path)],ages[age_bucket(days)]):
                            bucket[0] += size
                            bucket[1] += 1
                        item=(size,relative.as_posix(),days,info.st_nlink)
                        top(largest,item)
                        if days >= older_days and size >= min_bytes:
                            top(review,item)
                    except OSError as exc:
                        warn(f'Access skipped: {path}: {exc}')
                    finally:
                        tick = time.monotonic()
                        if progress is not None and tick-last_progress >= .25:
                            progress(entries,files,total)
                            last_progress = tick
        except OSError as exc:
            if folder == root:
                raise
            warn(f'Access skipped: {folder}: {exc}')
        if cancelled or capped:
            break
    if cancelled:
        complete = False
        warnings.append('Scan cancelled; results are partial.')
    def buckets(mapping):
        return [{'name':name,'bytes':size,'files':count}
                for name,(size,count) in sorted(mapping.items(),key=lambda kv:(-kv[1][0],kv[0]))]
    def file_rows(heap):
        return [{'path':p,'bytes':s,'modified_days_ago':days,'hard_links':links,
                 'review':'Inspect dependencies before cleanup'} for s,p,days,links in sorted(heap,reverse=True)]
    try:
        d=shutil.disk_usage(root)
        volume={'total':d.total,'used':d.used,'free':d.free}
    except OSError:
        volume=None
    return StorageReport(str(root),files,total,entries,skipped,complete,cancelled,warnings,
                         [{'name':name,'directory':is_dir,'bytes':size,'files':count}
                          for (name,is_dir),(size,count) in sorted(folders.items(),key=lambda kv:(-kv[1][0],kv[0]))],
                         buckets(categories),buckets(ages),file_rows(largest),file_rows(review),volume)
