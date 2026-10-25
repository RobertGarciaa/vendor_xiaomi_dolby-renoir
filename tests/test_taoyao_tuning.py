#!/usr/bin/env python3
"""Verify actual pinned donor transfer, scope, rollback and fail-closed provenance."""
import importlib.util
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('dax', ROOT / 'tools/gen-renoir-dax.py')
dax = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dax)

class DonorTests(unittest.TestCase):
    def test_original_transfer_and_scope(self):
        stock = (ROOT / 'proprietary/vendor/etc/dolby/dax-default.xml').read_bytes()
        donor = (ROOT / 'tuning/taoyao-dax-default.xml').read_bytes()
        output, report = dax.derive(stock, donor)
        before, after, reference = map(ET.fromstring, (stock, output, donor))
        path = "./tuning[@name='speaker_landscape']//band_optimizer"
        target_bands, donor_bands = after.findall(path), reference.findall(path)
        self.assertEqual(len(target_bands), 20)
        for target, source in zip(target_bands, donor_bands):
            self.assertEqual(target.attrib, source.attrib)
        for original, changed in zip(before.findall(path), target_bands):
            for channel in ('left', 'right'):
                changed.set('gain_' + channel, original.get('gain_' + channel))
        self.assertEqual(ET.tostring(before), ET.tostring(after))
        self.assertEqual(report['output_sha256'], 'ace26880c50c31ce8e0f7ad489dd9eee344e922a2737713a82d3d77b39933d66')
        self.assertEqual(dax.derive(stock)[1]['output_sha256'], '84abb44348ab88ec97adfcc742f27ec8b8ddf69316921d7b2d61728ae9a4205e')
        self.assertFalse(report['measured'])
        with self.assertRaises(ValueError):
            dax.derive(stock, donor + b' ')

if __name__ == '__main__':
    unittest.main()
