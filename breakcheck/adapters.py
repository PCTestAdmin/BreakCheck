"""Small, bounded format adapters. Never execute or modify project data."""
from __future__ import annotations

import gzip
from xml.etree import ElementTree

EXTENSIONS = {'.svg', '.obj', '.mtl', '.prproj'}
MAX_PROJECT_BYTES = 32 * 1024 * 1024


def xml_root(data):
    # Decode first, so UTF-16 or other encodings cannot bypass the DTD guard.
    text = data.decode('utf-8-sig')
    if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ValueError('XML DTDs and entities are not supported')
    return ElementTree.fromstring(text)


def read_references(path, warnings):
    suffix = path.suffix.lower()
    limit = MAX_PROJECT_BYTES if suffix == '.prproj' else 4 * 1024 * 1024
    with path.open('rb') as stream:
        magic = stream.read(2)
        stream.seek(0)
        if suffix == '.prproj' and magic == b'\x1f\x8b':
            with gzip.GzipFile(fileobj=stream) as archive:
                data = archive.read(limit + 1)
        else:
            data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Project exceeds adapter scan limit')
    if suffix == '.svg':
        root = xml_root(data)
        for node in root.iter():
            for key, value in node.attrib.items():
                if key in ('href', '{http://www.w3.org/1999/xlink}href'):
                    yield value, 'SVG', None
    elif suffix == '.prproj':
        root = xml_root(data)
        if root.tag.rsplit('}', 1)[-1] != 'PremiereData':
            raise ValueError('Unrecognized Premiere XML project')
        warnings.append(f'{path}: experimental Premiere media-path scan; stored paths may be stale')
        for node in root.iter():
            if node.tag.rsplit('}', 1)[-1] in {'FilePath', 'ActualMediaFilePath', 'RelativePath'} and node.text:
                yield node.text.strip(), 'Premiere media path (experimental)', None
    else:
        for number, line in enumerate(data.decode('utf-8-sig').splitlines(), 1):
            fields = line.strip().split(None, 1)
            if len(fields) != 2:
                continue
            key, value = fields
            value = value.strip().strip('"')
            if suffix == '.obj' and key.lower() == 'mtllib':
                # Multiple libraries on one line are not interpreted as a list.
                yield value, 'Wavefront material library', number
            elif suffix == '.mtl' and (key.lower().startswith('map_') or key.lower() in {'bump', 'disp', 'decal', 'refl', 'norm'}):
                if value.startswith('-'):
                    warnings.append(f'{path}:{number}: texture-map options are not supported')
                    continue
                yield value, 'Wavefront texture', number
