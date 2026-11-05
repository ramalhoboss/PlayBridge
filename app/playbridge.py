"""Direct PS5 AV receiver: WASAPI audio and refresh-paced video."""
import argparse,array,collections,json,os,queue,socket,struct,sys,threading,time,traceback
from fractions import Fraction
from pathlib import Path
HERE=Path(__file__).resolve().parent
BUNDLE=Path(getattr(sys,'_MEIPASS',HERE))
PAYLOAD_FILE=next((p for p in (BUNDLE/'PlayBridge.elf',HERE/'PlayBridge.elf',HERE.parent/'PlayBridge.elf') if p.is_file()),BUNDLE/'PlayBridge.elf')
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
from media_capture import CaptureRecorder,ReplayBuffer,is_idr,save_clip
from live_broadcast import LiveBroadcast
from console_control import ConsoleLink,POWER_OFF,REBOOT,REST
from console_discovery import SUPPORTED_FIRMWARE,firmware_name,locate,supported
from stream_metrics import StreamMetrics,export_diagnostics
import graphics_card
from av.codec.hwaccel import HWAccel
import numpy as np
HDR=struct.Struct('<4sBBHIQQI')
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
def capture_request(profile):
 # 1080p H.264 keeps sending 0 so an older manually loaded ELF can still stream. The second byte is the codec.
 p=PROFILES[profile];return struct.pack('<4sIII',b'PBO1',p['fps'],p['bitrate'],p.get('resolution',0)|p.get('codec',0)<<8)
def video_threads(resolution):
 # The console sends one slice per frame, so only frame threads can share the work. Each extra thread adds a frame of delay.
 return ('FRAME',3) if resolution>=6 else ('FRAME',2) if resolution==5 else ('SLICE',1)
