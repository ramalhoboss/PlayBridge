"""Going live: the console's own H.264 and AAC, copied as they arrive to Twitch, YouTube, TikTok, Kick, any RTMP server, or OBS on this PC,
to one of them or to several at once. Nothing is encoded again, so it costs this PC almost nothing, and the stream is exactly what the PS5
sent. To several services, FFmpeg's tee sends the same packets to each through a queue and a thread of its own, so a slow or refused one
never holds up the others. Only when Smaller stream is on,
for YouTube or another RTMP server, the graphics card makes the video again as AV1 or HEVC (enhanced RTMP) at a fraction of the bitrate.
The stream key is a password: it is never put in a message, a log or the diagnostics, and it is kept encrypted for this Windows user."""
import base64,io,logging,queue,sys,threading,time
from fractions import Fraction
import av
import av.logging
from av.codec.hwaccel import HWAccel
from media_capture import HEVC,codec_headers,is_idr,strip_adts
from frame_overlay import FrameOverlay
import video_encoders

OBS_PORT=9100
SERVICES={'twitch':'Twitch','youtube':'YouTube','tiktok':'TikTok','kick':'Kick','custom':'Other RTMP server','obs':'OBS on this PC'}
# The services whose server address is pasted with the key: TikTok gives a new one for each live stream, Kick shows its own in its dashboard.
WITH_SERVER=('tiktok','kick','custom')
# The services that need a key as well as their server address.
KEY_NEEDED=('twitch','youtube','tiktok','kick')
# The services that take HEVC and AV1 over RTMP. Twitch only does in its Enhanced Broadcasting beta, through OBS, and OBS gets the
# stream on this PC, where a new encode would only cost.
COMPRESSIBLE=('youtube','custom')
# YouTube's encrypted ingest, so the key never crosses the network in the clear. Twitch documents plain RTMP.
INGEST={'twitch':'rtmp://live.twitch.tv/app/','youtube':'rtmps://a.rtmps.youtube.com:443/live2/'}

def destination(service,key='',server=''):
 """The address to send to and the container it takes. Raises ValueError with words for the user."""
 if service=='obs':return f'udp://127.0.0.1:{OBS_PORT}?pkt_size=1316','mpegts'
 key=key.strip()
 # The usual slip: the whole address pasted where only its last part, the key, belongs.
 if key.lower().startswith(('rtmp://','rtmps://')):raise ValueError('That is a server address. Paste only the stream key here, the part after the last /.')
 # TikTok's keys carry their expiry and signature after a ?, so those characters are its own.
 if key and any(c in key for c in ('/#  \t' if service=='tiktok' else '/?#& \t')):raise ValueError('That stream key has characters a stream key never has.')
 if service in INGEST:
  if not key:raise ValueError('Enter your stream key.')
  return INGEST[service]+key,'flv'
 if service not in WITH_SERVER:raise ValueError('Choose where to go live.')
 server=server.strip()
 if not server.lower().startswith(('rtmp://','rtmps://')) or len(server)<10:raise ValueError('Enter a server address that starts with rtmp:// or rtmps://.')
 if service in KEY_NEEDED and not key:raise ValueError(f'Enter the stream key {SERVICES[service]} gave with the server address.')
 return (server.rstrip('/')+'/'+key if key else server),'flv'

def ready(service,key,server):
 """Whether a service has what it needs to go live, without saying what is missing."""
 try:destination(service,key,server);return True
 except ValueError:return False

def raw_targets(saved):
 """Each service's server and sealed key as the settings keep them, {service: {'key', 'server'}}, and the services switched on for Go
 live, in the order of SERVICES. Settings from before several services had one service, its key and server: it stays, switched on."""
 def text(value):return value if isinstance(value,str) else ''
 kept=saved.get('live_targets')
 if isinstance(kept,dict):
  targets={service:dict(key=text(item.get('key')),server=text(item.get('server'))) for service,item in kept.items() if service in SERVICES and isinstance(item,dict)}
  on=saved.get('live_on') if isinstance(saved.get('live_on'),list) else []
 else:
  service=saved.get('live_service')
  targets={service:dict(key=text(saved.get('live_key')),server=text(saved.get('live_server')))} if service in SERVICES else {}
  on=[service] if service in SERVICES else []
 return targets,[service for service in SERVICES if service in on]
