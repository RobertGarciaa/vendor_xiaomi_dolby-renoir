#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise untrusted binary boundaries without redistributing firmware."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

spec = importlib.util.spec_from_file_location('cnt_dump', Path(__file__).with_name('tfa-cnt-dump.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def seal(b):
    struct.pack_into('<I', b, 6, len(b))
    struct.pack_into('<I', b, 10, zlib.crc32(b[14:]))
    return b


def fixture():
    b = bytearray(50)
    b[:6] = b'PM3_01'
    struct.pack_into('<HHH', b, 40, 1, 1, 0)
    def add(data):
        off = len(b)
        b.extend(data)
        return off
    def ptr(off, typ):
        return struct.pack('<I', off | typ << 24)
    name = add(b'RCV\0')
    pname = add(b'stereo\0')
    common = add(struct.pack('<HH', 0, 0x2603))
    active = add(struct.pack('<HH', 9, 0x0203))
    restore = add(struct.pack('<HH', 8, 0x0203))
    profile = add(struct.pack('<BBH', 4, 0, 0x1234) + ptr(pname, 3)
                  + ptr(active, 16) + ptr(0, 17) + ptr(restore, 16))
    dev = add(struct.pack('<BBBBI', 2, 0, 0x34, 0, 0x12345678)
              + ptr(name, 3) + ptr(common, 16) + ptr(profile, 1))
    b[46:50] = ptr(dev, 0)
    return seal(b)


class ContainerTests(unittest.TestCase):
    def parse(self, b):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'fixture.cnt'
            p.write_bytes(b)
            c = module.Cnt(p)
            return c.header(), c.devices()

    def test_common_fields_and_profile_restore(self):
        header, devices = self.parse(fixture())
        self.assertTrue(header['crc_valid'])
        dev = devices[0]
        self.assertEqual(dev['devid'], 0x12345678)
        self.assertEqual(dev['items'][0]['field'], 0x2603)
        items = dev['profiles'][0]['items']
        self.assertEqual([i['phase'] for i in items], ['active', 'restore', 'restore'])
        self.assertEqual((items[0]['width'], items[0]['mask']), (4, 15))

    def test_corrupt_crc(self):
        b = fixture()
        b[-1] ^= 1
        with self.assertRaisesRegex(ValueError, 'CRC mismatch'):
            self.parse(b)

    def test_declared_size_and_truncation(self):
        with self.assertRaisesRegex(ValueError, 'declared size'):
            self.parse(fixture()[:-1])
        with self.assertRaisesRegex(ValueError, 'out-of-bounds'):
            self.parse(b'PM')

    def test_invalid_descriptor_with_valid_crc(self):
        b = fixture()
        struct.pack_into('<I', b, 46, 0xFFFFFF)
        with self.assertRaisesRegex(ValueError, 'out-of-bounds'):
            self.parse(seal(b))


if __name__ == '__main__':
    unittest.main()
