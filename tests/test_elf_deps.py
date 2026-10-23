#!/usr/bin/env python3
"""Regression checks for the ABI scan mistakes that excluded ARM DAP."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('abi', ROOT/'tools/check-elf-deps.py')
abi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(abi)


def header(bits, machine):
    return b'\x7fELF' + bytes([1 if bits == 32 else 2, 1]) + bytes(12) + struct.pack('<H', machine)


class ElfScanTest(unittest.TestCase):
    def test_ifunc_and_trailing_version_index(self):
        rows = '''
   519: 000a2e25 12 <OS specific>: 10 GLOBAL DEFAULT 18 memcpy@@LIBC
   520: 00000000 0 FUNC GLOBAL DEFAULT UND memcpy@LIBC (2)
   521: 00000000 0 NOTYPE WEAK DEFAULT UND optional
'''
        abi.symbols.cache_clear()
        with patch.object(abi, 'run', return_value=rows):
            defined, required = abi.symbols('fixture')
        self.assertEqual(defined, {('memcpy', 'LIBC')})
        self.assertEqual(required, {('memcpy', 'LIBC')})
        abi.symbols.cache_clear()

    def test_32_lookup_cannot_select_64_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path, bits, machine in [('vendor/lib64/libutils.so',64,183),
                                        ('vendor/lib/libutils.so',32,40)]:
                p = root/path; p.parent.mkdir(parents=True,exist_ok=True)
                p.write_bytes(header(bits,machine))
            self.assertEqual(abi.library('libutils.so',(32,40),root,None),root/'vendor/lib/libutils.so')
            (root/'vendor/lib/libutils.so').unlink()
            with self.assertRaises(ValueError):
                abi.library('libutils.so',(32,40),root,None)

    def test_bionic_absolute_symlink_stays_in_product(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            libc=root/'apex/com.android.runtime/lib/bionic/libc.so'
            libc.parent.mkdir(parents=True);libc.write_bytes(header(32,40))
            link=root/'system/lib/libc.so';link.parent.mkdir(parents=True)
            link.symlink_to('/apex/com.android.runtime/lib/bionic/libc.so')
            self.assertEqual(abi.library('libc.so',(32,40),root,None),libc)


if __name__ == '__main__':
    unittest.main()
