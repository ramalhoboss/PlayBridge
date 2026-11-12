"""Going live: the console's own H.264 and AAC, copied as they arrive to Twitch, YouTube, any RTMP server, or OBS on this PC.
Nothing is encoded again, so it costs this PC almost nothing, and the stream is exactly what the PS5 sent. Only when Smaller stream is on,
for YouTube or another RTMP server, the graphics card makes the video again as AV1 or HEVC (enhanced RTMP) at a fraction of the bitrate.
The stream key is a password: it is never put in a message, a log or the diagnostics, and it is kept encrypted for this Windows user."""
import base64,io,queue,sys,threading,time
from fractions import Fraction
import av
from av.codec.hwaccel import HWAccel
from media_capture import HEVC,codec_headers,is_idr,strip_adts
import video_encoders

OBS_PORT=9100
SERVICES={'twitch':'Twitch','youtube':'YouTube','custom':'Other RTMP server','obs':'OBS on this PC'}
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
 if key and any(c in key for c in '/?#& \t'):raise ValueError('That stream key has characters a stream key never has.')
 if service in INGEST:
  if not key:raise ValueError('Enter your stream key.')
  return INGEST[service]+key,'flv'
 if service!='custom':raise ValueError('Choose where to go live.')
 server=server.strip()
 if not server.lower().startswith(('rtmp://','rtmps://')) or len(server)<10:raise ValueError('Enter a server address that starts with rtmp:// or rtmps://.')
 return (server.rstrip('/')+'/'+key if key else server),'flv'

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
 Only the live thread encodes and writes, so the sound and the video still go out through one writer."""
 def __init__(self,decoder,stream):
  self.decoder=decoder;self.stream=stream;self.inbox=queue.Queue(16);self.outbox=queue.Queue(16)
  self.thread=threading.Thread(target=self._decode,name='PlayBridge live decode',daemon=True);self.thread.start()
 def _decode(self):
  while True:
   packet=self.inbox.get()
   # A packet the decoder cannot read costs its frame, not the stream.
   try:frames=self.decoder.decode(packet)
   except Exception:frames=[]
   for frame in frames:self.outbox.put(frame)
   if packet is None:self.outbox.put(None);return
 def _encode(self,frame):
  if frame.pts is None:return []
  if frame.format.name!=self.stream.pix_fmt:frame=frame.reformat(format=self.stream.pix_fmt)
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
  self.max_queue=600;self.max_bytes=48*1024*1024;self.queued_bytes=0;self.ending=threading.Event();self.queue=queue.Queue(1)
 @property
 def active(self):return self.thread is not None and self.thread.is_alive()
 def elapsed(self):return time.monotonic()-self.since if self.since is not None and self.state=='live' else 0
 def start(self,address,container,name,opener=None,encoder=None):
  """Starts at the next keyframe. The address holds the key, so it stays inside this object. With an encoder, the video is made
  again as HEVC or AV1 on the graphics card, for services that take them over RTMP (YouTube), at a fraction of the PS5's bitrate."""
  with self.lock:
   if self.active:return False
   if container=='flv' and self.codec==HEVC and not encoder:raise ValueError(f'{name} takes H.264 over RTMP, and 1440p and 4K come as HEVC. Choose a 1080p profile, or go through OBS.')
   self.name=name;self.encoder=encoder;self.queue=queue.Queue(self.max_queue);self.queued_bytes=0;self.ending=threading.Event();self.state='waiting';self.since=None;self.sent_bytes=0
   self.thread=threading.Thread(target=self._run,args=(address,container,opener or av.open),name='PlayBridge live',daemon=True);self.thread.start()
   return True
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
 def _converter(self,out,width,height):
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
  return Remaker(decoder,stream),stream
 def _run(self,address,container,opener):
  out=None;templates=[];base=None;pending=[];video_first=audio_first=None;vs=aus=None;sent=0;reason='';decoder=None
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
      options={'flvflags':'no_duration_filesize'} if container=='flv' else {}
      out=opener(address,'w',format=container,options=options,timeout=(10,10))
      if self.encoder:
       source=video_template.streams.video[0].codec_context;decoder,vs=self._converter(out,source.width,source.height)
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
   if reason:self.events.put(('error',reason))
   elif sent:self.events.put(('status',f'The live stream on {self.name} ended after {clock(time.monotonic()-self.since)}.'))
   self.state='idle';self.since=None
