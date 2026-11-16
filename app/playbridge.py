"""Direct PS5 AV receiver: WASAPI audio and refresh-paced video."""
import argparse,array,collections,json,os,queue,re,socket,struct,sys,threading,time,traceback
from fractions import Fraction
from pathlib import Path
HERE=Path(__file__).resolve().parent
BUNDLE=Path(getattr(sys,'_MEIPASS',HERE))
PAYLOAD_FILE=next((p for p in (BUNDLE/'PlayBridge.elf',HERE/'PlayBridge.elf',HERE.parent/'PlayBridge.elf') if p.is_file()),BUNDLE/'PlayBridge.elf')
# The controller companion, sent only when "Play on your PS5" is on: a process of its own on the PS5, apart from the video payload.
COMPANION_FILE=next((p for p in (BUNDLE/'PlayBridge-Controller.elf',HERE/'PlayBridge-Controller.elf',HERE.parent/'PlayBridge-Controller.elf') if p.is_file()),BUNDLE/'PlayBridge-Controller.elf')
def companion_bytes():
 try:return COMPANION_FILE.read_bytes()
 except OSError:return None
STATE=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'PlayBridge'
STATE.mkdir(parents=True,exist_ok=True)
def config():
 try:return json.loads((STATE/'settings.json').read_text(encoding='utf8'))
 except (OSError,ValueError):return {}
def save_config(**values):
 data=config();data.update(values);(STATE/'settings.json').write_text(json.dumps(data,indent=2),encoding='utf8')
DEPS=Path(os.environ['PLAYBRIDGE_DEPS']) if os.environ.get('PLAYBRIDGE_DEPS') else None
if not getattr(sys,'frozen',False) and DEPS is not None and DEPS.is_dir():sys.path.insert(0,str(DEPS))
import av,sounddevice as sd
from video_convert import reformat_for_display
from frame_pacing import FramePacer
from repeat_frames import RepeatFrames
from watch_alerts import MotionMeter
from media_capture import CaptureRecorder,ReplayBuffer,is_idr,save_clip
from live_broadcast import LiveBroadcast,seal,unseal
from phone_link import PhoneFeed
from compact_video import Compactor,recycle
from save_backup import SaveBackup
from fan_target import FanProfiles
from console_control import AWAY_END,CONTROL_PORT,ConsoleLink,POWER_OFF,REBOOT,REST,call as console_call,running_title
import discord_link,twitch_chat
from highlights import MomentLog
from console_discovery import SUPPORTED_FIRMWARE,firmware_name,locate,supported
from stream_metrics import StreamMetrics,export_diagnostics
from perf_watch import PerfWatch,line as perf_line
import bug_report
import away_play,graphics_card,network_link,secure_link,udp_video,updater
from audio_output import candidates,check_report,default_output,describe,output_name,output_settings
from mic_mix import LEVEL_MAX,MicMix,Microphone
from av.codec.hwaccel import HWAccel
import numpy as np
HDR=struct.Struct('<4sBBHIQQI')
# Which captures go to a Discord channel, the setting that chooses each, and whether it is on before anything is chosen.
DISCORD_KINDS=(('Screenshot','discord_shots',True),('Trophy clip','discord_trophies',True),('Replay','discord_clips',False),('Recording','discord_clips',False))
# How long the profile keeps the game while the console link comes back, as it does around a game's close screen.
PRESENCE_GRACE=60.0
def share_encoders():
 """H.264 encoders for a clip's Discord copy: a graphics card's first, so the processor stays free, then the processor's."""
 import video_encoders
 return [name for name in video_encoders.found() if name in video_encoders.SAME_CODEC]+['libx264','h264_mf']
PROFILES={'data_saver':{'name':'Data saver · 4 Mbps · 30 fps playback','fps':60,'bitrate':4000000,'playback_fps':30},'balanced':{'name':'Balanced · 1080p60 · 8 Mbps','fps':60,'bitrate':8000000},'high':{'name':'High quality · 1080p60 · 12 Mbps','fps':60,'bitrate':12000000},'very_high':{'name':'Very high · 1080p60 · 16 Mbps','fps':60,'bitrate':16000000},'ultra':{'name':'Ultra · 1080p60 · 20 Mbps','fps':60,'bitrate':20000000},'maximum':{'name':'Maximum · 1080p60 · 30 Mbps','fps':60,'bitrate':30000000},'qhd_balanced':{'name':'1440p60 · 20 Mbps','fps':60,'bitrate':20000000,'resolution':5},'qhd_high':{'name':'1440p60 · 30 Mbps','fps':60,'bitrate':30000000,'resolution':5},'qhd_maximum':{'name':'1440p60 · 50 Mbps','fps':60,'bitrate':50000000,'resolution':5},'uhd_balanced':{'name':'4K60 · 40 Mbps','fps':60,'bitrate':40000000,'resolution':6},'uhd_high':{'name':'4K60 · 60 Mbps','fps':60,'bitrate':60000000,'resolution':6},'uhd_maximum':{'name':'4K60 · 80 Mbps','fps':60,'bitrate':80000000,'resolution':6}}
RESOLUTION_NAMES={4:'1080p',5:'1440p',6:'4K'}
VIDEO_QUEUE_PACKETS=12
# Frame threads can finish several frames at once.
DECODED_FRAMES=4
def unreachable(host,elsewhere=None):
 """What to say when nothing at the address takes the connection, with the address, so a wrong one shows."""
 if elsewhere:return f'No PS5 answered at {host}, but one did at {elsewhere}. Enter that address in Settings, or select Find console.'
 return f'Unable to connect to the PS5 at {host}. Check its IP address and make sure the ELF loader is running.'
def last_seconds(steps,ended,window=3):
 """What the last seconds of a stream looked like on this PC: how long ago the last packet came, the longest wait for one,
 and the longest time spent on one. steps holds (arrived, kind, done) for each packet."""
 recent=[s for s in steps if s[0]>=ended-window]
 if not recent:return f'No packet in the last {window} s before the end'
 waits=[(b[0]-a[2],b[1]) for a,b in zip(recent,recent[1:])];busy=max(((s[2]-s[0]),s[1]) for s in recent)
 names={1:'video',2:'sound',3:'capture reply'};wait=max(waits) if waits else (0,1)
 return (f'Last {window} s: last packet {round((ended-recent[-1][0])*1000)} ms before the end, longest wait for the PS5 {round(wait[0]*1000)} ms '
  f'(before {names[wait[1]]}), longest time on one packet {round(busy[0]*1000)} ms ({names[busy[1]]}), {len(recent)} packets')
def reconnect_delay(attempt):
 """Seconds before connecting again: almost none after a stream that played, then 2, 4 and at most 8 for attempts that keep failing."""
 return .3 if attempt<=0 else min(2**min(attempt,3),8)
CAPTURE_TRY_SECONDS=.5
CAPTURE_WAIT_SECONDS=10
def connect_capture(host,give_up,wait=CAPTURE_WAIT_SECONDS,clock=time.monotonic):
 """Connects to the payload's capture port, which opens about a second after the upload. The PS5 gives no answer to a connect on a
 port nobody listens on, so tries stay short: a longer try would notice the opened port that much later. The wait is counted in
 time, not tries: sixty tries once took 36 s against a payload that had already ended, before PlayBridge sent a new one.
 give_up(seconds) waits between tries and says whether to stop. Returns the socket, or None."""
 end=clock()+wait
 while True:
  try:return socket.create_connection((host,9076),CAPTURE_TRY_SECONDS)
  except OSError:
   if clock()>=end or give_up(.1):return None
NOTIFY_FLAG=1<<16
# The picture and sound over UDP with error correction (udp_video), asked only of a payload that proved this PC's key.
UDP_FLAG=1<<17
# Away from home a connection crosses the internet, so it may take longer than on the home network.
AWAY_CONNECT_SECONDS=6
# Rest mode: how often a resting PS5 is asked whether it woke up, and how long its ELF loader gets to answer once it has.
WAKE_LOOK=3.0;LOADER_BACK=20.0
LOADER_GONE='Your PS5 woke up, but its ELF loader did not come back from rest mode. Run your exploit again, then connect.'
class AwayStep(Exception):
 """The line away from home carries another quality now: the stream starts again with that profile."""
