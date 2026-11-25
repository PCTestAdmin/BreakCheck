"""Guarded single-file moves: explicit confirmation, no destination overwrite."""
from __future__ import annotations
from dataclasses import dataclass
import ctypes
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from .core import scan, analyze, inside
from .repair import project, scoped
from .safety import stamp, state_path
from .agent import write_json

def rules_path():
    return state_path().parent / 'protection.json'

def rules():
    try:
        data = json.loads(rules_path().read_text(encoding='utf-8'))
    except FileNotFoundError:
        return []
    if not isinstance(data,list) or len(data)>1000:
        raise ValueError('Invalid protection rules.')
    for item in data:
        if not isinstance(item,dict) or not isinstance(item.get('path'),str) or not Path(item['path']).is_absolute() or item.get('mode') not in ('block','warn'):
            raise ValueError('Invalid protection rule.')
    return data

def set_rule(path, mode):
    p = Path(path).expanduser().resolve(strict=True)
    if mode not in ('block','warn'):
        raise ValueError('Invalid protection mode.')
    rows = [r for r in rules() if Path(r['path']) != p]
    rows.append({'path':str(p),'mode':mode})
    if len(rows)>1000:
        raise ValueError('Rule limit reached.')
    write_json(rules_path(),rows)

def remove_rule(path):
    p=Path(path).expanduser().resolve()
    write_json(rules_path(),[r for r in rules() if Path(r['path'])!=p])

def matching(source,destination):
    return [r for r in rules() if any(inside(p,Path(r['path'])) or inside(Path(r['path']),p)
                                     for p in (source,destination) if p is not None)]

@dataclass
class GuardPlan:
    root: Path
    source: Path
    destination: Path | None
    operation: str
    evidence: dict
    identity: tuple

    @property
    def token(self):
        return hashlib.sha256(json.dumps([str(self.root),str(self.source),str(self.destination),
             self.operation,self.evidence,self.identity],sort_keys=True).encode()).hexdigest()

    def as_dict(self):
        return {**self.evidence,'confirm':self.token,'operation':self.operation,
                'root':str(self.root),'source':str(self.source),
                'destination':str(self.destination) if self.destination else None}

def regular(p):
    info=p.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or getattr(info,'st_file_attributes',0)&0x400:
        raise ValueError('Only regular single-link files are supported.')
    return info

def preview(root,source,operation='move',destination=None):
    root=project(root)
    source=scoped(root,source)
    info=regular(source)
    if operation not in ('move','rename','delete'):
        raise ValueError('Unknown operation.')
    dest=None
    parent_identity=None
    if operation!='delete':
        if destination is None:
            raise ValueError('Choose a destination.')
        dest=scoped(root,destination)
        if os.path.lexists(dest):
            raise ValueError('Destination already exists.')
        parent=dest.parent.lstat()
        if not stat.S_ISDIR(parent.st_mode) or parent.st_dev!=info.st_dev:
            raise ValueError('Destination must be an existing directory on the same volume.')
        parent_identity=(parent.st_dev,parent.st_ino)
    elif destination is not None:
        raise ValueError('Delete review does not take a destination.')
    index=scan(root)
    result=analyze(index,source,operation,dest).as_dict()
    if stamp(regular(scoped(root,source)))!=stamp(info):
        raise ValueError('Source changed during scan.')
    matched=matching(source,dest)
    blocked=any(r['mode']=='block' for r in matched)
    evidence={'direct':result['direct'],'indirect':result['indirect'],'coverage':result['coverage'],
              'rules':matched,'blocked':blocked,
              'executable':operation!='delete' and not blocked and not index.warnings and (os.name=='nt' or sys.platform.startswith('linux')),
              'notice':'Only supported in-scope references detected. No detected references is not proof of safety. Rules apply only to this guarded workflow.'}
    return GuardPlan(root,source,dest,operation,evidence,(stamp(info),parent_identity))

def rename_no_replace(source,dest):
    if os.name=='nt':
        os.rename(source,dest)  # Windows refuses an existing destination.
    elif sys.platform.startswith('linux'):
        libc=ctypes.CDLL(None,use_errno=True)
        rename=getattr(libc,'renameat2',None)
        if rename is None:
            raise OSError('Atomic no-replace rename unavailable on this system.')
        rename.argtypes=(ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint)
        rename.restype=ctypes.c_int
        if rename(-100,os.fsencode(source),-100,os.fsencode(dest),1)!=0:
            err=ctypes.get_errno()
            raise OSError(err,os.strerror(err),str(dest))
    else:
        raise OSError('Guarded moves are supported on Windows and Linux only.')

def apply(plan,token):
    fresh=preview(plan.root,plan.source,plan.operation,plan.destination)
    if fresh.token!=token or plan.token!=token:
        raise ValueError('Preview changed. Review again.')
    if not fresh.evidence['executable']:
        raise ValueError('Operation blocked or advisory only.')
    # Check again immediately before the atomic, no-replace move. External
    # editors and other file operations must be stopped; no global lock exists.
    source=scoped(fresh.root,fresh.source)
    dest=scoped(fresh.root,fresh.destination)
    parent=dest.parent.lstat()
    if stamp(regular(source))!=fresh.identity[0] or (parent.st_dev,parent.st_ino)!=fresh.identity[1] or matching(source,dest)!=fresh.evidence['rules']:
        raise ValueError('Paths or protection rules changed. Review again.')
    rename_no_replace(source,dest)
    return dest