def saved_targets(saved):
 """raw_targets with each key read back for this Windows user."""
 targets,on=raw_targets(saved)
 return {service:dict(key=unseal(item['key']),server=item['server']) for service,item in targets.items()},on
def keep_target(saved,service,key,server):
 """The settings that keep key (sealed for this Windows user) and server for service, the other services as they were."""
 targets,on=raw_targets(saved)
 if service in SERVICES:targets[service]=dict(key=seal(key.strip()) if key.strip() else '',server=server.strip())
 return dict(live_targets=targets,live_on=on)
def switch_target(saved,service,on):
 """The settings with service switched on or off for Go live."""
 targets,chosen=raw_targets(saved);chosen=[name for name in chosen if name!=service]+([service] if on and service in SERVICES else [])
 return dict(live_targets=targets,live_on=[name for name in SERVICES if name in chosen])
def chosen_targets(saved):
 """The services switched on for Go live, [(service, key, server)], each with what it was given, ready or not."""
 targets,on=saved_targets(saved)
 return [(service,targets.get(service,{}).get('key',''),targets.get(service,{}).get('server','')) for service in on]

def names_text(names):
 """'Twitch', 'Twitch and YouTube', 'Twitch, YouTube and Kick'."""
 names=list(names)
 return ' and '.join(names) if len(names)<3 else ', '.join(names[:-1])+' and '+names[-1]

# Each service's queue in a stream to several: about five seconds of packets. A service that cannot take them that fast loses packets
# instead of holding up the others; one that drops the connection is called again after a pause, a few times.
FIFO_OPTIONS='queue_size=600:drop_pkts_on_overflow=1:attempt_recovery=1:recovery_wait_time=2:max_recovery_attempts=3:restart_with_keyframe=1'
def tee_part(text):
 """An address as one of tee's outputs: its separator, quote and escape characters escaped."""
 return ''.join('\\'+c if c in '\\|\'' else c for c in text)
def fan_out(destinations):
 """The tee address and options that send one stream to each of destinations, [(name, address, container)]. Each output is dropped
 alone when it fails (onfail=ignore), so the others go on."""
 parts=[]
 for _,address,container in destinations:
  options=f'f={container}:onfail=ignore'+(':flvflags=no_duration_filesize' if container=='flv' else '')
  parts.append(f'[{options}]{tee_part(address)}')
 return '|'.join(parts),{'use_fifo':'1','fifo_options':FIFO_OPTIONS}

class TeeWatch(logging.Handler):
 """Reads FFmpeg's own messages from the tee and its queues while a stream goes to several services, and turns the ones about a
 service into words for the user. The messages hold the addresses, and so the keys: they are matched here and never kept or shown."""
 def __init__(self,broadcast,destinations):
  super().__init__(logging.WARNING);self.broadcast=broadcast;self.destinations=list(destinations);self.full_said=0
 def emit(self,record):
  try:self.read(record.name,record.getMessage())
  except Exception:pass
 def read(self,source,message):
  broadcast=self.broadcast
  if source=='libav.fifo' and message.startswith('Error opening '):
   at=message[len('Error opening '):]
   for name,address,_ in self.destinations:
    if at.startswith(address):broadcast.target_failed(name,False);return
  elif source=='libav.tee' and message.startswith('Slave muxer #'):
   try:index=int(message[len('Slave muxer #'):].split()[0])
   except ValueError:return
   if 0<=index<len(self.destinations):broadcast.target_failed(self.destinations[index][0],True)
  elif source=='libav.fifo' and message.startswith('FIFO queue full'):
   # A queue fills while its service is called again after a refusal, too; that service has been named already.
   now=time.monotonic()
   if now-self.full_said>30 and all(state=='live' for state in broadcast.targets.values()):
    self.full_said=now;broadcast.events.put(('error','One of your services is losing parts of the stream: your upload cannot carry it to all of them. Choose a lower profile or fewer services.'))

