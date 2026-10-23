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
