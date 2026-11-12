import os,sys,tempfile,time,unittest
from pathlib import Path
from unittest import mock
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import av
import video_encoders,compact_video
from media_capture import CaptureRecorder
from media_fixture import packets
# FFmpeg reads AV1 with dav1d where it has it.
AV1=('av1','libdav1d')

def recording(folder,seconds=3):
 """A real PlayBridge recording, made the way the app makes one."""
 path=Path(folder)/'Recording.mp4';recorder=CaptureRecorder();recorder.start(path)
 for packet in packets(seconds):recorder.feed(*packet)
 recorder.stop(wait=True)
 return path

class EncoderChoiceTests(unittest.TestCase):
 def setUp(self):video_encoders._found=None
 def tearDown(self):video_encoders._found=None
 def test_only_encoders_that_really_work_are_offered_in_order(self):
  works={'hevc_amf','libsvtav1','av1_nvenc'}
  with mock.patch.object(video_encoders,'_works',side_effect=lambda name:name in works):
   self.assertEqual(video_encoders.found(),['av1_nvenc','hevc_amf','libsvtav1'])
 def test_a_live_stream_never_takes_the_processor(self):
  with mock.patch.object(video_encoders,'_works',side_effect=lambda name:name=='libsvtav1'):
   self.assertIsNone(video_encoders.for_live());self.assertEqual(video_encoders.for_files(),'libsvtav1')
 def test_amd_av1_comes_after_amd_hevc(self):
  with mock.patch.object(video_encoders,'_works',side_effect=lambda name:name in ('av1_amf','hevc_amf')):
   self.assertEqual(video_encoders.for_live(),'hevc_amf')
 def test_nothing_found_means_nothing_offered(self):
  with mock.patch.object(video_encoders,'_works',return_value=False):
   self.assertIsNone(video_encoders.for_live());self.assertIsNone(video_encoders.for_files())
 def test_the_probe_runs_once(self):
  with mock.patch.object(video_encoders,'_works',return_value=True) as probe:
   video_encoders.found();video_encoders.found()
  self.assertEqual(probe.call_count,len(video_encoders.HARDWARE+video_encoders.SOFTWARE))

class BitrateTests(unittest.TestCase):
 def test_av1_needs_less_than_hevc(self):
  for height in (1080,1440,2160):
   self.assertLess(video_encoders.bitrate('av1_nvenc',height,live=True),video_encoders.bitrate('hevc_amf',height,live=True))
 def test_bigger_pictures_get_more(self):
  self.assertLess(video_encoders.bitrate('hevc_amf',1080),video_encoders.bitrate('hevc_amf',1440));self.assertLess(video_encoders.bitrate('hevc_amf',1440),video_encoders.bitrate('hevc_amf',2160))
 def test_never_more_than_the_source_had(self):
  self.assertEqual(video_encoders.bitrate('hevc_amf',2160,source=10_000_000),8_000_000)
 def test_4k_live_is_far_below_the_ps5s_80_mbps(self):
  self.assertLessEqual(video_encoders.bitrate('hevc_amf',2160,live=True),25_000_000)
 def test_pixel_formats(self):
  self.assertEqual(video_encoders.pixel_format('hevc_amf',live=True),'nv12');self.assertEqual(video_encoders.pixel_format('hevc_amf'),'yuv420p')
  self.assertEqual(video_encoders.pixel_format('hevc_qsv'),'nv12');self.assertEqual(video_encoders.pixel_format('libsvtav1',live=True),'yuv420p')
 def test_every_encoder_has_a_name_for_people(self):
  for name in video_encoders.HARDWARE+video_encoders.SOFTWARE:self.assertIn(name,video_encoders.NAMES)