def seal(text):
 """The key, encrypted for this Windows user (DPAPI), as text for the settings file; '' if it cannot be."""
 if not text:return ''
 try:
  import ctypes
  from ctypes import wintypes
  class Blob(ctypes.Structure):_fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_char))]
  data=text.encode('utf8');source=Blob(len(data),ctypes.cast(ctypes.create_string_buffer(data,len(data)),ctypes.POINTER(ctypes.c_char)));out=Blob()
  if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source),'PlayBridge stream key',None,None,None,1,ctypes.byref(out)):return ''
  try:return base64.b64encode(ctypes.string_at(out.data,out.size)).decode('ascii')
  finally:ctypes.windll.kernel32.LocalFree(out.data)
 except Exception:return ''
def unseal(text):
 """The key sealed by seal(), or '' if it was sealed by another user or cannot be read."""
 if not text:return ''
 try:
  import ctypes
  from ctypes import wintypes
  class Blob(ctypes.Structure):_fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_char))]
  data=base64.b64decode(text);source=Blob(len(data),ctypes.cast(ctypes.create_string_buffer(data,len(data)),ctypes.POINTER(ctypes.c_char)));out=Blob()
  if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source),None,None,None,None,1,ctypes.byref(out)):return ''
  try:return ctypes.string_at(out.data,out.size).decode('utf8')
  finally:ctypes.windll.kernel32.LocalFree(out.data)
 except Exception:return ''

class Remaker:
 """Makes the video again with the decoder on a thread of its own, so the graphics card decodes the next frame while it encodes this
 one. One after the other, a 4K60 stream ran at 52 fps on an RX 6600 and fell behind; side by side it ran at 90.
 Only the live thread encodes and writes, so the sound and the video still go out through one writer. on_frame, when given, is called
 from the decoder's thread each time frames are ready, for a writer that should not wait for its next packet to take them."""
 def __init__(self,decoder,stream,on_frame=None,overlay=None):
  self.decoder=decoder;self.stream=stream;self.overlay=overlay;self.inbox=queue.Queue(16);self.outbox=queue.Queue(16);self.on_frame=on_frame
  self.thread=threading.Thread(target=self._decode,name='PlayBridge live decode',daemon=True);self.thread.start()
 def _decode(self):
  while True:
   packet=self.inbox.get()
   # A packet the decoder cannot read costs its frame, not the stream.
   try:frames=self.decoder.decode(packet)
   except Exception:frames=[]
   for frame in frames:self.outbox.put(frame)
   if frames and self.on_frame:self.on_frame()
   if packet is None:self.outbox.put(None);return
 def _encode(self,frame):
  if frame.pts is None:return []
  # A frame of this code's own is one made here in the encoder's format, or NV12, which only a graphics card's decoder gives and hands
  # over as a copy. A frame of the processor's decoder is also the picture its next frames are built on, so the overlay copies it first.
  own=frame.format.name=='nv12'
  if frame.format.name!=self.stream.pix_fmt:frame=frame.reformat(format=self.stream.pix_fmt);own=True
  if self.overlay:frame=self.overlay(frame,own)
  frame.time_base=Fraction(1,90000);return self.stream.encode(frame)
 def ready(self):
  """The new packets for every frame decoded so far."""
  items=[]
  while True:
   try:frame=self.outbox.get_nowait()
   except queue.Empty:return items
   if frame is None:self.outbox.put(None);return items
   items+=self._encode(frame)
 def put(self,packet):
  """Hands a packet to the decoder and returns what is ready. While the decoder is full its frames are encoded, so neither side
  can wait on the other for good."""
  items=[]
  while True:
   try:self.inbox.put(packet,timeout=.005);return items+self.ready()
   except queue.Full:items+=self.ready()
 def finish(self,timeout=5):
  """Everything still in the decoder and the encoder, at the end of a stream that ended well."""
  items=self.put(None);ends=time.monotonic()+timeout
  while time.monotonic()<ends:
   try:frame=self.outbox.get(timeout=.1)
   except queue.Empty:continue
   if frame is None:return items+self.stream.encode(None)
   items+=self._encode(frame)
  return items
 def close(self):
  """Lets the decoder thread end, whatever state the stream ended in."""
  while True:
   try:self.inbox.get_nowait()
   except queue.Empty:break
  try:self.inbox.put_nowait(None)
  except queue.Full:pass
  ends=time.monotonic()+2
  while self.thread.is_alive() and time.monotonic()<ends:
   try:self.outbox.get(timeout=.05)
   except queue.Empty:pass

