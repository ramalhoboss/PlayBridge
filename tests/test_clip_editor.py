"""The clip editor: a recording's length and stills along it, a stretch checked before it is made, and copies that start and end where
the player chose, as an MP4 at full size, a small MP4 and a GIF, with the recording left as it was."""
import hashlib,sys,tempfile,time,unittest
from fractions import Fraction
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import clip_editor

def make_recording(path,seconds=6,rate=30,size=(320,180)):
 """A recording whose frames say their own number in their colour, with sound."""
 import av,numpy as np
 with av.open(str(path),'w',format='mp4') as out:
  video=out.add_stream('libx264',rate=rate);video.width,video.height=size;video.pix_fmt='yuv420p';video.options={'g':str(rate*2),'preset':'ultrafast'}
  sound=out.add_stream('aac',rate=48000);sound.layout='stereo'
  for index in range(seconds*rate):
   picture=np.full((size[1],size[0],3),(index*255//(seconds*rate)),np.uint8);frame=av.VideoFrame.from_ndarray(picture,format='rgb24').reformat(format='yuv420p')
   frame.pts=index;frame.time_base=Fraction(1,rate);out.mux(video.encode(frame))
   if index%(rate//10)==0:
    tone=(np.sin(np.arange(4800)/48000*2*np.pi*440)*.2).astype('float32');chunk=av.AudioFrame.from_ndarray(np.stack([tone,tone]),format='fltp',layout='stereo');chunk.sample_rate=48000;chunk.pts=None
    out.mux(sound.encode(chunk))
  out.mux(video.encode(None));out.mux(sound.encode(None))

class ClipEditorTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.folder=tempfile.TemporaryDirectory();cls.source=Path(cls.folder.name,'Astro Bot 2026-11-15.mp4');make_recording(cls.source);cls.hash=hashlib.sha256(cls.source.read_bytes()).hexdigest()
 @classmethod
 def tearDownClass(cls):cls.folder.cleanup()
 def length(self,path):
  import av
  with av.open(str(path)) as inside:video=inside.streams.video[0];return float(video.duration*video.time_base),video.codec_context.width,video.codec_context.height,bool(inside.streams.audio)
 def test_info_stills_and_the_strip(self):
  described=clip_editor.info(self.source);self.assertAlmostEqual(described['seconds'],6,delta=.1);self.assertEqual((described['width'],described['height'],described['sound']),(320,180,True))
  early,late=clip_editor.still(self.source,.5),clip_editor.still(self.source,5.5);self.assertLess(early.convert('L').getpixel((10,10)),late.convert('L').getpixel((10,10))-100)
  made=clip_editor.strip(self.source,described['seconds'],Path(self.folder.name,'strip'),count=4);self.assertEqual(len(made),4);self.assertTrue(all(Path(path).is_file() for path in made))
  self.assertIsNone(clip_editor.info(Path(self.folder.name,'missing.mp4')))
 def test_a_stretch_is_checked_first(self):
  self.assertEqual(clip_editor.problem('small',1,4,6),'');self.assertIn('half a second',clip_editor.problem('small',1,1.2,6))
  self.assertIn('outside',clip_editor.problem('full',2,9,6));self.assertIn('at most 20',clip_editor.problem('gif',0,25,60));self.assertIn('Choose',clip_editor.problem('webm',0,2,6))
  self.assertEqual(clip_editor.target_for(self.source,'gif',lambda:time.struct_time((2026,11,15,21,5,9,0,0,0))).name,'Astro Bot 2026-11-15-clip-210509.gif')
  self.assertEqual(clip_editor.plan('small',30,dict(height=1080,width=1920,rate=60,sound=True))['height'],720);self.assertEqual(clip_editor.plan('small',300,dict(height=1080,rate=60,sound=True))['height'],360)
 def test_copies_start_and_end_where_chosen(self):
  for kind,suffix in (('full','.mp4'),('small','.mp4')):
   target=Path(self.folder.name,f'cut-{kind}{suffix}');shares=[]
   self.assertEqual(clip_editor.export(self.source,target,kind,1.5,4.0,['libx264'],shares.append),'')
   seconds,width,height,sound=self.length(target);self.assertAlmostEqual(seconds,2.5,delta=.15);self.assertTrue(sound);self.assertEqual(shares[-1],1.0)
   # The first picture is the one at 1.5 s, not the keyframe at 0 s before it.
   first=clip_editor.still(target,0).convert('L').getpixel((5,5));self.assertAlmostEqual(first,clip_editor.still(self.source,1.5).convert('L').getpixel((5,5)),delta=12)
  gif=Path(self.folder.name,'cut.gif');self.assertEqual(clip_editor.export(self.source,gif,'gif',2,3,['libx264']),'')
  from PIL import Image
  with Image.open(gif) as made:self.assertEqual(made.width,clip_editor.GIF_WIDTH);self.assertAlmostEqual(made.n_frames,15,delta=1)
  self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(),self.hash,'the recording is left as it was')
 def test_a_failed_copy_leaves_nothing(self):
  target=Path(self.folder.name,'nothing.mp4')
  self.assertIn('failed',clip_editor.export(self.source,target,'small',1,2,['no_such_encoder']));self.assertFalse(target.exists())
  self.assertIn('closed first',clip_editor.export(self.source,target,'small',1,2,['libx264'],stopping=lambda:True));self.assertFalse(target.exists())

if __name__=='__main__':unittest.main()
