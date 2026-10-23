"""Pure smali transformations: guard legacy access, preserve DAP and cleanup."""
import importlib.util
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('patch_geq', ROOT/'tools/patch-misound.py')
patch = importlib.util.module_from_spec(spec); spec.loader.exec_module(patch)
U = '    iget-object v0, p0, Lcom/miui/misound/view/GeqView;->u:Lp0/c;\n'
INIT = '''.method private a()V
    .registers 4
    invoke-static {}, Lp0/c;->r()Lp0/c;
    iput-object v0, p0, Lcom/miui/misound/view/GeqView;->u:Lp0/c;
    invoke-virtual {v0}, Lp0/c;->g()V
    return-void
.end method
'''
PRESET = '''.method public e(I[F)V
    .registers 5
    invoke-virtual {p0, p2}, Lcom/miui/misound/view/GeqView;->f([F)V
    if-ge p1, v0, :cond_2b
'''+U+'''    invoke-virtual {v0, v1, p1, p2}, Lp0/c;->z(Landroid/content/Context;IF)V
    :cond_2b
    return-void
.end method
'''
TOUCH = '''.method public onTouchEvent(Landroid/view/MotionEvent;)Z
    invoke-virtual {v0, v1}, Lm0/b;->e([I)V
'''+U+'''    invoke-virtual {v0, v1, v6, p1}, Lp0/c;->z(Landroid/content/Context;IF)V
    iget-object p1, p0, Lcom/miui/misound/view/GeqView;->k:[F
    return v0
.end method
'''
DESTROY = '''.method public onDestroy()V
    .registers 6
    invoke-virtual {v1, v2}, Landroid/app/Activity;->unregisterReceiver(Landroid/content/BroadcastReceiver;)V
    const-string v2, "dolby"

    invoke-virtual {v1, v2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1
    invoke-virtual {v1}, Landroid/media/audiofx/AudioEffect;->release()V
    invoke-super {p0}, Landroidx/fragment/app/Fragment;->onDestroy()V
    return-void
.end method
'''
class FixupTest(unittest.TestCase):
    def test_three_legacy_accesses_guarded_without_global_factory_patch(self):
        body=INIT+PRESET+TOUCH
        result=patch.guard_dolby_geq(body)
        self.assertEqual(result.count('->u:Lp0/c;'),3)
        self.assertIn('if-eqz v0, :renoir_legacy_init',result)
        self.assertIn('if-nez v0, :cond_2b',result)
        self.assertIn('if-nez v0, :renoir_legacy_band_done',result)
        self.assertEqual(result.count('Lm0/b;->e([I)V'),body.count('Lm0/b;->e([I)V'))
        self.assertLess(result.index('Lm0/b;->e([I)V'),result.index('if-nez v0, :renoir_legacy_band_done'))
        self.assertIn('->f([F)V',result)
    def test_fail_closed_on_layout_or_extra_legacy_access(self):
        original=INIT+PRESET+TOUCH
        for body in [original+U,original.replace('.registers 4','.registers 5'),
                     original.replace('->z(Landroid/content/Context;IF)V','->q()V'),
                     patch.guard_dolby_geq(original)]:
            with self.assertRaises(ValueError):patch.guard_dolby_geq(body)
    def test_null_destroy_still_releases_and_calls_super(self):
        result=patch.guard_destroy_selection(DESTROY)
        self.assertIn('const/4 v1, 0x0',result)
        self.assertEqual(result.count('return-void'),1)
        for instruction in ['->unregisterReceiver(', '->release()V', '->onDestroy()V']:
            self.assertEqual(result.count(instruction),DESTROY.count(instruction))
        self.assertIn(':renoir_destroy_selection_done',result)
        with self.assertRaises(ValueError):patch.guard_destroy_selection(result)

if __name__=='__main__':unittest.main()
