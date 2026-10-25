# Renoir taoyao speaker settings v2

User-selected experiment, 2026-10-25. Extends the landscape-only trial to:

- Original taoyao speaker_landscape and speaker_portrait tuning blocks, including
  Optimizer (positive gains retained), Regulator, Bass MBDRC and Virtual Bass.
- Original taoyao speaker endpoint settings in all nine profiles.

Both speaker routing blocks (device IDs, orientation, channel count and sample
rate) match the Redwood source. Portrait tuning is already identical. Profile
speaker settings actually differ in Dynamic (0), Movie (1), Music (2), Voice (8);
Custom and mobility profile speaker settings are already identical.

Preserved byte-for-byte outside the selected blocks: shared profile globals,
IEQ/GEQ presets, headphone/Bluetooth/USB/other endpoint tuning, XML versions and
technology authorization. Shared globals are deliberately retained because they
also govern non-speaker endpoints. This is a speaker-only transplant, not the
entire taoyao XML.

Redwood DMS/engine libraries and renoir kernel, CNT, ACDB, mixer, amplifier
protection/calibration are untouched. DAX's own speaker processing changes to the
donor settings and must not be described as unchanged protection throughout.
No foreign amplifier calibration or engine binaries are extracted/installed.

The pinned taoyao XML is already extracted from the supplied stock and stored at
`tuning/taoyao-dax-default.xml`. No additional extraction is needed.
Reference SHA256: 592576b5796841090534859d8caa0c6ac6f87a9ed618910bd51af4a0c4487b8e.
Generated SHA256: 20fd40e2be4cab7e2b15d8fcb23ebd3f0e5577d4ae1459a5bf0833dcf2669459.

Active Soong module: renoir_dax_taoyao_speaker_v2. Destination remains
/vendor/etc/dolby/dax-default.xml. Format/tool match does not establish acoustic
fitness or complete runtime compatibility. No ROM build, flashing, installation
or acoustic validation was performed. Compare Music and Dynamic independently
after the user builds/flashes, beginning at low volume.

Reproduce:

```sh
python3 tools/gen-renoir-dax.py --stock proprietary/vendor/etc/dolby/dax-default.xml --donor tuning/taoyao-dax-default.xml --speaker-settings --out /tmp/dax-taoyao-speaker.xml --report /tmp/dax-taoyao-speaker.json
python3 tests/test_dax_tuning.py
python3 tests/test_taoyao_tuning.py
```

Rollback: change dolby-dax-default.xml src in Android.bp to
:renoir_dax_taoyao_original_v1 for the landscape-only trial, or
:renoir_dax_static_v1 for static-v1. Both generator modules remain reproducible.
