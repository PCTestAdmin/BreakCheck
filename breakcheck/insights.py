"""Read-only report helpers: graph and cautious asset inventory."""
from __future__ import annotations

ASSETS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.bmp', '.tif', '.tiff',
          '.mp3', '.wav', '.flac', '.ogg', '.mp4', '.mov', '.mkv', '.avi', '.obj', '.mtl'}
NOTICE = 'No detected incoming reference does not mean unused or safe to delete.'


def candidates(index):
    """Return media assets with no detected incoming file or directory reference."""
    referenced = {ref.target for ref in index.references}
    return sorted(
        ((path, size) for path, size in index.inventory.items()
         if path.suffix.lower() in ASSETS
         and path not in referenced
         and not any(parent in referenced for parent in path.parents)),
        key=lambda item: (-item[1], str(item[0])))


def impact_graph(report, node_limit=60, edge_limit=120):
    """Return a bounded graph of real observed edges, not inferred synthetic links."""
    roles = {report.target: 'Target'}
    broken = {(i.reference.source, i.reference.target) for i in report.direct}
    direct = {i.reference.source for i in report.direct}
    indirect = set(report.indirect)
    affected = direct | indirect
    observed = {(r.source, r.target) for r in report.scan.references
                if (r.source, r.target) in broken
                or (r.source in indirect and r.target in affected)}
    edges = []
    omitted = 0

    def role(path):
        if path == report.target:
            return 'Target'
        if path in direct:
            return 'Direct'
        if path in indirect:
            return 'Indirect'
        return 'Referenced'

    ordered = sorted(observed, key=lambda e: (e not in broken, str(e[0]), str(e[1])))
    for source, target in ordered:
        new = {source, target} - roles.keys()
        if len(roles) + len(new) > node_limit or len(edges) >= edge_limit:
            omitted += 1
            continue
        for path in (source, target):
            roles[path] = role(path)
        edges.append((source, target, (source, target) in broken))
    return roles, edges, omitted
