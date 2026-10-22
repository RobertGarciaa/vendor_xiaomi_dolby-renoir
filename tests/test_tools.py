#!/usr/bin/env python3
"""Exercise failure preservation and DEX ordering without executing blobs."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

patch = load('patch', ROOT / 'tools/patch-misound.py')
extract = load('extract', ROOT / 'extract-files.py')


def dex(strings):
    # Minimal string-table fixture; this exercises the validator, not ART.
    out = bytearray(112 + len(strings)*4)
    out[:8] = b'dex\n035\0'
    struct.pack_into('<II', out, 0x38, len(strings), 112)
    for i, (length, encoded) in enumerate(strings):
        struct.pack_into('<I', out, 112+4*i, len(out))
        out.extend(bytes([length]) + encoded + b'\0')
    return bytes(out)

class ToolsTest(unittest.TestCase):
    def test_dex_utf16_order_and_duplicates(self):
        # MUTF8 C0 80 sorts before ASCII even though its encoded bytes do not.
        self.assertFalse(patch.dex_strings_sorted(dex([(1,b'\xc0\x80'),(1,b'A')]))[1])
        self.assertTrue(patch.dex_strings_sorted(dex([(1,b'A'),(1,b'\xc0\x80')]))[1])
        self.assertTrue(patch.dex_strings_sorted(dex([(1,b'A'),(1,b'A')]))[1])
        # Supplementary codepoint is two UTF16 units, ordered before U+E000.
        self.assertFalse(patch.dex_strings_sorted(dex([
            (2,b'\xed\xa0\x80\xed\xb0\x80'),(1,b'\xee\x80\x80')]))[1])

    def test_bad_later_blob_does_not_replace_earlier_output(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);src=p/'dump';dst=p/'output';src.mkdir();dst.mkdir()
            (src/'one').write_bytes(b'new one');(src/'two').write_bytes(b'bad')
            (dst/'one').write_bytes(b'last verified one')
            listing=p/'list';listing.write_text('one\ntwo\n')
            sums=p/'sums';sums.write_text('\n'.join(
                f'{hashlib.sha256(data).hexdigest()} {len(data)} {name}'
                for name,data in [('one',b'new one'),('two',b'expected two')]))
            previous=(extract.LIST,extract.SUMS,extract.PROPRIETARY)
            try:
                extract.LIST=str(listing);extract.SUMS=str(sums);extract.PROPRIETARY=str(dst)
                with self.assertRaises(SystemExit): extract.extract(str(src))
                self.assertEqual((dst/'one').read_bytes(),b'last verified one')
                self.assertFalse((dst/'two').exists())
            finally: extract.LIST,extract.SUMS,extract.PROPRIETARY=previous

    def test_vintf_source_matches_extraction_manifest(self):
        # The original Soong module used a filename extraction never produces.
        path='vendor/etc/vintf/manifest/manifest_vendor.dolby.hardware.dms.xml'
        self.assertIn(path,(ROOT/'proprietary-files.txt').read_text().splitlines())
        self.assertIn('vintf_fragments: ["proprietary/'+path+'"]',
                      (ROOT/'Android.bp').read_text())

    def test_bad_xml_preserves_previous_output(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);stock=p/'stock.xml';out=p/'output.xml';out.write_text('last verified')
            for text in ['<broken>', '<root><libraries/><libraries/><effects/></root>']:
                stock.write_text(text)
                result=subprocess.run([sys.executable,str(ROOT/'tools/gen-audio-effects.py'),
                    '--stock',str(stock),'--out',str(out)],capture_output=True)
                self.assertNotEqual(result.returncode,0)
                self.assertEqual(out.read_text(),'last verified')

if __name__=='__main__': unittest.main()
