#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Ensure the candidate only changes its authorized speaker gains."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('dax', ROOT / 'tools/gen-renoir-dax.py')
dax = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dax)


def fixture():
    bands = ''.join(f'<band_optimizer frequency="{i+1}" gain_left="{-i}" gain_right="{i}"/>'
                    for i in range(20))
    return (f'<device_data><preset id="user"><band_geq gain="48"/></preset>'
            f'<tuning name="speaker_landscape" endpoint_type="speaker"><data>'
            f'<audio-optimizer-bands>{bands}</audio-optimizer-bands>'
            f'<regulator-enable value="true"/></data></tuning>'
            f'<tuning name="speaker_portrait"><data>unchanged</data></tuning>'
            f'<tuning name="headphone"><gain value="96"/></tuning></device_data>').encode()


class TuningTests(unittest.TestCase):
    def test_scope_and_provenance(self):
        source = fixture()
        digest = hashlib.sha256(source).hexdigest()
        with patch.object(dax, 'STOCK_SHA256', digest):
            output, report = dax.derive(source)
            self.assertEqual(dax.derive(source)[0], output)
        before, after = ET.fromstring(source), ET.fromstring(output)
        for index in (0, 2, 3):
            self.assertEqual(ET.tostring(before[index]), ET.tostring(after[index]))
        for old, new in zip(before.findall('.//band_optimizer'), after.findall('.//band_optimizer')):
            self.assertEqual(old.get('frequency'), new.get('frequency'))
            self.assertEqual(old.get('gain_left'), new.get('gain_left'))
            self.assertEqual(new.get('gain_right'), '0')
        self.assertFalse(report['measured'])
        self.assertEqual(len(report['changes']), 19)
        self.assertEqual(report['source_sha256'], digest)

    def test_wrong_source_preserves_previous_output(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / 'stock.xml').write_bytes(fixture())
            (p / 'out.xml').write_bytes(b'previous verified output')
            run = subprocess.run([sys.executable, str(ROOT / 'tools/gen-renoir-dax.py'),
                                  '--stock', str(p / 'stock.xml'), '--out', str(p / 'out.xml')],
                                 capture_output=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertEqual((p / 'out.xml').read_bytes(), b'previous verified output')

    def test_refuse_overwriting_source(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'stock.xml'
            p.write_bytes(fixture())
            run = subprocess.run([sys.executable, str(ROOT / 'tools/gen-renoir-dax.py'),
                                  '--stock', str(p), '--out', str(p)], capture_output=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertEqual(p.read_bytes(), fixture())


if __name__ == '__main__':
    unittest.main()
