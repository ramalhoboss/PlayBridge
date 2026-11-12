import os,socket,sys,tempfile,threading,time,unittest
from pathlib import Path
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import av
import live_broadcast as live
from media_fixture import packets
# FFmpeg reads AV1 with dav1d where it has it.
AV1=('av1','libdav1d')

def events(broadcast):
 found=[]
 while True:
  try:found.append(broadcast.events.get_nowait())
  except Exception:return found
def drain(broadcast,limit=10):
 started=time.monotonic()
 while not broadcast.queue.empty() and time.monotonic()-started<limit:time.sleep(.02)
 time.sleep(.2)

class DestinationTests(unittest.TestCase):
 def test_twitch_and_youtube_take_only_the_key(self):
  self.assertEqual(live.destination('twitch',' live_123_abc '),('rtmp://live.twitch.tv/app/live_123_abc','flv'))
  self.assertEqual(live.destination('youtube','abcd-efgh-ijkl'),('rtmps://a.rtmps.youtube.com:443/live2/abcd-efgh-ijkl','flv'))
 def test_a_missing_or_odd_key_is_refused(self):
  with self.assertRaisesRegex(ValueError,'Enter your stream key'):live.destination('twitch','')
  with self.assertRaisesRegex(ValueError,'never has'):live.destination('twitch','abc/def')
  with self.assertRaisesRegex(ValueError,'never has'):live.destination('youtube','abc def')
  with self.assertRaisesRegex(ValueError,'server address'):live.destination('twitch','rtmp://live.twitch.tv/app/live_123')
 def test_any_rtmp_server_with_or_without_a_key(self):
  self.assertEqual(live.destination('custom','key1','rtmp://example.test/live/'),('rtmp://example.test/live/key1','flv'))
  self.assertEqual(live.destination('custom','','rtmps://example.test/live/key2'),('rtmps://example.test/live/key2','flv'))
  with self.assertRaisesRegex(ValueError,'rtmp://'):live.destination('custom','key','http://example.test/live')
 def test_obs_gets_mpeg_ts_on_this_pc_only(self):
  address,container=live.destination('obs','ignored')
  self.assertTrue(address.startswith('udp://127.0.0.1:'));self.assertEqual(container,'mpegts')
 def test_the_clock_reads_as_hours_minutes_seconds(self):
  self.assertEqual(live.clock(0),'0:00:00');self.assertEqual(live.clock(3725.9),'1:02:05')

@unittest.skipUnless(sys.platform=='win32','DPAPI is Windows only')
class KeyTests(unittest.TestCase):
 def test_a_sealed_key_reads_back_and_is_not_the_key(self):
  sealed=live.seal('live_123_secret');self.assertTrue(sealed);self.assertNotIn('live_123_secret',sealed);self.assertEqual(live.unseal(sealed),'live_123_secret')
 def test_nothing_or_rubbish_gives_no_key(self):
  self.assertEqual(live.seal(''),'');self.assertEqual(live.unseal(''),'');self.assertEqual(live.unseal('bm90IGEga2V5'),'');self.assertEqual(live.unseal('%%%'),'')

class BroadcastTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.packets=packets(2)
 def test_the_console_stream_goes_out_untouched_as_flv(self):
  with tempfile.TemporaryDirectory() as folder:
   path=str(Path(folder)/'live.flv');b=live.LiveBroadcast();self.assertTrue(b.start(path,'flv','Test'))
   for packet in self.packets:b.feed(*packet)
   drain(b);self.assertEqual(b.state,'live');self.assertGreater(b.elapsed(),0);b.stop(wait=True)
   messages=[m for _,m in events(b)];self.assertIn('You are live on Test.',messages);self.assertTrue(any(m.startswith('The live stream on Test ended after') for m in messages))
   with av.open(path) as result:
    self.assertEqual(result.streams.video[0].codec_context.name,'h264');self.assertEqual(result.streams.audio[0].codec_context.name,'aac')
    frames=sum(1 for _ in result.decode(video=0))
   self.assertGreaterEqual(frames,50)
 def test_a_smaller_stream_is_made_again_as_av1_in_enhanced_flv(self):
  # The processor's AV1 stands in for a graphics card's here, so the test runs on any PC; the app only offers the cards' encoders.
  with tempfile.TemporaryDirectory() as folder:
   path=str(Path(folder)/'live.flv');b=live.LiveBroadcast();self.assertTrue(b.start(path,'flv','Test',encoder='libsvtav1'))
   for packet in self.packets:b.feed(*packet)
   drain(b,30);self.assertEqual(b.state,'live');b.stop(wait=True)
   messages=[m for _,m in events(b)];self.assertIn('You are live on Test in AV1.',messages)
   with av.open(path) as result:
    self.assertIn(result.streams.video[0].codec_context.name,AV1);self.assertEqual(result.streams.audio[0].codec_context.name,'aac')
    frames=sum(1 for _ in result.decode(video=0))
   self.assertGreaterEqual(frames,50)
 def test_hevc_from_the_ps5_may_go_over_rtmp_once_it_is_made_again(self):
  b=live.LiveBroadcast();b.codec=live.HEVC
  with tempfile.TemporaryDirectory() as folder:
   self.assertTrue(b.start(str(Path(folder)/'x.flv'),'flv','Test',encoder='libsvtav1'));b.stop(wait=True)
 def test_only_youtube_and_other_rtmp_servers_get_a_smaller_stream(self):
  self.assertEqual(live.COMPRESSIBLE,('youtube','custom'))
 def test_obs_gets_mpeg_ts_over_udp(self):
  receiver=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);receiver.bind(('127.0.0.1',0));receiver.settimeout(5);port=receiver.getsockname()[1]
  try:
   b=live.LiveBroadcast();b.start(f'udp://127.0.0.1:{port}?pkt_size=1316','mpegts','OBS on this PC')
   for packet in self.packets:b.feed(*packet)
   first=receiver.recv(2048);drain(b);b.stop(wait=True)
  finally:receiver.close()
  self.assertEqual(len(first),1316);self.assertEqual(first[0],0x47)
 def test_an_rtmp_server_is_called_and_a_refusal_never_shows_the_key(self):
  server=socket.create_server(('127.0.0.1',0));port=server.getsockname()[1];greeting=[]
  def answer():
   connection,_=server.accept()
   with connection:greeting.append(connection.recv(1))
  thread=threading.Thread(target=answer,daemon=True);thread.start()
  try:
   b=live.LiveBroadcast();b.start(f'rtmp://127.0.0.1:{port}/app/secret_key_42','flv','Test server')
   for packet in self.packets:b.feed(*packet)
   b.thread.join(20)
  finally:server.close()
  self.assertEqual(greeting,[b'\x03'])
  found=events(b);self.assertTrue(found);self.assertTrue(all('secret_key_42' not in m for _,m in found))
  self.assertIn(('error','Could not reach Test server. Check the stream key and your connection.'),found)
 def test_hevc_is_refused_for_rtmp_but_not_for_obs(self):
  b=live.LiveBroadcast();b.codec=live.HEVC
  with self.assertRaisesRegex(ValueError,'1080p profile'):b.start('rtmp://127.0.0.1:1/app/x','flv','Twitch')
  self.assertFalse(b.active)
 def test_a_slow_upload_ends_the_stream_and_says_why(self):
  b=live.LiveBroadcast();b.max_queue=4;b.thread=threading.Thread(target=time.sleep,args=(1,));b.thread.start();b.name='Twitch';import queue;b.queue=queue.Queue(4)
  for packet in self.packets[:10]:b.feed(*packet)
  self.assertTrue(b.ending.is_set());self.assertIn('could not keep up',events(b)[0][1])
 def test_a_new_ps5_session_ends_the_stream(self):
  b=live.LiveBroadcast()
  with tempfile.TemporaryDirectory() as folder:
   b.start(str(Path(folder)/'x.flv'),'flv','YouTube');b.reset_session()
  self.assertFalse(b.active);self.assertIn(('status','The live stream on YouTube ended with the PS5 connection.'),events(b))

if __name__=='__main__':unittest.main()
