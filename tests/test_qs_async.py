from pathlib import Path
import importlib.util,tempfile,subprocess,shutil
repo=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('old',repo/'tests/test_controller.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
stubs=m.STUBS.copy()
stubs['android/os/Handler.java'] = """package android.os; import java.util.*; public class Handler {
 static class Entry {Handler owner;Runnable r;Entry(Handler h,Runnable v){owner=h;r=v;}}
 static List<Entry> q=new ArrayList<>();public Handler(Looper l){}
 public boolean post(Runnable r){q.add(new Entry(this,r));return true;}
 public boolean postDelayed(Runnable r,long delay){return post(r);}
 public void removeCallbacks(Runnable r){q.removeIf(x->x.owner==this&&x.r==r);}
 public void removeCallbacksAndMessages(Object x){q.removeIf(e->e.owner==this);}
 public static void drain(){int n=0;while(!q.isEmpty()){
 if(++n>10000)throw new AssertionError("callback loop");q.remove(0).r.run();}}}
"""
s=stubs['android/media/audiofx/AudioEffect.java'].replace('int priority;','public static int delayEnable=0;public static boolean ignoreEnable=false; int priority;')
s=s.replace('parameters.put(key,a);','''if(param==0 && ignoreEnable){} else if(param==0 && delayEnable>0){
 final int k=key;final int[] v=a;final int delay=delayEnable;
 new android.os.Handler(android.os.Looper.getMainLooper()).post(new Runnable(){int left=delay;public void run(){
 if(--left==0)parameters.put(k,v);else new android.os.Handler(android.os.Looper.getMainLooper()).post(this);}});
 }else parameters.put(key,a);''')
stubs['android/media/audiofx/AudioEffect.java']=s
s=stubs['org/lineageos/dolby/ContractTest.java']
point=' DolbyEffectService.DolbyAudioEffect high='
insert='''
 final int[] completed={0};final boolean[] success={false};
 AudioEffect.delayEnable=4;int initialWrites=AudioEffect.writes;
 c.setEnabledAsync(false,r->{completed[0]++;success[0]=r.ok;});
 check(c.isEnablePending()&&Boolean.TRUE.equals(c.readEnabled()),"old readback must stay pending");
 c.setEnabledAsync(false,r->{throw new AssertionError("duplicate toggle accepted");});
 check(AudioEffect.writes==initialWrites+1,"pending taps must not send repeated writes");
 Handler.drain();check(completed[0]==1&&success[0]&&!c.isEnablePending(),"delayed DMS confirmation succeeds once");
 check(c.readProfile()==1,"toggle preserves profile");
 AudioEffect.delayEnable=0;AudioEffect.ignoreEnable=true;initialWrites=AudioEffect.writes;
 c.setEnabledAsync(true,r->{completed[0]++;success[0]=r.ok;});Handler.drain();
 check(completed[0]==2&&!success[0]&&!c.isEnablePending(),"missing confirmation fails within bounded reads");
 check(AudioEffect.writes==initialWrites+1,"timeout must not resend a command");
 AudioEffect.ignoreEnable=false;
 c.setEnabledAsync(true,r->{completed[0]++;success[0]=r.ok;});Handler.drain();
 check(completed[0]==3&&success[0],"new request works after timeout");
 c.setEnabledAsync(false,r->{completed[0]++;success[0]=r.ok;});
 service.onDestroy();Handler.drain();
 check(completed[0]==4&&!success[0]&&!c.isEnablePending(),"service retirement cancels verification");
 service=new DolbyEffectService();service.onCreate();Handler.drain();c.setEnabled(true);
'''
s=s.replace(point,insert+point)
s=s.replace(' high.release();', ' int rejectedBefore=completed[0];\n c.setEnabledAsync(false,r->{completed[0]++;success[0]=r.ok;});\n check(completed[0]==rejectedBefore+1&&!success[0]&&!c.isEnablePending()&&high.hasControl(),"async rejection must clear pending and preserve higher owner");\n high.release();')

stubs['org/lineageos/dolby/ContractTest.java']=s
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp);src=p/'src'
 for name,text in stubs.items():
  f=src/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(text)
 for name in ['DolbyEffectService','DolbyEffectController','DolbyPrefs']:
  f=repo/'packages/DolbyControl/src/org/lineageos/dolby'/f'{name}.java'
  shutil.copy2(f,src/'org/lineageos/dolby')
 subprocess.run(['javac','-Xlint:all','-d',str(p/'classes'),*[str(f) for f in src.rglob('*.java')]],check=True)
 subprocess.run(['java','-cp',str(p/'classes'),'org.lineageos.dolby.ContractTest'],check=True)
print('PASS: delayed enable, repeated taps, timeout without rewrite, recovery, service retirement')
