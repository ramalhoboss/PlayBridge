"""Highlights: trophies and presses noted beside a recording, loud moments read from its own sound, the best moments without overlaps,
a reel that fits a minute, and the wide and vertical videos made of them."""
import json,sys,tempfile,time,unittest
from fractions import Fraction
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import highlights

def make_recording(path,seconds=12,rate=30,size=(320,180),loud=(7.0,8.0)):
 """A quiet recording with one loud second, and a picture whose left half is red and right half blue."""
 import av,numpy as np
 with av.open(str(path),'w',format='mp4') as out:
  video=out.add_stream('libx264',rate=rate);video.width,video.height=size;video.pix_fmt='yuv420p';video.options={'g':str(rate*2),'preset':'ultrafast'}
  sound=out.add_stream('aac',rate=48000);sound.layout='stereo'
  picture=np.zeros((size[1],size[0],3),np.uint8);picture[:,:size[0]//2]=(220,30,30);picture[:,size[0]//2:]=(30,30,220)
  for index in range(seconds*rate):
   frame=av.VideoFrame.from_ndarray(picture,format='rgb24').reformat(format='yuv420p');frame.pts=index;frame.time_base=Fraction(1,rate);out.mux(video.encode(frame))
  samples=48000*seconds;level=np.full(samples,.01,np.float32);level[int(loud[0]*48000):int(loud[1]*48000)]=.6
  tone=(np.sin(np.arange(samples)/48000*2*np.pi*440)*level).astype(np.float32)
  for start in range(0,samples,1024):
   part=tone[start:start+1024];chunk=av.AudioFrame.from_ndarray(np.stack([part,part]),format='fltp',layout='stereo');chunk.sample_rate=48000;chunk.pts=start
   out.mux(sound.encode(chunk))
  out.mux(video.encode(None));out.mux(sound.encode(None))

class MomentLogTests(unittest.TestCase):
 def test_trophies_and_presses_go_beside_the_recording(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder,'PlayBridge-20261115-210000-000000.mp4');now=[1000.0];log=highlights.MomentLog(lambda:now[0])
   log.count(50);log.begin(path,1000.0)
   now[0]=1003.2;log.count(55);now[0]=1003.9;log.count(57);log.trophy('First Steps',1005.5);log.trophy('Before',990.0)
   self.assertIsNone(log.finish(Path(folder,'other.mp4')))
   written=log.finish(path);self.assertEqual(written,Path(folder,'PlayBridge-20261115-210000-000000.moments.json'))
   data=json.loads(written.read_text(encoding='utf-8'))
   self.assertEqual(data['trophies'],[[5.5,'First Steps']]);self.assertEqual(data['presses'],[[3,7]]);self.assertEqual(highlights.read_sidecar(path)['started'],1000.0)
   self.assertIsNone(log.finish(path))
 def test_nothing_noted_leaves_no_file(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder,'a.mp4');log=highlights.MomentLog();log.begin(path,time.time());self.assertIsNone(log.finish(path));self.assertFalse(highlights.sidecar(path).exists())
   log.begin(path,time.time());log.drop();log.trophy('x');self.assertIsNone(log.finish(path))

class FindingTests(unittest.TestCase):
 def test_start_from_the_name(self):
  expected=time.mktime((2026,11,15,21,5,9,0,0,-1))
  self.assertEqual(highlights.started_at('PlayBridge-20261115-210509-123456.mp4'),expected)
  self.assertEqual(highlights.started_at('PS5 Uncharted 20261115_210509_00263369.mp4'),expected)
  self.assertIsNone(highlights.started_at('clip.mp4'))
 def test_loud_and_busy_moments(self):
  steps=[-40.0]*40;steps[20]=-28.0;steps[21]=-25.0;steps[30]=-90.0
  self.assertEqual(highlights.loud_moments(steps),[(10.75,60.0)])
  self.assertEqual(highlights.loud_moments([-90.0]*5),[])
  busy=highlights.busy_moments([[1,2],[2,2],[3,2],[4,9],[5,3]])
  self.assertEqual(busy,[(4.5,36.0)])
  self.assertEqual(highlights.busy_moments([]),[])
 def test_the_reel_keeps_the_best_that_fit_in_order(self):
  moments=[dict(start=0,end=12,score=100),dict(start=50,end=60,score=40),dict(start=20,end=30,score=70),dict(start=80,end=120,score=60)]
  self.assertEqual(highlights.reel(moments,length=40),[(0,12),(20,30),(50,60)])
  self.assertEqual(highlights.reel([]),[])

class RecordingTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.folder=tempfile.TemporaryDirectory();cls.source=Path(cls.folder.name,'PlayBridge-20261115-210000-000000.mp4');make_recording(cls.source)
 @classmethod
 def tearDownClass(cls):cls.folder.cleanup()
 def test_the_loud_second_is_found_and_a_trophy_beside_it(self):
  levels=highlights.levels(self.source);self.assertAlmostEqual(len(levels),24,delta=1)
  found=highlights.find(self.source,12.0)
  self.assertEqual([item['kind'] for item in found],['loud']);self.assertTrue(6.5<=found[0]['moment']<=8.5,found)
  # A trophy from the play log at 9 s into the recording overlaps the loud moment, and wins it.
  began=highlights.started_at(self.source)
  found=highlights.find(self.source,12.0,trophies=[(began+9,'')])
  self.assertEqual(found[0]['kind'],'trophy');self.assertEqual((found[0]['start'],found[0]['end']),(1.0,12.0));self.assertEqual(len(found),1)
  self.assertEqual(found[0]['label'],'Trophy')
 def test_notes_beside_the_recording_come_first(self):
  side=highlights.sidecar(self.source)
  try:
   side.write_text(json.dumps(dict(version=1,started=0,trophies=[[2.0,'Crash Landing']],presses=[])),encoding='utf-8')
   found=highlights.find(self.source,12.0,trophies=[(highlights.started_at(self.source)+9,'')])
   self.assertEqual(found[0]['label'],'Trophy: Crash Landing');self.assertEqual(found[0]['start'],0.0)
   # Two trophies close together: the later one is cut to begin where the first ends, so both are kept.
   side.write_text(json.dumps(dict(version=1,started=0,trophies=[[2.0,'One'],[9.5,'Two']],presses=[])),encoding='utf-8')
   found=sorted(highlights.find(self.source,12.0),key=lambda item:item['start'])
   self.assertEqual([(item['label'],item['start'],item['end']) for item in found],[('Trophy: One',0.0,6.0),('Trophy: Two',6.0,12.0)])
  finally:side.unlink()
 def made(self,path):
  import av
  with av.open(str(path)) as inside:
   video=inside.streams.video[0];frames=[frame.to_ndarray(format='rgb24') for frame in inside.decode(video=0)]
   return video.codec_context.width,video.codec_context.height,frames,bool(inside.streams.audio)
 def test_a_wide_reel_of_two_stretches(self):
  target=Path(self.folder.name,'reel.mp4')
  self.assertEqual(highlights.render(self.source,target,[(1,3),(6,9)],'wide',['libx264']),'')
  width,height,frames,sound=self.made(target);self.assertEqual((width,height,sound),(320,180,True));self.assertAlmostEqual(len(frames),150,delta=4)
 def test_vertical_from_the_middle(self):
  target=Path(self.folder.name,'fill.mp4')
  self.assertEqual(highlights.render(self.source,target,[(2,4)],'fill',['libx264']),'')
  width,height,frames,_=self.made(target);self.assertEqual((width,height),(1080,1920));picture=frames[10]
  # The middle of a picture half red, half blue: red on the left of the vertical clip, blue on its right.
  self.assertGreater(int(picture[960,100,0]),150);self.assertGreater(int(picture[960,980,2]),150)
 def test_vertical_with_the_whole_picture(self):
  target=Path(self.folder.name,'fit.mp4')
  self.assertEqual(highlights.render(self.source,target,[(2,4)],'fit',['libx264']),'')
  width,height,frames,_=self.made(target);self.assertEqual((width,height),(1080,1920));picture=frames[10]
  # The whole picture across the middle, red at its far left and blue at its far right; above it the darker blurred copy.
  self.assertGreater(int(picture[960,20,0]),150);self.assertGreater(int(picture[960,1060,2]),150)
  self.assertLess(int(picture[200,540].max()),170)
 def test_what_cannot_be_made_says_why(self):
  target=Path(self.folder.name,'none.mp4')
  self.assertIn('No highlights',highlights.render(self.source,target,[],'wide',['libx264']))
  self.assertIn('outside',highlights.render(self.source,target,[(10,40)],'wide',['libx264']))
  self.assertIn('at most 3 minutes',highlights.problem('fill',[(0,200)],400))
  self.assertIn('No H.264 encoder',highlights.render(self.source,target,[(1,2)],'wide',[]))
  self.assertIn('cannot be read',highlights.render(Path(self.folder.name,'missing.mp4'),target,[(1,2)],'wide',['libx264']))
  self.assertFalse(target.exists())

if __name__=='__main__':unittest.main()
