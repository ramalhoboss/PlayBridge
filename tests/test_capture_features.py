import os,queue,sys,time,tempfile,unittest,argparse,json,threading,socket,struct
from pathlib import Path
from unittest.mock import patch
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import av,numpy as np
from PIL import Image
import playbridge as core
from media_capture import CaptureRecorder,ReplayBuffer,codec_headers,is_idr,nal_units,save_clip,strip_adts
from media_fixture import packets

class MediaTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.packets=packets(2)
 def player(self):return core.Player(argparse.Namespace(renderer='gdi',profile='balanced',auto_reconnect=True,device=None,connect_only=True,host='127.0.0.1',record=False,preview=False,headless=True,seconds=0))
 def test_a_recording_gives_a_still_for_its_thumbnail_and_a_broken_one_gives_none(self):
  from desktop_features import video_thumbnail
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'capture.mp4';r=CaptureRecorder()
   for p in self.packets:
    if p[2]<22500:r.feed(*p)
   self.assertTrue(r.start(path))
   for p in self.packets:
    if p[2]>=22500:r.feed(*p);time.sleep(.001)
   r.stop(wait=True);still=video_thumbnail(path)
   self.assertIsNotNone(still);self.assertLessEqual(still.width,300);self.assertLessEqual(still.height,170);self.assertGreater(still.width,0)
   broken=Path(tmp)/'broken.mp4';broken.write_bytes(b'not a video');self.assertIsNone(video_thumbnail(broken))
 def test_recording_starts_at_later_keyframe_with_audio(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'capture.mp4';r=CaptureRecorder()
   for p in self.packets:
    if p[2]<22500:r.feed(*p)
   self.assertTrue(r.start(path))
   for p in self.packets:
    if p[2]>=22500:r.feed(*p);time.sleep(.001)
   r.stop(wait=True);self.assertFalse(r.active);self.assertEqual(r.error,'');self.assertTrue(path.is_file())
   with av.open(str(path)) as f:
    self.assertEqual([s.type for s in f.streams],['video','audio']);self.assertEqual(f.streams.video[0].codec_context.name,'h264');self.assertEqual(f.streams.audio[0].codec_context.name,'aac')
    frames=list(f.decode(video=0));self.assertGreater(len(frames),30);self.assertTrue(frames[0].key_frame);self.assertEqual((frames[0].width,frames[0].height),(160,96))
   with av.open(str(path)) as f:self.assertGreater(sum(x.samples for x in f.decode(audio=0)),48000)
 def test_recording_cancelled_without_keyframe(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'none.mp4';r=CaptureRecorder();r.start(p);r.stop(wait=True);self.assertFalse(p.exists());self.assertFalse(list(Path(tmp).glob('*.partial.mp4')))
 def test_queue_overflow_is_explicit_and_bounded(self):
  with tempfile.TemporaryDirectory() as tmp:
   r=CaptureRecorder();r.max_bytes=1;r.start(Path(tmp)/'overflow.mp4');r.feed(*self.packets[0]);r.stop(wait=True);self.assertIn('disk could not keep up',r.error);self.assertEqual(r.queued_bytes,0)
 def test_native_size_screenshot(self):
  with tempfile.TemporaryDirectory() as tmp:
   with patch.object(core,'STATE',Path(tmp)):
    core.save_config(capture_folder=tmp);p=self.player();a=np.zeros((96,160,3),dtype=np.uint8);a[:]=[20,40,60];p.last_native_frame=av.VideoFrame.from_ndarray(a,format='rgb24');p.render_size=(80,48);p.take_screenshot();p.screenshot_thread.join(3)
    files=list((Path(tmp)/'Screenshots').glob('*.png'));self.assertEqual(len(files),1)
    with Image.open(files[0]) as image:self.assertEqual(image.size,(160,96));self.assertEqual(image.getpixel((0,0)),(20,40,60))
 def test_reconnect_and_manual_stop(self):
  p=self.player();calls=[]
  def session():
   calls.append(1)
   if len(calls)==2:p.intentional_disconnect=True
  p.network_session=session;p.network();self.assertEqual(len(calls),2);self.assertEqual(p.stats['reconnection_attempts'],1);self.assertTrue(p.session_done.is_set())
 def test_the_end_of_a_stream_says_whether_the_pc_stopped_reading(self):
  # A video packet that took 1.37 s to handle, then little more: the PS5 gives up on a reader that stalls for 1 s.
  text=core.last_seconds([(0.0,1,0.001),(0.016,2,0.017),(0.033,1,1.4),(1.41,1,1.411)],1.5)
  self.assertIn('longest time on one packet 1367 ms (video)',text);self.assertIn('last packet 90 ms before the end',text)
  # The PS5 that stopped sending shows as a long wait instead.
  self.assertIn('longest wait for the PS5 1199 ms (before sound)',core.last_seconds([(0.0,1,0.001),(1.2,2,1.201)],1.3))
  self.assertEqual(core.last_seconds([],5),'No packet in the last 3 s before the end')
 def test_reconnect_waits_little_after_a_stream_and_longer_after_failures(self):
  self.assertEqual([core.reconnect_delay(n) for n in range(6)],[.3,2,4,8,8,8])
 def test_a_stream_that_played_reconnects_at_once(self):
  # Closing a game used to end the session and wait seconds before the picture came back.
  p=self.player();calls=[]
  def session():
   calls.append(time.perf_counter())
   if len(calls)==1:p.stats['sessions_connected']+=1
   else:p.intentional_disconnect=True
  p.network_session=session;p.network();self.assertEqual(len(calls),2);self.assertLess(calls[1]-calls[0],1)
  # The session's timeline says how long the picture was away.
  self.assertIn('Connecting again in 0.3 s',[text for _,text in p.events])
 def test_reconnect_disabled(self):
  p=self.player();p.args.auto_reconnect=False;calls=[];p.network_session=lambda:calls.append(1);p.network();self.assertEqual(len(calls),1)
 def test_adts_validation(self):
  data=next(p[1] for p in self.packets if p[0]==2);raw,asc=strip_adts(data);self.assertEqual(len(raw),len(data)-7);self.assertEqual(asc,b'\x11\x90')
  with self.assertRaises(ValueError):strip_adts(b'bad')
class ReplayTests(unittest.TestCase):
 def test_only_the_last_seconds_stay_and_nothing_is_copied(self):
  buffer=ReplayBuffer(2);first=b'x'*10;buffer.feed(1,first,0,0);self.assertIs(buffer.take()[0][1],first)
  for second in range(1,6):buffer.feed(1,b'y'*10,second*90000,second*90000)
  self.assertEqual([p[2]//90000 for p in buffer.take()],[3,4,5]);self.assertEqual(buffer.bytes,30)
 def test_the_memory_limit_wins_over_the_seconds(self):
  buffer=ReplayBuffer(100,max_bytes=25)
  for n in range(5):buffer.feed(1,b'y'*10,n,n)
  self.assertEqual(len(buffer.take()),2);self.assertEqual(buffer.bytes,20)
 def test_off_keeps_nothing(self):
  buffer=ReplayBuffer(0);buffer.feed(1,b'y',0,0);self.assertEqual(buffer.take(),[]);buffer=ReplayBuffer(5);buffer.feed(1,b'y',0,0);buffer.resize(0);self.assertEqual(buffer.take(),[]);self.assertEqual(buffer.bytes,0)
 def test_a_new_session_starts_empty(self):
  buffer=ReplayBuffer(5);buffer.feed(1,b'y',0,0);buffer.reset();self.assertEqual(buffer.take(),[])
 def saved(self,source,codec=0,headers=b''):
  events=queue.SimpleQueue()
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'replay.mp4';save_clip(source,path,events,codec,headers)
   messages=[]
   while not events.empty():messages.append(events.get_nowait()[1])
   if not path.exists():return None,messages
   with av.open(str(path)) as media:return (media.streams.video[0].codec_context.name,sum(1 for _ in media.decode(video=0))),messages
 def test_a_replay_is_a_playable_recording_with_its_own_messages(self):
  media,messages=self.saved(packets(2));self.assertEqual(media[0],'h264');self.assertGreater(media[1],30);self.assertEqual(messages,['Saving replay','Replay saved'])
 def test_no_keyframe_in_the_buffer_saves_nothing_and_says_so(self):
  source=[p for p in packets(1) if p[0]==2 or not is_idr(p[1])]
  media,messages=self.saved(source);self.assertIsNone(media);self.assertIn('Replay cancelled',messages[-1])
 def test_a_replay_of_hevc_keeps_hevc(self):
  media,messages=self.saved(packets(2,'libx265'),1);self.assertEqual(media[0],'hevc');self.assertGreater(media[1],30);self.assertEqual(messages[-1],'Replay saved')
 def test_headers_seen_earlier_complete_a_keyframe_without_them(self):
  source=packets(2);headers=codec_headers(next(p[1] for p in source if p[0]==1))
  def bare(data):return b''.join(b'\x00\x00\x00\x01'+n for n in nal_units(data) if n[0]&31 not in (7,8))
  media,_=self.saved([(k,bare(d) if k==1 else d,p,t) for k,d,p,t in source],0,headers);self.assertEqual(media[0],'h264')
class HevcPacketTests(unittest.TestCase):
 idr=b'\x00\x00\x00\x01\x26\x01\xaa';trail=b'\x00\x00\x00\x01\x02\x01\xaa';sets=b'\x00\x00\x00\x01\x40\x01\x00\x00\x00\x01\x42\x01\x00\x00\x00\x01\x44\x01'
 def test_keyframes_by_the_right_codec(self):
  self.assertTrue(is_idr(self.idr,1));self.assertFalse(is_idr(self.trail,1));self.assertTrue(is_idr(b'\x00\x00\x00\x01\x65',0));self.assertFalse(is_idr(b'\x00\x00\x00\x01\x65',1))
 def test_headers_by_the_right_codec(self):
  self.assertEqual(codec_headers(self.sets+self.idr,1),self.sets);self.assertEqual(codec_headers(self.idr,1),b'');self.assertEqual(codec_headers(b'\x00\x00\x00\x01\x67\x00\x00\x00\x01\x68',0),b'\x00\x00\x00\x01\x67\x00\x00\x00\x01\x68')
if __name__=='__main__':unittest.main(verbosity=2)
