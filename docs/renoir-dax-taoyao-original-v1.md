> Historical landscape-only candidate; active build input is now
> [speaker settings v2](renoir-dax-taoyao-speaker-v2.md). This module remains for rollback.

# Renoir taoyao original landscape candidate

Selected by user on 2026-10-25. This experimental build input replaces only
speaker_landscape Audio Optimizer L/R gains with the original taoyao values,
including positive gains. It is not a measured optimum or a safety certification.
No averaging with dubai or additional guessed cuts: the donor already includes
the shared 47 Hz, 469 Hz and 3750–4688 Hz attenuation patterns.

Reference: taoyao OS1.0.34.0.ULIMIXM (byte-identical XML to prior OS1.0.26 source).
SHA256: 592576b5796841090534859d8caa0c6ac6f87a9ed618910bd51af4a0c4487b8e.
Generated SHA256: ace26880c50c31ce8e0f7ad489dd9eee344e922a2737713a82d3d77b39933d66.
38 gain fields differ from Redwood; 39 differ from static-v1.

Preserved: Redwood engine, immutable original XML, all profiles (including
Dynamic and Music), GEQ, IEQ, regulator, bass, volume processing, portrait,
headphones and other endpoints. Renoir CNT, ACDB, mixer, kernel and amplifier
protection/calibration are untouched. No logical/physical channel remapping.

Soong installs renoir_dax_taoyao_original_v1 through dolby-dax-default.xml.
Only XML generation and semantic verification were run, not a ROM build,
flash, live installation or acoustic measurement. After the user builds/flashes,
verify installed SHA and compare at low volume using fixed profile and position.
Preserving protection settings does not prove the new curve safe at all levels.

Rollback: change dolby-dax-default.xml src in Android.bp back to
:renoir_dax_static_v1. That module is retained and its generated hash remains
84abb44348ab88ec97adfcc742f27ec8b8ddf69316921d7b2d61728ae9a4205e.

Reproduce candidate:

```sh
python3 tools/gen-renoir-dax.py --stock proprietary/vendor/etc/dolby/dax-default.xml --donor tuning/taoyao-dax-default.xml --out /tmp/dax-taoyao.xml --report /tmp/dax-taoyao.json
python3 tests/test_dax_tuning.py
python3 tests/test_taoyao_tuning.py
```
