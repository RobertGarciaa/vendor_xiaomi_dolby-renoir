"""Contract fixtures only; no Java/smali/DEX compiler or real APK build."""
from pathlib import Path
import importlib.util
import hashlib
import io
import struct
import unittest
import zipfile
import zlib
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('apk_contract',ROOT/'tools/misound_apk_contract.py')
contract=importlib.util.module_from_spec(spec);spec.loader.exec_module(contract)

def fixture_dex(payload):
    data=bytearray(112)+payload
    data[:8]=b'dex\n035\0';struct.pack_into('<I',data,32,len(data))
    data[12:32]=hashlib.sha1(data[32:]).digest()
    struct.pack_into('<I',data,8,zlib.adler32(data[12:])&0xffffffff)
    return bytes(data)

def fixture_zip(main,compat=None):
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('classes.dex',fixture_dex(main))
        if compat is not None:z.writestr('classes2.dex',fixture_dex(compat))
    archive.seek(0);return archive

class ContractTest(unittest.TestCase):
    def payload(self):return b'\0'.join(contract.REQUIRED_UUIDS+(contract.GUARD_MARKER,))
    def test_required_contract(self):
        contract.verify_apk(fixture_zip(self.payload(),b'Lmiui/util/FeatureParser;'))
    def test_stale_missing_or_hardware_artifact(self):
        for payload,compat in [(b'\0'.join(contract.REQUIRED_UUIDS),b'Lmiui/util/FeatureParser;'),
             (self.payload(),None),(self.payload(),b'wrong class'),
             (self.payload()+contract.OLD_UUIDS[0],b'Lmiui/util/FeatureParser;')]:
            with self.assertRaises(ValueError):contract.verify_apk(fixture_zip(payload,compat))
    def test_dex_corruption(self):
        data=bytearray(fixture_dex(b'hello'));data[-1]^=1
        with self.assertRaises(ValueError):contract.verify_dex(data)
        with self.assertRaises(ValueError):contract.verify_dex(b'dex\n')
    def test_build_module_uses_checked_artifact(self):
        source=(ROOT/'Android.bp').read_text()
        self.assertIn('apk: ":renoir_misound_verified_apk"',source)
        self.assertIn('main: "tools/misound_apk_contract.py"',source)
        self.assertIn('Stale MiSound APK', (ROOT/'tools/misound_apk_contract.py').read_text())

if __name__=='__main__':unittest.main()
