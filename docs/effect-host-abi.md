# Effect host ABI correction — 2026-10-23

The first flashed build had two independent defects:

1. DolbyControl in `/system/priv-app` lacked its system privileged permission
   allowlist for `MODIFY_AUDIO_ROUTING`; system_server repeatedly aborted.
2. `android.hardware.audio.service` is ELF32 and loads the HIDL effect factory,
   but the image contained DAP only in `/vendor/lib64/soundfx`.

The permission fix installs the XML on system. The ABI fix keeps the existing
32-bit core/audio HAL and adds unmodified Redwood ARM builds of only:

- `vendor/lib/soundfx/libswdap.so`
- `vendor/lib/libdapparamstorage.so`
- `vendor/lib/vendor.dolby.hardware.dms@2.0.so`

The same modules retain their ARM64 variants. DMS daemon/implementation stay
64-bit; HIDL Binder carries requests from the 32-bit client library. No stub,
C++ pointer cast, global system library replacement or HAL bitness flip is used.
The blobs were recovered from the previous Redwood analysis staging copy;
SHA256/size pins are in proprietary-files.sha256sum. They remain git-ignored.

## Why the old scan rejected ARM

The old research `find_lib()` searched vendor/lib64 before vendor/lib for
**both** ABIs. This made 32-bit size_t symbols (`...Ejj`, `_Znwj`) appear
unresolved against 64-bit providers (`...Emm`, `_Znwm`). That result was invalid.

The new checker selects the exact ELF class **and machine**, follows product
Bionic APEX links, parses readelf's multiword ARM IFUNC types, and preserves
symbol versions instead of reading the trailing `(2)` as a symbol name.

## Checks

```bash
python3 tools/verify-blobs.py
python3 -m unittest discover -s tests -p 'test_elf_deps.py'
python3 tools/check-elf-deps.py \
  --product-out /path/to/out/target/product/renoir \
  --blob-root proprietary \
  proprietary/vendor/lib/soundfx/libswdap.so \
  proprietary/vendor/lib/libdapparamstorage.so \
  proprietary/vendor/lib/vendor.dolby.hardware.dms@2.0.so
```

The original three ARM blobs resolve all strong imports (including symbol
versions) against the current product and the ARM blob overlay. Provider paths
must still match the on-device vendor linker namespace. Static resolution does
not prove runtime service readiness, processing correctness or acoustic safety.

After the actual image is rebuilt:

```bash
python3 tools/check-product-install.py --product-out /path/to/product/renoir
python3 tools/check-elf-deps.py --product-out /path/to/product/renoir \
  /path/to/product/renoir/vendor/lib/soundfx/libswdap.so
```

The old image will fail: it has neither the permission XML nor the ARM DAP.
Do not flash the unchanged old ZIP. Do not clear app/user data to fix either
problem. Keep enforcing. Confirm system_server survives, DMS registers, DAP
loads and creates, routes work, and screen-close/reboot state persists before
calling the port operational. A successful module build is not a boot test.
