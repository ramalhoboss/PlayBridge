"""Discord: the profile's game through a stand-in for the Discord app's pipe, posts through a stand-in for Discord's web server (nothing
leaves this PC), and the small copy of a clip that fits Discord's 10 MB."""
import io,json,os,queue,struct,sys,tempfile,threading,time,unittest,urllib.error
from types import SimpleNamespace
from unittest.mock import patch
from fractions import Fraction
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
import discord_link as dl

APP='123456789012345678'

class FakeDiscord:
 """The Discord app's end of its pipe: READY after the handshake, an answer with the same nonce to each command."""
 def __init__(self,refuse=False):self.refuse=refuse;self.out=b'';self.commands=[];self.lock=threading.Condition();self.closed=False
 def frame(self,opcode,data):
  body=json.dumps(data).encode()
  with self.lock:self.out+=struct.pack('<II',opcode,len(body))+body;self.lock.notify_all()
 def write(self,data):
  opcode,length=struct.unpack('<II',data[:8]);message=json.loads(data[8:8+length])
  if opcode==dl.HANDSHAKE:
   self.frame(dl.CLOSE,{'code':4000,'message':'Invalid Client ID'}) if self.refuse else self.frame(dl.FRAME,{'cmd':'DISPATCH','evt':'READY','data':{'user':{'username':'player'}}})
  elif opcode==dl.FRAME:
   self.commands.append(message);self.frame(dl.FRAME,{'cmd':message['cmd'],'nonce':message['nonce'],'data':{}})
  return len(data)
 def read(self,size):
  with self.lock:
   self.lock.wait_for(lambda:self.out or self.closed,timeout=2)
   part,self.out=self.out[:size],self.out[size:];return part
 def close(self):self.closed=True

def wait_for(test,seconds=4):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  if test():return True
  time.sleep(.02)
 return False

class PresenceTests(unittest.TestCase):
 def test_the_game_reaches_the_profile_and_clears_after(self):
  discord=FakeDiscord();opened=[]
  def opener(path):
   opened.append(path)
   if path!=dl.PIPES[1]:raise FileNotFoundError(path)
   return discord
  presence=dl.Presence(lambda:APP,opener);self.addCleanup(presence.stop)
  shown=dl.activity('Nebula Drift',1_700_000_000,'Twitch');presence.show(shown)
  self.assertTrue(wait_for(lambda:discord.commands and discord.commands[-1]['args']['activity']==shown))
  sent=discord.commands[-1]['args']['activity'];self.assertEqual(sent['details'],'Nebula Drift');self.assertEqual(sent['state'],'Live on Twitch');self.assertEqual(sent['timestamps']['start'],1_700_000_000)
  self.assertIn('as player',presence.state);self.assertEqual(presence.text('Nebula Drift'),'Your Discord profile shows Nebula Drift.')
  presence.show(None);self.assertTrue(wait_for(lambda:discord.commands[-1]['args']['activity'] is None))
  count=len(discord.commands);presence.show(None);time.sleep(.3);self.assertEqual(len(discord.commands),count)
 def test_no_discord_and_a_refused_id_are_told(self):
  presence=dl.Presence(lambda:APP,lambda path:(_ for _ in ()).throw(FileNotFoundError(path)));self.addCleanup(presence.stop)
  self.assertTrue(wait_for(lambda:presence.state=='Discord is not open on this PC.'))
  refused=dl.Presence(lambda:APP,lambda path:FakeDiscord(refuse=True));self.addCleanup(refused.stop)
  self.assertTrue(wait_for(lambda:'refused' in refused.state));self.assertIn('Invalid Client ID',refused.state)
  odd=dl.Presence(lambda:'not a number',lambda path:FakeDiscord());self.addCleanup(odd.stop)
  self.assertTrue(wait_for(lambda:'not a number' in odd.state))

class Answer(io.BytesIO):
 def __enter__(self):return self
 def __exit__(self,*args):return False

