"""Performance checks between versions: a minute of streaming makes a note, a run of a few notes is kept for its version and setup,
another setup starts another run, and a version is compared with the one before on the same setup only, a stage counting as slower
only when it is clearly so."""
import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import perf_watch

def snapshot(decode=4.0,present=9.0,width=1920,decoder='d3d11va',frames=1800):
 timing=lambda p95:dict(samples=frames,mean=p95/2,p50=p95/2,p95=p95,max=p95*2)
 return dict(renderer='d3d11',video_decoder=decoder,graphics_card='Radeon RX 7600',stream=dict(decoded_width=width,decoded_height=width*9//16),
  capture_info=dict(fps_target=60),timings_ms=dict(video_decode_ms=timing(decode),receive_to_present_ms=timing(present),packet_body_read_ms=timing(1)))

class Clock:
 def __init__(self):self.now=0.0
 def __call__(self):return self.now

class PerfWatchTests(unittest.TestCase):
 def setUp(self):
  self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup);self.path=Path(self.folder.name,'perf-history.json')
 def stream(self,watch,clock,minutes,**values):
  for _ in range(minutes*60):clock.now+=1;watch.second(True,snapshot(**values))
 def test_notes_make_a_run_kept_for_its_version(self):
  clock=Clock();watch=perf_watch.PerfWatch(self.path,'1.7.1',clock)
  self.stream(watch,clock,2);self.assertIsNone(watch.finish(),'two minutes are too few')
  self.stream(watch,clock,3);watch.second(False,snapshot());clock.now+=600;watch.second(True,snapshot())
  self.assertEqual(len(watch.notes),3,'a pause does not count as streaming')
  record=watch.finish();self.assertEqual((record['version'],record['minutes'],record['p95']),('1.7.1',3.0,dict(video_decode_ms=4.0,receive_to_present_ms=9.0)))
  self.assertEqual(record['setup'],'d3d11|d3d11va|Radeon RX 7600|1920x1080|60')
  self.assertEqual(watch.history(),[record]);self.assertNotIn('packet_body_read_ms',record['p95'])
 def test_another_setup_is_another_run_and_few_frames_are_left_out(self):
  clock=Clock();watch=perf_watch.PerfWatch(self.path,'1.7.1',clock)
  self.stream(watch,clock,3);self.stream(watch,clock,1,width=1280)
  self.assertEqual([item['setup'].split('|')[3] for item in watch.history()],['1920x1080'])
  self.assertEqual(len(watch.notes),1);self.stream(watch,clock,3,width=1280,frames=100);self.assertEqual(len(watch.notes),1,'too few frames make no note')
  self.assertIsNone(perf_watch.setup_of(dict(stream={})))
 def measured(self,version,count=1,**values):
  clock=Clock();watch=perf_watch.PerfWatch(self.path,version,clock)
  for _ in range(count):self.stream(watch,clock,3,**values);watch.finish()
  return watch
 def test_a_version_against_the_one_before_on_the_same_setup(self):
  self.assertEqual(perf_watch.compare([],'1.8.0')['state'],'waiting')
  self.measured('1.7.0',decode=9.0);self.measured('1.7.1',2,decode=4.0)
  self.assertEqual(perf_watch.PerfWatch(self.path,'1.7.1').check(),dict(state='same',against='1.7.0',slower=[]),'faster is not reported')
  # 1.8.0-beta.1 decodes slower, on the same setup: compared with 1.7.1, the version just before it.
  found=self.measured('1.8.0-beta.1',decode=6.5).check()
  self.assertEqual(found,dict(state='slower',against='1.7.1',slower=[dict(stage='decoding',before=4.0,after=6.5)]))
  self.assertIn('decoding takes 6.5 ms on this PC where 1.7.1 took 4.0 ms',perf_watch.line(found,'1.8.0-beta.1'))
  # Another decoder is another setup: nothing to compare it with.
  self.assertEqual(self.measured('1.8.0',decoder='software',decode=12).check()['state'],'first')
 def test_small_changes_are_not_slower(self):
  self.measured('1.7.1',decode=1.0,present=9.0);found=self.measured('1.8.0',decode=1.6,present=10.5).check()
  self.assertEqual(found['state'],'same','1.6 ms is 60% more but under a millisecond more; 10.5 ms is under a quarter more')
 def test_a_damaged_history_is_left_out(self):
  self.path.write_text(json.dumps([dict(version='x',setup='s',p95={}),dict(version='1.7.1',setup='s',p95=dict(video_decode_ms='slow')),'nonsense']),encoding='utf8')
  self.assertEqual(perf_watch.PerfWatch(self.path).history(),[]);self.path.write_text('{',encoding='utf8');self.assertEqual(perf_watch.PerfWatch(self.path).history(),[])
  self.assertIn('after a few minutes',perf_watch.line(dict(state='waiting')))

if __name__=='__main__':unittest.main()
