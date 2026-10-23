# MiSound GEQ on renoir

Source fix, 2026-10-23. No APK/ROM compilation, installation or acoustic
validation was performed for this revision.

## Findings

The pinned Redwood GeqView initializes `p0/c.r()` even when its `w` Dolby
capability is true. The factory may instantiate an absent framework
`android.media.audiofx.DiracSound`. Both the factory and parallel legacy band
writes are unnecessary for the independent DAP path:

`GeqView.d/g/onTouchEvent -> m0/b.e -> c/a.n -> AudioEffect.setParameter`

`m0/b.e` subtracts the mean of the 20 fixed-point band values and sends parameter
110 to all profiles returned by the engine. The same source confirms that
`p0/d` is a different MiSound effect, not the DAP provider. Selecting that class
with `soundfx.type=mi` does not implement it on PixelOS.

The patch only bypasses the three legacy access sites in GeqView **when its
original Dolby capability is true**. Paint setup, UI mirror, saved custom
curve, DAP normalization, preset mapping, DAP writes and non-Dolby behavior are
retained. `GeqView.c()` persists the custom curve; it is not a band writer in
this pinned source (a correction to the handoff).

`y/h.onDestroy` maps an absent selector value to false and continues all original
receiver/effect/Bluetooth cleanup and the superclass call. The earlier two null
guards remain. No early teardown return is added.

## Entry screen

`DolbyEqActivity` is GEQ only, not the Dolby master/profile screen. Its manifest
orientation is `behind`, not landscape. Merely forwarding Settings to it would
remove master/profile controls. The small DolbyControl entry now exposes those
two operations using the existing controller and launches the original
DolbyEqActivity for GEQ. QS and Settings share engine readback and persistence;
there is no second EQ implementation. Unknown engine state is unavailable and
rejected changes are reported. The unsupported general MiSound settings screen
is no longer a prerequisite. No Dirac/MiSound stub or global type prop is added.

The GEQ entry requires both live DAP state and readable original Dolby capability.
An unreadable capability is reported, not forced to true.

## Required build inputs

The prebuilt verifier requires the destroy and GEQ fixup markers as well as the
previous null guards and software UUIDs. The old APK must fail this contract.
Before the next user-run ROM build, regenerate MiSound from the pinned stock
input with the updated import pipeline, for example from the ROM root:

```sh
vendor/xiaomi/dolby-renoir/tools/import-misound.sh \
  --dump /home/ccc/dumpyara/working/redwood_global-ota_full-OS2.0.17.0.UMSMIXM-user-14.0-4ddcd3c40c \
  --signing-keys vendor/lineage-priv/keys
```

Use the actual ROM signing keys if different. Soong signs its imported APK using
its configured platform certificate; direct test installs must match the
installed signature. Do not uninstall or clear data to hide a signature issue.
Native Dolby blobs and DAX tuning are unchanged; re-extracting those is not
needed. Build the updated DolbyControl and vendor SELinux policy/contexts as part
of the ROM. An APK-only update cannot install property contexts.

## Live device observation before this revision

Read-only ADB saw `Enforcing`, but the capability's label was still
`u:object_r:vendor_audio_prop:s0`, with `Access denied finding property`.
The value was blank to shell; that does not prove the stored value is false or
missing. The dedicated `vendor_dolby_config_prop` policy already in this
repository has not been installed on that device. No current crash buffer entry
was available in this observation; earlier crash evidence is in the handoff.

## Validation gates after the user builds/flashes

1. Check `getprop -Z ro.vendor.audio.dolby.dax.support` is the dedicated Dolby
   type, `getprop ...` is true, and app property-read denials are absent.
2. Settings and QS: toggle, each profile, engine readback, back/reopen.
3. Enter original GEQ: no Dirac/MiSound construction in Dolby mode; each preset,
   custom choice and drag must retain responsive UI and not crash.
4. Capture the service's read-only engine dump before and after changing GEQ:
   `adb shell dumpsys activity service org.lineageos.dolby/.DolbyEffectService`.
   The added dump reads the existing keeper's enabled/profile state and all four
   profiles' 20 values for parameter 110. It never creates a writer or restores
   preferences. An unavailable read is reported as an error. Confirm live DAP
   parameter 110 readback changes, including after reopening;
   do not count a displayed curve or log line as proof of effect acceptance.
5. Test pause/resume, QS toggles during editor use and reboot persistence.
6. Listen at moderate volume with fixed test content, then compare measured
   output if available. DAP code reachability does not prove audible improvement.

The pipeline has been checked against the original disassembly with pure text
transformations. This does not substitute for smali assembly, ART verification,
Java/ROM compilation or these device gates.
