#!/usr/bin/env python3
#
# Copyright (C) 2026 The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#
"""Parse a TFA98xx container (.cnt) using the kernel's own structure layout.

The on-device speaker amplifier on renoir is a pair of NXP TFA9873 parts
(I2C 0x34 and 0x35). Their tuning lives in vendor/firmware/tfa98xx.cnt and is
interpreted at runtime by techpack/audio/asoc/codecs/tfa98xx. That driver is
the authoritative description of the format, so this parser mirrors
inc/tfa98xx_parameters.h rather than guessing.

Layouts used (all packed, see "#pragma pack (push, 1)"):

  TfaContainer_t  id[2] version[2] subversion[2] size u32 CRC u32 rev u16
                  customer[8] application[8] type[8]
                  ndev u16 nprof u16 nliveData u16
                  index[]          (TfaDescPtr_t)
  TfaDescPtr_t    offset:24 | type:8   (one u32, little endian)
  TfaDeviceList_t length u8 bus u8 dev u8 func u8
                  (4 bytes of padding alignment follows in practice)
                  name TfaDescPtr_t, list[] TfaDescPtr_t
  TfaProfileList_t length:8 group:8 ID:16
                  name TfaDescPtr_t, list[] TfaDescPtr_t
  TfaBitfield_t   value u16, field u16

This is read-only analysis. Nothing here writes to a device.

Usage:
  ./tfa-cnt-dump.py <tfa98xx.cnt> [--json out.json]
"""

import argparse
import json
import struct
import sys

# enum TfaDescriptorType, inc/tfa98xx_parameters.h
DSC = {
    0: "DEVICE", 1: "PROFILE", 2: "REGISTER", 3: "STRING", 4: "FILE",
    5: "PATCH", 6: "MARKER", 7: "MODE", 8: "SET_INPUT_SELECT",
    9: "SET_OUTPUT_SELECT", 10: "SET_PROGRAM_CONFIG", 11: "SET_LAGW",
    12: "SET_GAINS", 13: "SET_VBAT_FACTORS", 14: "SET_SENSES_CAL",
    15: "SET_SENSES_DELAY", 16: "BITFIELD", 17: "DEFAULT", 18: "LIVEDATA",
    19: "LIVEDATA_STRING", 20: "GROUP", 21: "CMD", 22: "SET_MBDRC",
    23: "FILTER", 24: "NOINIT", 25: "FEATURES", 26: "CFMEM",
    27: "SET_FWK_USE_CASE", 28: "SET_VDDP_CONFIG",
}


class Cnt:
    def __init__(self, path):
        self.b = open(path, "rb").read()

    def desc_ptr(self, off):
        v = struct.unpack_from("<I", self.b, off)[0]
        return v & 0xFFFFFF, (v >> 24) & 0xFF

    def cstr(self, off):
        if not 0 < off < len(self.b):
            return None
        end = self.b.find(b"\0", off)
        if end < 0:
            return None
        return self.b[off:end].decode("ascii", "replace")

    def header(self):
        b = self.b
        if len(b) < 46:
            raise ValueError("file too small for a TfaContainer_t header")
        return {
            "id": b[0:2].decode("ascii", "replace"),
            "version": b[2:4].decode("ascii", "replace"),
            "subversion": b[4:6].decode("ascii", "replace"),
            "size": struct.unpack_from("<I", b, 6)[0],
            "crc": struct.unpack_from("<I", b, 10)[0],
            "rev": struct.unpack_from("<H", b, 14)[0],
            "customer": b[16:24].decode("ascii", "replace").rstrip("\0"),
            "application": b[24:32].decode("ascii", "replace").rstrip("\0"),
            "type": b[32:40].decode("ascii", "replace").rstrip("\0"),
            "ndev": struct.unpack_from("<H", b, 40)[0],
            "nprof": struct.unpack_from("<H", b, 42)[0],
            "nlive": struct.unpack_from("<H", b, 44)[0],
        }

    def devices(self):
        """Walk the container index and return device lists with profiles."""
        hdr = self.header()
        out = []
        for i in range(hdr["ndev"]):
            base, typ = self.desc_ptr(46 + i * 4)
            if typ != 0 or not 0 < base < len(self.b):
                continue
            length = self.b[base]
            dev = {
                "index": i,
                "offset": base,
                "length": length,
                "bus": self.b[base + 1],
                "dev_addr": self.b[base + 2],
                "func": self.b[base + 3],
                "name": None,
                "profiles": [],
            }
            nm_off, _ = self.desc_ptr(base + 8)
            dev["name"] = self.cstr(nm_off)
            for j in range(length):
                poff, ptyp = self.desc_ptr(base + 12 + j * 4)
                if ptyp != 1 or not 0 < poff < len(self.b):
                    continue
                plen, group, pid = struct.unpack_from("<BBH", self.b, poff)
                pname_off, _ = self.desc_ptr(poff + 4)
                prof = {
                    "name": self.cstr(pname_off),
                    "group": group,
                    "id": pid,
                    "length": plen,
                    "items": [],
                }
                for k in range(max(0, plen - 1)):
                    ioff, ityp = self.desc_ptr(poff + 8 + k * 4)
                    item = {"type": DSC.get(ityp, ityp), "offset": ioff}
                    if ityp == 3:
                        item["string"] = self.cstr(ioff)
                    elif ityp == 16:
                        value, field = struct.unpack_from("<HH", self.b, ioff)
                        item["value"] = value
                        item["field"] = field
                    prof["items"].append(item)
                dev["profiles"].append(prof)
            out.append(dev)
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cnt")
    ap.add_argument("--json")
    args = ap.parse_args()

    c = Cnt(args.cnt)
    hdr = c.header()
    devs = c.devices()

    print("== TfaContainer_t")
    for k in ("id", "version", "subversion", "size", "customer",
              "application", "type", "ndev", "nprof", "nlive"):
        print(f"   {k:12s} {hdr[k]}")
    print(f"   crc          0x{hdr['crc']:08x}")

    for d in devs:
        print(f"\n== DEV{d['index']} 0x{d['dev_addr']:02x}  name={d['name']!r} "
              f"(bus={d['bus']} func={d['func']} items={d['length']})")
        for p in d["profiles"]:
            print(f"   PROFILE {p['name']!r} group={p['group']} "
                  f"id=0x{p['id']:04x} items={len(p['items'])}")
            for it in p["items"]:
                if it["type"] == "STRING":
                    print(f"      STRING   {it['string']!r}")
                elif it["type"] == "BITFIELD":
                    print(f"      BITFIELD field=0x{it['field']:04x} "
                          f"value={it['value']}")
                else:
                    print(f"      {it['type']}")

    if args.json:
        with open(args.json, "w") as f:
            json.dump({"header": hdr, "devices": devs}, f, indent=2)
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    sys.exit(main())
