"""Direct PS5 AV receiver: WASAPI audio and latest-frame video."""
import argparse,array,collections,json,os,socket,struct,sys,threading,time,traceback
from fractions import Fraction
from pathlib import Path
HERE=Path(__file__).resolve().parent
PAYLOAD_FILE=HERE/'PlayBridge.elf' if (HERE/'PlayBridge.elf').is_file() else HERE.parent/'PlayBridge.elf'
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
from media_capture import CaptureRecorder
from av.video.reformatter import VideoReformatter,Interpolation
import numpy as np
HDR=struct.Struct('<4sBBHIQQI')
PROFILES={'data_saver':{'name':'Data saver · 4 Mbps · 30 fps playback','fps':60,'bitrate':4000000,'playback_fps':30},'balanced':{'name':'Balanced · 1080p60 · 8 Mbps','fps':60,'bitrate':8000000},'high':{'name':'High quality · 1080p60 · 12 Mbps','fps':60,'bitrate':12000000}}
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
  self.recorder=CaptureRecorder();self.last_native_frame=None;self.capture_info=None;self.notice='';self.notice_until=0;self.screenshot_thread=None;self.retry_at=0;self.intentional_disconnect=False;self.renderer=('gdi' if sys.platform=='win32' else 'tk') if args.renderer=='auto' else args.renderer;self.timings=Timings();self.args=args;self.stop=threading.Event();self.session_done=threading.Event();self.ready_image=None;self.render_size=(1280,720);self.volume=1.0;self.muted=False;self.save_at=0;self.connection_state='Connecting…';self.lock=threading.Lock();self.pcm=bytearray();self.frame=None;self.frame_at=0;self.frame_decoded_at=0;self.last_drawn=None;self.audio=None;self.sock=None;self.error='';self.stats=collections.Counter();self.peak=0;self.output_name='';self.first_video=None;self.first_audio=None;self.first_arrival=None;self.latest_pts={};self.arrival_origin=None;self.transport_growth_ms=0;self.started=time.perf_counter()
 def device(self):
  apis=sd.query_hostapis();devs=sd.query_devices();preferred=self.args.device
  if preferred is None:
   try:preferred=json.loads((STATE/'settings.json').read_text())['output']
   except (OSError,ValueError,KeyError):pass
  if preferred is None:
   try:preferred=json.loads((Path.home()/'AppData/Local/BossQuickDock Receiver/settings.json').read_text())['output']
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
  if self.muted:data=bytes(take)
  elif self.volume!=1.0:data=(np.frombuffer(data,dtype='<i2').astype(np.float32)*self.volume).astype('<i2').tobytes()
  outdata[:]=data+bytes(need-take)
 def push_audio(self,data):
  samples=np.frombuffer(data,dtype='<i2');peak=int(np.abs(samples.astype(np.int32)).max()) if len(samples) else 0
  with self.lock:
   self.peak=max(peak,self.peak*.9);self.pcm.extend(data)
   if len(self.pcm)>11520:
    skip=(len(self.pcm)-7680)//4*4;del self.pcm[:skip];self.stats['audio_trim_samples']+=skip//4
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
 def network_session(self):
  try:
   if not self.args.connect_only:
    with socket.create_connection((self.args.host,9021),5) as loader:loader.sendall(PAYLOAD_FILE.read_bytes());loader.shutdown(socket.SHUT_WR)
   for _ in range(60):
    try:self.sock=socket.create_connection((self.args.host,9076),.5);break
    except OSError:
     if self.stop.wait(.1) or self.intentional_disconnect:return
   if self.sock is None:raise RuntimeError('PS5 listener did not start on 9076')
   self.sock.sendall(struct.pack('<4sIII',b'PBO1',PROFILES[self.args.profile]['fps'],PROFILES[self.args.profile]['bitrate'],0))
   self.connection_state='Starting capture…';self.sock.settimeout(5);self.sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
   video=av.CodecContext.create('h264','r');video.thread_count=1;video.thread_type='SLICE'
   audio=av.CodecContext.create('aac','r');resampler=av.AudioResampler(format='s16',layout='stereo',rate=48000)
   record=(STATE/'av3-test.wire').open('wb') if self.args.record else None
   try:
    while not self.stop.is_set():
     raw=self.exact(32);magic,version,kind,_,size,pts,dts,_=HDR.unpack(raw)
     if magic!=b'PSAV' or version!=1 or kind not in (1,2,3) or not 0<size<=0x200200:raise ValueError('Invalid packet header')
     body_at=time.perf_counter();payload=self.exact(size);now=time.perf_counter();self.timings.add('packet_body_read_ms',(now-body_at)*1000)
     if record:record.write(raw+payload)
     if kind==3:
      if size>4096:raise ValueError('Invalid capture acknowledgement')
      info=json.loads(payload.decode('utf8'))
      if not isinstance(info,dict) or info.get('protocol')!=2:raise ValueError('Unsupported capture acknowledgement')
      self.capture_info=info;continue
     if self.connection_state!='Connected':self.stats['sessions_connected']+=1
     self.connection_state='Connected';self.error=''
     if self.capture_info is None:self.capture_info={'protocol':1,'confirmed':False}
     self.recorder.feed(kind,payload,pts,dts)
     self.latest_pts[kind]=pts;self.stats['received_bytes']+=size
     if kind==1:
      if self.first_video is None:self.first_video=pts;self.first_arrival=now
      growth=(now-self.first_arrival)-(pts-self.first_video)/90000
      self.transport_growth_ms=round(growth*1000,1)
      p=av.Packet(payload);p.pts=pts;p.dts=dts;p.time_base=Fraction(1,90000)
      decode_at=time.perf_counter();decoded=video.decode(p);self.timings.add('video_decode_ms',(time.perf_counter()-decode_at)*1000)
      for f in decoded:
       with self.lock:
        if self.frame is not None:self.stats['video_replaced']+=1
        self.last_native_frame=f;self.frame=f;self.frame_at=now;self.frame_decoded_at=time.perf_counter();self.stats['video_decoded']+=1
     else:
      if self.first_audio is None:self.first_audio=pts
      for p in audio.parse(payload):
       for f in audio.decode(p):
        for pcm in resampler.resample(f):self.push_audio(bytes(pcm.planes[0])[:pcm.samples*4])
      self.stats['audio_packets']+=1
   finally:
    if record:record.close()
  except Exception as e:
   if not self.stop.is_set() and not self.intentional_disconnect:self.error=('The PS5 connection ended. You can reconnect.' if isinstance(e,EOFError) else 'The PS5 stopped sending data.' if isinstance(e,socket.timeout) else 'Unable to connect to the PS5. Check its IP address and make sure the ELF loader is running.' if isinstance(e,OSError) else str(e));(STATE/'av3-error.log').write_text(traceback.format_exc(),encoding='utf8')
  finally:
   if self.sock:self.sock.close()
   self.connection_state='Disconnected' if not self.error else 'Not connected'
 def network(self):
  attempt=0
  try:
   while not self.stop.is_set() and not self.intentional_disconnect:
    self.sock=None;self.first_video=None;self.first_audio=None;self.first_arrival=None;self.capture_info=None;self.transport_growth_ms=0;self.latest_pts={}
    self.recorder.reset_session()
    with self.lock:self.pcm.clear();self.frame=None;self.ready_image=None;self.last_native_frame=None
    self.network_session();self.recorder.stop(wait=True)
    if self.stop.is_set() or self.intentional_disconnect or not self.args.auto_reconnect:break
    attempt+=1;self.stats['reconnection_attempts']+=1
    delay=min(2**min(attempt,3),8);self.retry_at=time.perf_counter()+delay;self.connection_state='Reconnecting…'
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
    path=self.capture_path('Screenshots','.png');r=VideoReformatter();image=r.reformat(frame,format='rgb24',interpolation=Interpolation.BILINEAR|Interpolation.BITEXACT).to_image();image.save(path)
    self.stats['screenshots_saved']+=1;self.notify('Screenshot saved: '+str(path))
   except Exception:self.notify('Unable to save screenshot. Check the capture folder.')
  self.screenshot_thread=threading.Thread(target=save,name='PlayBridge screenshot',daemon=True);self.screenshot_thread.start()
 def toggle_recording(self):
  if self.recorder.active:self.recorder.stop();self.notify('Saving recording…');return
  if self.connection_state!='Connected' or self.last_native_frame is None:self.notify('Connect to your PS5 before recording.');return
  try:
   if self.recorder.start(self.capture_path('Recordings','.mp4')):self.notify('Recording armed. Waiting for a keyframe…')
  except Exception:self.notify('Unable to start recording. Check the capture folder.')
 def poll_capture_events(self):
  import queue
  while True:
   try:kind,message,path=self.recorder.events.get_nowait()
   except queue.Empty:break
   self.notify(message+(': '+path if path else ''))
 def open_captures(self):
  try:os.startfile(str(self.capture_folder()))
  except OSError:self.notify('Unable to open the capture folder.')
 def snapshot(self):
  with self.lock:
   s=dict(self.stats);s['audio_queue_ms']=round(len(self.pcm)/192,1)
  s['timings_ms']=self.timings.summary();s['latency_scope']='PC stages only; transport growth is relative to first video packet, not total HDMI-to-PC latency'
  s.update(recording_state=self.recorder.state,capture_info=self.capture_info,profile_requested=self.args.profile,renderer=self.renderer,output=self.output_name,error=self.error,observed_seconds=round(time.perf_counter()-self.started,2),transport_delay_growth_ms=self.transport_growth_ms)
  (STATE/'av3-stats.json').write_text(json.dumps(s,indent=2),encoding='utf8');return s
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
  self.worker.join(timeout=6);self.converter.join(timeout=2);self.recorder.stop(wait=True)
  if self.screenshot_thread is not None:self.screenshot_thread.join(timeout=3)
  if self.audio:self.audio.stop();self.audio.close()
  print(json.dumps(self.snapshot(),indent=2));return 1 if self.error else 0
 def convert_video(self):
  next_frame_at=0
  while not self.stop.is_set():
   rate=PROFILES[self.args.profile].get('playback_fps',0)
   if rate and time.perf_counter()<next_frame_at:
    self.stop.wait(max(0,min(.005,next_frame_at-time.perf_counter())));continue
   with self.lock:f=self.frame;self.frame=None;arrived=self.frame_at;decoded_at=self.frame_decoded_at
   if f is None:self.stop.wait(.001);continue
   began=time.perf_counter();next_frame_at=began+1/rate if rate else 0;self.timings.add('decoded_slot_wait_ms',(began-decoded_at)*1000);w,h=self.render_size;scale=min(w/f.width,h/f.height);rw=max(1,int(f.width*scale));rh=max(1,int(f.height*scale))
   try:image=reformat_for_display(f,rw,rh,'bgr0') if self.renderer=='gdi' else reformat_for_display(f,rw,rh,'rgb24').to_image()
   except Exception as e:self.error='Video presentation: '+str(e);continue
   with self.lock:
    if self.ready_image is not None:self.stats['prepared_replaced']+=1
    prepared=time.perf_counter();self.timings.add('video_convert_ms',(prepared-began)*1000);self.ready_image=(image,arrived,prepared);self.stats['last_conversion_ms']=round((time.perf_counter()-began)*1000,2)
 def restart(self):
  if self.worker.is_alive():return
  self.intentional_disconnect=False;self.error='';self.sock=None;self.first_video=None;self.first_audio=None;self.first_arrival=None;self.session_done.clear();self.connection_state='Connecting…'
  with self.lock:self.pcm.clear();self.frame=None;self.ready_image=None
  self.stats['reconnections']+=1;self.worker=threading.Thread(target=self.network,daemon=True);self.worker.start()
 def ui(self):
  from playbridge_ui import run_ui
  run_ui(self)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--profile',choices=tuple(PROFILES),default=config().get('profile','balanced'));ap.add_argument('--auto-reconnect',action=argparse.BooleanOptionalAction,default=config().get('auto_reconnect',True));ap.add_argument('--renderer',choices=('auto','gdi','tk'),default='auto');ap.add_argument('--host',default=config().get('host','192.168.1.73'));ap.add_argument('--connect-only',action='store_true',default=config().get('connect_only',False));ap.add_argument('--preview',action='store_true');ap.add_argument('--seconds',type=int,default=0);ap.add_argument('--headless',action='store_true');ap.add_argument('--record',action='store_true',help='Save raw diagnostic wire packets; use F9 for MP4 recording');ap.add_argument('--device');ap.add_argument('--devices',action='store_true');args=ap.parse_args()
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
