#!/usr/bin/env python3
"""Pure text/macro regression checks; no APK, DEX or policy compilation."""
from pathlib import Path
import importlib.util
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('misound_patch',ROOT/'tools/patch-misound.py')
patch=importlib.util.module_from_spec(spec);spec.loader.exec_module(patch)
METHOD='''.method private w0()V
    .registers 10
    invoke-virtual {v0}, Lmiuix/preference/DropDownPreference;->getValue()Ljava/lang/String;

    move-result-object v0

    const-string v1, "dolby"
    invoke-virtual {v0, v1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    return-void
.end method
'''

PREF_METHOD='''.method public onCreatePreferences(Landroid/os/Bundle;Ljava/lang/String;)V
    .registers 8
    invoke-direct {p0}, Ly/h;->r0()V

    iget-object p1, p0, Ly/h;->w:Lmiuix/preference/DropDownPreference;

    invoke-virtual {p1}, Lmiuix/preference/DropDownPreference;->getValue()Ljava/lang/String;

    move-result-object p1

    const-string p2, "dolby"

    invoke-virtual {p1, p2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result p1

    invoke-static {p1, p1, p1}, Lm0/d;->g(ZZZ)V
    return-void
.end method
'''

class EntryTests(unittest.TestCase):
    def test_guard_before_equals_no_new_selection(self):
        value=patch.guard_effect_selection('before\n'+METHOD+'after\n')
        self.assertTrue(value.startswith('before\n') and value.endswith('after\n'))
        self.assertLess(value.index('if-nez v0, :renoir_selection_ready'),value.index('->equals'))
        self.assertEqual(value.count('const-string v1, "dolby"'),1)
        self.assertEqual(value.count(patch.SELECTION_GUARD_MARKER),1)
        self.assertIn('return-void\n\n    :renoir_selection_ready',value)

    def test_wrong_or_repatched_input_rejected(self):
        for body in ('',METHOD+METHOD,METHOD.replace('.registers 10','.registers 9'),
                     METHOD.replace('DropDownPreference','OtherPreference'),patch.guard_effect_selection(METHOD)):
            with self.assertRaises(ValueError):patch.guard_effect_selection(body)

    def test_create_guard_resolves_null_to_false_not_early_return(self):
        body=patch.guard_create_preferences_selection(PREF_METHOD)
        self.assertLess(body.index('if-nez p1, :renoir_create_selection_known'),
                        body.index('->equals'))
        self.assertIn('const/4 p1, 0x0',body)
        self.assertIn(':renoir_create_selection_done',body)
        # The screen setup before and after the consumer must survive.
        self.assertIn('invoke-direct {p0}, Ly/h;->r0()V',body)
        self.assertIn('Lm0/d;->g(ZZZ)V',body)
        # No value is substituted for the missing selection.
        self.assertEqual(body.count('const-string p2, "dolby"'),1)
        for bad in ('',PREF_METHOD+PREF_METHOD,
                    PREF_METHOD.replace('.registers 8','.registers 9'),
                    PREF_METHOD.replace('Ly/h;->r0()V','Ly/h;->r9()V'),
                    patch.guard_create_preferences_selection(PREF_METHOD)):
            with self.assertRaises(ValueError):patch.guard_create_preferences_selection(bad)

    def test_property_is_exact_and_typed(self):
        lines=[s.split() for s in (ROOT/'sepolicy/vendor/property_contexts').read_text().splitlines()
               if s.strip() and not s.lstrip().startswith('#')]
        self.assertEqual(lines,[['ro.vendor.audio.dolby.dax.support',
            'u:object_r:vendor_dolby_config_prop:s0','exact','bool']])

    def test_policy_has_only_narrow_read_permissions(self):
        source=(ROOT/'sepolicy/vendor/property.te').read_text()
        rules=[s for s in source.splitlines() if s and not s.startswith('#')]
        self.assertEqual(rules,['vendor_restricted_prop(vendor_dolby_config_prop)',
            'get_prop(platform_app_all, vendor_dolby_config_prop)',
            'get_prop(shell, vendor_dolby_config_prop)'])
        self.assertNotIn('get_prop(appdomain',source)
        self.assertNotIn('set_prop(',source)

if __name__=='__main__':unittest.main()