class CompactTests(unittest.TestCase):
 def test_a_recording_becomes_av1_with_the_same_sound_and_length(self):
  with tempfile.TemporaryDirectory() as folder:
   source=recording(folder);target=Path(folder)/'small.mp4'
   self.assertEqual(compact_video.compact(source,target,'libsvtav1'),'')
   with av.open(str(source)) as before,av.open(str(target)) as after:
    self.assertIn(after.streams.video[0].codec_context.name,AV1);self.assertEqual(after.streams.audio[0].codec_context.name,'aac')
    self.assertAlmostEqual(compact_video.duration(after,after.streams.video[0]),compact_video.duration(before,before.streams.video[0]),delta=1.0)
    self.assertGreaterEqual(sum(1 for _ in after.decode(video=0)),80)
 def test_closing_the_app_stops_it_with_a_reason(self):
  with tempfile.TemporaryDirectory() as folder:
   source=recording(folder)
   self.assertEqual(compact_video.compact(source,Path(folder)/'small.mp4','libsvtav1',stopping=lambda:True),'PlayBridge closed first.')
 def test_it_waits_while_a_stream_plays(self):
  with tempfile.TemporaryDirectory() as folder:
   source=recording(folder);calls=[]
   def busy():calls.append(1);return len(calls)<3
   with mock.patch.object(compact_video.time,'sleep'):
    self.assertEqual(compact_video.compact(source,Path(folder)/'small.mp4','libsvtav1',busy=busy),'')
   self.assertGreaterEqual(len(calls),3)

class CompactorTests(unittest.TestCase):
 def run_one(self,folder,recycled=True,encoder='libsvtav1',original_size=None):
  source=recording(folder)
  if original_size is not None:
   with open(source,'ab') as grow:grow.write(b'\0'*original_size)
  def recycle(path):
   if recycled:Path(path).unlink()
   return recycled
  with mock.patch.object(compact_video,'recycle',side_effect=recycle):
   worker=compact_video.Compactor(lambda:False,encoder=encoder);worker.add(source)
   self.assertEqual(worker.remembered(),[str(source)])
   worker.thread.join(timeout=120)
  messages=[];
  while not worker.events.empty():messages.append(worker.events.get())
  return source,worker,messages
 def test_the_smaller_file_takes_the_original_name(self):
  with tempfile.TemporaryDirectory() as folder:
   source,worker,messages=self.run_one(folder,original_size=4_000_000)
   self.assertEqual(worker.remembered(),[]);self.assertTrue(source.exists())
   with av.open(str(source)) as result:self.assertIn(result.streams.video[0].codec_context.name,AV1)
   self.assertEqual(messages[-1][0],'status');self.assertIn('AV1 on the processor',messages[-1][1])
   self.assertEqual(list(Path(folder).glob('*'+compact_video.SUFFIX)),[])
 def test_when_the_recycle_bin_refuses_both_files_stay(self):
  with tempfile.TemporaryDirectory() as folder:
   source,worker,messages=self.run_one(folder,recycled=False,original_size=4_000_000)
   self.assertTrue(source.exists());self.assertTrue((Path(folder)/'Recording (smaller).mp4').exists())
 def test_a_file_that_would_not_shrink_is_left_alone(self):
  def bigger(source,target,*_):
   Path(target).write_bytes(b'\0'*(Path(source).stat().st_size+1));return ''
  with tempfile.TemporaryDirectory() as folder:
   with mock.patch.object(compact_video,'compact',side_effect=bigger):source,worker,messages=self.run_one(folder)
   with av.open(str(source)) as kept:self.assertEqual(kept.streams.video[0].codec_context.name,'h264')
   self.assertIn('already as small',messages[-1][1]);self.assertEqual(list(Path(folder).glob('*'+compact_video.SUFFIX)),[])
 def test_no_encoder_says_so(self):
  with tempfile.TemporaryDirectory() as folder:
   with mock.patch.object(video_encoders,'for_files',return_value=None):
    source,worker,messages=self.run_one(folder,encoder=None)
   self.assertEqual(messages[-1][0],'error');self.assertIn('no encoder',messages[-1][1])
 def test_partial_files_and_missing_files_are_not_taken(self):
  worker=compact_video.Compactor(lambda:False,encoder='libsvtav1')
  with mock.patch.object(worker,'_run'):
   worker.add('C:/x/Recording'+compact_video.SUFFIX);self.assertEqual(worker.remembered(),[])
   worker.resume(['C:/nowhere/at/all.mp4',3]);self.assertEqual(worker.remembered(),[])
 def test_a_stream_holds_it_and_the_status_says_so(self):
  worker=compact_video.Compactor(lambda:True,encoder='libsvtav1');worker.current='C:/v/Recording.mp4';worker.waiting=['C:/v/b.mp4']
  self.assertEqual(worker.status(),'Making Recording.mp4 smaller waits until the stream stops · 1 more waiting.')
  worker.busy=lambda:False;worker.share=.42
  self.assertEqual(worker.status(),'Making Recording.mp4 smaller · 42% · 1 more waiting')

if __name__=='__main__':unittest.main()
