import sys,unittest,tempfile,zipfile,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from stream_metrics import StreamMetrics,export_diagnostics
class MetricsTests(unittest.TestCase):
 def test_rates_and_stale_window(self):
  now=[0.0];m=StreamMetrics(lambda:now[0]);m.packet(1000000,True);now[0]=1;m.packet(1000000,True);self.assertEqual(m.summary()['received_mbps'],8.0);self.assertEqual(m.summary()['video_packets_per_second'],1.0);now[0]=7;self.assertIsNone(m.summary()['received_mbps']);self.assertEqual(len(m.samples),0)
 def test_resolution_and_reset(self):
  from types import SimpleNamespace
  m=StreamMetrics();m.frame(SimpleNamespace(width=2560,height=1440,format=SimpleNamespace(name='yuv420p')));self.assertEqual(m.summary()['decoded_height'],1440);m.reset();self.assertEqual(m.summary()['decoded_width'],0)
 def test_export_excludes_sensitive_context(self):
  snapshot={'output':'PRIVATE_DEVICE','error':'PRIVATE_PATH','host':'PRIVATE_IP','stream':{'decoded_width':1920,'secret':'PRIVATE_STREAM'},'capture_info':{'protocol':2,'registration_key':'PRIVATE_KEY'},'timings_ms':{'video_decode_ms':{'p95':2},'PRIVATE_TIMING':{'p95':9}}}
  with tempfile.TemporaryDirectory() as folder:
   path=export_diagnostics(Path(folder)/'report.zip',snapshot)
   with zipfile.ZipFile(path) as z:
    data=z.read('diagnostics.json').decode();self.assertNotIn('PRIVATE_',data);report=json.loads(data);self.assertEqual(report['stream']['decoded_width'],1920);self.assertEqual(report['timings_ms']['video_decode_ms']['p95'],2)
if __name__=='__main__':unittest.main()
