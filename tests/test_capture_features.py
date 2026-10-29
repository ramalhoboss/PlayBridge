import os,sys,time,tempfile,unittest,argparse,json,threading,socket,struct
from pathlib import Path
from unittest.mock import patch
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import av,numpy as np
from PIL import Image
import playbridge as core
from media_capture import CaptureRecorder,strip_adts
from media_fixture import packets

class MediaTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.packets=packets(2)
 def player(self):return core.Player(argparse.Namespace(renderer='gdi',profile='balanced',auto_reconnect=True,device=None,connect_only=True,host='127.0.0.1',record=False,preview=False,headless=True,seconds=0))
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
 def test_reconnect_disabled(self):
  p=self.player();p.args.auto_reconnect=False;calls=[];p.network_session=lambda:calls.append(1);p.network();self.assertEqual(len(calls),1)
 def test_adts_validation(self):
  data=next(p[1] for p in self.packets if p[0]==2);raw,asc=strip_adts(data);self.assertEqual(len(raw),len(data)-7);self.assertEqual(asc,b'\x11\x90')
  with self.assertRaises(ValueError):strip_adts(b'bad')
if __name__=='__main__':unittest.main(verbosity=2)