def capture_request(profile,notices=False,udp=False):
 # 1080p H.264 keeps sending 0 so an older manually loaded ELF can still stream. The second byte is the codec, and the bits above it
 # flags: notices asks the PS5 to show one when the stream starts and ends. A payload before 1.6 refuses any flag, so it is sent
 # only while its setting is on.
 p=PROFILES[profile];return struct.pack('<4sIII',b'PBO1',p['fps'],p['bitrate'],p.get('resolution',0)|p.get('codec',0)<<8|(NOTIFY_FLAG if notices else 0)|(UDP_FLAG if udp else 0))
def video_threads(resolution):
 # The console sends one slice per frame, so only frame threads can share the work. Each extra thread adds a frame of delay.
 return ('FRAME',3) if resolution>=6 else ('FRAME',2) if resolution==5 else ('SLICE',1)
# Packets the GPU may take without returning a picture before software takes over.
GPU_PATIENCE=30
EXTRA_SURFACES=4
# Slow decoding spreads out a burst from the network, but a picture that stays on the GPU arrives with the whole burst, and the decoder can finish it before the next thread wakes up.
GPU_DECODED_FRAMES=9
# A trophy clip: the seconds before the moment the trophy was earned and after it, and how far apart the console's clock and this PC's
# may be for the console's time of it to count.
CLIP_BEFORE=30;CLIP_AFTER=5;CLOCK_SLACK=3
def gpu_decoder(codec=0,on_gpu=False,adapter=None):
 # Measured on a 4K recording: 12 ms from packet to picture with the same pixels, against 33 ms on frame threads, and 3.7 ms when the picture stays on the GPU. Returns None where the GPU cannot decode.
 # FFmpeg names the card by its place in Windows' list; without one it takes the default, which on a laptop with two cards is the processor's.
 # A chosen card that will not decode leaves the default one.
 for device in dict.fromkeys((None if adapter is None else str(adapter),None)):
  try:video=av.CodecContext.create('hevc' if codec else 'h264','r',hwaccel=HWAccel(device_type='d3d11va',device=device,allow_software_fallback=False,is_hw_owned=on_gpu))
  except (av.error.FFmpegError,NotImplementedError):continue
  if not video.is_hwaccel:continue
  # Frames waiting for their turn hold on to their surfaces, and running out stops the decoder.
  if on_gpu:video.options={'extra_hw_frames':str(EXTRA_SURFACES)}
  return video
 return None
def audio_limits(resolution):
 # Audio shares the socket with video, so it arrives late behind large frames: over 100 ms at 4K, under 20 ms on a calm 1080p stream. Returns the PCM bytes that start a trim and the bytes it keeps (192 per ms); the queue only grows to the lateness it meets.
 return (30720,23040) if resolution>=5 else (11520,7680)
def resolution_notice(info):
 """Explains a capture running below the requested resolution."""
 if not isinstance(info,dict) or not info.get('resolution_requested') or info['resolution_requested']==info.get('resolution'):return ''
 wanted=RESOLUTION_NAMES.get(info['resolution_requested'],'this resolution');actual=RESOLUTION_NAMES.get(info.get('resolution'),'a lower resolution')
 if info.get('refused_by'):return f"PS5 refused {wanted} ({info['refused_by']:#010x}), streaming {actual}"
 return f"PS5 video output does not allow {wanted}, streaming {actual}"
