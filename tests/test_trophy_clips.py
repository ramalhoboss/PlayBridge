"""Trophy clips: the moment a trophy was earned, kept from the instant replay already in memory, 30 seconds before it and 5 after."""
import queue,sys,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import playbridge as core

IDR=b'\x00\x00\x00\x01\x65'+b'\x88'*20;P=b'\x00\x00\x00\x01\x41'+b'\x9a'*10
TICK=1500;FIRST=900000
def stream(seconds,keyframe_every=60):
 """seconds of a 60 fps stream with sound: (kind, data, pts, dts), a keyframe every so many frames."""
 out=[]
 for i in range(seconds*60):
  pts=FIRST+i*TICK;out.append((1,IDR if i%keyframe_every==0 else P,pts,pts))
  if i%2==0:out.append((2,b'aac',pts,pts))
 return out

class ClipTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.saved=[];self.notes=[]
 def player(self,packets,seconds=60):
  folder=Path(self.tmp.name)
  return SimpleNamespace(replay=SimpleNamespace(take=lambda:list(packets),seconds=seconds),codec=0,notify=self.notes.append,
   recorder=SimpleNamespace(events=None,headers=b''),capture_path=lambda kind,suffix:folder/kind/('PlayBridge-20261114-120000-000000'+suffix),trophy_events=queue.SimpleQueue())
 def cut(self,me,earned,moment,now):
  with patch.object(core,'save_clip',lambda chosen,path,*rest:self.saved.append((chosen,path,rest))),patch.object(core.time,'time',return_value=now):
   core.Player.save_trophy_clip(me,earned,moment)
 def test_the_clip_runs_from_30_seconds_before_the_trophy_to_5_after(self):
  packets=stream(60);newest=FIRST+(60*60-1)*TICK
  self.cut(self.player(packets),[dict(id=3,name='Trophy: Done!',grade='gold',at=990)],990.0,1000.0)
  chosen,path,rest=self.saved[0];video=[packet[2] for packet in chosen if packet[0]==1]
  # The newest packet came in at 1000 s; the moment was 10 s before it, so the clip ends 5 s before the newest packet.
  end=newest-5*90000;self.assertEqual(max(video),end);self.assertEqual(min(video),end-35*90000)
  self.assertTrue(any(packet[0]==2 for packet in chosen));self.assertEqual(len(video),35*60+1)
  self.assertEqual(path.name,'PlayBridge-Trophy-Trophy Done-20261114-120000-000000.mp4');self.assertEqual(rest[-1],'Trophy clip')
 def test_a_replay_that_does_not_reach_back_says_so(self):
  # One keyframe, at the start of the minute in memory: none falls inside the 35 seconds of the clip.
  self.cut(self.player(stream(60,keyframe_every=60*60)),[dict(id=3,name='',grade='',at=999)],999.0,1006.0)
  self.assertEqual(self.saved,[]);self.assertIn('does not reach back',self.notes[0])
 def test_a_trophy_without_a_name_keeps_a_plain_file_name(self):
  self.cut(self.player(stream(60)),[dict(id=3,name='',grade='',at=990)],990.0,1000.0)
  self.assertEqual(self.saved[0][1].name,'PlayBridge-Trophy-20261114-120000-000000.mp4')

class MomentTests(unittest.TestCase):
 def unlocked(self,at,since,now,settings=None,seconds=60):
  moments=[];notes=[];done=threading.Event()
  me=SimpleNamespace(replay=SimpleNamespace(seconds=seconds),notify=notes.append,trophy_events=queue.SimpleQueue(),recorder=SimpleNamespace(active=False),save_trophy_clip=lambda earned,moment:(moments.append(moment),done.set()))
  with patch.object(core,'config',return_value=settings or {}),patch.object(core,'CLIP_AFTER',0),patch.object(core.time,'time',return_value=now):
   core.Player.trophy_unlocked(me,'PPSA00001',[dict(id=3,name='Trophy 3',grade='bronze',at=at)],since)
   done.wait(2)
  return moments,notes,me.trophy_events
 def test_the_consoles_time_is_used_when_it_falls_between_the_two_reads(self):
  moments,_,events=self.unlocked(995,990.0,1000.0);self.assertEqual(moments,[995]);self.assertEqual(events.get_nowait()[0],'PPSA00001')
 def test_a_console_clock_that_is_off_leaves_the_moment_of_the_read(self):
  self.assertEqual(self.unlocked(500,990.0,1000.0)[0],[1000.0]);self.assertEqual(self.unlocked(1500,990.0,1000.0)[0],[1000.0])
 def test_without_instant_replay_it_says_how_to_get_one(self):
  moments,notes,events=self.unlocked(995,990.0,1000.0,seconds=0)
  self.assertEqual(moments,[]);self.assertIn('instant replay',notes[0]);self.assertFalse(events.empty())
 def test_turned_off_the_trophy_is_still_heard_but_no_clip_is_kept(self):
  moments,notes,events=self.unlocked(995,990.0,1000.0,settings=dict(trophy_clips=False))
  self.assertEqual((moments,notes),([],[]));self.assertFalse(events.empty())
 def test_while_recording_each_trophy_is_noted_for_the_highlights(self):
  noted=[];me=SimpleNamespace(trophy_events=queue.SimpleQueue(),recorder=SimpleNamespace(active=True),moments=SimpleNamespace(trophy=lambda name,at:noted.append((name,at))))
  with patch.object(core,'config',return_value=dict(trophy_clips=False)),patch.object(core.time,'time',return_value=1000.0):
   core.Player.trophy_unlocked(me,'PPSA00001',[dict(id=3,name='Trophy 3',grade='bronze',at=995),dict(id=4,name='',grade='silver',at=996)],990.0)
  self.assertEqual(noted,[('Trophy 3',996),('Trophy',996)])

if __name__=='__main__':unittest.main()
