import os,tempfile,unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from desktop_features import CursorHider,capture_items,saved_consoles,remember_console,clock_text,format_bytes

class CaptureLibraryTests(unittest.TestCase):
 def test_library_ignores_partial_recordings_and_empty_files(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);(root/'Screenshots').mkdir();(root/'Recordings').mkdir()
   (root/'Screenshots'/'one.png').write_bytes(b'photo');(root/'Screenshots'/'empty.png').touch()
   (root/'Recordings'/'unfinished.partial.mp4').write_bytes(b'incomplete');(root/'Recordings'/'complete.mp4').write_bytes(b'video')
   items=capture_items(root)
   self.assertEqual({i.path.name for i in items},{'one.png','complete.mp4'})
   self.assertEqual([i.path.name for i in capture_items(root,'Videos')],['complete.mp4'])
 def test_newest_limit_is_global_across_media_types(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder)
   for name in ('Screenshots','Recordings'):(root/name).mkdir()
   for name,stamp in [('Screenshots/old.png',1),('Recordings/new.mp4',3),('Screenshots/middle.png',2)]:
    path=root/name;path.write_bytes(b'x');os.utime(path,(stamp,stamp))
   self.assertEqual([i.path.name for i in capture_items(root,limit=2)],['new.mp4','middle.png'])
 def test_missing_capture_folders_are_empty(self):
  with tempfile.TemporaryDirectory() as folder:self.assertEqual(capture_items(folder),[])
 def test_subdirectories_are_not_followed(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);(root/'Screenshots'/'nested').mkdir(parents=True);(root/'Screenshots'/'nested'/'private.png').write_bytes(b'x')
   self.assertEqual(capture_items(root),[])

class SavedConsolesTests(unittest.TestCase):
 profiles={'balanced':{},'maximum':{}}
 def test_updating_host_replaces_its_name_and_profile(self):
  data={'consoles':[{'name':'Old','host':'192.168.1.100','profile':'balanced'}]}
  items=remember_console(data,'Living room','192.168.1.100','maximum',self.profiles)
  self.assertEqual(items,[{'name':'Living room','host':'192.168.1.100','profile':'maximum'}])
 def test_malformed_saved_settings_do_not_break_dialog(self):
  self.assertEqual(saved_consoles({'consoles':'bad'},self.profiles),[])
  items=saved_consoles({'consoles':[None,{'host':'bad'},{'host':'192.168.1.100','profile':'removed'}]},self.profiles)
  self.assertEqual(items[0]['profile'],'balanced')
 def test_invalid_host_or_profile_cannot_be_saved(self):
  for host,profile in [('not an ip','balanced'),('192.168.1.100','missing')]:
   with self.assertRaises(ValueError):remember_console({},'PS5',host,profile,self.profiles)
 def test_favourites_stay_bounded(self):
  data={}
  for i in range(1,20):data['consoles']=remember_console(data,'PS5',f'192.168.1.{i}','balanced',self.profiles)
  self.assertEqual(len(data['consoles']),12);self.assertEqual(data['consoles'][0]['host'],'192.168.1.19')
 def test_session_labels(self):
  self.assertEqual(clock_text(3661),'01:01:01');self.assertEqual(clock_text(-3),'00:00:00');self.assertEqual(format_bytes(1048576),'1.0 MB')

class FakeWindow:
 def __init__(self):self.changes=[];self.timers={};self.count=0
 def configure(self,cursor):self.changes.append(cursor)
 def after(self,_,callback):self.count+=1;self.timers[self.count]=callback;return self.count
 def after_cancel(self,timer):del self.timers[timer]
 def fire(self):
  callbacks=list(self.timers.values());self.timers.clear()
  for callback in callbacks:callback()

class CursorHiderTests(unittest.TestCase):
 def test_moving_the_mouse_over_a_window_changes_nothing(self):
  # Any change here repaints over the video, so a moving mouse must not cause one.
  window=FakeWindow();cursor=CursorHider(window)
  for _ in range(50):cursor.moved()
  self.assertEqual(window.changes,[]);self.assertEqual(window.timers,{})
 def test_a_pause_hides_it_and_movement_brings_it_back_once(self):
  window=FakeWindow();cursor=CursorHider(window);cursor.active=True
  for _ in range(5):cursor.moved()
  self.assertEqual(window.changes,[]);self.assertEqual(len(window.timers),1)
  window.fire();self.assertEqual(window.changes,['none'])
  for _ in range(5):cursor.moved()
  self.assertEqual(window.changes,['none','']);self.assertEqual(len(window.timers),1)
 def test_leaving_fullscreen_shows_it_and_stops_the_timer(self):
  window=FakeWindow();cursor=CursorHider(window);cursor.active=True;cursor.moved();window.fire()
  cursor.moved();cursor.active=False;cursor.moved()
  self.assertEqual(window.changes,['none','']);self.assertEqual(window.timers,{})
