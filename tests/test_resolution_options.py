import argparse,json,os,socket,struct,subprocess,sys,threading,time,unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import av,numpy as np
import playbridge as core
from media_capture import is_idr
from media_fixture import packets

def wire(kind,data,pts=0,dts=0):return struct.pack('<4sBBHIQQI',b'PSAV',1,kind,0,len(data),pts,dts,0)+data

class FakeConsole:
 """A socketpair standing in for the payload: records the request, then sends what the test gives it."""
 def __init__(self,ack,media):
  self.app,self.console=socket.socketpair();self.request=None;self.ack=ack;self.media=media;self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
 def run(self):
  data=b''
  while len(data)<16:data+=self.console.recv(16-len(data))
  self.request=struct.unpack('<4sIII',data)
  if self.ack is not None:
   body=json.dumps(self.ack).encode();self.console.sendall(wire(3,body))
  # The app may close first, for example after a decoder failure.
  try:
   for kind,payload,pts,dts in self.media:self.console.sendall(wire(kind,payload,pts,dts))
  except OSError:pass
  self.console.close()

def paced(media):
 """The real console sends in real time; closing at once would end the session with packets still queued for the decoder."""
 for item in media:
  yield item;time.sleep(.002)

def noisy_packets(count=60):
 """Noise takes real work to decode: the fixture's flat frames finish before a release can catch a thread busy."""
 v=av.CodecContext.create('libx264','w');v.width=160;v.height=96;v.pix_fmt='yuv420p';v.time_base=Fraction(1,60);v.framerate=Fraction(60,1);v.bit_rate=8000000;v.options={'preset':'ultrafast','tune':'zerolatency'};v.open()
 grain=np.random.default_rng(1).integers(0,255,(96,160,3),dtype=np.uint8);result=[]
 for i in range(count):
  f=av.VideoFrame.from_ndarray(np.roll(grain,i*3,axis=1),format='rgb24').reformat(format='yuv420p');f.pts=i;f.time_base=Fraction(1,60)
  result+=[bytes(p) for p in v.encode(f)]
 return result

def release_busy_decoder():
 """Runs in a child process: a decoder that deadlocks on release would also hang the test runner."""
 p=core.Player(argparse.Namespace(renderer='gdi',profile='uhd_balanced',auto_reconnect=False,device=None,connect_only=True,host='127.0.0.1',record=False,preview=False,headless=True,seconds=0))
 p.capture_info={'resolution':6};done=threading.Event();items=[(data,n*1500,n*1500,0) for n,data in enumerate(noisy_packets())]
 class StopAfterLast:
  # The session ending right after a packet: the worker releases the decoder while its threads are still busy.
  def get(self,timeout=None):
   item=items.pop(0)
   if not items:done.set()
   return item
 p.decode_video(StopAfterLast(),done);print(json.dumps({'decoded':p.stats['video_decoded'],'failure':str(p.decode_failure or '')}))

class ResolutionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.packets=packets(2)
 def player(self,profile='balanced'):return core.Player(argparse.Namespace(renderer='gdi',profile=profile,auto_reconnect=False,device=None,connect_only=True,host='127.0.0.1',record=False,preview=False,headless=True,seconds=0))
 def stream(self,profile,ack,media,player=None):
  p=player or self.player(profile);console=FakeConsole(ack,media)
  with patch.object(core.socket,'create_connection',return_value=console.app):p.network_session()
  console.thread.join(timeout=5);return p,console
 def ack(self,**fields):return dict({'protocol':2,'confirmed':True,'fps_target':60,'bitrate_target':8000000,'resource_profile':14,'resolution':4,'resolution_requested':4,'output_mode':16,'refused_by':0},**fields)
 def test_profiles_match_the_payload_bitrate_lists(self):
  allowed={4:{4,8,12,16,20,30},5:{20,30,50},6:{40,60,80}}
  for name,profile in core.PROFILES.items():
   self.assertIn(profile['bitrate']//1000000,allowed[profile.get('resolution',4)],name)
 def test_request_carries_the_resolution(self):
  for profile,field in (('balanced',0),('qhd_high',5),('uhd_maximum',6)):
   _,console=self.stream(profile,self.ack(),[])
   self.assertEqual(console.request,(b'PBO1',60,core.PROFILES[profile]['bitrate'],field))
 def test_stream_decodes_on_the_worker_with_audio(self):
  p,_=self.stream('balanced',self.ack(),paced(self.packets))
  self.assertGreater(p.stats['video_decoded'],30);self.assertGreater(p.stats['audio_samples_decoded'],0);self.assertEqual(p.stats['video_packets_dropped'],0)
  self.assertEqual((p.last_native_frame.width,p.last_native_frame.height),(160,96))
 def test_decoder_threads_follow_the_confirmed_resolution(self):
  self.assertEqual(core.video_threads(4),('SLICE',1));self.assertEqual(core.video_threads(5),('FRAME',2));self.assertEqual(core.video_threads(6),('FRAME',3))
  # A 4K request stepped down to 1080p must not pay frame-thread delay.
  p,_=self.stream('uhd_balanced',self.ack(resolution=4,resolution_requested=6),[]);self.assertEqual(p.video_decoder().thread_count,1)
  p,_=self.stream('uhd_balanced',self.ack(resolution=6,resolution_requested=6),[]);self.assertEqual(p.video_decoder().thread_count,3)
 def test_audio_queue_limit_follows_the_confirmed_resolution(self):
  # Audio arrives late behind large frames above 1080p, and a burst of late audio must not be trimmed away.
  p=self.player();late=bytes(192*120)
  for info,kept,trimmed in (({'resolution':6},len(late),False),({'resolution':5},len(late),False),({'resolution':4},7680,True),({'protocol':2},7680,True)):
   p.pcm.clear();p.stats['audio_trim_samples']=0;p.capture_info=info;p.push_audio(late)
   self.assertEqual(len(p.pcm),kept,info);self.assertEqual(p.stats['audio_trim_samples']>0,trimmed,info)
  # The queue stays bounded at 4K too.
  p.pcm.clear();p.capture_info={'resolution':6};p.push_audio(bytes(192*200));self.assertEqual(len(p.pcm),23040)
 def test_decoded_frames_reach_the_pacer_in_order_with_their_timestamps(self):
  p,_=self.stream('balanced',self.ack(),paced(self.packets));p.render_size=(80,48)
  self.assertEqual(p.stats['video_replaced']>0,p.stats['video_decoded']>core.DECODED_FRAMES);self.assertEqual(len(p.frames),core.DECODED_FRAMES)
  stamps={x[2]/90000 for x in self.packets if x[0]==1};thread=threading.Thread(target=p.convert_video,daemon=True);thread.start();until=time.perf_counter()+3
  while p.frames and time.perf_counter()<until:time.sleep(.005)
  p.stop.set();thread.join(3);self.assertEqual(len(p.pacer.items),core.DECODED_FRAMES)
  pts=[x[0] for x in p.pacer.items];self.assertEqual(pts,sorted(pts));self.assertTrue(all(any(abs(x-s)<1e-6 for s in stamps) for x in pts))
 def test_the_playback_cap_converts_only_the_newest_frame(self):
  p,_=self.stream('data_saver',self.ack(),paced(self.packets));p.render_size=(80,48);newest=p.frames[-1][0].pts;before=p.stats['video_replaced'];thread=threading.Thread(target=p.convert_video,daemon=True);thread.start();until=time.perf_counter()+3
  while p.frames and time.perf_counter()<until:time.sleep(.005)
  p.stop.set();thread.join(3);self.assertEqual(p.pacer.newest,newest/90000);self.assertEqual(p.stats['video_replaced']-before,core.DECODED_FRAMES-1)
 def test_frame_threaded_decoder_releases_while_busy(self):
  run=subprocess.run([sys.executable,'-c','import test_resolution_options as t;t.release_busy_decoder()'],cwd=Path(__file__).parent,capture_output=True,text=True,timeout=30)
  self.assertEqual(run.returncode,0,run.stderr[-500:])
  report=json.loads(run.stdout.strip().splitlines()[-1]);self.assertGreater(report['decoded'],10);self.assertEqual(report['failure'],'')
 def test_older_payload_without_resolution_fields_still_streams(self):
  p,_=self.stream('balanced',{'protocol':2,'confirmed':True,'fps_target':60,'bitrate_target':8000000,'resource_profile':14},paced(self.packets))
  self.assertGreater(p.stats['video_decoded'],30);self.assertEqual(core.resolution_notice(p.capture_info),'');self.assertEqual(p.video_decoder().thread_count,1)
 def test_slow_decoder_drops_until_idr_and_keeps_audio(self):
  video=[x for x in self.packets if x[0]==1];audio=[x for x in self.packets if x[0]==2]
  self.assertGreater(sum(is_idr(x[1]) for x in video),1)
  class Slow:
   decoded=[]
   def decode(self,packet):
    time.sleep(.1);self.decoded.append(bytes(packet));return []
  slow=Slow();p=self.player()
  with patch.object(core.Player,'video_decoder',return_value=slow):self.stream('balanced',self.ack(),self.packets,p)
  self.assertGreater(p.stats['video_packets_dropped'],0);self.assertGreater(p.stats['audio_samples_decoded'],0);self.assertEqual(p.error,'The PS5 connection ended. You can reconnect.')
  self.assertEqual(p.stats['audio_packets'],len(audio))
  # Whatever the decoder got after the first gap starts at an IDR, never a frame whose reference is missing.
  sent=[x[1] for x in video];positions=[sent.index(d) for d in slow.decoded]
  gap=next((i for i in range(1,len(positions)) if positions[i]!=positions[i-1]+1),None)
  if gap is not None:self.assertTrue(is_idr(sent[positions[gap]]))
 def test_decoder_failure_ends_the_session_with_its_message(self):
  class Broken:
   def decode(self,packet):raise ValueError('decoder exploded')
  p=self.player();video=[x for x in self.packets if x[0]==1]
  # The console keeps the socket open long enough for the reader to see the failure.
  def media():
   for item in video:
    yield item;time.sleep(.005)
  with patch.object(core.Player,'video_decoder',return_value=Broken()):self.stream('balanced',self.ack(),media(),p)
  self.assertEqual(p.error,'decoder exploded')
 def test_manual_mode_explains_a_rejected_request(self):
  p,_=self.stream('uhd_balanced',None,[]);self.assertIn('load the current PlayBridge.elf',p.error)
 def test_notice_explains_a_step_down(self):
  self.assertEqual(core.resolution_notice(None),'');self.assertEqual(core.resolution_notice({'protocol':1,'confirmed':False}),'')
  self.assertEqual(core.resolution_notice(self.ack()),'');self.assertEqual(core.resolution_notice(self.ack(resolution=6,resolution_requested=6)),'')
  self.assertEqual(core.resolution_notice(self.ack(resolution=4,resolution_requested=6)),'PS5 video output does not allow 4K, streaming 1080p')
  self.assertEqual(core.resolution_notice(self.ack(resolution=5,resolution_requested=6,refused_by=0x81950008)),'PS5 refused 4K (0x81950008), streaming 1440p')
if __name__=='__main__':unittest.main()