class PostTests(unittest.TestCase):
 def test_webhook_addresses_are_checked(self):
  self.assertEqual(dl.webhook_problem('https://discord.com/api/webhooks/123/abc-DEF_1'),'')
  self.assertEqual(dl.webhook_problem(''),'')
  for bad in ('http://discord.com/api/webhooks/1/a','https://discord.com.evil.test/api/webhooks/1/a','https://example.com/api/webhooks/1/a','https://discord.com/api/channels/1'):
   self.assertTrue(dl.webhook_problem(bad),bad)
 def test_a_post_carries_the_words_and_the_file_and_waits_once_when_asked(self):
  seen=[]
  def opener(request,timeout):
   seen.append(request)
   if len(seen)==1:raise urllib.error.HTTPError(request.full_url,429,'slow down',{},io.BytesIO(b'{"retry_after":0.01}'))
   return Answer(b'{}')
  self.assertEqual(dl.post('https://discord.com/api/webhooks/1/a','Hello @everyone',('shot.png','image/png',b'PNGDATA'),opener=opener),'')
  self.assertEqual(len(seen),2);request=seen[-1];body=request.data
  self.assertTrue(request.full_url.endswith('?wait=true'));self.assertIn(b'name="files[0]"; filename="shot.png"',body);self.assertIn(b'PNGDATA',body)
  self.assertIn(b'"parse": []',body);self.assertEqual(request.get_header('User-agent'),'PlayBridge')
  gone=dl.post('https://discord.com/api/webhooks/1/a','x',opener=lambda request,timeout:(_ for _ in ()).throw(urllib.error.HTTPError(request.full_url,404,'gone',{},io.BytesIO(b''))))
  self.assertIn('no longer exists',gone)
 def test_words_name_the_game_and_the_trophy(self):
  self.assertEqual(dl.message_for('Trophy clip','C:/x/PlayBridge-Trophy-First Blood-20261115-101010-123456.mp4','Nebula'),'🏆 Trophy earned in **Nebula**: **First Blood**')
  self.assertEqual(dl.message_for('Screenshot','a.png'),'📸 Screenshot from my PS5')

def make_clip(path,seconds=35,size=(1920,1080),rate=60):
 import av
 import numpy as np
 with av.open(str(path),'w',format='mp4') as out:
  video=out.add_stream('libx264',rate=rate);video.width,video.height=size;video.pix_fmt='yuv420p';video.bit_rate=40_000_000;video.options={'preset':'ultrafast'}
  sound=out.add_stream('aac',rate=48000);sound.layout='stereo'
  noise=np.random.default_rng(1).integers(0,255,(size[1]//8,size[0]//8,3),dtype=np.uint8)
  for index in range(seconds*rate):
   picture=np.roll(noise,index*2,axis=1).repeat(8,0).repeat(8,1);frame=av.VideoFrame.from_ndarray(picture,format='rgb24').reformat(format='yuv420p');frame.pts=index;frame.time_base=Fraction(1,rate)
   out.mux(video.encode(frame))
   if index%(rate//10)==0:
    tone=(np.sin(np.arange(4800)/48000*2*np.pi*440)*.2).astype('float32')
    chunk=av.AudioFrame.from_ndarray(np.stack([tone,tone]),format='fltp',layout='stereo');chunk.sample_rate=48000;chunk.pts=None
    out.mux(sound.encode(chunk))
  out.mux(video.encode(None));out.mux(sound.encode(None))

class ShareCopyTests(unittest.TestCase):
 def test_a_35_second_1080p60_clip_fits_discord(self):
  import av
  folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup);source=Path(folder.name,'clip.mp4');target=Path(folder.name,'small.mp4')
  make_clip(source);self.assertGreater(source.stat().st_size,dl.UPLOAD_MOST)
  self.assertEqual(dl.share_copy(source,target,['libx264']),'')
  self.assertLessEqual(target.stat().st_size,dl.UPLOAD_MOST)
  with av.open(str(target)) as result:
   video=result.streams.video[0];self.assertEqual((video.codec_context.height,video.codec_context.name),(720,'h264'));self.assertTrue(result.streams.audio)
   self.assertAlmostEqual(dl.duration(result,video),35,delta=1.0)
 def test_a_long_clip_is_refused_with_the_reason(self):
  folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup);source=Path(folder.name,'clip.mp4')
  make_clip(source,seconds=2,size=(320,180))
  original=dl.LONGEST;dl.LONGEST=1.0
  try:self.assertIn('longer than',dl.share_copy(source,Path(folder.name,'s.mp4'),['libx264']))
  finally:dl.LONGEST=original

class WebhookTests(unittest.TestCase):
 def test_only_chosen_kinds_go_and_a_test_message_reaches_the_channel(self):
  posted=[];notes=[]
  def opener(request,timeout):posted.append(request.data);return Answer(b'{}')
  folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup);shot=Path(folder.name,'PlayBridge-1.png')
  from PIL import Image
  Image.new('RGB',(64,36),(10,20,30)).save(shot)
  hook=dl.Webhook(lambda:'https://discord.com/api/webhooks/1/a',lambda kind:kind=='Screenshot',lambda:'Nebula',notes.append,folder.name,opener=opener);self.addCleanup(hook.stop)
  hook.share('Replay',shot);hook.share('Screenshot',shot);self.assertTrue(wait_for(lambda:len(posted)==1))
  self.assertIn('Screenshot from **Nebula**'.encode(),posted[0]);self.assertEqual(hook.status,'Screenshot sent to your channel.')
  self.assertEqual(hook.test(),'');self.assertTrue(wait_for(lambda:len(posted)==2));self.assertIn(b'PlayBridge is connected',posted[1])
  quiet=dl.Webhook(lambda:'',lambda kind:True,lambda:'',notes.append,folder.name,opener=opener);self.addCleanup(quiet.stop)
  quiet.share('Screenshot',shot);time.sleep(.2);self.assertEqual(len(posted),2);self.assertIn('Paste a webhook',quiet.test())

