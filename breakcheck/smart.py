"""Reference-aware duplicate review; zero detected references is not safety."""
from pathlib import Path
from .core import scan, inside
from .safety import duplicates, state_path


def smart_duplicates(root, budget=None):
    root = Path(root).expanduser().resolve(strict=True)
    state = state_path().resolve().parent
    if inside(root, state):
        raise ValueError('Choose a folder outside application data.')
    warnings = []
    kwargs = {'coverage': warnings}
    if budget is not None:
        kwargs['budget'] = budget
    groups, skipped = duplicates(root, **kwargs)
    counts = {}
    # A drive-wide dependency parse can be very expensive and includes app data.
    if root == Path(root.anchor) or inside(state, root):
        warnings.append('Dependency counts unavailable for drive-wide or application-data-containing scans.')
    elif groups:
        index = scan(root)
        targets = {root / path for _, paths in groups for path in paths}
        sources = {target: set() for target in targets}
        for ref in index.references:
            if ref.target in sources:
                sources[ref.target].add(ref.source)
        counts = {str(path.relative_to(root).as_posix()): len(items) for path,items in sources.items()}
        warnings.extend(index.warnings[:100])
        warnings.append(f'Dependency coverage: {index.files_parsed}/{index.files_seen} files parsed; {index.unsupported} unsupported; {index.skipped} skipped.')
    review = []
    for i,(size,paths) in enumerate(groups,1):
        for path in sorted(paths, key=lambda p: (-(counts.get(p) or 0),p)):
            count = counts.get(path)
            review.append({'group': i, 'path': path, 'size': size, 'references': count,
                           'review': 'Keep: detected references' if count else ('Review: none detected' if count == 0 else 'Review: coverage unavailable')})
    return groups, skipped, warnings, review
