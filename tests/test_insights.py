import contextlib
import gzip
import io
import json
import tempfile
import unittest
from pathlib import Path
from breakcheck.core import scan, analyze
from breakcheck.insights import candidates, impact_graph, NOTICE
from breakcheck.__main__ import main


class InsightsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.logo = self.write('assets/logo.png', b'logo')

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode('utf-8'))
        return path

    def test_svg_href_and_xlink(self):
        svg = self.write('image.svg', '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"><image href="assets/logo.png"/><image xlink:href="assets/logo.png"/><use href="#local"/></svg>')
        r = analyze(scan(self.root), self.logo)
        self.assertEqual({i.reference.source for i in r.direct}, {svg})
        self.assertEqual(len(r.direct), 1)

    def test_obj_material_and_texture_chain(self):
        obj = self.write('mesh.obj', 'mtllib mesh.mtl\n')
        mtl = self.write('mesh.mtl', 'map_Kd assets/logo.png\n')
        r = analyze(scan(self.root), self.logo)
        self.assertEqual([i.reference.source for i in r.direct], [mtl])
        self.assertEqual(r.indirect, [obj])

    def test_mtl_options_warn(self):
        self.write('mesh.mtl', 'map_Kd -s 1 1 1 assets/logo.png\n')
        s = scan(self.root)
        self.assertFalse(s.references)
        self.assertTrue(any('texture-map options' in w for w in s.warnings))

    def test_premiere_plain_and_gzip(self):
        data = b'<PremiereData><Media><FilePath>assets/logo.png</FilePath></Media></PremiereData>'
        a = self.write('one.prproj', data)
        b = self.write('two.prproj', gzip.compress(data))
        r = analyze(scan(self.root), self.logo)
        self.assertEqual({i.reference.source for i in r.direct}, {a, b})
        self.assertEqual(len(r.scan.warnings), 2)

    def test_malformed_gzip_and_xml_dtd_are_reported(self):
        self.write('bad.prproj', b'\x1f\x8b\x08')
        self.write('bad.svg', '<!DOCTYPE svg [<!ENTITY a "assets/logo.png">]><svg><image href="&a;"/></svg>')
        s = scan(self.root)
        self.assertEqual(s.skipped, 2)
        self.assertFalse(s.references)

    def test_bad_deflate_and_tab_separated_wavefront(self):
        self.write('bad.prproj', b'\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff\x07' + b'\x00' * 8)
        mtl = self.write('mesh.mtl', 'map_Kd\t assets/logo.png\n')
        r = analyze(scan(self.root), self.logo)
        self.assertEqual([i.reference.source for i in r.direct], [mtl])
        self.assertEqual(r.scan.skipped, 1)

    def test_candidates_exclude_referenced_media_and_directories(self):
        unused = self.write('assets/unused.jpg', b'x' * 20)
        smaller = self.write('assets/other.wav', b'x')
        self.write('nested/protected.mp4', b'x' * 30)
        self.write('index.html', '<img src="assets/logo.png"><a href="nested/">dir</a>')
        s = scan(self.root)
        self.assertEqual(candidates(s), [(unused, 20), (smaller, 1)])
        self.assertTrue(unused.exists())

    def test_graph_real_edges_and_limits(self):
        a = self.write('a.md', '[Logo](assets/logo.png)')
        b = self.write('b.md', '[A](a.md)')
        r = analyze(scan(self.root), self.logo)
        roles, edges, omitted = impact_graph(r)
        self.assertEqual(roles, {self.logo: 'Target', a: 'Direct', b: 'Indirect'})
        self.assertEqual(set(edges), {(a, self.logo, True), (b, a, False)})
        self.assertEqual(omitted, 0)
        roles, edges, omitted = impact_graph(r, node_limit=2)
        self.assertEqual(len(roles), 2)
        self.assertEqual(len(edges), 1)
        self.assertEqual(omitted, 1)

    def test_move_graph_outgoing_reference(self):
        source = self.write('index.html', '<img src="assets/logo.png">')
        report = analyze(scan(self.root), source, 'move', self.root / 'pages/index.html')
        roles, edges, omitted = impact_graph(report)
        self.assertEqual(roles[source], 'Target')
        self.assertEqual(roles[self.logo], 'Referenced')
        self.assertEqual(edges, [(source, self.logo, True)])

    def test_inventory_cli(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(['inventory', str(self.root), '--json']), 0)
        data = json.loads(out.getvalue())
        self.assertEqual(data['notice'], NOTICE)
        self.assertEqual(data['candidates'], [{'path': str(self.logo), 'bytes': 4}])


if __name__ == '__main__':
    unittest.main()