class Timings:
 def __init__(self):self.values=collections.defaultdict(lambda:collections.deque(maxlen=1800));self.lock=threading.Lock()
 def add(self,name,ms):
  with self.lock:self.values[name].append(ms)
 def summary(self):
  with self.lock:copies={k:list(v) for k,v in self.values.items()}
  result={}
  for name,values in copies.items():
   a=sorted(values);n=len(a)
   result[name]={'samples':n,'mean':round(sum(a)/n,3),'p50':round(a[(n-1)//2],3),'p95':round(a[int((n-1)*.95)],3),'max':round(a[-1],3)}
  return result
class Player:
 def __init__(self,args):
  self.metrics=StreamMetrics();self.metrics_lock=threading.Lock();self.recorder=CaptureRecorder();self.broadcast=LiveBroadcast();self.phone_feed=PhoneFeed();self.last_native_frame=None;self.capture_info=None;self.notice='';self.notice_until=0;self.screenshot_thread=None;self.retry_at=0;self.intentional_disconnect=False;self.follow=config().get('host_auto',True);self.elsewhere=None;self.renderer=(('gdi' if args.headless or not config().get('direct_video',True) else 'd3d11') if sys.platform=='win32' else 'tk') if args.renderer=='auto' else args.renderer;self.timings=Timings();self.args=args;self.stop=threading.Event();self.session_done=threading.Event();self.render_size=(1280,720);self.volume=1.0;self.muted=False;self.save_at=0;self.connection_state='Connecting…';self.lock=threading.Lock();self.pcm=bytearray();self.frames=collections.deque();self.last_drawn=None;self.audio=None;self.sock=None;self.error='';self.stats=collections.Counter();self.peak=0;self.output_name='';self.first_video=None;self.first_audio=None;self.first_arrival=None;self.latest_pts={};self.events=collections.deque(maxlen=60);self.arrival_origin=None;self.transport_growth_ms=0;self.decode_failure=None;self.started=time.perf_counter();self.pacer=FramePacer(self.stats);self.repeats=RepeatFrames(self.stats);self.motion=MotionMeter();self.decoder_name='software';self.decoder_on_gpu=False;self.codec=0;self.console=None;self.video_hidden=False;self.sound_hidden=False;self.replay=ReplayBuffer(config().get('replay_seconds',60));self.moments=MomentLog();self.replay_thread=None;self.link=ConsoleLink(STATE/'library',self.notify);self.link.on_trophy=self.trophy_unlocked;self.trophy_events=queue.SimpleQueue();self.gaps=collections.deque(maxlen=30)
  self.update_state='idle';self.updates=updater.Updater(STATE/'update',automatic=bool(config().get('update_auto',True)),on_change=self.update_changed,channel=config().get('update_channel','stable'));self.restart_after_update=False
  self.perf_watch=PerfWatch(STATE/'perf-history.json')
  # The payload's logs from this run, for finding out why a stream ended. They stay on this PC and the next start clears them.
  self.link.log_folder=STATE/'ps5-logs'
  # Each game's saves, copied to the PC when it closes: read only, from the console's own files.
  self.link.saves=SaveBackup(lambda:self.capture_folder()/'PS5 saves',self.link.game_name,self.notify,recycle,streaming=lambda:self.connection_state=='Connected')
  self.link.saves.auto=bool(config().get('save_backup',True))
  # Each game's fan level: the PS5's own unless chosen in Settings.
  self.link.fans=FanProfiles(STATE/'library'/'fans.json')
  # Your voice in what is saved or sent, only while the microphone is on.
  self.mic_mix=MicMix(av);self.microphone=Microphone(self.mic_mix,sd,console=lambda:self.args.host);self.microphone.notify=self.notify
  # This PC's key, written into each payload it sends (secure_link): the video payload's ports and the controller companion then take
  # this PC only, and everything between them is encrypted. A payload loaded by hand holds no key and stays open, as before.
  # Whether the last video connection was sealed; None until one is made, so a report never claims either before then.
  self.link_secured=None
  self.payload_pairing=secure_link.Pairing(lambda:config().get('pairing_key',''),lambda sealed:save_config(pairing_key=sealed),seal,unseal)
  self.link.connect=lambda host,port:self.payload_pairing.connect(*self.reach(host,port),secure_link.CONTROL,self.reach_seconds())
  self.microphone.connect=lambda host,port:self.payload_pairing.connect(*self.reach(host,port),secure_link.MIC,self.reach_seconds())
  # Play away from home (away_play): whether this session runs away from home, the way there, the quality steps and the stream over UDP.
  self.away_active=False;self.away_route=None;self.away_rate=None;self.away_profile=None;self.udp_video=None;self.udp_lost_seen=0;self.step_again=False
  try:self.mic_mix.level=min(LEVEL_MAX,max(0.0,float(config().get('mic_level',1.0))))
  except (TypeError,ValueError):pass
  # Discord: the game on your profile, and your captures in a channel of yours. Both stay off until set in Settings.
  saved=config();self.discord=dict(app=str(saved.get('discord_app','') or '').strip(),url=unseal(saved.get('discord_webhook','')) if isinstance(saved.get('discord_webhook'),str) else '',
   kinds={kind:bool(saved.get(key,on)) for kind,key,on in DISCORD_KINDS})
  self.presence=discord_link.Presence(lambda:self.discord['app']);self.presence_title=None;self.presence_started=0.0;self.presence_seen=0.0
  self.discord_hook=discord_link.Webhook(lambda:self.discord['url'],lambda kind:self.discord['kinds'].get(kind,False),self.playing_name,self.notify,STATE/'discord',
   busy=lambda:self.connection_state=='Connected',encoders=share_encoders)
  # Your Twitch chat for the overlay, read as an anonymous viewer. Off until a channel is set in Settings.
  self.chat_channel=twitch_chat.channel_name(str(saved.get('twitch_chat','') or ''));self.chat=twitch_chat.Chat(lambda:self.chat_channel)
  # Recordings made smaller after they are saved, only while no stream plays. Off unless chosen in Settings. A file waits too while its
  # Discord copy is made, so it is not replaced under it.
  self.compactor=Compactor(lambda:self.connection_state=='Connected' or self.discord_hook.working());self.compact_saved=None
  if config().get('compact_recordings',False):self.compactor.resume(config().get('compact_waiting',[]))
  # The graphics card that decodes and draws, the same one for both. Read once: changing it applies the next time the app opens.
  try:self.adapter=graphics_card.choose(config().get('graphics_card',graphics_card.AUTOMATIC)) if sys.platform=='win32' else None
  except Exception:self.adapter=None
  try:
   self.link.log_folder.mkdir(parents=True,exist_ok=True)
   for old in self.link.log_folder.glob('session-*'):old.unlink()
  except OSError:self.link.log_folder=None
 def device(self):
  apis=sd.query_hostapis();devs=sd.query_devices();preferred=self.args.device
  if preferred is None:
   try:preferred=json.loads((STATE/'settings.json').read_text())['output']
   except (OSError,ValueError,KeyError):preferred='auto'
  for i,d in enumerate(devs):
   label=d['name']+' ['+apis[d['hostapi']]['name']+']'
   if d['max_output_channels']>=2 and (str(i)==str(preferred) or preferred==label):return i
  return default_output()
 def open_audio(self,index=None):
  """Opens the chosen output, or else a Windows default one, and says whether one opened. When every output refuses, PlayBridge still
  opens and streams the picture, without sound, and the status line says why: in 1.5.0 one such PC could not open the app at all.
  Any refusal is written to audio-check.txt, so a PC we cannot see can tell us why."""
  if index is None:
   try:index=self.device()
   except Exception:index=None
  if self.audio:
   previous,self.audio=self.audio,None
   try:previous.stop();previous.close()
   except Exception:pass
  with self.lock:self.pcm.clear()
  attempts=[]
  for candidate in candidates(index):
   stream=None
   try:
    stream=sd.RawOutputStream(device=candidate,samplerate=48000,channels=2,dtype='int16',blocksize=480,latency='low',extra_settings=output_settings(candidate),callback=self.audio_callback);stream.start()
    self.output_name=output_name(candidate)
   except Exception as e:
    attempts.append((candidate,e))
    if stream is not None:
     try:stream.close()
     except Exception:pass
    continue
   self.audio=stream;self.stats['output_device']=candidate;self.stats['device_latency_ms']=round(stream.latency*1000,1)
   if attempts:self.audio_check(attempts,candidate,stream.latency)
   return True
  self.output_name='';self.stats['output_device']=None;self.stats.pop('device_latency_ms',None);self.audio_check(attempts,None,None)
  self.notify('No sound: '+describe(attempts[0][1])+'. Choose another output in the audio menu.');self.notice_until=time.perf_counter()+30
  return False
 def audio_check(self,attempts,opened,latency):
  try:(STATE/'audio-check.txt').write_text(check_report(attempts,opened,latency,time.strftime('%Y-%m-%d %H:%M:%S')),encoding='utf8')
  except OSError:pass
 def audio_callback(self,outdata,frames,timing,status):
  need=frames*4
  with self.lock:
   take=min(need,len(self.pcm));data=bytes(self.pcm[:take]);del self.pcm[:take]
   self.stats['audio_bytes_played']+=take
   if take<need:self.stats['audio_empty_callbacks']+=1
   if status.output_underflow:self.stats['device_underflows']+=1
  if self.muted or self.sound_hidden:data=bytes(take)
  elif self.volume!=1.0:data=(np.frombuffer(data,dtype='<i2').astype(np.float32)*self.volume).astype('<i2').tobytes()
  outdata[:]=data+bytes(need-take)
 def push_audio(self,data):
  samples=np.frombuffer(data,dtype='<i2');peak=int(np.abs(samples.astype(np.int32)).max()) if len(samples) else 0;high,keep=audio_limits((self.capture_info or {}).get('resolution',4))
  with self.lock:
   self.peak=max(peak,self.peak*.9);self.pcm.extend(data)
   if len(self.pcm)>high:
    skip=(len(self.pcm)-keep)//4*4;del self.pcm[:skip];self.stats['audio_trim_samples']+=skip//4
   self.stats['audio_samples_decoded']+=len(data)//4
   self.stats['audio_peak']=max(self.stats['audio_peak'],peak)
 def exact(self,n):
  b=bytearray()
  while len(b)<n and not self.stop.is_set():
   d=self.sock.recv(n-len(b))
   if not d:raise EOFError('Transmission ended')
   b.extend(d)
  if len(b)!=n:raise EOFError('Stopped')
  return bytes(b)
 def video_decoder(self,software=False):
  resolution=(self.capture_info or {}).get('resolution',4);on_gpu=self.renderer=='d3d11'
  # 1080p already decodes in time on one thread, with no delay for the GPU to remove, but a picture that stays on the GPU costs almost nothing at any size.
  video=None if software or (resolution<5 and not self.codec and not on_gpu) else gpu_decoder(self.codec,on_gpu,self.adapter)
  self.decoder_name='software' if video is None else 'gpu';self.decoder_on_gpu=on_gpu and video is not None
  # Above 1080p the processor may not keep up, so say why before the picture stutters.
  if video is None and resolution>=5:self.notify(graphics_card.processor_notice(resolution,self.graphics()))
  if video is None:video=av.CodecContext.create('hevc' if self.codec else 'h264','r');video.thread_type,video.thread_count=video_threads(max(resolution,5) if self.codec else resolution)
  return video
 def graphics(self):
  """The graphics card and the stream sizes it decodes, read once. None where it cannot be read."""
  try:return graphics_card.probe(self.adapter)
  except Exception:return None
 def decode_video(self,packets,done):
  # Beside the socket reader, so a slow decoder cannot stall audio or the console's 1 s send timeout.
  # sizes: each packet's bytes and whether it is a keyframe, by its timestamp, for telling a game's repeated frames apart.
  video=None;waiting_idr=False;unanswered=0;arrivals={};sizes={}
  try:
   while not done.is_set():
    try:payload,pts,dts,arrived=packets.get(timeout=.1)
    except queue.Empty:continue
    # Its output stopped working, so frames have to come back to memory, and this decoder's references stay with it.
    if video is not None and self.decoder_on_gpu and self.renderer!='d3d11':video=None;waiting_idr=True;arrivals.clear();sizes.clear();unanswered=0
    if waiting_idr and not is_idr(payload,self.codec):self.stats['video_packets_dropped']+=1;continue
    waiting_idr=False
    if video is None:video=self.video_decoder()
    p=av.Packet(payload);p.pts=pts;p.dts=dts;p.time_base=Fraction(1,90000);arrivals[pts]=arrived;key=is_idr(payload,self.codec);sizes[pts]=(len(payload),key);self.motion.add(len(payload),key)
    decode_at=time.perf_counter()
    try:decoded=video.decode(p)
    except av.error.FFmpegError:
     if self.decoder_name!='gpu':raise
     decoded=[];unanswered=GPU_PATIENCE
    self.timings.add('video_decode_ms',(time.perf_counter()-decode_at)*1000)
    unanswered=0 if decoded else unanswered+1
    if self.decoder_name=='gpu' and unanswered>=GPU_PATIENCE:
     # The reference frames stay with the GPU decoder, so software starts at the next keyframe.
     video=self.video_decoder(software=True);waiting_idr=True;unanswered=0;arrivals.clear();sizes.clear()
    for f in decoded:
     # Frame threads return a picture some packets after its own, and its delay counts from its own.
     arrived=arrivals.pop(f.pts,arrived);packet=sizes.pop(f.pts,None)
     with self.metrics_lock:self.metrics.frame(f)
     # A copy of the frame before it, from a game slower than the stream, goes no further while in-between pictures can be made.
     if packet is not None and self.repeats.skip(f.pts,packet[0],packet[1],self.link.game_fps):
      with self.lock:self.last_native_frame=f;self.stats['video_decoded']+=1
      continue
     with self.lock:
      if len(self.frames)>=(GPU_DECODED_FRAMES if self.decoder_on_gpu else DECODED_FRAMES):self.frames.popleft();self.stats['video_replaced']+=1
      self.last_native_frame=f;self.frames.append((f,arrived,time.perf_counter()));self.stats['video_decoded']+=1
  except Exception as e:self.decode_failure=e
  finally:
   # Releasing a frame-threaded decoder while a packet is still in flight can deadlock the process, so drain it first.
   if video is not None:
    try:video.decode(None)
    except Exception:pass
 def find_console(self):
  # The console answers this with nothing loaded on it, so a moved address, rest mode or another firmware need no upload to find out.
  found=locate(self.args.host);self.elsewhere=None
  if found and found['ip']!=self.args.host and not self.follow:
   # An address typed in Settings stays the one used. The console that answered elsewhere is only named if that address fails.
   self.console=None;self.elsewhere=found['ip'];return
  self.console=found
  if self.console is None:return
  if self.console['resting'] and not self.wait_awake():return
  if not supported(self.console):raise RuntimeError(f"Your PS5 runs firmware {firmware_name(self.console['firmware'])}. PlayBridge works on {firmware_name(SUPPORTED_FIRMWARE)} only, so nothing was sent to it.")
  if self.console['ip']!=self.args.host:self.args.host=self.console['ip'];save_config(host=self.args.host)
 def wait_awake(self):
  """The PS5 answers its discovery in rest mode too, so PlayBridge waits for it to wake (with its own controller, or the PlayStation
  App) and then connects. True once it is on, False when the player stopped waiting."""
  self.connection_state='Waiting for your PS5 to wake up…';self.event('The PS5 is in rest mode: waiting for it to wake up');ip=self.console['ip']
  while not self.stop.wait(WAKE_LOOK):
   if self.intentional_disconnect:return False
   found=locate(ip)
   if found and found['ip']==ip and not found['resting']:
    self.console=found;self.woke=True;self.connection_state='Connecting…';self.event('The PS5 woke up');return True
  return False
 def waiting_text(self):
  """What the live view says while no picture has come yet."""
  if self.connection_state.startswith('Waiting for your PS5'):return 'Your PS5 is in rest mode. Wake it with its controller or the PlayStation App, and PlayBridge connects.'
  return 'Connecting to your console…'
 def loader_connection(self):
  """The ELF loader's port. Just after the PS5 wakes from rest mode it can take a few seconds to answer; one that never does did not
  come back with the console, and that is said rather than a wrong address."""
  until=time.monotonic()+(LOADER_BACK if self.woke else 0)
  while True:
   try:return socket.create_connection((self.args.host,9021),5)
   except OSError:
    if time.monotonic()>=until or self.stop.wait(1) or self.intentional_disconnect:
     if self.woke:raise RuntimeError(LOADER_GONE) from None
     raise
 def console_label(self):
  if not self.console:return self.args.host
  return '  ·  '.join(part for part in (self.console['name'],firmware_name(self.console.get('firmware','')),self.args.host) if part)
 def network_session(self):
  try:
   self.away_active=False;self.away_route=None;self.udp_video=None;self.udp_lost_seen=0;reused=False;away=self.away_settings();self.woke=False
   if not self.args.connect_only:
    self.find_console()
    if self.stop.is_set() or self.intentional_disconnect:return
    if away.get('on') and self.away_needed():
     # The PS5 is not on this PC's network: away from home, the payload waiting there is reached the way Settings keeps. Nothing is
     # sent to it.
     self.away_route=away_play.route_of(away)
     if self.away_route is None:raise RuntimeError('Away from home: type your home address in Settings › Console › Away from home.')
     self.away_active=True
    elif away.get('on'):reused=self.reuse_waiting()
    if not self.away_active and not reused:
     if not PAYLOAD_FILE.is_file():raise RuntimeError('The bundled PlayBridge.elf is missing. Reinstall the complete PlayBridge package.')
     payload,self.payload_pairing.video=self.payload_pairing.stamp(PAYLOAD_FILE.read_bytes(),self.away_flags())
     with self.loader_connection() as loader:loader.sendall(payload);loader.shutdown(socket.SHUT_WR)
   # A payload loaded by hand holds no key.
   else:self.payload_pairing.video=False
   if self.away_active:self.sock=self.connect_away()
   elif not reused:
    self.sock=connect_capture(self.args.host,lambda wait:self.stop.wait(wait) or self.intentional_disconnect)
    if self.sock is None:
     if self.stop.is_set() or self.intentional_disconnect:return
     raise RuntimeError('PS5 listener did not start on 9076')
    self.sock=self.payload_pairing.wrap(self.sock,secure_link.VIDEO)
   self.link_secured=self.payload_pairing.video
   self.event('Connection secured: only this PC, encrypted' if self.payload_pairing.video else 'Connection open: the payload holds no key')
   try:self.stats['network_link']=network_link.link(self.sock.getpeername()[0])
   except OSError:self.stats['network_link']=None
   udp=self.away_active and away.get('transport','udp')!='tcp' and isinstance(self.sock,secure_link.SecureSocket)
   self.sock.sendall(capture_request(self.session_profile(),bool(config().get('ps5_notices',False)),udp))
   # Its reports start at once, so the payload knows where to send before its first picture.
   if udp:self.udp_video=udp_video.UdpVideo(self.sock,self.away_route.address(9076),self.sock.udp_keys(),keyframe=lambda packet:is_idr(packet,self.codec),watch=False)
   self.connection_state='Starting capture…';self.sock.settimeout(5);self.sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
   audio=av.CodecContext.create('aac','r');resampler=av.AudioResampler(format='s16',layout='stereo',rate=48000)
   record=(STATE/'av3-test.wire').open('wb') if self.args.record else None
   self.decode_failure=None;decode_done=threading.Event();decode_queue=queue.Queue(VIDEO_QUEUE_PACKETS);waiting_idr=False;behind_at=None;last_video=None
   decoder_thread=threading.Thread(target=self.decode_video,args=(decode_queue,decode_done),name='PlayBridge video decode',daemon=True);decoder_thread.start()
   # When each packet arrived and when PlayBridge was done with it, for the last seconds of the session: if the PS5 ends a stream,
   # this says whether it stopped sending or PlayBridge stopped reading (the payload gives up after 1 s without being read).
   steps=collections.deque(maxlen=1000);pending=None;rate_at=time.perf_counter()+1
   try:
    while not self.stop.is_set():
     if pending:steps.append((*pending,time.perf_counter()));pending=None
     raw=self.exact(32);magic,version,kind,_,size,pts,dts,_=HDR.unpack(raw)
     if magic!=b'PSAV' or version!=1 or kind not in (1,2,3) or not 0<size<=0x200200:raise ValueError('Invalid packet header')
     body_at=time.perf_counter();payload=self.exact(size);now=time.perf_counter();self.timings.add('packet_body_read_ms',(now-body_at)*1000);pending=(now,kind)
     if record:record.write(raw+payload)
     if kind==3:
      if size>4096:raise ValueError('Invalid capture acknowledgement')
      info=json.loads(payload.decode('utf8'))
      if not isinstance(info,dict) or info.get('protocol')!=2:raise ValueError('Unsupported capture acknowledgement')
      self.capture_info=info;self.codec=self.recorder.codec=self.broadcast.codec=self.phone_feed.codec=1 if info.get('codec')==1 else 0
      if self.udp_video is not None and self.sock is not self.udp_video:
       if info.get('transport')=='udp':
        self.udp_video.take_over();self.udp_video.settimeout(self.sock.gettimeout());self.sock=self.udp_video;self.event('Picture and sound over UDP, with error correction')
       else:self.udp_video.detach();self.udp_video=None;self.event('The PS5 kept the stream on TCP')
      # A payload that says nothing about it has no control port to look for.
      if info.get('control') and self.link.session is None:self.link.begin(self.args.host)
      continue
     if self.connection_state!='Connected':self.stats['sessions_connected']+=1;self.event('Picture and sound arriving')
     self.connection_state='Connected';self.error=''
     if self.capture_info is None:self.capture_info={'protocol':1,'confirmed':False}
     if kind==2 and self.microphone.on:self.feed_mixed(payload,pts)
     else:self.recorder.feed(kind,payload,pts,dts);self.replay.feed(kind,payload,pts,dts);self.broadcast.feed(kind,payload,pts,dts);self.phone_feed.feed(kind,payload,pts,dts)
     self.latest_pts[kind]=pts;self.stats['received_bytes']+=size
     # Away from home, once a second: a line that loses too much steps the quality down, and minutes without loss step it back up.
     if self.away_active and self.away_rate is not None and now>=rate_at:
      rate_at=now+1;loss,lost=self.away_loss()
      change=self.away_rate.second(loss,lost,self.transport_growth_ms if self.udp_video is None else 0)
      if change:self.away_profile=change;raise AwayStep(change)
     with self.metrics_lock:self.metrics.packet(size,kind==1)
     if kind==1:
      if self.first_video is None:self.first_video=pts;self.first_arrival=now
      # Where the picture stopped arriving and for how long: a pattern, such as every few seconds, points at Wi-Fi.
      if last_video is not None and now-last_video>network_link.STREAM_GAP:self.stats['stream_gaps']+=1;self.gaps.append((round(now-self.started,1),round((now-last_video)*1000)))
      last_video=now
      growth=(now-self.first_arrival)-(pts-self.first_video)/90000
      self.transport_growth_ms=round(growth*1000,1)
      if self.decode_failure:raise self.decode_failure
      # Every frame references the previous one, so a dropped packet means waiting for the next IDR.
      if waiting_idr and not is_idr(payload,self.codec):self.stats['video_packets_dropped']+=1
      else:
       try:
        decode_queue.put_nowait((payload,pts,dts,now))
        if waiting_idr:self.event(f'Decoding fell behind: {round((now-behind_at)*1000)} ms without a new picture, until the next keyframe')
        waiting_idr=False
       except queue.Full:
        if not waiting_idr:behind_at=now
        waiting_idr=True;self.stats['video_packets_dropped']+=1
     else:
      if self.first_audio is None:self.first_audio=pts
      for p in audio.parse(payload):
       for f in audio.decode(p):
        for pcm in resampler.resample(f):self.push_audio(bytes(pcm.planes[0])[:pcm.samples*4])
      self.stats['audio_packets']+=1
   finally:
    ended=time.perf_counter()
    if pending:steps.append((*pending,ended))
    self.ending=last_seconds(steps,ended)
    decode_done.set();decoder_thread.join(timeout=2)
    if record:record.close()
  except AwayStep as step:
   self.step_again=True;self.event(f'Away from home: the stream starts again at {PROFILES[str(step)]["name"]} for this line')
  except Exception as e:
   self.event(f'Stream ended: {type(e).__name__}: {str(e)[:100]}')
   if getattr(self,'ending',''):self.event(self.ending);self.ending=''
   if not self.stop.is_set() and not self.intentional_disconnect:self.error=('The PS5 closed the connection before streaming. In manual mode, load the current PlayBridge.elf.' if isinstance(e,(EOFError,ConnectionResetError)) and self.capture_info is None and self.args.connect_only else 'The PS5 connection ended. You can reconnect.' if isinstance(e,EOFError) else 'The PS5 stopped sending data.' if isinstance(e,socket.timeout) else unreachable(self.args.host,self.elsewhere) if isinstance(e,OSError) else str(e));(STATE/'av3-error.log').write_text(traceback.format_exc(),encoding='utf8')
  finally:
   self.link.last_look();self.link.end()
   # A UDP side the payload never took gives the TCP connection back before it closes.
   if self.udp_video is not None and self.sock is not self.udp_video:self.udp_video.detach()
   if self.sock:self.sock.close()
   self.connection_state='Disconnected' if not self.error else 'Not connected'
 def update_changed(self):
  """Each step of an update goes on the session timeline once, so a check that went wrong can be seen in av3-stats.json."""
  state=self.updates.state
  if state!=self.update_state:
   self.update_state=state
   if state!='checking':self.event('Update: '+self.updates.text())
 def event(self,text):
  """A timeline of the session for av3-stats.json on this PC only: exported diagnostics leave it out."""
  self.events.append((round(time.perf_counter()-self.started,2),text))
 def network(self):
  attempt=0
  try:
   while not self.stop.is_set() and not self.intentional_disconnect:
    self.sock=None;self.first_video=None;self.first_audio=None;self.first_arrival=None;self.capture_info=None;self.transport_growth_ms=0;self.latest_pts={}
    self.recorder.reset_session();self.replay.reset();self.broadcast.reset_session();self.phone_feed.reset_session();self.mic_mix.reset();self.codec=0
    with self.metrics_lock:self.metrics.reset()
    with self.lock:self.pcm.clear();self.frames.clear();self.pacer.clear();self.last_native_frame=None
    streamed=self.stats['sessions_connected'];self.network_session();self.recorder.stop(wait=True);self.perf_watch.finish()
    again=self.step_again;self.step_again=False
    if self.stop.is_set() or self.intentional_disconnect or not (self.args.auto_reconnect or again):break
    self.stats['reconnection_attempts']+=1
    # A stream that was playing comes back at once, as when closing a game changes the console's picture.
    # Only attempts that never streamed wait longer each time.
    attempt=0 if self.stats['sessions_connected']>streamed else attempt+1
    self.retry_at=time.perf_counter()+reconnect_delay(attempt);self.connection_state='Reconnecting…';self.event(f'Connecting again in {reconnect_delay(attempt)} s')
    while time.perf_counter()<self.retry_at:
     if self.stop.wait(.1) or self.intentional_disconnect:break
    if self.stop.is_set() or self.intentional_disconnect:break
  finally:self.session_done.set()
 def notify(self,message):self.notice=message;self.notice_until=time.perf_counter()+6
 def feed_mixed(self,payload,pts):
  """The console's sound with your voice added, for everything that saves or sends the stream. The sound you hear is never changed."""
  try:mixed=self.mic_mix.mix(payload,pts)
  except Exception as problem:
   # The console's own sound carries on and the microphone goes off with a reason, rather than a recording without sound.
   self.microphone.close();self.notify('Microphone off: '+str(problem));self.notice_until=time.perf_counter()+15;mixed=[(payload,pts)]
  for data,stamp in mixed:self.recorder.feed(2,data,stamp,stamp);self.replay.feed(2,data,stamp,stamp);self.broadcast.feed(2,data,stamp,stamp);self.phone_feed.feed(2,data,stamp,stamp)
 def capture_folder(self):
  path=Path(config().get('capture_folder',str(Path.home()/'Videos'/'PlayBridge')));path.mkdir(parents=True,exist_ok=True);return path
 def capture_path(self,folder,suffix):
  from datetime import datetime
  path=self.capture_folder()/folder;path.mkdir(parents=True,exist_ok=True)
  return path/('PlayBridge-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+suffix)
 def take_screenshot(self):
  with self.lock:frame=self.last_native_frame
  if frame is None:self.notify('No video frame available yet.');return
  if self.screenshot_thread is not None and self.screenshot_thread.is_alive():return
  def save():
   try:
    path=self.capture_path('Screenshots','.png');picture=frame
    if frame.format.name=='d3d11':
     from d3d11_presenter import to_system
     picture=to_system(frame)
    image=reformat_for_display(picture,picture.width,picture.height,'rgb24').to_image();image.save(path)
    self.stats['screenshots_saved']+=1;self.notify('Screenshot saved: '+str(path));self.discord_hook.share('Screenshot',path)
   except Exception:self.notify('Unable to save screenshot. Check the capture folder.')
  self.screenshot_thread=threading.Thread(target=save,name='PlayBridge screenshot',daemon=True);self.screenshot_thread.start()
 def toggle_recording(self):
  if self.recorder.active:self.recorder.stop();self.notify('Saving recording…');return
  if self.connection_state!='Connected' or self.last_native_frame is None:self.notify('Connect to your PS5 before recording.');return
  try:
   if self.recorder.start(self.capture_path('Recordings','.mp4')):self.notify('Recording armed. Waiting for a keyframe…')
  except Exception:self.notify('Unable to start recording. Check the capture folder.')
 def save_replay(self):
  if not self.replay.seconds:self.notify('Instant replay is off. Turn it on in Settings.');return
  if self.replay_thread is not None and self.replay_thread.is_alive():return
  packets=self.replay.take()
  if not any(packet[0]==1 for packet in packets):self.notify('Nothing to save yet.');return
  try:path=self.capture_path('Recordings','.mp4')
  except OSError:self.notify('Unable to save the replay. Check the capture folder.');return
  self.notify('Saving replay…')
  self.replay_thread=threading.Thread(target=save_clip,args=(packets,path,self.recorder.events,self.codec,self.recorder.headers),name='PlayBridge replay',daemon=True);self.replay_thread.start()
 def trophy_unlocked(self,title,earned,since):
  """Trophies that just appeared in the running game's record, from the console link's thread. The window hears of them, and a clip of
  the moment is kept from the instant replay already in memory. The console says when each was earned; that time is used when it
  falls between the two reads that found it, as it does when the two clocks agree, and otherwise the clip ends at the second read."""
  now=time.time();at=max(trophy['at'] for trophy in earned);moment=at if since-CLOCK_SLACK<=at<=now+CLOCK_SLACK else now
  self.trophy_events.put((title,earned))
  if self.recorder.active:
   for trophy in earned:self.moments.trophy(trophy.get('name') or 'Trophy',moment)
  if not config().get('trophy_clips',True):return
  if not self.replay.seconds:self.notify('Trophy earned. Turn on instant replay in Settings to keep a clip of the moment.');return
  timer=threading.Timer(max(0,moment+CLIP_AFTER-now),self.save_trophy_clip,args=(earned,moment));timer.daemon=True;timer.start()
 def save_trophy_clip(self,earned,moment):
  """CLIP_BEFORE seconds before the moment and CLIP_AFTER after it. The newest packet in memory arrived about now, and the stream's
  clock runs at 90 kHz, so the moment is that many ticks before it."""
  packets=self.replay.take();video=[packet for packet in packets if packet[0]==1]
  if not video:return
  end=max(packet[2] for packet in video)-round((time.time()-(moment+CLIP_AFTER))*90000);start=end-(CLIP_BEFORE+CLIP_AFTER)*90000
  chosen=[packet for packet in packets if start<=packet[2]<=end]
  if not any(packet[0]==1 and is_idr(packet[1],self.codec) for packet in chosen):self.notify('Trophy earned, but the instant replay does not reach back to it.');return
  named=next((trophy['name'] for trophy in earned if trophy['name']),'')
  try:path=self.capture_path('Recordings','.mp4')
  except OSError:self.notify('Unable to save the trophy clip. Check the capture folder.');return
  label=re.sub(r'[^A-Za-z0-9 ._-]+','',named).strip()[:48]
  path=path.with_name(path.name.replace('PlayBridge-','PlayBridge-Trophy-'+(label+'-' if label else ''),1))
  save_clip(chosen,path,self.recorder.events,self.codec,self.recorder.headers,'Trophy clip')
 def console_power(self,command):
  """Rest, turn off or reboot. The payload answers once the console has taken the request, with the console's own result; a console
  that stops answering right after it was asked is on its way. Either way the session must not try to come back after that."""
  def ask(sock):
   try:result,_=console_call(sock,command)
   except (OSError,ValueError):return None
   return result
  def done(result):
   if result:self.notify(f'Your PS5 refused this ({result&0xffffffff:#010x}).');return
   self.intentional_disconnect=True
   self.notify({REST:'Your PS5 is going to rest.',REBOOT:'Your PS5 is restarting.'}.get(command,'Your PS5 is turning off.') if result==0 else 'Your PS5 stopped answering as it was asked to '+{REST:'rest.',REBOOT:'restart.'}.get(command,'turn off.'))
   if self.sock:
    try:self.sock.shutdown(socket.SHUT_RDWR)
    except OSError:pass
  if not self.link.online:self.notify('The PS5 is not connected.');return
  self.notify({REST:'Asking your PS5 to rest…',REBOOT:'Asking your PS5 to restart…'}.get(command,'Asking your PS5 to turn off…'))
  if not self.link.work(ask,done):self.notify('The PS5 is not connected.')
 def poll_capture_events(self):
  while True:
   try:kind,message,path=self.recorder.events.get_nowait()
   except queue.Empty:break
   self.notify(message+(': '+path if path else ''))
   # The moments noted while it recorded go beside the file, for its highlights.
   if kind=='status' and path and message==self.recorder.started:self.moments.begin(path,getattr(self.recorder,'began',time.time()))
   elif kind in ('saved','error') and path:self.moments.finish(path)
   elif not self.recorder.active:self.moments.drop()
   # Discord hears first, so a file that is also made smaller waits for its copy to be made.
   if kind=='saved' and path:self.discord_hook.share(message.rsplit(' saved',1)[0],path)
   if kind=='saved' and path and config().get('compact_recordings',False):self.compactor.add(path)
  while True:
   try:_,message,_=self.compactor.events.get_nowait()
   except queue.Empty:break
   self.notify(message)
  # The list of files still to make smaller is saved here, on the app's own thread, so no two threads write the settings at once.
  waiting=self.compactor.remembered()
  if waiting!=self.compact_saved:
   if self.compact_saved is not None or waiting:save_config(compact_waiting=waiting)
   self.compact_saved=waiting
  while True:
   try:_,message=self.broadcast.events.get_nowait()
   except queue.Empty:break
   self.notify(message)
  self.show_presence()
 def playing_name(self):
  """The name of the game running on the PS5, or ''."""
  title=running_title(self.link.status) if self.link.online else None
  return self.link.game_name(title) if title else ''
 def show_presence(self):
  """Your Discord profile follows the game on the PS5, with the time since it opened, and says so when you are live."""
  now=time.time();title=running_title(self.link.status) if self.link.online else None
  if title:self.presence_seen=now
  elif not self.link.online and self.presence_title and now-self.presence_seen<PRESENCE_GRACE:title=self.presence_title
  if title!=self.presence_title:self.presence_title=title;self.presence_started=now
  if not title or not self.discord['app']:self.presence.show(None);return
  live=self.broadcast.name if self.broadcast.state=='live' else ''
  self.presence.show(discord_link.activity(self.link.game_name(title),self.presence_started,live))
 def set_discord(self,app_id=None,url=None,kind=None,on=None):
  """Keeps a Discord setting the moment it changes: the application's ID, the webhook (sealed for this Windows user, like the stream
  key) or whether a kind of capture goes to the channel. Returns what is wrong with what was typed, or ''."""
  if app_id is not None:
   app_id=str(app_id).strip();self.discord['app']=app_id;save_config(discord_app=app_id);self.presence.poke()
   if app_id and not discord_link.APP_ID.match(app_id):return 'An application ID is the long number on the application\'s General Information page.'
  if url is not None:
   url=str(url).strip();problem=discord_link.webhook_problem(url)
   if problem:return problem
   self.discord['url']=url;save_config(discord_webhook=seal(url) if url else '')
  if kind is not None:
   for name,key,_ in DISCORD_KINDS:
    if key==kind:self.discord['kinds'][name]=bool(on)
   save_config(**{kind:bool(on)})
  return ''
 def go_live(self,service,key,server=''):
  """Starts sending the stream on to one service. Returns what stopped it, in words, or ''."""
  return self.go_live_many([(service,key,server)])
 def go_live_many(self,targets):
  """Starts sending the stream on to each of targets, [(service, key, server)], at once. Returns what stopped it, in words, or ''."""
  from live_broadcast import COMPRESSIBLE,SERVICES,destination,names_text
  if self.broadcast.active:return 'You are already live.'
  if not targets:return 'Switch on at least one service to go live on.'
  destinations=[]
  for service,key,server in targets:
   try:address,container=destination(service,key,server)
   except ValueError as problem:return str(problem) if len(targets)==1 else f'{SERVICES.get(service,"A service")}: {problem}'
   destinations.append((SERVICES[service],address,container))
  if self.connection_state!='Connected':return 'Connect to your PS5 before going live.'
  # Smaller stream: only where every service takes HEVC and AV1 over RTMP, and only on a graphics card's encoder.
  encoder=None
  import video_encoders
  if config().get('live_compress',False) and all(service in COMPRESSIBLE for service,_,_ in targets):
   encoder=video_encoders.for_live()
   if encoder is None:self.notify('This PC\'s graphics card makes neither HEVC nor AV1, so the stream goes as the PS5 sent it.')
  # The overlay and the chat can only be drawn into a video made again, so without Smaller stream the graphics card makes it again as H.264.
  if (config().get('live_overlay',False) or (config().get('chat_stream',False) and self.chat_channel)) and encoder is None:
   encoder=video_encoders.for_live_h264()
   if encoder is None:self.notify('This PC\'s graphics card cannot make the video again, so the live stream goes without the overlay.')
  # One service gets the stream as it always did; several get it through one tee, made again at most once.
  try:self.broadcast.start_many(destinations,encoder=encoder)
  except ValueError as problem:return str(problem)
  self.notify(f'Going live on {names_text(name for name,_,_ in destinations)} at the next keyframe…');return ''
 def end_live(self):
  if self.broadcast.active:self.broadcast.stop();self.notify('Ending the live stream…')
 def open_captures(self):
  try:os.startfile(str(self.capture_folder()))
  except OSError:self.notify('Unable to open the capture folder.')
 def away_needed(self):
  """With away play on: whether the PS5 is away from this PC. No PS5 answering here is away; one that answers through a router or a
  tunnel (a Tailscale route home) is away too, so the stream takes the away quality and the payload already waiting."""
  if self.console is None:return self.elsewhere is None
  return network_link.nearby(self.args.host) is False
 def at_home(self):
  """The PS5 on this PC's own network, as console_discovery finds it, or None when this PC is away from it."""
  found=locate(self.args.host)
  if found is None or network_link.nearby(found['ip']) is False:return None
  return found
 def reach(self,host,port):
  """Where one of the console's ports is from here: through the away route while this session runs away from home, else as it is."""
  route=self.away_route if self.away_active else None
  return route.address(port) if route is not None else (host,port)
 def reach_seconds(self):return AWAY_CONNECT_SECONDS if self.away_active else 2.0
 def away_settings(self):
  away=config().get('away');return away if isinstance(away,dict) else {}
 def away_flags(self):
  """The flags for a payload sent from here: with away play on, it waits for this PC after each stream, for the away hours."""
  away=self.away_settings()
  if not away.get('on'):return 0
  hours=away.get('hours') if away.get('hours') in away_play.HOURS else away_play.USUAL_HOURS
  return secure_link.FLAG_AWAY|hours<<8
 def session_profile(self):
  """The quality asked for: the chosen one at home; away, the away quality, or the step the line allows."""
  if not self.away_active:self.away_rate=None;self.away_profile=None;return self.args.profile
  away=self.away_settings();chosen=away.get('profile') if away.get('profile') in PROFILES else away_play.USUAL_PROFILE
  if self.away_rate is None or self.away_rate.top!=chosen:self.away_rate=away_play.AwayRate(PROFILES,chosen);self.away_profile=None
  return self.away_profile or chosen
 def away_loss(self):
  """Over UDP, the share of datagrams lost in the last second and the records lost since the last look; over TCP, none."""
  if self.udp_video is None or self.sock is not self.udp_video:return 0.0,0
  stats=self.udp_video.stats();lost=stats['records_lost']-self.udp_lost_seen;self.udp_lost_seen=stats['records_lost']
  return (self.udp_video.losses[-1] if self.udp_video.losses else 0.0),lost
 def reuse_waiting(self):
  """At home with away play on, the payload of an earlier stream may still be waiting: this PC's key opens it, and nothing is sent."""
  try:sock=socket.create_connection((self.args.host,9076),.6)
  except OSError:return False
  try:self.sock=secure_link.SecureSocket(sock,self.payload_pairing.key(),secure_link.VIDEO,2.0)
  except (OSError,EOFError,secure_link.SecureError):
   sock.close();return False
  self.payload_pairing.video=True;self.event('The payload waiting on the PS5 took this PC again');return True
 def connect_away(self):
  """The video connection away from home, through the way Settings keeps. Only the payload that holds this PC's key answers there."""
  host,port=self.away_route.address(9076);self.payload_pairing.video=True
  try:sock=socket.create_connection((host,port),AWAY_CONNECT_SECONDS)
  except OSError:
   raise RuntimeError(f'Nothing answered at your home address ({host}, port {port}). Check that the PS5 is on, not in rest mode, and that away play was turned on at home.') from None
  try:return secure_link.SecureSocket(sock,self.payload_pairing.key(),secure_link.VIDEO,AWAY_CONNECT_SECONDS)
  except (OSError,EOFError,secure_link.SecureError) as error:
   sock.close()
   if isinstance(error,secure_link.SecureError) and 'another PC' in str(error):raise RuntimeError(str(error)) from None
   raise RuntimeError('The PS5 is not waiting for this PC: its PlayBridge payload was not sent with away play on, or its hours ran out. Start it again at home.') from None
 def send_away_payloads(self,console):
  """At home, with no stream running: the payload and the controller companion go now, with the away flags, so they wait for this
  PC even after PlayBridge closes. A payload already waiting is told to leave first, as the new one could not take its port."""
  if self.tell_away_end():
   time.sleep(1.2);until=time.monotonic()+5
   while time.monotonic()<until:
    try:socket.create_connection((console,9076),.5).close();time.sleep(.3)
    except OSError:break
  flags=self.away_flags();sent=[]
  for name,data in (('PlayBridge.elf',PAYLOAD_FILE.read_bytes() if PAYLOAD_FILE.is_file() else None),('PlayBridge-Controller.elf',companion_bytes())):
   if data is None:continue
   stamped,keyed=self.payload_pairing.stamp(data,flags)
   if not keyed:continue
   try:
    with socket.create_connection((console,9021),5) as loader:loader.sendall(stamped);loader.shutdown(socket.SHUT_WR)
    sent.append(name);time.sleep(.5)
   except OSError:break
  return sent
 def prepare_away(self,hours,done=None):
  """At home, with no stream running: finds the way in from outside and keeps it (away_play.prepare), then sends the payloads that
  wait for this PC. done(result, sent, problem) says how it went: result None with the problem when nothing was changed."""
  def work():
   result=None;sent=[];problem=''
   try:
    found=self.at_home() if self.connection_state!='Connected' else None
    if self.connection_state=='Connected':problem='Disconnect first: the payload that waits for you cannot start while a stream runs.'
    elif found is None:problem='Turn this on at home, with the PS5 on: no PS5 answered on this network.'
    elif found['resting']:problem='Your PS5 is in rest mode. Turn it on, then turn this on.'
    elif not supported(found):problem=f"Your PS5 runs firmware {firmware_name(found['firmware'])}. PlayBridge works on {firmware_name(SUPPORTED_FIRMWARE)} only."
    else:
     keep=self.away_settings();first=keep.get('first') if isinstance(keep.get('first'),int) else None
     result=away_play.prepare(found['ip'],hours,first=first)
     for name in ('profile','transport'):
      if name in keep:result[name]=keep[name]
     if result.get('method')=='manual' and keep.get('address'):result['address']=keep['address']
     save_config(away=result);sent=self.send_away_payloads(found['ip'])
     if 'PlayBridge.elf' not in sent:problem='The PS5\'s ELF loader did not take the payload. Start it, then connect once here at home before you leave: the payload sent then waits for you.'
     self.event(f"Away play prepared: {result.get('method')}"+(f", sent {', '.join(sent)}" if sent else ', nothing sent'))
   except Exception as error:
    problem=f'That did not work: {error}';self.event(f'Away play prepare failed: {type(error).__name__}: {str(error)[:100]}')
   if done:done(result,sent,problem)
  threading.Thread(target=work,name='PlayBridge away prepare',daemon=True).start()
 def tell_away_end(self):
  """Tells the payload waiting on the PS5 to leave once no stream runs: over the control link when it is open, else on its own."""
  if self.link.online:return self.link.send(AWAY_END)
  away=self.away_settings();places=[(self.args.host,CONTROL_PORT)];route=away_play.route_of(away)
  if route is not None:places.append(route.address(CONTROL_PORT))
  for host,port in places:
   try:sock=socket.create_connection((host,port),3)
   except OSError:continue
   try:
    with secure_link.SecureSocket(sock,self.payload_pairing.key(),secure_link.CONTROL) as link:
     result,_=console_call(link,AWAY_END);return result==0
   except (OSError,EOFError,ValueError,struct.error,secure_link.SecureError):sock.close()
  return False
 def end_away(self,done=None):
  """Away play ends: the payload waiting is told to leave, the router's forwards go when this PC is at home, and the settings keep only
  the choices."""
  def work():
   away=self.away_settings();told=self.tell_away_end();removed=False
   # Only the home router holds the forwards: away from home another router answers, and nothing of it is touched.
   if away.get('method')=='router' and isinstance(away.get('first'),int) and not self.away_active and self.at_home() is not None:
    try:router=away_play.Router.find()
    except OSError:router=None
    if router is not None:away_play.remove_all(router,away['first']);removed=True
   save_config(away={k:away[k] for k in ('hours','profile','transport','address','first') if k in away}|{'on':False})
   self.event(f'Away play ended: payload told {told}, forwards removed {removed}')
   if done:done(told,removed)
  threading.Thread(target=work,name='PlayBridge away end',daemon=True).start()
 def companion_payload(self):
  """The controller companion to send, with this PC's key in it when this PC can seal its datagrams; None when it is missing."""
  data=companion_bytes()
  if data is None:return None
  return self.payload_pairing.stamp(data,self.away_flags())[0]
 def snapshot(self):
  with self.lock:
   s=dict(self.stats);s['audio_queue_ms']=round(len(self.pcm)/192,1)
  if self.link_secured is not None:s['secured']=self.link_secured
  # Away from home: no address, only how the stream travels and what the line loses.
  over_udp=self.udp_video is not None and self.sock is self.udp_video
  s['away']=dict(active=self.away_active,transport='udp' if over_udp else 'tcp',profile=self.away_profile or '',udp=self.udp_video.stats() if over_udp else None)
  with self.metrics_lock:s['stream']=self.metrics.summary()
  voice=self.mic_mix.voice;s.update(microphone=self.microphone.on,mic_mixed=self.mic_mix.mixed,mic_short_ms=round(voice.short/48),mic_dropped_ms=round(voice.dropped/48))
  s['timings_ms']=self.timings.summary();s['events']=list(self.events);s['gap_log']=list(self.gaps);s['latency_scope']='PC stages only; transport growth is relative to first video packet, not total HDMI-to-PC latency'
  s.update(recording_state=self.recorder.state,live_state=self.broadcast.state,capture_info=self.capture_info,profile_requested=self.args.profile,renderer=self.renderer,video_decoder=self.decoder_name,**graphics_card.report(self.graphics()),output=self.output_name,error=self.error,observed_seconds=round(time.perf_counter()-self.started,2),transport_delay_growth_ms=self.transport_growth_ms)
  (STATE/'av3-stats.json').write_text(json.dumps(s,indent=2),encoding='utf8');return s
 def report_details(self,look):
  """Report a problem: the details for a new GitHub issue (see bug_report)."""
  return bug_report.details(self.snapshot(),look,perf_line(self.perf_watch.check()))
 def export_diagnostics(self,path):
  try:
   export_diagnostics(path,self.snapshot());self.notify("Diagnostics exported.")
  except Exception:self.notify("Unable to export diagnostics. Check the destination folder.")
 def run(self):
  self.open_audio();self.converter=threading.Thread(target=self.convert_video,daemon=True);self.converter.start();self.worker=threading.Thread(target=(lambda:self.session_done.set()) if self.args.preview else self.network,daemon=True);self.worker.start()
  if self.args.preview:self.connection_state='Ready to connect'
  # New versions from GitHub; never in a timed or headless run, which are tests.
  if not (self.args.headless or self.args.seconds or self.args.preview):
   threading.Thread(target=updater.tidy,args=(self.updates.folder,),name='PlayBridge update tidy',daemon=True).start();self.updates.start()
  if self.args.headless:
   self.session_done.wait(self.args.seconds or 10)
  else:self.ui()
  self.updates.close()
  # A version downloaded and checked goes in now, once this one has closed; Restart and update also opens it again.
  if self.updates.install(relaunch=self.restart_after_update):self.event(f'Installing PlayBridge {self.updates.version} after closing')
  self.stop.set()
  if self.sock:
   try:self.sock.shutdown(socket.SHUT_RDWR)
   except OSError:pass
  self.compactor.stop();self.discord_hook.stop();self.presence.stop();self.chat.stop();self.link.end();self.link.performance.end();self.worker.join(timeout=6);self.converter.join(timeout=2);self.recorder.stop(wait=True);self.broadcast.stop(wait=True)
  if self.screenshot_thread is not None:self.screenshot_thread.join(timeout=3)
  if self.replay_thread is not None:self.replay_thread.join(timeout=30)
  if self.audio:self.audio.stop();self.audio.close()
  print(json.dumps(self.snapshot(),indent=2));return 1 if self.error else 0
 def convert_video(self):
  next_frame_at=0
  while not self.stop.is_set():
   # Behind the game grid nobody sees the console's menu, so it costs nothing beyond decoding.
   if self.video_hidden:
    # Counted, so frames decoded behind another page are not taken for frames lost on the way to the screen.
    with self.lock:self.stats['hidden_frames']+=len(self.frames)+len(self.pacer.items);self.frames.clear();self.pacer.clear()
    self.stop.wait(.01);continue
   rate=PROFILES[self.args.profile].get('playback_fps',0)
   if rate and time.perf_counter()<next_frame_at:
    self.stop.wait(max(0,min(.005,next_frame_at-time.perf_counter())));continue
   with self.lock:
    # The playback cap only ever needs the newest frame; otherwise every frame goes to the pacer.
    while rate and len(self.frames)>1:self.frames.popleft();self.stats['video_replaced']+=1
    item=self.frames.popleft() if self.frames else None
   if item is None:self.stop.wait(.001);continue
   f,arrived,decoded_at=item
   began=time.perf_counter();next_frame_at=began+1/rate if rate else 0;self.timings.add('decoded_slot_wait_ms',(began-decoded_at)*1000);w,h=self.render_size;scale=min(w/f.width,h/f.height);rw=max(1,int(f.width*scale));rh=max(1,int(f.height*scale))
   # Left on the GPU by a decoder that is about to be replaced.
   if self.renderer!='d3d11' and f.format.name=='d3d11':continue
   try:image=f if self.renderer=='d3d11' else reformat_for_display(f,rw,rh,'bgr0') if self.renderer=='gdi' else reformat_for_display(f,rw,rh,'rgb24').to_image()
   except Exception as e:self.error='Video presentation: '+str(e);continue
   with self.lock:
    prepared=time.perf_counter();self.timings.add('video_convert_ms',(prepared-began)*1000);self.pacer.add(f.pts/90000 if f.pts is not None else prepared,(image,arrived,prepared),prepared);self.stats['last_conversion_ms']=round((time.perf_counter()-began)*1000,2)
 def use_gdi(self):
  self.renderer='gdi'
  with self.lock:self.frames.clear();self.pacer.clear();self.last_native_frame=None
 def restart(self):
  if self.worker.is_alive():return
  self.intentional_disconnect=False;self.error='';self.sock=None;self.first_video=None;self.first_audio=None;self.first_arrival=None;self.session_done.clear();self.connection_state='Connecting…'
  with self.lock:self.pcm.clear();self.frames.clear();self.pacer.clear()
  self.stats['reconnections']+=1;self.worker=threading.Thread(target=self.network,daemon=True);self.worker.start()
 def ui(self):
  # The Qt look when it was chosen and Qt is there; otherwise, or if it cannot start, the Tk window, so PlayBridge always opens.
  if self.args.ui=='qt':
   try:from qt_shell import run_qt
   except ImportError as error:self.event(f'Qt look unavailable: {error}')
   else:
    try:run_qt(self);return
    except RuntimeError as error:self.event(f'Qt look did not start: {error}')
  from playbridge_ui import run_ui
  run_ui(self)

def main():
 # A new version, just downloaded, started by the old one to take its place: nothing else opens.
 if len(sys.argv)>2 and sys.argv[1]=='--finish-update':
  import updater;return updater.finish(sys.argv[2],'--relaunch' in sys.argv[3:])
 ap=argparse.ArgumentParser();ap.add_argument('--profile',choices=tuple(PROFILES),default=config().get('profile','balanced'));ap.add_argument('--auto-reconnect',action=argparse.BooleanOptionalAction,default=config().get('auto_reconnect',True));ap.add_argument('--renderer',choices=('auto','d3d11','gdi','tk'),default='auto');ap.add_argument('--ui',choices=('tk','qt'),default=config().get('ui') if config().get('ui') in ('tk','qt') else 'qt');ap.add_argument('--host',default=config().get('host','192.168.1.100'));ap.add_argument('--connect-only',action='store_true',default=config().get('connect_only',False));ap.add_argument('--preview',action='store_true');ap.add_argument('--seconds',type=int,default=0);ap.add_argument('--headless',action='store_true');ap.add_argument('--record',action='store_true',help='Save raw diagnostic wire packets; use F9 for MP4 recording');ap.add_argument('--device');ap.add_argument('--devices',action='store_true');args=ap.parse_args()
 if args.devices:print(sd.query_devices());return 0
 guard=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
 try:guard.bind(('127.0.0.1',19077 if args.preview else 19076))
 except OSError:raise RuntimeError('PlayBridge or another PS5 receiver is already running. Close it before opening another session.')
 try:return Player(args).run()
 finally:guard.close()
if __name__=='__main__':
 try:sys.exit(main())
 except Exception:
  (STATE/'av3-error.log').write_text(traceback.format_exc(),encoding='utf8')
  try:
   import tkinter.messagebox as mb;mb.showerror('PlayBridge — Unable to start',str(sys.exc_info()[1]))
  except Exception:pass
  raise