# Packets the GPU may take without returning a picture before software takes over.
GPU_PATIENCE=30
EXTRA_SURFACES=4
# Slow decoding spreads out a burst from the network, but a picture that stays on the GPU arrives with the whole burst, and the decoder can finish it before the next thread wakes up.
GPU_DECODED_FRAMES=9
def gpu_decoder(codec=0,on_gpu=False):
 # Measured on a 4K recording: 12 ms from packet to picture with the same pixels, against 33 ms on frame threads, and 3.7 ms when the picture stays on the GPU. Returns None where the GPU cannot decode.
 try:video=av.CodecContext.create('hevc' if codec else 'h264','r',hwaccel=HWAccel(device_type='d3d11va',allow_software_fallback=False,is_hw_owned=on_gpu))
 except (av.error.FFmpegError,NotImplementedError):return None
 # Frames waiting for their turn hold on to their surfaces, and running out stops the decoder.
 if on_gpu:video.options={'extra_hw_frames':str(EXTRA_SURFACES)}
 return video if video.is_hwaccel else None
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
  self.metrics=StreamMetrics();self.metrics_lock=threading.Lock();self.recorder=CaptureRecorder();self.broadcast=LiveBroadcast();self.last_native_frame=None;self.capture_info=None;self.notice='';self.notice_until=0;self.screenshot_thread=None;self.retry_at=0;self.intentional_disconnect=False;self.follow=config().get('host_auto',True);self.elsewhere=None;self.renderer=(('gdi' if args.headless or not config().get('direct_video',True) else 'd3d11') if sys.platform=='win32' else 'tk') if args.renderer=='auto' else args.renderer;self.timings=Timings();self.args=args;self.stop=threading.Event();self.session_done=threading.Event();self.render_size=(1280,720);self.volume=1.0;self.muted=False;self.save_at=0;self.connection_state='Connecting…';self.lock=threading.Lock();self.pcm=bytearray();self.frames=collections.deque();self.last_drawn=None;self.audio=None;self.sock=None;self.error='';self.stats=collections.Counter();self.peak=0;self.output_name='';self.first_video=None;self.first_audio=None;self.first_arrival=None;self.latest_pts={};self.events=collections.deque(maxlen=60);self.arrival_origin=None;self.transport_growth_ms=0;self.decode_failure=None;self.started=time.perf_counter();self.pacer=FramePacer(self.stats);self.decoder_name='software';self.decoder_on_gpu=False;self.codec=0;self.console=None;self.video_hidden=False;self.sound_hidden=False;self.replay=ReplayBuffer(config().get('replay_seconds',60));self.replay_thread=None;self.link=ConsoleLink(STATE/'library',self.notify)
  # The payload's logs from this run, for finding out why a stream ended. They stay on this PC and the next start clears them.
  self.link.log_folder=STATE/'ps5-logs'
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
  return next(a['default_output_device'] for a in apis if a['name']=='Windows WASAPI' and a['default_output_device']>=0)
 def open_audio(self,index=None):
  if index is None:index=self.device()
  if self.audio:
   previous,self.audio=self.audio,None
   try:previous.stop();previous.close()
   except Exception:pass
  with self.lock:self.pcm.clear()
  self.audio=sd.RawOutputStream(device=index,samplerate=48000,channels=2,dtype='int16',blocksize=480,latency='low',callback=self.audio_callback)
  self.audio.start();self.output_name=sd.query_devices(index)['name'];self.stats['output_device']=index;self.stats['device_latency_ms']=round(self.audio.latency*1000,1)
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
  video=None if software or (resolution<5 and not self.codec and not on_gpu) else gpu_decoder(self.codec,on_gpu)
  self.decoder_name='software' if video is None else 'gpu';self.decoder_on_gpu=on_gpu and video is not None
  # Above 1080p the processor may not keep up, so say why before the picture stutters.
  if video is None and resolution>=5:self.notify(graphics_card.processor_notice(resolution,self.graphics()))
  if video is None:video=av.CodecContext.create('hevc' if self.codec else 'h264','r');video.thread_type,video.thread_count=video_threads(max(resolution,5) if self.codec else resolution)
  return video
 def graphics(self):
  """The graphics card and the stream sizes it decodes, read once. None where it cannot be read."""
  try:return graphics_card.probe()
  except Exception:return None
 def decode_video(self,packets,done):
  # Beside the socket reader, so a slow decoder cannot stall audio or the console's 1 s send timeout.
  video=None;waiting_idr=False;unanswered=0;arrivals={}
  try:
   while not done.is_set():
    try:payload,pts,dts,arrived=packets.get(timeout=.1)
    except queue.Empty:continue
    # Its output stopped working, so frames have to come back to memory, and this decoder's references stay with it.
    if video is not None and self.decoder_on_gpu and self.renderer!='d3d11':video=None;waiting_idr=True;arrivals.clear();unanswered=0
    if waiting_idr and not is_idr(payload,self.codec):self.stats['video_packets_dropped']+=1;continue
    waiting_idr=False
    if video is None:video=self.video_decoder()
    p=av.Packet(payload);p.pts=pts;p.dts=dts;p.time_base=Fraction(1,90000);arrivals[pts]=arrived
    decode_at=time.perf_counter()
    try:decoded=video.decode(p)
    except av.error.FFmpegError:
     if self.decoder_name!='gpu':raise
     decoded=[];unanswered=GPU_PATIENCE
    self.timings.add('video_decode_ms',(time.perf_counter()-decode_at)*1000)
    unanswered=0 if decoded else unanswered+1
    if self.decoder_name=='gpu' and unanswered>=GPU_PATIENCE:
     # The reference frames stay with the GPU decoder, so software starts at the next keyframe.
     video=self.video_decoder(software=True);waiting_idr=True;unanswered=0;arrivals.clear()
    for f in decoded:
     # Frame threads return a picture some packets after its own, and its delay counts from its own.
     arrived=arrivals.pop(f.pts,arrived)
     with self.metrics_lock:self.metrics.frame(f)
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
  if self.console['resting']:raise RuntimeError('Your PS5 is in rest mode. Turn it on, then connect.')
  if not supported(self.console):raise RuntimeError(f"Your PS5 runs firmware {firmware_name(self.console['firmware'])}. PlayBridge works on {firmware_name(SUPPORTED_FIRMWARE)} only, so nothing was sent to it.")
  if self.console['ip']!=self.args.host:self.args.host=self.console['ip'];save_config(host=self.args.host)
 def console_label(self):
  if not self.console:return self.args.host
  return '  ·  '.join(part for part in (self.console['name'],firmware_name(self.console.get('firmware','')),self.args.host) if part)
 def network_session(self):
  try:
   if not self.args.connect_only:
    self.find_console()
    if not PAYLOAD_FILE.is_file():raise RuntimeError('The bundled PlayBridge.elf is missing. Reinstall the complete PlayBridge package.')
    payload=PAYLOAD_FILE.read_bytes()
    with socket.create_connection((self.args.host,9021),5) as loader:loader.sendall(payload);loader.shutdown(socket.SHUT_WR)
   self.sock=connect_capture(self.args.host,lambda wait:self.stop.wait(wait) or self.intentional_disconnect)
   if self.sock is None:
    if self.stop.is_set() or self.intentional_disconnect:return
    raise RuntimeError('PS5 listener did not start on 9076')
   self.sock.sendall(capture_request(self.args.profile))
   self.connection_state='Starting capture…';self.sock.settimeout(5);self.sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
   audio=av.CodecContext.create('aac','r');resampler=av.AudioResampler(format='s16',layout='stereo',rate=48000)
   record=(STATE/'av3-test.wire').open('wb') if self.args.record else None
   self.decode_failure=None;decode_done=threading.Event();decode_queue=queue.Queue(VIDEO_QUEUE_PACKETS);waiting_idr=False
   decoder_thread=threading.Thread(target=self.decode_video,args=(decode_queue,decode_done),name='PlayBridge video decode',daemon=True);decoder_thread.start()
   # When each packet arrived and when PlayBridge was done with it, for the last seconds of the session: if the PS5 ends a stream,
   # this says whether it stopped sending or PlayBridge stopped reading (the payload gives up after 1 s without being read).
   steps=collections.deque(maxlen=1000);pending=None
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
      self.capture_info=info;self.codec=self.recorder.codec=self.broadcast.codec=1 if info.get('codec')==1 else 0
      # A payload that says nothing about it has no control port to look for.
      if info.get('control') and self.link.session is None:self.link.begin(self.args.host)
      continue
     if self.connection_state!='Connected':self.stats['sessions_connected']+=1;self.event('Picture and sound arriving')
     self.connection_state='Connected';self.error=''
     if self.capture_info is None:self.capture_info={'protocol':1,'confirmed':False}
     self.recorder.feed(kind,payload,pts,dts);self.replay.feed(kind,payload,pts,dts);self.broadcast.feed(kind,payload,pts,dts)
     self.latest_pts[kind]=pts;self.stats['received_bytes']+=size
     with self.metrics_lock:self.metrics.packet(size,kind==1)
     if kind==1:
      if self.first_video is None:self.first_video=pts;self.first_arrival=now
      growth=(now-self.first_arrival)-(pts-self.first_video)/90000
      self.transport_growth_ms=round(growth*1000,1)
      if self.decode_failure:raise self.decode_failure
      # Every frame references the previous one, so a dropped packet means waiting for the next IDR.
      if waiting_idr and not is_idr(payload,self.codec):self.stats['video_packets_dropped']+=1
      else:
       try:decode_queue.put_nowait((payload,pts,dts,now));waiting_idr=False
       except queue.Full:waiting_idr=True;self.stats['video_packets_dropped']+=1
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
  except Exception as e:
   self.event(f'Stream ended: {type(e).__name__}: {str(e)[:100]}')
   if getattr(self,'ending',''):self.event(self.ending);self.ending=''
   if not self.stop.is_set() and not self.intentional_disconnect:self.error=('The PS5 closed the connection before streaming. In manual mode, load the current PlayBridge.elf.' if isinstance(e,(EOFError,ConnectionResetError)) and self.capture_info is None and self.args.connect_only else 'The PS5 connection ended. You can reconnect.' if isinstance(e,EOFError) else 'The PS5 stopped sending data.' if isinstance(e,socket.timeout) else unreachable(self.args.host,self.elsewhere) if isinstance(e,OSError) else str(e));(STATE/'av3-error.log').write_text(traceback.format_exc(),encoding='utf8')
  finally:
   self.link.last_look();self.link.end()
   if self.sock:self.sock.close()
   self.connection_state='Disconnected' if not self.error else 'Not connected'
 def event(self,text):
  """A timeline of the session for av3-stats.json on this PC only: exported diagnostics leave it out."""
  self.events.append((round(time.perf_counter()-self.started,2),text))
 def network(self):
  attempt=0
  try:
   while not self.stop.is_set() and not self.intentional_disconnect:
    self.sock=None;self.first_video=None;self.first_audio=None;self.first_arrival=None;self.capture_info=None;self.transport_growth_ms=0;self.latest_pts={}
    self.recorder.reset_session();self.replay.reset();self.broadcast.reset_session();self.codec=0
    with self.metrics_lock:self.metrics.reset()
    with self.lock:self.pcm.clear();self.frames.clear();self.pacer.clear();self.last_native_frame=None
    streamed=self.stats['sessions_connected'];self.network_session();self.recorder.stop(wait=True)
    if self.stop.is_set() or self.intentional_disconnect or not self.args.auto_reconnect:break
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
    self.stats['screenshots_saved']+=1;self.notify('Screenshot saved: '+str(path))
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
 def console_power(self,command):
  # The console answers before it goes, and the session must not try to come back after that.
  def done(result):
   if result:self.notify(f'The PS5 refused this ({result:#010x}).');return
   self.intentional_disconnect=True;self.notify({REST:'Your PS5 is going to rest.',REBOOT:'Your PS5 is restarting.'}.get(command,'Your PS5 is turning off.'))
   if self.sock:
    try:self.sock.shutdown(socket.SHUT_RDWR)
    except OSError:pass
  if not self.link.send(command,b'',done):self.notify('The PS5 is not connected.')
 def poll_capture_events(self):
  while True:
   try:kind,message,path=self.recorder.events.get_nowait()
   except queue.Empty:break
   self.notify(message+(': '+path if path else ''))
  while True:
   try:_,message=self.broadcast.events.get_nowait()
   except queue.Empty:break
   self.notify(message)
 def go_live(self,service,key,server=''):
  """Starts sending the stream on. Returns what stopped it, in words, or ''."""
  from live_broadcast import SERVICES,destination
  if self.broadcast.active:return 'You are already live.'
  try:address,container=destination(service,key,server)
  except ValueError as problem:return str(problem)
  if self.connection_state!='Connected':return 'Connect to your PS5 before going live.'
  try:self.broadcast.start(address,container,SERVICES[service])
  except ValueError as problem:return str(problem)
  self.notify(f'Going live on {SERVICES[service]} at the next keyframe…');return ''
 def end_live(self):
  if self.broadcast.active:self.broadcast.stop();self.notify('Ending the live stream…')
 def open_captures(self):
  try:os.startfile(str(self.capture_folder()))
  except OSError:self.notify('Unable to open the capture folder.')
 def snapshot(self):
  with self.lock:
   s=dict(self.stats);s['audio_queue_ms']=round(len(self.pcm)/192,1)
  with self.metrics_lock:s['stream']=self.metrics.summary()
  s['timings_ms']=self.timings.summary();s['events']=list(self.events);s['latency_scope']='PC stages only; transport growth is relative to first video packet, not total HDMI-to-PC latency'
  s.update(recording_state=self.recorder.state,live_state=self.broadcast.state,capture_info=self.capture_info,profile_requested=self.args.profile,renderer=self.renderer,video_decoder=self.decoder_name,**graphics_card.report(self.graphics()),output=self.output_name,error=self.error,observed_seconds=round(time.perf_counter()-self.started,2),transport_delay_growth_ms=self.transport_growth_ms)
  (STATE/'av3-stats.json').write_text(json.dumps(s,indent=2),encoding='utf8');return s
 def export_diagnostics(self,path):
  try:
   export_diagnostics(path,self.snapshot());self.notify("Diagnostics exported.")
  except Exception:self.notify("Unable to export diagnostics. Check the destination folder.")
 def run(self):
  self.open_audio();self.converter=threading.Thread(target=self.convert_video,daemon=True);self.converter.start();self.worker=threading.Thread(target=(lambda:self.session_done.set()) if self.args.preview else self.network,daemon=True);self.worker.start()
  if self.args.preview:self.connection_state='Ready to connect'
  if self.args.headless:
   self.session_done.wait(self.args.seconds or 10)
  else:self.ui()
  self.stop.set()
  if self.sock:
   try:self.sock.shutdown(socket.SHUT_RDWR)
   except OSError:pass
  self.link.end();self.worker.join(timeout=6);self.converter.join(timeout=2);self.recorder.stop(wait=True);self.broadcast.stop(wait=True)
  if self.screenshot_thread is not None:self.screenshot_thread.join(timeout=3)
  if self.replay_thread is not None:self.replay_thread.join(timeout=30)
  if self.audio:self.audio.stop();self.audio.close()
  print(json.dumps(self.snapshot(),indent=2));return 1 if self.error else 0
 def convert_video(self):
  next_frame_at=0
  while not self.stop.is_set():
   # Behind the game grid nobody sees the console's menu, so it costs nothing beyond decoding.
   if self.video_hidden:
    with self.lock:self.frames.clear();self.pacer.clear()
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
  from playbridge_ui import run_ui
  run_ui(self)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--profile',choices=tuple(PROFILES),default=config().get('profile','balanced'));ap.add_argument('--auto-reconnect',action=argparse.BooleanOptionalAction,default=config().get('auto_reconnect',True));ap.add_argument('--renderer',choices=('auto','d3d11','gdi','tk'),default='auto');ap.add_argument('--host',default=config().get('host','192.168.1.100'));ap.add_argument('--connect-only',action='store_true',default=config().get('connect_only',False));ap.add_argument('--preview',action='store_true');ap.add_argument('--seconds',type=int,default=0);ap.add_argument('--headless',action='store_true');ap.add_argument('--record',action='store_true',help='Save raw diagnostic wire packets; use F9 for MP4 recording');ap.add_argument('--device');ap.add_argument('--devices',action='store_true');args=ap.parse_args()
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
