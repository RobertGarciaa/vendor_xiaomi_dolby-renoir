#!/usr/bin/env python3
"""Run the real controller/service against an in-process AudioEffect contract fake.

No Android device, proprietary blob, or native library is executed. The fake
models positive GET byte counts, equal-priority ownership, rejected writes and
parameter callbacks, so it detects the failure modes found in code review.
"""
from pathlib import Path
import shutil, subprocess, tempfile, textwrap
ROOT = Path(__file__).resolve().parents[1]
STUBS = {
'android/os/IBinder.java': 'package android.os; public interface IBinder {}',
'android/os/Looper.java': 'package android.os; public class Looper { public static Looper getMainLooper(){return new Looper();}}',
'android/os/UserHandle.java': 'package android.os; public class UserHandle {public static int myUserId(){return 0;}}',
'android/os/SystemProperties.java': 'package android.os; public class SystemProperties {public static boolean getBoolean(String key,boolean d){return true;}}',
'android/os/Handler.java': '''package android.os; import java.util.*; public class Handler {
 static List<Runnable> q=new ArrayList<>(); public Handler(Looper l){} public boolean post(Runnable r){q.add(r);return true;}
 public boolean postDelayed(Runnable r,long delay){return post(r);} public void removeCallbacks(Runnable r){q.removeIf(x->x==r);}
 public void removeCallbacksAndMessages(Object x){q.clear();} public static void drain(){int n=0;while(!q.isEmpty()){
 if(++n>10000)throw new AssertionError("callback loop");q.remove(0).run();}} }''',
'android/util/Log.java': '''package android.util; public class Log {
 public static int i(String t,String m){return 0;} public static int w(String t,String m){return 0;}
 public static int w(String t,String m,Throwable e){return 0;}public static int e(String t,String m,Throwable e){return 0;}}''',
'android/content/SharedPreferences.java': '''package android.content; public interface SharedPreferences {
 boolean getBoolean(String k,boolean d); int getInt(String k,int d); String getString(String k,String d);
 boolean contains(String k); Editor edit(); interface Editor {Editor putBoolean(String k,boolean v);
 Editor putInt(String k,int v);Editor putString(String k,String v);Editor remove(String k);void apply();}}''',
'android/content/Context.java': '''package android.content; import java.util.*; public class Context {
 public static final int MODE_PRIVATE=0; static final Map<String,Object> values=new HashMap<>();
 public boolean isDeviceProtectedStorage(){return true;}public Context getApplicationContext(){return this;}public Context createDeviceProtectedStorageContext(){return this;}
 public <T> T getSystemService(Class<T> c){try{return c.getConstructor().newInstance();}catch(Exception e){throw new RuntimeException(e);}}
 public void startService(Intent i){}public void sendBroadcast(Intent i){}public void registerReceiver(BroadcastReceiver r,IntentFilter f){}
 public void unregisterReceiver(BroadcastReceiver r){}
 public SharedPreferences getSharedPreferences(String f,int mode){return new SharedPreferences(){
 public boolean getBoolean(String k,boolean d){return (boolean)values.getOrDefault(k,d);}
 public int getInt(String k,int d){return (int)values.getOrDefault(k,d);}
 public String getString(String k,String d){return (String)values.getOrDefault(k,d);}
 public boolean contains(String k){return values.containsKey(k);}public Editor edit(){return new Editor(){
 public Editor putBoolean(String k,boolean v){values.put(k,v);return this;}
 public Editor putInt(String k,int v){values.put(k,v);return this;}
 public Editor putString(String k,String v){values.put(k,v);return this;}
 public Editor remove(String k){values.remove(k);return this;}public void apply(){}};}};}}''',
'android/content/Intent.java': '''package android.content; public class Intent {
 public static final String ACTION_USER_SWITCHED="user",EXTRA_USER_HANDLE="user_handle";
 public Intent(String s){}public Intent(Context c,Class<?> t){}public Intent setPackage(String p){return this;}
 public int getIntExtra(String n,int d){return d;}}''',
'android/content/IntentFilter.java': 'package android.content; public class IntentFilter {public IntentFilter(String a){}}',
'android/content/BroadcastReceiver.java': 'package android.content; public abstract class BroadcastReceiver {public abstract void onReceive(Context c,Intent i);}',
'android/app/Service.java': '''package android.app; import android.content.*;import android.os.*;
 public class Service extends Context {public static final int START_STICKY=1;
 protected void dump(java.io.FileDescriptor f,java.io.PrintWriter w,String[] a){}
 public void onCreate(){}public int onStartCommand(Intent i,int f,int s){return 0;}
 public IBinder onBind(Intent i){return null;}public void onDestroy(){}public void stopSelf(){}}''',
'android/media/AudioDeviceInfo.java': 'package android.media; public class AudioDeviceInfo {}',
'android/media/AudioDeviceCallback.java': '''package android.media; public class AudioDeviceCallback {
 public void onAudioDevicesAdded(AudioDeviceInfo[] d){}public void onAudioDevicesRemoved(AudioDeviceInfo[] d){}}''',
'android/media/AudioManager.java': '''package android.media; import android.os.Handler;public class AudioManager {
 public AudioManager(){}public void registerAudioDeviceCallback(AudioDeviceCallback c,Handler h){}
 public void unregisterAudioDeviceCallback(AudioDeviceCallback c){}
 public static AudioServerStateCallback server;public static java.util.concurrent.Executor executor;
 public static class AudioServerStateCallback {public void onAudioServerDown(){}public void onAudioServerUp(){}}
 public void setAudioServerStateCallback(java.util.concurrent.Executor e,AudioServerStateCallback c){executor=e;server=c;}
 public void clearAudioServerStateCallback(){server=null;}
 public static void down(){executor.execute(()->server.onAudioServerDown());}
 public static void up(){executor.execute(()->server.onAudioServerUp());}}''',
'android/media/audiofx/AudioEffect.java': '''package android.media.audiofx;
 import java.util.*;import java.nio.*;public class AudioEffect {
 public static final int SUCCESS=0; static List<AudioEffect> handles=new ArrayList<>();
 static Map<Integer,int[]> parameters=new HashMap<>(); public static int creations=0,writes=0,shortReply=-1;
 int priority;public boolean released;OnControlStatusChangeListener control;
 OnEnableStatusChangeListener enabled;OnParameterChangeListener changed;
 public interface OnControlStatusChangeListener {void onControlStatusChange(AudioEffect e,boolean control);}
 public interface OnEnableStatusChangeListener {void onEnableStatusChange(AudioEffect e,boolean enabled);}
 public interface OnParameterChangeListener {void onParameterChange(AudioEffect e,int status,byte[] p,byte[] v);}
 public void setControlStatusListener(OnControlStatusChangeListener l){control=l;}
 public void setEnableStatusListener(OnEnableStatusChangeListener l){enabled=l;}
 public void setParameterListener(OnParameterChangeListener l){changed=l;}
 @SuppressWarnings("this-escape") public AudioEffect(UUID t,UUID i,int priority,int session){this.priority=priority;creations++;
 AudioEffect old=handles.isEmpty()?null:handles.get(0);int at=0;
 while(at<handles.size()&&handles.get(at).priority>priority)at++;handles.add(at,this);
 if(at==0&&old!=null&&old.control!=null)old.control.onControlStatusChange(old,false);}
 public boolean hasControl(){return !released&&!handles.isEmpty()&&handles.get(0)==this;}
 public void release(){boolean was=hasControl();released=true;handles.remove(this);
 if(was&&!handles.isEmpty()&&handles.get(0).control!=null)handles.get(0).control.onControlStatusChange(handles.get(0),true);}
 static int read(byte[] b,int o){return ByteBuffer.wrap(b).order(ByteOrder.LITTLE_ENDIAN).getInt(o);}
 public int setParameter(int cmd,byte[] value){if(!hasControl())return -5;writes++;
 int param=read(value,0);int key=param;int start=8;
 if(param==0x1000000){key=0x1000005+(read(value,12)<<16)+(read(value,8)<<8);start=16;}
 int[] a=new int[(value.length-start)/4];for(int n=0;n<a.length;n++)a[n]=read(value,start+4*n);parameters.put(key,a);
 for(AudioEffect h:new ArrayList<>(handles))if(h!=this&&h.changed!=null)h.changed.onParameterChange(h,0,new byte[]{5},value);
 return 0;}
 public int getParameter(int cmd,byte[] out){if(shortReply>=0)return shortReply;
 boolean scoped=cmd>=0x1000005&&cmd<0x2000000;int key=scoped?cmd:cmd-5;int n=scoped?(((cmd>>16)&255)==110?20:1):1;
 int[] a=parameters.getOrDefault(key,new int[n]);ByteBuffer b=ByteBuffer.wrap(out).order(ByteOrder.LITTLE_ENDIAN);
 for(int x:a)b.putInt(x);return a.length*4;}
 public int setEnabled(boolean v){if(!hasControl())return -5;return 0;}
 }''',
'org/lineageos/dolby/ContractTest.java': '''package org.lineageos.dolby;
 import android.os.Handler;import android.media.audiofx.AudioEffect;import java.util.*;
 public class ContractTest {
 static void check(boolean b,String m){if(!b)throw new AssertionError(m);}
 public static void main(String[] args){
 DolbyEffectService service=new DolbyEffectService();service.onCreate();
 DolbyEffectController c=DolbyEffectController.get(service);
 check(Boolean.FALSE.equals(c.readEnabled()),"GET returning 4 bytes must succeed");
 AudioEffect.shortReply=0;check(c.readEnabled()==null,"short read must fail");AudioEffect.shortReply=-1;
 DolbyEffectService.DolbyAudioEffect ui=new DolbyEffectService.DolbyAudioEffect(0,0);
 check(ui.hasControl(),"MiSound takes equal-priority control");int creations=AudioEffect.creations;
 c.readEnabled();c.readProfile();c.hasControl();
 check(AudioEffect.creations==creations&&ui.hasControl(),"reads must not steal control");
 ui.setProfile(2);ui.setDsOn(true);int[] gains=new int[20];gains[0]=17;
 ui.setProfileParameter(2,110,gains);Handler.drain();
 check(c.getRequestedProfile()==2&&c.isEnabledRequested(),"MiSound changes must persist");
 check(Arrays.equals(c.getProfileParameter(110,20),gains),"20-value positive GET must work");
 int writes=AudioEffect.writes;c.captureEngineState("route");
 check(AudioEffect.writes==writes&&ui.hasControl(),"route observation must not overwrite UI");
 check(c.setEnabled(false).ok,"explicit QS change must succeed");
 check(ui.hasControl(),"temporary QS writer must release control back to open MiSound");
 check(ui.getProfile()==2&&!ui.getDsOn(),"QS must preserve live profile");
 ui.setProfile(1);ui.setDsOn(true);Handler.drain();
 check(c.getRequestedProfile()==1&&c.isEnabledRequested(),"edits after QS must still work");
 ui.release();Handler.drain();int before=AudioEffect.creations;
 check(c.hasControl()&&AudioEffect.creations==before,"keeper must regain control without recreation");
 DolbyEffectService.DolbyAudioEffect high=new DolbyEffectService.DolbyAudioEffect(100,0);
 check(!c.setEnabled(false).ok&&high.hasControl(),"higher priority must reject, not fake success");
 high.release();
 android.media.AudioManager.down();Handler.drain();
 int downCreations=AudioEffect.creations;
 check(c.readEnabled()==null&&AudioEffect.creations==downCreations,"reads must not recreate while server down");
 android.media.AudioManager.up();Handler.drain();
 check(c.readProfile()==1&&Boolean.TRUE.equals(c.readEnabled()),"server restart must restore state");
 service.onDestroy();
 DolbyEffectService next=new DolbyEffectService();next.onCreate();Handler.drain();
 check(c.readProfile()==1&&Boolean.TRUE.equals(c.readEnabled()),"restart must restore observed UI state");
 next.onDestroy();
 DolbyEffectService.DolbyAudioEffect openUi=new DolbyEffectService.DolbyAudioEffect(0,0);
 openUi.setProfile(8);openUi.setDsOn(false);
 DolbyEffectService late=new DolbyEffectService();late.onCreate();Handler.drain();
 check(openUi.hasControl()&&c.readProfile()==8,"late keeper must not steal control or restore stale prefs");
 late.onDestroy();openUi.release();System.out.println("PASS: GET lengths, passive reads, UI persistence, QS lease, rejection, restart");
 }}'''
}

def main():
    javac=shutil.which('javac');java=shutil.which('java')
    if not javac or not java: raise SystemExit('JDK required')
    with tempfile.TemporaryDirectory(prefix='dolby-contract-') as d:
        p=Path(d);src=p/'src'
        for name,text in STUBS.items():
            f=src/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(textwrap.dedent(text))
        for name in ['DolbyEffectService','DolbyEffectController','DolbyPrefs']:
            shutil.copy2(ROOT/'packages/DolbyControl/src/org/lineageos/dolby'/f'{name}.java',src/'org/lineageos/dolby')
        subprocess.run([javac,'-Xlint:all','-d',str(p/'classes')]+[str(f) for f in src.rglob('*.java')],check=True)
        subprocess.run([java,'-cp',str(p/'classes'),'org.lineageos.dolby.ContractTest'],check=True)
if __name__=='__main__':main()