def clock(seconds):
 seconds=int(seconds);return f'{seconds//3600}:{seconds//60%60:02d}:{seconds%60:02d}'

class LiveBroadcast:
 """Takes the packets the player receives and sends them on from a thread of its own, so a slow upload never holds up the picture."""
 def __init__(self):
  self.lock=threading.Lock();self.events=queue.SimpleQueue();self.thread=None;self.state='idle';self.codec=0;self.headers=b'';self.name='';self.since=None;self.sent_bytes=0;self.encoder=None
  # In a stream to several services: each one's state, 'live', 'trying' (refused, being called again) or 'ended'.
  self.targets={}
  self.max_queue=600;self.max_bytes=48*1024*1024;self.queued_bytes=0;self.ending=threading.Event();self.queue=queue.Queue(1)
  # The overlay drawn into the stream while the video is made again: set by the window, (BGRA bytes, width, height) or None.
  self.overlay_image=None;self.frame_overlay=FrameOverlay()
 @property
 def active(self):return self.thread is not None and self.thread.is_alive()
 def elapsed(self):return time.monotonic()-self.since if self.since is not None and self.state=='live' else 0
 def start(self,address,container,name,opener=None,encoder=None):
  """Starts at the next keyframe. The address holds the key, so it stays inside this object. With an encoder, the video is made
  again as HEVC or AV1 on the graphics card, for services that take them over RTMP (YouTube), at a fraction of the PS5's bitrate."""
  with self.lock:
   if self.active:return False
   if container=='flv' and self.codec==HEVC and not encoder:raise ValueError(f'{name} takes H.264 over RTMP, and 1440p and 4K come as HEVC. Choose a 1080p profile, or go through OBS.')
   self.name=name;self.encoder=encoder;self.queue=queue.Queue(self.max_queue);self.queued_bytes=0;self.ending=threading.Event();self.state='waiting';self.since=None;self.sent_bytes=0;self.targets={}
   self.thread=threading.Thread(target=self._run,args=(address,container,opener or av.open),name='PlayBridge live',daemon=True);self.thread.start()
   return True
 def start_many(self,destinations,opener=None,encoder=None):
  """Starts one stream to each of destinations, [(name, address, container)], at the next keyframe. One goes as start() sends it."""
  destinations=list(destinations)
  if not destinations:raise ValueError('Choose where to go live.')
  if len(destinations)==1:
   name,address,container=destinations[0];return self.start(address,container,name,opener,encoder)
  with self.lock:
   if self.active:return False
   rtmp=[name for name,_,container in destinations if container=='flv']
   if rtmp and self.codec==HEVC and not encoder:raise ValueError(f'{names_text(rtmp)} take H.264 over RTMP, and 1440p and 4K come as HEVC. Choose a 1080p profile, or go through OBS.')
   address,options=fan_out(destinations)
   self.name=names_text(name for name,_,_ in destinations);self.encoder=encoder;self.queue=queue.Queue(self.max_queue);self.queued_bytes=0;self.ending=threading.Event();self.state='waiting';self.since=None;self.sent_bytes=0
   self.targets={name:'live' for name,_,_ in destinations}
   self.thread=threading.Thread(target=self._run,args=(address,'tee',opener or av.open,options,destinations),name='PlayBridge live',daemon=True);self.thread.start()
   return True
 def target_failed(self,name,ended):
  """A service of a stream to several refused it or dropped it: it is called again after a pause (ended False) or left out for good."""
  with self.lock:
   before=self.targets.get(name)
   if before is None or before=='ended':return
   self.targets[name]='ended' if ended else 'trying'
   left=[target for target,state in self.targets.items() if state!='ended']
   if ended and left:self.name=names_text(left)
  if ended:self.events.put(('error',f'{name} ended the live stream.'+(f' It goes on on {names_text(left)}.' if left else '')))
  elif before=='live':self.events.put(('error',f'{name} did not take the live stream: check its stream key and server. PlayBridge calls it again a few times, and the other services go on.'))
 def feed(self,kind,data,pts,dts):
  headers=codec_headers(data,self.codec) if kind==1 else b''
  with self.lock:
   if headers:self.headers=headers
   if not self.active or self.ending.is_set():return
   try:
    if self.queued_bytes+len(data)>self.max_bytes:raise queue.Full
    self.queue.put_nowait((kind,data,pts,dts,self.headers));self.queued_bytes+=len(data)
   except queue.Full:
    if self.encoder:self.events.put(('error',f'The live stream on {self.name} ended: your upload or this PC\'s graphics card could not keep up. Choose a lower profile.'))
    else:self.events.put(('error',f'The live stream on {self.name} ended: your upload could not keep up. Choose a profile with a lower bitrate.'))
    self.state='ending';self.ending.set()
 def stop(self,wait=False):
  with self.lock:
   thread=self.thread
   if thread is None or not thread.is_alive():return
   self.state='ending';self.ending.set()
  if wait and thread is not threading.current_thread():thread.join(timeout=10)
 def reset_session(self):
  """A new connection to the PS5 starts its clock again, so a stream in progress ends with the old one."""
  if self.active:self.events.put(('status',f'The live stream on {self.name} ended with the PS5 connection.'))
  self.stop(wait=True)
  with self.lock:self.headers=b''
 def _converter(self,out,width,height,shared=False):
  """The decoder and the output stream for making the video again. The decoder uses the graphics card where it can, and hands its
  frames back to this thread, so the picture on screen keeps its own decoder untouched."""
  decoder=None
  if sys.platform=='win32':
   try:decoder=av.CodecContext.create('hevc' if self.codec==HEVC else 'h264','r',hwaccel=HWAccel(device_type='d3d11va',allow_software_fallback=True))
   except Exception:decoder=None
  if decoder is None:decoder=av.CodecContext.create('hevc' if self.codec==HEVC else 'h264','r')
  stream=out.add_stream(self.encoder,rate=60)
  stream.width,stream.height=width,height;stream.pix_fmt=video_encoders.pixel_format(self.encoder,live=True)
  stream.bit_rate=video_encoders.bitrate(self.encoder,height,live=True);stream.time_base=Fraction(1,90000);stream.codec_context.time_base=Fraction(1,90000)
  # A keyframe every two seconds, which is what YouTube asks for.
  stream.codec_context.gop_size=120;stream.options=video_encoders.options(self.encoder,live=True)
  # Through tee the video's headers go once, ahead of the stream, as each service's FLV needs them; tee does not ask for that itself.
  if shared:stream.codec_context.flags|=av.codec.context.Flags.global_header
  return Remaker(decoder,stream,overlay=lambda frame,own:self.frame_overlay.draw(frame,self.overlay_image,own)),stream
 def _run(self,address,container,opener,options=None,destinations=None):
  out=None;templates=[];base=None;pending=[];video_first=audio_first=None;vs=aus=None;sent=0;reason='';decoder=None;watch=None;level=None;propagated=True
  if destinations:
   # FFmpeg's messages about each service, read while the stream goes to several. Nothing else of FFmpeg's is shown for it.
   level=av.logging.get_level();watch=TeeWatch(self,destinations);logger=logging.getLogger('libav');logger.addHandler(watch);propagated=logger.propagate;logger.propagate=False
   if level is None or level<av.logging.WARNING:av.logging.set_level(av.logging.WARNING)
  try:
   while not self.ending.is_set():
    try:packet=self.queue.get(timeout=.1)
    except queue.Empty:continue
    kind,data,pts,dts,headers=packet
    with self.lock:self.queued_bytes-=len(data)
    if base is None:
     if kind!=1 or not is_idr(data,self.codec):continue
     base=min(pts,dts);video_first=data if codec_headers(data,self.codec) else headers+data
    if pts<base:continue
    pending.append(packet)
    if kind==2 and audio_first is None:audio_first=data
    if out is None:
     if video_first is None or audio_first is None:
      if len(pending)>240:reason=f'The live stream on {self.name} did not start: the PS5 sent no sound.';break
      continue
     video_template=opener(io.BytesIO(video_first),format='hevc' if self.codec==HEVC else 'h264');audio_template=opener(io.BytesIO(audio_first),format='aac');templates=[video_template,audio_template]
     try:
      options=options or ({'flvflags':'no_duration_filesize'} if container=='flv' else {})
      out=opener(address,'w',format=container,options=options,timeout=(10,10))
      if self.encoder:
       source=video_template.streams.video[0].codec_context;decoder,vs=self._converter(out,source.width,source.height,shared=container=='tee')
      else:vs=out.add_stream_from_template(video_template.streams.video[0])
      aus=out.add_stream_from_template(audio_template.streams.audio[0]);aus.codec_context.extradata=strip_adts(audio_first)[1]
     except Exception:reason=f'Could not reach {self.name}. Check the stream key and your connection.';break
    for k,b,p,d,h in pending:
     if k==2:b=strip_adts(b)[0]
     if k==1 and decoder is not None:
      # Made again on the graphics card: the PS5's packet is decoded and only the new one is sent.
      packet=av.Packet(b if codec_headers(b,self.codec) or not is_idr(b,self.codec) else h+b);packet.pts=p-base;packet.dts=d-base;packet.time_base=Fraction(1,90000)
      items=decoder.put(packet)
     else:
      item=av.Packet(b);item.pts=p-base;item.dts=d-base;item.time_base=Fraction(1,90000);item.stream=vs if k==1 else aus
      if k==1:item.is_keyframe=is_idr(b,self.codec)
      items=[item]
     # The first write is when the server is reached, so a wrong key or address shows here.
     try:
      for item in items:out.mux(item);sent+=1;self.sent_bytes+=item.size
     except Exception:reason=f'{self.name} closed the live stream.' if sent else f'Could not reach {self.name}. Check the stream key and your connection.';break
     if sent and self.since is None:self.since=time.monotonic();self.state='live';self.events.put(('status',f'You are live on {self.name}'+(f' in {video_encoders.kind(self.encoder).upper()}.' if decoder is not None else '.')))
    pending.clear()
    if reason:break
  except Exception:reason=reason or f'The live stream on {self.name} stopped because of an error.'
  finally:
   if out is not None:
    try:
     if decoder is not None and not reason:out.mux(decoder.finish())
    except Exception:pass
    try:out.close()
    except Exception:pass
   if decoder is not None:decoder.close()
   for template in templates:
    try:template.close()
    except Exception:pass
   if watch is not None:
    logger=logging.getLogger('libav');logger.removeHandler(watch);logger.propagate=propagated
    if level is None or level<av.logging.WARNING:av.logging.set_level(level)
   if reason:self.events.put(('error',reason))
   elif sent:self.events.put(('status',f'The live stream on {self.name} ended after {clock(time.monotonic()-self.since)}.'))
   self.state='idle';self.since=None
