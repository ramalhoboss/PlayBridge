import os,socket,sys,tempfile,threading,time,unittest
from pathlib import Path
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import av
import numpy as np
import live_broadcast as live
import video_encoders
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
 def test_tiktok_takes_its_server_and_a_key_with_its_expiry(self):
  key='stream-7300000000000000000?expire=1800000000&sign=0a1b2c'
  self.assertEqual(live.destination('tiktok',key,'rtmp://push-rtmp.example.test/game/'),('rtmp://push-rtmp.example.test/game/'+key,'flv'))
  with self.assertRaisesRegex(ValueError,'stream key TikTok gave'):live.destination('tiktok','','rtmp://push-rtmp.example.test/game/')
  with self.assertRaisesRegex(ValueError,'rtmp://'):live.destination('tiktok',key,'')
  with self.assertRaisesRegex(ValueError,'never has'):live.destination('tiktok','stream 1','rtmp://push-rtmp.example.test/game/')
  with self.assertRaisesRegex(ValueError,'never has'):live.destination('twitch',key)
  self.assertNotIn('tiktok',live.COMPRESSIBLE);self.assertEqual(live.SERVICES['tiktok'],'TikTok')
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
 def overlay_reaches_the_viewers(self,encoder,packets):
  # An opaque green panel, as hud.render gives it, drawn into the stream's top left corner while the video is made again.
  with tempfile.TemporaryDirectory() as folder:
   path=str(Path(folder)/'live.flv');b=live.LiveBroadcast();b.overlay_image=(bytes((0,255,0,255))*40*20,40,20)
   self.assertTrue(b.start(path,'flv','Test',encoder=encoder))
   for packet in packets:b.feed(*packet)
   drain(b,30);b.stop(wait=True)
   with av.open(path) as result:pictures=[frame.to_ndarray(format='rgb24') for frame in result.decode(video=0)]
  self.assertGreaterEqual(len(pictures),50)
  for picture in pictures[5:]:
   inside=picture[16+10,16+20];outside=picture[60,100]
   self.assertTrue(inside[1]>180 and inside[0]<90 and inside[2]<90,inside.tolist());self.assertLess(int(outside[1]),110,outside.tolist())
 def test_the_overlay_reaches_the_viewers(self):self.overlay_reaches_the_viewers('libsvtav1',self.packets)
 def test_the_overlay_reaches_the_viewers_through_this_pcs_card(self):
  encoder=video_encoders.for_live_h264()
  if not encoder:self.skipTest('no graphics card H.264 encoder on this PC')
  # A graphics card's encoder takes no picture as small as the other tests' one; the PS5's is 720p at the least.
  self.overlay_reaches_the_viewers(encoder,packets(2,size=(640,368)))
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

class SeveralServicesTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.packets=packets(2)
 def test_kick_takes_its_server_and_key(self):
  self.assertEqual(live.destination('kick','sk_us-west-2_abc','rtmps://ingest.example.net/app'),('rtmps://ingest.example.net/app/sk_us-west-2_abc','flv'))
  with self.assertRaisesRegex(ValueError,'stream key Kick gave'):live.destination('kick','','rtmps://ingest.example.net/app')
  self.assertTrue(live.ready('twitch','abc',''));self.assertFalse(live.ready('kick','abc',''));self.assertTrue(live.ready('obs','',''))
 def test_settings_from_before_keep_their_one_service_switched_on(self):
  sealed=live.seal('old_key')
  targets,on=live.saved_targets(dict(live_service='twitch',live_key=sealed,live_server=''))
  self.assertEqual((targets,on),({'twitch':{'key':'old_key','server':''}},['twitch']))
  self.assertEqual(live.saved_targets({}),({},[]));self.assertEqual(live.saved_targets(dict(live_targets='x',live_service='nope')),({},[]))
 def test_each_service_keeps_its_own_key_sealed(self):
  saved=dict(live_service='twitch',live_key=live.seal('t_key'))
  saved.update(live.keep_target(saved,'kick',' k_key ',' rtmps://ingest.example.net/app '))
  self.assertNotIn('k_key',str(saved['live_targets']))
  targets,on=live.saved_targets(saved)
  self.assertEqual(targets['kick'],{'key':'k_key','server':'rtmps://ingest.example.net/app'});self.assertEqual(targets['twitch']['key'],'t_key');self.assertEqual(on,['twitch'])
  saved.update(live.switch_target(saved,'kick',True));saved.update(live.switch_target(saved,'youtube',True))
  self.assertEqual(saved['live_on'],['twitch','youtube','kick'])
  self.assertEqual(live.chosen_targets(saved),[('twitch','t_key',''),('youtube','',''),('kick','k_key','rtmps://ingest.example.net/app')])
  saved.update(live.switch_target(saved,'twitch',False));self.assertEqual(saved['live_on'],['youtube','kick'])
  saved.update(live.keep_target(saved,'kick','',''));self.assertEqual(live.saved_targets(saved)[0]['kick'],{'key':'','server':''})
 def test_names_read_as_a_list(self):
  self.assertEqual(live.names_text(['Twitch']),'Twitch');self.assertEqual(live.names_text(['Twitch','Kick']),'Twitch and Kick');self.assertEqual(live.names_text(['Twitch','YouTube','Kick']),'Twitch, YouTube and Kick')
 def test_each_address_is_one_output_of_tee(self):
  address,options=live.fan_out([('A','rtmp://x/app/k|y','flv'),('B',"udp://127.0.0.1:9100?pkt_size=1316",'mpegts')])
  self.assertEqual(address,'[f=flv:onfail=ignore:flvflags=no_duration_filesize]rtmp://x/app/k\\|y|[f=mpegts:onfail=ignore]udp://127.0.0.1:9100?pkt_size=1316')
  self.assertEqual(options['use_fifo'],'1');self.assertIn('drop_pkts_on_overflow=1',options['fifo_options'])
 def test_one_service_goes_as_before(self):
  with tempfile.TemporaryDirectory() as folder:
   b=live.LiveBroadcast();self.assertTrue(b.start_many([('YouTube',str(Path(folder)/'one.flv'),'flv')]))
   for packet in self.packets:b.feed(*packet)
   drain(b);b.stop(wait=True)
   self.assertEqual(b.targets,{});self.assertIn('You are live on YouTube.',[m for _,m in events(b)])
 def several(self,encoder=None,expected=('h264',),source=None):
  with tempfile.TemporaryDirectory() as folder:
   paths=[str(Path(folder)/'a.flv'),str(Path(folder)/'b.flv')]
   b=live.LiveBroadcast();self.assertTrue(b.start_many([('Twitch',paths[0],'flv'),('Kick',paths[1],'flv')],encoder=encoder))
   self.assertEqual(b.name,'Twitch and Kick')
   for packet in source or self.packets:b.feed(*packet)
   drain(b,30);self.assertEqual(b.state,'live');b.stop(wait=True)
   messages=[m for _,m in events(b)];self.assertTrue(any(m.startswith('You are live on Twitch and Kick') for m in messages),messages)
   for path in paths:
    with av.open(path) as result:
     self.assertIn(result.streams.video[0].codec_context.name,expected);self.assertEqual(result.streams.audio[0].codec_context.name,'aac')
     frames=sum(1 for _ in result.decode(video=0))
    self.assertGreaterEqual(frames,50,path)
 def test_the_same_stream_goes_to_each_service(self):self.several()
 def test_a_stream_made_again_once_goes_to_each_service(self):self.several('libsvtav1',AV1)
 def test_the_overlay_stream_of_this_pcs_card_goes_to_each_service(self):
  encoder=video_encoders.for_live_h264()
  if not encoder:self.skipTest('no graphics card H.264 encoder on this PC')
  self.several(encoder,('h264',),packets(2,size=(640,368)))
 def test_a_refused_service_is_named_without_its_key_and_the_others_go_on(self):
  with tempfile.TemporaryDirectory() as folder:
   path=str(Path(folder)/'a.flv');b=live.LiveBroadcast()
   self.assertTrue(b.start_many([('YouTube',path,'flv'),('Kick','rtmp://127.0.0.1:1/app/secret_key_42','flv')]))
   for packet in self.packets:b.feed(*packet)
   ends=time.monotonic()+20
   while b.targets.get('Kick')=='live' and time.monotonic()<ends:time.sleep(.1)
   self.assertEqual(b.targets['Kick'],'trying');self.assertEqual(b.targets['YouTube'],'live')
   b.stop(wait=True)
   with av.open(path) as result:frames=sum(1 for _ in result.decode(video=0))
   self.assertGreaterEqual(frames,50)
  found=events(b);self.assertTrue(all('secret_key_42' not in m for _,m in found))
  self.assertTrue(any(m.startswith('Kick did not take the live stream') for _,m in found),found)
 def test_a_service_that_ends_is_left_out_and_named(self):
  b=live.LiveBroadcast();b.targets={'Twitch':'live','Kick':'live'};b.name='Twitch and Kick'
  watch=live.TeeWatch(b,[('Twitch','rtmp://a/app/1','flv'),('Kick','rtmp://b/app/2','flv')])
  watch.read('libav.tee','Slave muxer #1 failed: Error number -10053 occurred, continuing with 1/2 slaves.')
  self.assertEqual(b.targets,{'Twitch':'live','Kick':'ended'});self.assertEqual(b.name,'Twitch')
  self.assertIn(('error','Kick ended the live stream. It goes on on Twitch.'),events(b))
  watch.read('libav.fifo','FIFO queue full');self.assertEqual(events(b),[])
 def test_a_full_queue_says_the_upload_cannot_carry_it_once(self):
  b=live.LiveBroadcast();b.targets={'Twitch':'live','Kick':'live'}
  watch=live.TeeWatch(b,[('Twitch','rtmp://a/app/1','flv'),('Kick','rtmp://b/app/2','flv')])
  watch.read('libav.fifo','FIFO queue full');watch.read('libav.fifo','FIFO queue full')
  found=events(b);self.assertEqual(len(found),1);self.assertIn('upload cannot carry',found[0][1])
 def test_hevc_is_refused_for_several_rtmp_services(self):
  b=live.LiveBroadcast();b.codec=live.HEVC
  with self.assertRaisesRegex(ValueError,'Twitch and Kick take H.264'):b.start_many([('Twitch','rtmp://127.0.0.1:1/app/x','flv'),('Kick','rtmp://127.0.0.1:1/app/y','flv')])
  self.assertFalse(b.active)
 def test_ffmpeg_messages_go_back_as_they_were(self):
  import logging,av.logging
  logger=logging.getLogger('libav');before=(list(logger.handlers),logger.propagate,av.logging.get_level())
  with tempfile.TemporaryDirectory() as folder:
   b=live.LiveBroadcast();b.start_many([('A',str(Path(folder)/'a.flv'),'flv'),('B',str(Path(folder)/'b.flv'),'flv')])
   for packet in self.packets[:40]:b.feed(*packet)
   b.stop(wait=True)
  self.assertEqual((list(logger.handlers),logger.propagate,av.logging.get_level()),before)

if __name__=='__main__':unittest.main()