class AppTests(unittest.TestCase):
 """The app's side: the profile follows the PS5's game, settings are kept, and each saved capture is handed over before it is made smaller."""
 def setUp(self):
  import playbridge as core
  self.core=core;self.shown=[];self.shared=[]
  self.me=SimpleNamespace(link=SimpleNamespace(online=True,status={},game_name=lambda title:{'PPSA01':'Nebula Drift'}.get(title,title)),discord=dict(app=APP,url='',kinds={'Screenshot':True}),
   presence=SimpleNamespace(show=self.shown.append,poke=lambda:None),presence_title=None,presence_started=0.0,presence_seen=0.0,broadcast=SimpleNamespace(state='',name='Twitch'))
 def test_the_profile_follows_the_game_and_waits_out_a_short_drop(self):
  core=self.core;me=self.me
  with patch.object(core,'running_title',lambda status:status.get('title')):
   me.link.status={'title':'PPSA01'}
   with patch.object(core.time,'time',return_value=1000.0):core.Player.show_presence(me)
   self.assertEqual((self.shown[-1]['details'],self.shown[-1]['state'],self.shown[-1]['timestamps']['start']),('Nebula Drift','Playing on PS5',1000))
   me.broadcast.state='live'
   with patch.object(core.time,'time',return_value=1010.0):core.Player.show_presence(me)
   self.assertEqual((self.shown[-1]['state'],self.shown[-1]['timestamps']['start']),('Live on Twitch',1000))
   me.link.online=False
   with patch.object(core.time,'time',return_value=1040.0):core.Player.show_presence(me)
   self.assertEqual(self.shown[-1]['timestamps']['start'],1000)
   with patch.object(core.time,'time',return_value=1100.0):core.Player.show_presence(me)
   self.assertIsNone(self.shown[-1])
   me.link.online=True;me.discord['app']=''
   with patch.object(core.time,'time',return_value=1200.0):core.Player.show_presence(me)
   self.assertIsNone(self.shown[-1])
 def test_settings_are_kept_and_a_wrong_webhook_is_not(self):
  core=self.core;me=self.me;kept={}
  with patch.object(core,'save_config',lambda **values:kept.update(values)):
   self.assertEqual(core.Player.set_discord(me,url='https://discord.com/api/webhooks/1/abc'),'')
   self.assertEqual(me.discord['url'],'https://discord.com/api/webhooks/1/abc');self.assertNotIn('abc',kept['discord_webhook']);self.assertEqual(core.unseal(kept['discord_webhook']),me.discord['url'])
   self.assertTrue(core.Player.set_discord(me,url='https://example.com/x'));self.assertEqual(me.discord['url'],'https://discord.com/api/webhooks/1/abc')
   self.assertTrue(core.Player.set_discord(me,app_id='12ab'));self.assertEqual(kept['discord_app'],'12ab')
   core.Player.set_discord(me,kind='discord_clips',on=True);self.assertTrue(me.discord['kinds']['Replay'] and me.discord['kinds']['Recording']);self.assertTrue(kept['discord_clips'])
 def test_each_saved_capture_reaches_discord_before_it_is_made_smaller(self):
  core=self.core;order=[];events=queue.SimpleQueue()
  for name in ('Recording','Replay','Trophy clip'):events.put(('saved',f'{name} saved',f'C:/clips/{name}.mp4'))
  events.put(('error','Unable to save',''))
  finished=[];me=SimpleNamespace(recorder=SimpleNamespace(events=events,active=False,started='Recording started'),moments=SimpleNamespace(finish=finished.append,drop=lambda:None,begin=lambda path,at:None),notify=lambda text:None,discord_hook=SimpleNamespace(share=lambda kind,path:order.append(('discord',kind))),
   compactor=SimpleNamespace(add=lambda path:order.append(('smaller',Path(path).stem)),events=queue.SimpleQueue(),remembered=lambda:[]),compact_saved=[],broadcast=SimpleNamespace(events=queue.SimpleQueue()),show_presence=lambda:order.append('presence'))
  with patch.object(core,'config',lambda:{'compact_recordings':True}):core.Player.poll_capture_events(me)
  self.assertEqual(order,[('discord','Recording'),('smaller','Recording'),('discord','Replay'),('smaller','Replay'),('discord','Trophy clip'),('smaller','Trophy clip'),'presence'])
  self.assertEqual(finished,['C:/clips/Recording.mp4','C:/clips/Replay.mp4','C:/clips/Trophy clip.mp4'],'each saved file closes its highlight moments')
 def test_share_encoders_end_with_the_processors(self):
  self.assertEqual(self.core.share_encoders()[-2:],['libx264','h264_mf'])

if __name__=='__main__':unittest.main()
