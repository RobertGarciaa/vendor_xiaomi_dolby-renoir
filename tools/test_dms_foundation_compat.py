#!/usr/bin/env python3
"""ELF dynamic-string isolation must never alter instructions or other bytes."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('compat', Path(__file__).with_name('dms_foundation_compat.py'))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class IsolationTests(unittest.TestCase):
    def test_wrong_hash_rejected_before_parsing(self):
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            c.isolate(b'not an ELF', 'provider')

    def test_renamed_provider_has_no_platform_soname(self):
        # Live fixtures are supplied explicitly; no proprietary data is committed.
        import os
        root = os.environ.get('DOLBY_COMPAT_FIXTURES')
        if not root:
            self.skipTest('Set DOLBY_COMPAT_FIXTURES to the verified original fixture directory')
        for name, mode in [('libstagefright_foundation-v30.so', 'provider'), ('libdlbdsservice-original.so', 'consumer')]:
            with self.subTest(mode=mode):
                data = (Path(root) / name).read_bytes()
                out = c.isolate(data, mode)
                self.assertEqual(len(out), len(data))
                start = data.index(c.OLD + b'\0')
                expected = c.NEW + b'\0' * (len(c.OLD) + 1 - len(c.NEW))
                self.assertEqual(out[start:start + len(expected)], expected)
                self.assertEqual(out[:start], data[:start])
                self.assertEqual(out[start + len(expected):], data[start + len(expected):])
                with self.assertRaisesRegex(ValueError, 'SHA256'):
                    c.isolate(out, mode)
                bad = bytearray(data)
                bad[-1] ^= 1
                with self.assertRaisesRegex(ValueError, 'SHA256'):
                    c.isolate(bytes(bad), mode)


if __name__ == '__main__':
    unittest.main()
