"""Your phone as a screen and a controller, in its own browser, on this PC's network. Nothing is installed on the phone.
PlayBridge serves one page. A phone pairs once with a six-digit code shown on the PC, then gets the game's picture as fragmented MP4 over
a WebSocket (Media Source Extensions, or Managed Media Source on an iPhone) and its sound beside it as plain samples the page plays
itself, and sends its touch controls back. The PC is the only
thing that talks to the PS5: each phone's controller goes to the controller companion from a port of its own, so each phone is a player of
its own there, like each PC. Off by default, and it only answers devices on the local network."""
import base64,collections,hashlib,hmac,http.server,io,ipaddress,json,os,queue,re,secrets,socket,struct,sys,threading,time,urllib.parse
from fractions import Fraction
from pathlib import Path
import av
from media_capture import HEVC,codec_headers,is_idr,strip_adts
import pad_input as pad
import secure_link

PORT=9080
MAX_PHONES=4
PAGE=Path(__file__).resolve().parent/'assets'/'phone.html'

# ---- WebSocket (RFC 6455): only what the page uses. Frames from a browser are always masked and never this large.
GUID=b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
TEXT,BINARY,CLOSE,PING,PONG=1,2,8,9,10
# Why the PC closes a phone's connection, as the page reads it: not paired, four phones already, or closed with Disconnect phones.
NOT_PAIRED,NO_ROOM,CLOSED_ON_PC=4401,4429,4410
def accept_key(key):return base64.b64encode(hashlib.sha1(key.encode('ascii')+GUID).digest()).decode('ascii')
def ws_frame(opcode,data):
 n=len(data);head=bytes([0x80|opcode])
 if n<126:head+=bytes([n])
 elif n<65536:head+=bytes([126])+struct.pack('>H',n)
 else:head+=bytes([127])+struct.pack('>Q',n)
 return head+data
def read_exact(stream,n):
 data=stream.read(n)
 if data is None or len(data)!=n:raise EOFError('The phone closed the connection.')
 return data
def ws_read(stream,limit=4096):
 """(opcode, payload) of the next whole frame from the phone."""
 b0,b1=read_exact(stream,2);n=b1&0x7f
 if not b0&0x80 or not b1&0x80:raise ValueError('Only whole, masked frames are taken.')
 if n==126:n=struct.unpack('>H',read_exact(stream,2))[0]
 elif n==127:n=struct.unpack('>Q',read_exact(stream,8))[0]
 if n>limit:raise ValueError('That message is too large.')
 mask=read_exact(stream,4);data=read_exact(stream,n)
 return b0&0x0f,bytes(b^mask[i&3] for i,b in enumerate(data))

def scan_address(address,code=''):
 """What the QR code in Settings › Phone opens: the page, and the pairing code while one shows. The code goes after #, which a
 browser never sends anywhere; the page reads it, pairs, and takes it out of the address bar."""
 if not address:return ''
 return address.rstrip('/')+'/'+(f'#code={code}' if code and code.isdigit() and len(code)==6 else '')

# ---- Pairing: a code shown on the PC, used once, for five minutes and five tries. A phone keeps its token; the PC keeps only its hash.
def digest(token):return hashlib.sha256(token.encode('ascii')).hexdigest()
class Pairing:
 LIFE=300;TRIES=5
 def __init__(self,hashes=(),save=None):
  self.lock=threading.Lock();self.code=None;self.until=0;self.left=0;self.hashes=set(hashes);self.save=save
 def new_code(self,now):
  with self.lock:self.code=f'{secrets.randbelow(10**6):06d}';self.until=now+self.LIFE;self.left=self.TRIES;return self.code
 def showing(self,now):
  """The code and its seconds left while it can still be used, or None."""
  with self.lock:return (self.code,int(self.until-now)) if self.code and now<self.until else None
 def pair(self,code,now):
  """('ok', token), ('wrong', tries left), or ('closed', None) when no code is showing."""
  with self.lock:
   if not self.code or now>=self.until:self.code=None;return 'closed',None
   if not hmac.compare_digest(str(code).strip().encode()[:16],self.code.encode()):
    self.left-=1
    if self.left<=0:self.code=None
    return 'wrong',self.left
   token=secrets.token_hex(16);self.hashes.add(digest(token));self.code=None;hashes=sorted(self.hashes)
  if self.save:self.save(hashes)
  return 'ok',token
 def knows(self,token):
  if not isinstance(token,str) or len(token)!=32:return False
  try:mine=digest(token)
  except UnicodeEncodeError:return False
  with self.lock:return any(hmac.compare_digest(mine,known) for known in self.hashes)
 def forget(self):
  with self.lock:self.hashes.clear();self.code=None
  if self.save:self.save([])
 def count(self):
  with self.lock:return len(self.hashes)

# ---- Fragmented MP4: the muxer's bytes cut into the init segment and one fragment per packet, each marked when it starts a picture.
def boxes(data,start=0,end=None):
 """(type, start, end) of each whole box from start, stopping at the first that is not all there."""
 end=len(data) if end is None else end;at=start
 while at+8<=end:
  size,kind=struct.unpack_from('>I4s',data,at)
  if size==1 and at+16<=end:size=struct.unpack_from('>Q',data,at+8)[0]
  if size<8 or at+size>end:return
  yield kind.decode('latin-1'),at,at+size;at+=size
def child(data,start,end,kind,skip=8):
 return next(((s,e) for k,s,e in boxes(data,start+skip,end) if k==kind),None)
def fragment_sync(moof,track=1):
 """True when this fragment's first sample for the track is a keyframe, False when it is not, None when the track is not in it."""
 for kind,start,end in boxes(moof,8):
  if kind!='traf':continue
  tfhd=child(moof,start,end,'tfhd');trun=child(moof,start,end,'trun')
  if not tfhd or not trun:continue
  flags=struct.unpack_from('>I',moof,tfhd[0]+8)[0]&0xffffff;at=tfhd[0]+12
  if struct.unpack_from('>I',moof,at)[0]!=track:continue
  at+=4;default=None
  for bit,size in ((0x1,8),(0x2,4),(0x8,4),(0x10,4)):
   if flags&bit:at+=size
  if flags&0x20:default=struct.unpack_from('>I',moof,at)[0]
  flags=struct.unpack_from('>I',moof,trun[0]+8)[0]&0xffffff;at=trun[0]+16
  if flags&0x1:at+=4
  if flags&0x4:sample=struct.unpack_from('>I',moof,at)[0]
  elif flags&0x400:
   for bit in (0x100,0x200):
    if flags&bit:at+=4
   sample=struct.unpack_from('>I',moof,at)[0]
  else:sample=default
  return sample is None or not sample&0x10000
 return None
def sample_lengths(moov):
 """Each track's usual sample length in its own clock, from the movie header, and whether the stream may change it: an AAC frame is
 always 1024 samples (the sound track's clock is its sample rate); a video frame starts at 60 fps and follows what the stream shows."""
 lengths={}
 for kind,start,end in boxes(moov,8):
  if kind!='trak':continue
  tkhd=child(moov,start,end,'tkhd');mdia=child(moov,start,end,'mdia')
  if not tkhd or not mdia:continue
  mdhd=child(moov,mdia[0],mdia[1],'mdhd');hdlr=child(moov,mdia[0],mdia[1],'hdlr')
  if not mdhd or not hdlr:continue
  track=struct.unpack_from('>I',moov,tkhd[0]+(28 if moov[tkhd[0]+8] else 20))[0];clock=struct.unpack_from('>I',moov,mdhd[0]+(28 if moov[mdhd[0]+8] else 20))[0]
  handler=moov[hdlr[0]+16:hdlr[0]+20]
  if handler==b'soun':lengths[track]=[1024,False]
  elif handler==b'vide' and clock:lengths[track]=[max(1,clock//60),True]
 return lengths
def fill_lengths(moof,lengths):
 """The fragment with every sample of no length given its track's usual one. With one fragment per frame the MP4 muxer writes a
 length of 0 for most sound samples, and a phone's browser (Media Source) takes a sample of no length followed by the next for a
 break in the stream: it then drops the picture up to the next whole one, so the phone showed one picture a second, late."""
 moof=bytearray(moof)
 for kind,start,end in boxes(moof,8):
  if kind!='traf':continue
  tfhd=child(moof,start,end,'tfhd');trun=child(moof,start,end,'trun')
  if not tfhd or not trun:continue
  flags=struct.unpack_from('>I',moof,tfhd[0]+8)[0]&0xffffff;track=struct.unpack_from('>I',moof,tfhd[0]+12)[0];at=tfhd[0]+16
  for bit,size in ((0x1,8),(0x2,4)):
   if flags&bit:at+=size
  places=[at] if flags&0x8 else []
  flags=struct.unpack_from('>I',moof,trun[0]+8)[0]&0xffffff;count=struct.unpack_from('>I',moof,trun[0]+12)[0];at=trun[0]+16
  if flags&0x1:at+=4
  if flags&0x4:at+=4
  if flags&0x100:
   step=4*sum(1 for bit in (0x100,0x200,0x400,0x800) if flags&bit)
   # A sample's own length replaces the default one.
   places=[at+k*step for k in range(count) if at+k*step+4<=trun[1]]
  for place in places:
   length=struct.unpack_from('>I',moof,place)[0];usual=lengths.get(track)
   if usual is None:continue
   if not length:struct.pack_into('>I',moof,place,usual[0])
   elif usual[1]:usual[0]=length
 return bytes(moof)
def video_mime(init,audio_object=None):
 """The type the page gives Media Source, from the H.264 settings in the init segment (and the AAC's when the MP4 has sound)."""
 at=init.find(b'avcC')
 if at<0 or at+8>len(init):return None
 sound=f', mp4a.40.{audio_object}' if audio_object else ''
 return f'video/mp4; codecs="avc1.{init[at+5]:02X}{init[at+6]:02X}{init[at+7]:02X}{sound}"'
class Fragments:
 """What the MP4 muxer writes. It has no seek on purpose: the movie header is empty and every fragment carries its own, so the
 muxer never goes back."""
 def __init__(self,deliver,audio_object=None):
  self.deliver=deliver;self.audio_object=audio_object;self.buffer=bytearray();self.head=b'';self.moof=None;self.lengths={}
 def write(self,data):
  self.buffer+=data;used=0
  for kind,start,end in boxes(self.buffer):
   box=bytes(self.buffer[start:end]);used=end
   if kind=='ftyp':self.head=box
   elif kind=='moov':init=self.head+box;self.lengths=sample_lengths(box);self.deliver('init',init,video_mime(init,self.audio_object))
   elif kind=='moof':self.moof=fill_lengths(box,self.lengths)
   elif kind=='mdat' and self.moof is not None:self.deliver('fragment',self.moof+box,fragment_sync(self.moof));self.moof=None
  del self.buffer[:used]
  return len(data)

class Viewer:
 """One phone's picture: what waits to be sent to it. A phone that falls behind (its Wi-Fi slower than the stream for a while) loses
 what waits and goes on at the next picture that needs no other, rather than the stream backing up for everyone. About two seconds
 of the phone stream may wait; more would only be seen late. The phone keeps the stream's start it already has, so its page jumps
 over the gap instead of starting its player again."""
 LIMIT=1536*1024
 def __init__(self):
  self.lock=threading.Lock();self.items=collections.deque();self.size=0;self.wake=threading.Event();self.waiting=True;self.init=None;self.dropped=0
 def offer(self,kind,data,info):
  with self.lock:
   if kind=='init':self.items.clear();self.size=0;self.waiting=True;self.init=(data,info);self.items.append(('init',data,info));self.size+=len(data)
   elif info is not None or not self.waiting:
    if self.waiting:
     if not info:return
     self.waiting=False
    if self.size+len(data)>self.LIMIT:
     # A start the phone has not been sent yet stays first in line.
     start=self.items[0] if self.items and self.items[0][0]=='init' else None
     self.items.clear();self.size=0;self.waiting=True;self.dropped+=1
     if start:self.items.append(start);self.size+=len(start[1])
     return
    self.items.append((kind,data,info));self.size+=len(data)
   else:return
  self.wake.set()
 def take(self,timeout):
  if not self.wake.wait(timeout):return None
  with self.lock:
   if not self.items:self.wake.clear();return None
   item=self.items.popleft();self.size-=len(item[1])
   if not self.items:self.wake.clear()
   return item

def encoder_options(name,bitrate=0):
 """The phone encoder's options: its fastest setting with no delay, and a whole picture asked for made a real one (an IDR with its
 headers) on AMD, NVIDIA and Intel. With a bitrate, no picture may be larger than about three frames' share of it: a whole picture
 was ten times the others (200 KB at 1080p from the real PS5), so on the phone's Wi-Fi it came late every second, the picture
 stopped and the sound behind it ran dry. Capped, the same pictures made at 720p stay under 32 KB."""
 cap={'maxrate':str(bitrate),'bufsize':str(bitrate*3//60)} if bitrate else {}
 if name=='libx264':return {'preset':'ultrafast','tune':'zerolatency',**cap}
 if name=='h264_amf':return {'usage':'ultralowlatency','forced_idr':'1',**({'rc':'cbr','enforce_hrd':'1','filler_data':'0'} if cap else {}),**cap}
 if name=='h264_nvenc':return {'preset':'p1','tune':'ull','forced-idr':'1',**({'rc':'cbr'} if cap else {}),**cap}
 if name=='h264_qsv':return {'forced_idr':'1',**cap}
 return cap

# ---- The sound for the phones: plain 16-bit samples the page plays itself.
# A phone's browser played the sound inside the MP4 with its own player, and after each time the stream came late that player waited
# longer before it played on (0.6, then 1.2, then 2.5 s, measured here), so the picture stopped with it. Pictures alone do not do
# that. Each message: SOUND, the time on the phones' clock in seconds (little-endian double), the sample rate (uint32), the channels
# (uint16), then the samples, interleaved 16-bit little-endian. Stereo at 48 kHz is 1.5 Mbps.
SOUND=b'PBAU'
def sound_message(seconds,rate,channels,samples):return SOUND+struct.pack('<dIH',seconds,rate,channels)+samples
class Sound:
 """The PS5's AAC (ADTS frames) decoded to 16-bit samples, one message for each frame."""
 def __init__(self,first):
  self.decoder=av.CodecContext.create('aac','r');self.decoder.extradata=strip_adts(first)[1];self.resampler=None
 def make(self,adts,pts):
  out=[]
  try:
   for frame in self.decoder.decode(av.Packet(strip_adts(adts)[0])):
    if self.resampler is None:
     channels=frame.layout.nb_channels if hasattr(frame.layout,'nb_channels') else len(frame.layout.channels)
     self.resampler=av.AudioResampler(format='s16',layout='mono' if channels==1 else 'stereo',rate=frame.sample_rate)
    for made in self.resampler.resample(frame):
     channels=1 if made.layout.name=='mono' else 2
     out.append(sound_message(pts/90000,made.sample_rate,channels,bytes(made.planes[0])[:made.samples*channels*2]))
  except (av.error.FFmpegError,ValueError):pass
  return out

# Put in the phone stream's own queue by its decoder thread: a frame is ready to be made again.
READY=('ready',)
def wake(inbox):
 try:inbox.put_nowait(READY)
 except queue.Full:pass

class PhoneFeed:
 """Takes the packets the player receives, like Go live, and makes the phones' stream from a thread of its own that only runs while a
 phone watches. The PS5's H.264 up to 720p is copied as it is; HEVC and larger pictures are made again as 720p H.264 at 6 Mbps on the
 graphics card (or the processor when the card has no H.264 encoder), because a phone's browser plays H.264 everywhere. 720p is
 sharp on a phone's screen, and half of 1080p's 12 Mbps reaches it over Wi-Fi with room to spare, so the picture comes sooner."""
 COPY_HEIGHT=720;HEIGHT=720;BITRATE=6_000_000;KEY_EVERY=60
 # Pictures the PS5 did not send are filled in from the last one for at most this many in a row (half a second); a longer gap is
 # the PS5 stopping, and the phone waits with it.
 FILL_MOST=30
 def __init__(self):
  self.lock=threading.Lock();self.codec=0;self.headers=b'';self.viewers=set();self.thread=None;self.ending=threading.Event();self.queue=queue.Queue(600)
  self.init=None;self.mode='';self.error=''
  # For the phone log: (when, what, how much) for the last seconds, and how often the phones' stream started again.
  self.recent=collections.deque(maxlen=4000);self.restarts=0;self.last_video=None
 def note(self,what,value):self.recent.append((time.perf_counter(),what,value))
 def report(self,seconds=2.0):
  """What the PC saw of the phones' stream in the last seconds: the longest wait between two pictures from the PS5, how long a
  picture took from the PS5's packet to the phones (middle and longest), how many pictures were made up, and the restarts so far."""
  now=time.perf_counter();rows=[(what,value) for at,what,value in list(self.recent) if now-at<=seconds]
  took=sorted(value for what,value in rows if what=='pc');gaps=[value for what,value in rows if what=='gap']
  return {'ps5_gap_ms':max(gaps,default=0),'pc_ms':took[len(took)//2] if took else None,'pc_max_ms':took[-1] if took else None,
          'made_up':sum(1 for what,_ in rows if what=='made'),'restarts':self.restarts}
 def feed(self,kind,data,pts,dts):
  headers=codec_headers(data,self.codec) if kind==1 else b'';now=time.perf_counter()
  with self.lock:
   if headers:self.headers=headers
   if self.thread is None or self.ending.is_set():return
   if kind==1:
    if self.last_video is not None and now-self.last_video>.034:self.note('gap',round((now-self.last_video)*1000))
    self.last_video=now
   try:self.queue.put_nowait((kind,data,pts,dts,self.headers,now))
   except queue.Full:self.restart_locked()
 def join(self):
  """A phone starts watching: it gets the stream's start now, or as soon as there is one."""
  viewer=Viewer()
  with self.lock:
   self.viewers.add(viewer)
   if self.init:viewer.offer('init',*self.init)
   if self.thread is None or not self.thread.is_alive():self.start_locked()
  return viewer
 def leave(self,viewer):
  with self.lock:
   self.viewers.discard(viewer)
   if not self.viewers and self.thread is not None:self.ending.set();self.thread=None
 def reset_session(self):
  """A new connection to the PS5 starts its clock again, so the phones start again with it."""
  with self.lock:
   self.headers=b''
   if self.viewers:self.restart_locked()
 def restart_locked(self):
  self.ending.set();self.thread=None;self.init=None;self.restarts+=1;self.last_video=None
  if self.viewers:self.start_locked()
 def start_locked(self):
  self.ending=threading.Event();self.queue=queue.Queue(600)
  self.thread=threading.Thread(target=self._run,args=(self.ending,self.queue),name='PlayBridge phone stream',daemon=True);self.thread.start()
 def deliver(self,ending,kind,data,info):
  with self.lock:
   # A stream that was replaced may still be finishing a packet: nothing of it reaches the phones.
   if ending.is_set():return
   if kind=='init':self.init=(data,info)
   viewers=list(self.viewers)
  for viewer in viewers:viewer.offer(kind,data,info)
 def _encoder(self):
  """The first encoder that works here, with its options: capped picture sizes when it takes them, else as it can."""
  for name in ('h264_nvenc','h264_amf','h264_qsv','libx264'):
   for options in (encoder_options(name,self.BITRATE),encoder_options(name)):
    if self._works(name,options,self.BITRATE):return name,options
  return None,None
 @staticmethod
 def _works(name,options,bitrate):
  try:
   context=av.CodecContext.create(name,'w');context.width=context.height=256;context.pix_fmt='yuv420p' if name=='libx264' else 'nv12';context.time_base=Fraction(1,60);context.framerate=Fraction(60,1);context.bit_rate=bitrate
   context.options=dict(options);context.open();frame=av.VideoFrame(256,256,context.pix_fmt)
   for plane in frame.planes:plane.update(bytes(plane.buffer_size))
   packets=0
   for index in range(2):frame.pts=index;packets+=len(context.encode(frame))
   return packets+len(context.encode(None))>0
  except Exception:return False
 def _shrinker(self,out,source,on_frame=None):
  from live_broadcast import Remaker
  name,options=self._encoder()
  if name is None:raise RuntimeError('This PC has no H.264 encoder for the phone.')
  decoder=None
  try:
   from av.codec.hwaccel import HWAccel
   decoder=av.CodecContext.create('hevc' if self.codec==HEVC else 'h264','r',hwaccel=HWAccel(device_type='d3d11va',allow_software_fallback=True))
  except Exception:decoder=None
  if decoder is None:decoder=av.CodecContext.create('hevc' if self.codec==HEVC else 'h264','r')
  height=min(self.HEIGHT,source.height);width=(source.width*height//source.height)//2*2
  stream=out.add_stream(name,rate=60);stream.width,stream.height=width,height;stream.pix_fmt='yuv420p' if name=='libx264' else 'nv12'
  stream.bit_rate=self.BITRATE;stream.time_base=Fraction(1,90000);stream.codec_context.time_base=Fraction(1,90000)
  # A picture that needs no other every second, so a phone that joins or falls behind is back within a second: the page jumps to the
  # newest picture when it is far behind, and that jump starts from such a picture. The AMD encoder in its low-latency use ignores the
  # interval and made one in all (seen with the real PS5), so every 60th frame also asks for one, which AMD only turns into a picture
  # with its headers when forced_idr is on.
  stream.codec_context.gop_size=self.KEY_EVERY;stream.codec_context.max_b_frames=0
  stream.options=dict(options)
  every=self.KEY_EVERY;most=self.FILL_MOST;note=self.note;kinds=av.video.frame.PictureType
  class Shrinker(Remaker):
   """Also fills in the pictures the PS5 does not send. On a still screen the PS5 leaves some out (58.4 a second instead of 60 in a
   real session, gaps of 50 to 175 ms), and each gap broke the phone's buffer in two: its page then stopped and jumped, and the
   sound stopped with it. When the next picture comes, the places it skipped get the last picture again first, so the phone's
   pictures have no gap. Nothing is made up before then: a picture that is only late (Wi-Fi from the PS5 brings many 35 to 60 ms
   late) still comes, and making one up on a timer threw those real pictures away, which the owner saw as a much worse picture."""
   made=0;last=None;last_pts=None;step=1500
   def _encode(self,frame):
    if frame.pts is None:return []
    items=[]
    if self.last_pts is not None:
     if frame.pts<=self.last_pts+self.step//2:return []
     if 1000<frame.pts-self.last_pts<2000:self.step=frame.pts-self.last_pts
     filled=0
     while filled<most and frame.pts-self.last_pts>1.5*self.step:
      self.last_pts+=self.step;filled+=1;self.last.pts=self.last_pts;items+=self._send(self.last);note('made',1)
    small=frame.reformat(width=width,height=height,format=stream.pix_fmt,interpolation='BILINEAR');small.time_base=Fraction(1,90000)
    self.last=small;self.last_pts=frame.pts
    return items+self._send(small)
   def _send(self,small):
    # Only every 60th picture is a whole one (the PS5's own whole pictures are not copied as such).
    small.pict_type=kinds.I if self.made%every==0 else kinds.NONE
    self.made+=1
    return self.stream.encode(small)
  self.mode=f'made again as {height}p H.264'
  return Shrinker(decoder,stream,on_frame),stream
 def _run(self,ending,inbox):
  out=None;templates=[];base=None;video_first=None;vs=None;remaker=None;last_dts=None;sound=None
  # When each picture's packet reached the PC (by its time on the phones' clock), for the phone log.
  arrived={}
  def send(packet):
   if not packet.duration:packet.duration=1500
   at=arrived.pop(packet.pts,None)
   if at is not None:self.note('pc',round((time.perf_counter()-at)*1000))
   if len(arrived)>600:arrived.clear()
   out.mux_one(packet)
  try:
   while not ending.is_set():
    try:item=inbox.get(timeout=.1)
    except queue.Empty:item=None
    if item is READY and remaker is not None:
     # A picture made again goes to the encoder as soon as the decoder has it, not with the next packet a frame later.
     for packet in remaker.ready():send(packet)
    if item is None or item is READY:continue
    kind,data,pts,dts,headers,at=item
    if base is None:
     if kind!=1 or not is_idr(data,self.codec):continue
     base=min(pts,dts);video_first=data if codec_headers(data,self.codec) else headers+data
    if pts<base:continue
    if kind==2:
     # The sound goes to the phones as plain samples beside the MP4 (see Sound).
     if sound is None:sound=Sound(data)
     for message in sound.make(data,pts-base):self.deliver(ending,'sound',message,None)
     continue
    if out is None:
     video_template=av.open(io.BytesIO(video_first),format='hevc' if self.codec==HEVC else 'h264');templates=[video_template]
     out=av.open(Fragments(lambda kind,data,info:self.deliver(ending,kind,data,info)),'w',format='mp4',
      container_options={'movflags':'frag_every_frame+empty_moov+default_base_moof','flush_packets':'1'})
     source=video_template.streams.video[0].codec_context
     if self.codec!=HEVC and source.height<=self.COPY_HEIGHT:vs=out.add_stream_from_template(video_template.streams.video[0]);self.mode='as the PS5 sends it'
     else:remaker,vs=self._shrinker(out,source,lambda:wake(inbox))
     self.error=''
    arrived[pts-base]=at
    if remaker is not None:
     packet=av.Packet(data if codec_headers(data,self.codec) or not is_idr(data,self.codec) else headers+data);packet.pts=pts-base;packet.dts=dts-base;packet.time_base=Fraction(1,90000)
     items=remaker.put(packet)
    else:
     packet=av.Packet(data);packet.pts=pts-base;packet.dts=dts-base;packet.time_base=Fraction(1,90000);packet.stream=vs
     # Each picture's length, for the muxer, from the time to the next one.
     packet.is_keyframe=is_idr(data,self.codec);packet.duration=dts-last_dts if last_dts is not None and 0<dts-last_dts<=9000 else 1500;last_dts=dts
     items=[packet]
    for packet in items:send(packet)
  except Exception as error:self.error=f'The phone stream stopped: {error}'
  finally:
   for thing in [out]+templates:
    try:
     if thing is not None:thing.close()
    except Exception:pass
   if remaker is not None:remaker.close()

class ArrivalSpread:
 """How much later than its quickest a phone's controller states reach this PC. Each state carries the phone's own clock (ms); the
 two clocks differ by a constant that drifts only slowly, so the quickest arrival of the last half minute or so stands for no delay
 and every other one is that much later: Wi-Fi holding the phone's sending back, mostly."""
 WINDOW=30.0;MOST=4000
 def __init__(self):self.best=None;self.earlier_best=None;self.window_at=None;self.extras=[]
 def note(self,sent_ms,now):
  offset=now*1000-sent_ms
  if self.window_at is None or now-self.window_at>=self.WINDOW:self.earlier_best=self.best;self.best=None;self.window_at=now
  self.best=offset if self.best is None else min(self.best,offset)
  base=self.best if self.earlier_best is None else min(self.best,self.earlier_best)
  if len(self.extras)<self.MOST:self.extras.append(offset-base)
 def take(self):
  """Since the last call: how many states came, and how much later than the quickest the middle one and the latest one came (ms);
  None when none came."""
  extras=sorted(self.extras);self.extras=[]
  if not extras:return None
  return len(extras),round(extras[len(extras)//2]),round(extras[-1])

class PhonePad:
 """One phone's controller: its own UDP port to the controller companion, so the companion gives it a controller of its own. Like the
 PC's, it is on the PS5 only while the phone plays: from its first press until two minutes with nothing pressed. A page left open
 on a phone never holds a controller there."""
 IDLE=pad.PadBridge.IDLE
 def __init__(self,host,key=None,reach=None):
  # reach(host, port): where the companion's port is from here, away from home too.
  self.reach=reach or (lambda host,port:(host,port))
  self.host=host;self.udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.udp.setblocking(False);self.sequence=0;self.answer=None
  # Its datagrams, sealed once the companion proves it holds this PC's key (secure_link.PadLink).
  self.wire_link=secure_link.PadLink(key)
  self.used_at=None;self.joined=False;self.spread=ArrivalSpread()
 def in_use(self,now):return self.used_at is not None and now-self.used_at<self.IDLE
 def send(self,state,now):
  if not pad.at_rest(state):self.used_at=now
  if not self.in_use(now):self.leave();return
  if self.put(pad.wire(self.sequence,state)):self.sequence+=1;self.joined=True
 def put(self,data):
  try:
   for datagram in self.wire_link.datagrams(data):pad.send_datagram(self.udp,datagram,self.reach(self.host(),pad.PAD_PORT))
  except OSError:return False
  return True
 def leave(self):
  """Its controller leaves the PS5 at once; the next press brings it back. Nothing neutral goes first (see PadBridge.quit)."""
  if self.joined:
   for _ in range(pad.PadBridge.QUIT_COPIES):self.put(pad.QUIT)
  self.joined=False;self.used_at=None;self.answer=None
 def heard(self):
  """The companion's newest answer to this phone, or None. A socket that never sent has no port yet, and Windows answers every read
  on it with an error, so it is not read; the reads are counted as well, so no error can keep this from returning."""
  if not self.sequence:return self.answer
  for _ in range(32):
   try:data,_=self.udp.recvfrom(128)
   except (BlockingIOError,InterruptedError):break
   # A closed port on the console is reported as an error on the next read; the reads after it go on.
   except OSError:continue
   data=self.wire_link.take(data)
   answer=pad.read_status(data) if data is not None else None
   if answer is not None:self.answer=answer
  return self.answer
 def close(self):self.leave();self.udp.close()
def read_pad_message(text,with_time=False):
 """A phone's controller state: {"b": buttons, "s": [lx, ly, rx, ry, l2, r2], "t": the phone's clock in ms}, each kept to the
 console's ranges. with_time: (state, t) instead, t None when missing or not a number; (None, None) for anything else."""
 try:message=json.loads(text)
 except ValueError:message=None
 if not isinstance(message,dict) or not isinstance(message.get('b'),int) or not isinstance(message.get('s'),list) or len(message['s'])!=6 or not all(isinstance(v,int) for v in message['s']):
  return (None,None) if with_time else None
 state=pad.PadState(message['b']&pad.CONSOLE_BUTTONS,*(max(0,min(255,v)) for v in message['s']))
 if not with_time:return state
 sent=message.get('t')
 return state,(sent if isinstance(sent,(int,float)) and not isinstance(sent,bool) and 0<=sent<1e12 else None)

STAT_COUNTS=('waits','stall_ms','seeks','ranges','dropped','frames','sound_late','sound_lost_ms','sound_trims','sound_resyncs','sound_rate','sound_out_ms')
def read_stats_message(text):
 """A phone page's report on how it plays, every 2 s: {"type": "stats", "player", "waits", "stall_ms", "seeks", "ranges",
 "dropped", "frames", "sound_late", "sound_lost_ms", "sound_trims", "sound_resyncs", "sound_rate", "sound_out_ms",
 "sound_underruns", "behind", "picture_aim", "aim"}, counts since it started and seconds now (aim is the sound's store), each
 kept to a sane range; None for anything else.
 sound_underruns is None where the phone's browser does not count them (it sends -1)."""
 try:message=json.loads(text)
 except ValueError:return None
 if not isinstance(message,dict) or message.get('type')!='stats':return None
 number=lambda v,low,high:v if isinstance(v,(int,float)) and not isinstance(v,bool) and low<=v<=high else 0
 report={key:int(number(message.get(key),0,1e9)) for key in STAT_COUNTS}
 report.update({key:round(float(number(message.get(key),-60,60)),3) for key in ('behind','picture_aim','aim')})
 underruns=message.get('sound_underruns')
 report['sound_underruns']=int(underruns) if isinstance(underruns,(int,float)) and not isinstance(underruns,bool) and 0<=underruns<=1e9 else None
 # How the page plays: the picture in the browser's player and the sound itself ("split"), or both in the browser's ("media").
 report['player']=message.get('player') if message.get('player') in ('split','media') else '-'
 return report
def stats_line(phone,page,viewer,pc,controller=None):
 """One line of the phone log: what the page says and what the PC saw for it in the same seconds. controller: ArrivalSpread.take()
 for the phone's controller in those seconds."""
 took='-' if pc['pc_ms'] is None else f"{pc['pc_ms']} ms (longest {pc['pc_max_ms']})"
 return (f"phone {phone} ({page.get('player','-')}): stalls {page['waits']} ({page['stall_ms']} ms in all), jumps {page['seeks']}, buffer pieces {page['ranges']}, "
         f"behind {page['behind']:.2f} s (aim {page.get('picture_aim',0):.2f}), store {page['aim']:.2f} s, pictures dropped {page['dropped']}/{page['frames']}, "
         f"sound late {page.get('sound_late',0)} ({page.get('sound_lost_ms',0)} ms left out), taken back {page.get('sound_trims',0)}, "
         f"rejoined {page.get('sound_resyncs',0)}, output {page.get('sound_rate',0)} Hz {page.get('sound_out_ms',0)} ms, "
         f"ran out {'?' if page.get('sound_underruns') is None else page['sound_underruns']} | "
         f"PC: longest wait for the PS5 {pc['ps5_gap_ms']} ms, PC time {took}, pictures made up {pc['made_up']}, "
         f"waiting {viewer.size//1024} KB, fell behind {viewer.dropped}, restarts {pc['restarts']} | "
         +("controller: no states" if controller is None else f"controller: {controller[0]} states, {controller[1]} ms later than its quickest (latest {controller[2]})"))

class PhoneLog:
 """The phone log on this PC (phone-log.txt beside the session stats): a line every 2 s for each phone that plays, so a stall on
 a phone can be traced to the PS5, this PC, the Wi-Fi or the phone without anyone sending a file. Kept under 2 MB (the older
 half goes to phone-log.old.txt)."""
 LIMIT=2*1024*1024
 def __init__(self,path):self.path=path;self.lock=threading.Lock()
 def write(self,line):
  with self.lock:
   try:
    if self.path.exists() and self.path.stat().st_size>self.LIMIT:self.path.replace(self.path.with_name(self.path.stem+'.old.txt'))
    with open(self.path,'a',encoding='utf8') as file:file.write(time.strftime('%Y-%m-%d %H:%M:%S ')+line+'\n')
   except OSError:pass

def local_address(toward):
 """This PC's address on the network that reaches the PS5, for the phone to open. A UDP connect only asks Windows for the route
 and sends nothing. When the PS5 is this PC itself (a stand-in) or has no route, the address of the usual way out is used, then any
 private address this PC has, so a phone is never told to open 127.0.0.1."""
 for target in (toward,'192.168.1.1','10.0.0.1'):
  if not target:continue
  try:
   with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as probe:probe.connect((target,9));found=probe.getsockname()[0]
  except OSError:continue
  if found and not found.startswith('127.') and found!='0.0.0.0':return found
 try:
  for *_,place in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET):
   if ipaddress.ip_address(place[0]).is_private and not place[0].startswith('127.'):return place[0]
 except (OSError,ValueError):pass
 return '127.0.0.1'
def nearby(address):
 """Only devices on this network may use the page: private, link-local and this PC itself."""
 try:ip=ipaddress.ip_address(address)
 except ValueError:return False
 if ip.version==6 and ip.ipv4_mapped:ip=ip.ipv4_mapped
 return ip.is_private or ip.is_link_local or ip.is_loopback

PANEL_GETS=('/api/games','/api/captures','/api/log','/api/icon/','/api/thumb/','/api/file/')
MEDIA={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.gif':'image/gif','.mp4':'video/mp4','.webm':'video/webm'}
def byte_range(header,size):
 """The one range a 'Range: bytes=a-b' header asks for, as (first, last) inclusive, or None for the whole file (no header, or one this
 server does not split, such as several ranges). ValueError when the range lies past the end."""
 match=re.fullmatch(r'\s*bytes\s*=\s*(\d*)\s*-\s*(\d*)\s*',header or '')
 if not match or match.group(1)==match.group(2)=='':return None
 first,last=match.groups()
 if first=='':
  if int(last)==0:raise ValueError('empty range')
  first,last=max(0,size-int(last)),size-1
 else:first,last=int(first),min(int(last),size-1) if last else size-1
 if first>=size or first>last:raise ValueError('past the end')
 return first,last
def disposition(name,save):
 """Shown in the page, or saved under its own name; the plain name is for browsers that do not read the UTF-8 one."""
 plain=''.join(c if 32<=ord(c)<127 and c not in '"\\' else '_' for c in name)
 return f'{"attachment" if save else "inline"}; filename="{plain}"; filename*=UTF-8\'\'{urllib.parse.quote(name,safe="")}'
def send_file(handler,path,save=False):
 """A capture, whole or the part a video player asks for, read a megabyte at a time so a long recording never sits in memory."""
 try:file=open(path,'rb')
 except OSError:handler.reply(404,b'{"error":"missing"}');return
 with file:
  size=os.fstat(file.fileno()).st_size
  try:span=byte_range(handler.headers.get('Range'),size)
  except ValueError:
   handler.send_response(416);handler.send_header('Content-Range',f'bytes */{size}');handler.send_header('Content-Length','0');handler.end_headers();return
  first,last=span or (0,size-1)
  handler.send_response(206 if span else 200);handler.send_header('Content-Type',MEDIA.get(Path(path).suffix.lower(),'application/octet-stream'))
  handler.send_header('Content-Length',str(last-first+1));handler.send_header('Accept-Ranges','bytes')
  if span:handler.send_header('Content-Range',f'bytes {first}-{last}/{size}')
  handler.send_header('Content-Disposition',disposition(Path(path).name,save));handler.send_header('Cache-Control','no-store')
  handler.send_header('X-Content-Type-Options','nosniff');handler.end_headers()
  if handler.command=='HEAD':return
  file.seek(first);left=last-first+1
  try:
   while left>0:
    chunk=file.read(min(left,1<<20))
    if not chunk:break
    handler.wfile.write(chunk);left-=len(chunk)
  except OSError:pass
  # A file that shrank while it was sent leaves the reply short, so the connection cannot carry another one.
  if left:handler.close_connection=True

class QuietServer(http.server.ThreadingHTTPServer):
 """A phone that leaves, sleeps or loses Wi-Fi drops its connection; that is normal and not worth a traceback."""
 def handle_error(self,request,client_address):
  if isinstance(sys.exc_info()[1],(OSError,EOFError)):return
  super().handle_error(request,client_address)

class PhoneServer:
 """The page, pairing and the phones' WebSockets. play(): whether phones may play (Play on your PS5 is on and the PS5 is connected)."""
 def __init__(self,feed,pairing,host,play,port=PORT,log=None):
  self.feed=feed;self.pairing=pairing;self.host=host;self.play=play;self.port=port;self.server=None;self.phones=0;self.lock=threading.Lock();self.error=''
  # The PS5 payloads' key for the phones' controllers (secure_link.Pairing.pad_key), set by the app; None sends them as they are.
  self.pad_key=None
  # Where the companion's port is from here (app.reach), set by the app too.
  self.pad_reach=None
  # The phone log (a PhoneLog), and a number for each phone that connects, so its lines can be told apart.
  self.log=log;self.connected=0
  # The controllers, and a way to close and to tell something to each phone connected now.
  self.pads=set();self.closers={};self.sayers={}
  # The More panel (a phone_panel.Panel), set by the app; None leaves it out.
  self.panel=None
 @property
 def running(self):return self.server is not None
 def in_use(self,now):
  """Whether a phone plays now, so the PC sends the controller companion when nothing answers."""
  with self.lock:return any(phone.in_use(now) for phone in self.pads)
 def disconnect(self):
  """Every phone connected now is told the PC closed it and is let go, its controller off the PS5. Its page then waits until it is
  asked to connect again. How many were connected."""
  with self.lock:closers=list(self.closers.values())
  for close in closers:close()
  return len(closers)
 def alert(self,title,text):
  """Alert me when: each phone connected now shows it over the game and vibrates. Sent from a thread of its own, since a phone on a
  slow Wi-Fi link can keep its connection busy for seconds. How many phones it goes to."""
  with self.lock:sayers=list(self.sayers.values())
  def tell():
   for say in sayers:
    try:say({'type':'alert','title':title,'text':text})
    except OSError:pass
  if sayers:threading.Thread(target=tell,name='PlayBridge phone alert',daemon=True).start()
  return len(sayers)
 def start(self):
  if self.server is not None:return True
  owner=self
  class Handler(http.server.BaseHTTPRequestHandler):
   # A phone that goes quiet on a kept-alive connection frees its thread after this many seconds.
   protocol_version='HTTP/1.1';server_version='PlayBridge';timeout=30
   def log_message(self,*args):pass
   def reply(self,code,body=b'',kind='application/json'):
    self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
    self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
   def allowed(self):
    if nearby(self.client_address[0]):return True
    self.reply(403,b'{"error":"network"}');return False
   def do_GET(self):
    if not self.allowed():return
    # The page also opens with a choice after it (?player=media picks the browser's own player).
    # /tv is the same page for a big screen: a TV, a Steam Deck or a PC browser, played with a remote, a controller or a keyboard.
    if self.path.split('?',1)[0] in ('/','/index.html','/tv'):
     try:self.reply(200,PAGE.read_bytes(),'text/html; charset=utf-8')
     except OSError:self.reply(500,b'{"error":"page"}')
    elif self.path=='/api/check':self.reply(200 if owner.pairing.knows(self.headers.get('X-Token','')) else 401,b'{}')
    elif self.path=='/ws' and self.headers.get('Upgrade','').lower()=='websocket' and self.headers.get('Sec-WebSocket-Key'):owner.websocket(self)
    elif owner.panel is not None and self.path.startswith(PANEL_GETS):owner.panel_get(self)
    else:self.reply(404,b'{"error":"missing"}')
   def do_HEAD(self):
    # A video player may ask for a capture's size first.
    if not self.allowed():return
    if owner.panel is not None and self.path.startswith('/api/file/'):owner.panel_get(self)
    else:self.send_response(404);self.send_header('Content-Length','0');self.end_headers()
   def do_POST(self):
    if not self.allowed():return
    if owner.panel is not None and self.path in ('/api/start','/api/ticket'):owner.panel_post(self);return
    if self.path!='/api/pair':self.reply(404,b'{"error":"missing"}');return
    try:
     size=int(self.headers.get('Content-Length','0'))
     if not 0<size<=256:raise ValueError
     code=json.loads(self.rfile.read(size)).get('code','')
    except (ValueError,AttributeError):self.reply(400,b'{"error":"request"}');return
    result,value=owner.pairing.pair(code,time.monotonic())
    if result=='ok':self.reply(200,json.dumps({'token':value}).encode())
    elif result=='wrong':self.reply(403 if value else 429,json.dumps({'error':'code','left':value}).encode())
    else:self.reply(410,b'{"error":"closed"}')
  try:server=QuietServer(('0.0.0.0',self.port),Handler)
  except OSError as error:self.error=f'Port {self.port} is in use on this PC ({error.strerror or error}).';return False
  server.daemon_threads=True;self.server=server;self.error='';self.port=server.server_address[1]
  threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.25},name='PlayBridge phone page',daemon=True).start()
  return True
 def paired(self,handler):
  if self.pairing.knows(handler.headers.get('X-Token','')):return True
  handler.reply(401,b'{"error":"pair"}');return False
 def panel_get(self,handler):
  """The More panel's lists and pictures for a paired phone, and a capture for whoever holds its ticket."""
  path,_,query=handler.path.partition('?');path=urllib.parse.unquote(path);panel=self.panel
  if path.startswith('/api/file/'):
   # A ticket stands for the token here: a video or picture element and a download link cannot send a header.
   item=panel.redeem(path[len('/api/file/'):])
   if item is None:handler.reply(410,b'{"error":"ticket"}')
   else:send_file(handler,item.path,save='save=1' in query.split('&'))
   return
  if not self.paired(handler):return
  if path=='/api/games':handler.reply(200,json.dumps({'games':panel.game_list()}).encode())
  elif path=='/api/captures':handler.reply(200,json.dumps({'captures':panel.capture_list()}).encode())
  elif path=='/api/log':handler.reply(200,json.dumps({'lines':panel.log_lines()}).encode())
  else:
   if path.startswith('/api/icon/'):data,kind=panel.icon_bytes(path[len('/api/icon/'):]),'image/png'
   elif path.startswith('/api/thumb/'):data,kind=panel.thumb_bytes(path[len('/api/thumb/'):]),'image/jpeg'
   else:data,kind=None,''
   if data:handler.reply(200,data,kind)
   else:handler.reply(404,b'{"error":"missing"}')
 def panel_post(self,handler):
  """Starting a game, or a ticket to look at or save a capture."""
  if not self.paired(handler):return
  try:
   size=int(handler.headers.get('Content-Length','0'))
   if not 0<size<=512:raise ValueError
   asked=json.loads(handler.rfile.read(size));key=str(asked.get('id',''))
  except (ValueError,AttributeError):handler.reply(400,b'{"error":"request"}');return
  if handler.path=='/api/start':
   if not self.play():answer=dict(state='problem',text='Starting a game needs Play on your PS5, in PlayBridge › Settings › Console.')
   else:answer=self.panel.start_game(key,bool(asked.get('switch')))
   handler.reply(200,json.dumps(answer).encode())
  else:
   url=self.panel.ticket(key)
   if url:handler.reply(200,json.dumps({'url':url}).encode())
   else:handler.reply(404,b'{"error":"missing"}')
 def stop(self):
  server=self.server;self.server=None
  if server is not None:
   threading.Thread(target=lambda:(server.shutdown(),server.server_close()),name='PlayBridge phone page stop',daemon=True).start()
 def websocket(self,handler):
  handler.send_response(101);handler.send_header('Upgrade','websocket');handler.send_header('Connection','Upgrade')
  handler.send_header('Sec-WebSocket-Accept',accept_key(handler.headers['Sec-WebSocket-Key']));handler.end_headers();handler.wfile.flush()
  # The page sends its controller state at least ten times a second, so this much silence means the phone is gone.
  connection=handler.connection;connection.settimeout(20);writes=threading.Lock();handler.close_connection=True
  # Each picture leaves at once: with Nagle's wait the end of a picture can sit on the PC until the phone acknowledges the one before,
  # which over Wi-Fi comes in bursts and runs the phone's small store dry.
  try:connection.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
  except OSError:pass
  def send(opcode,data):
   with writes:connection.sendall(ws_frame(opcode,data))
  def say(message):send(TEXT,json.dumps(message).encode())
  try:opcode,data=ws_read(handler.rfile)
  except (OSError,EOFError,ValueError):return
  try:token=json.loads(data).get('token') if opcode==TEXT else None
  except (ValueError,AttributeError):token=None
  if not self.pairing.knows(token):
   try:send(CLOSE,struct.pack('>H',NOT_PAIRED))
   except OSError:pass
   return
  with self.lock:
   if self.phones>=MAX_PHONES:
    try:send(CLOSE,struct.pack('>H',NO_ROOM))
    except OSError:pass
    return
   self.phones+=1;self.connected+=1;number=self.connected
  viewer=self.feed.join();phone=PhonePad(self.host,self.pad_key,self.pad_reach);done=threading.Event();told=None;key=object()
  def close_now():
   # The page hears why, then the read below stops at once.
   done.set()
   try:send(CLOSE,struct.pack('>H',CLOSED_ON_PC))
   except OSError:pass
   try:connection.shutdown(socket.SHUT_RDWR)
   except OSError:pass
  with self.lock:self.pads.add(phone);self.closers[key]=close_now;self.sayers[key]=say
  def writer():
   try:
    while not done.is_set():
     item=viewer.take(.5)
     if item is None:continue
     kind,data,info=item
     if kind=='init':say({'type':'init','mime':info})
     send(BINARY,data)
   except OSError:pass
   done.set()
  threading.Thread(target=writer,name='PlayBridge phone writer',daemon=True).start()
  try:
   say({'type':'hello','play':bool(self.play()),'joined':False})
   while not done.is_set():
    opcode,data=ws_read(handler.rfile)
    if opcode==CLOSE:break
    if opcode==PING:send(PONG,data);continue
    if opcode!=TEXT:continue
    report=read_stats_message(data)
    if report is not None:
     if self.log is not None:self.log.write(stats_line(number,report,viewer,self.feed.report(),phone.spread.take()))
     continue
    state,sent=read_pad_message(data,True)
    if state is not None and sent is not None:phone.spread.note(sent,time.monotonic())
    if state is not None:
     if self.play():phone.send(state,time.monotonic())
     else:phone.leave()
    answer=phone.heard();answer=answer if phone.joined else None
    shown=(bool(self.play()),phone.joined,answer[0] if answer else None,answer[1] if answer else 0,answer[3] if answer else 0)
    if shown!=told:told=shown;say({'type':'pad','play':shown[0],'joined':shown[1],'state':shown[2],'error':shown[3]&0xffffffff,'player':shown[4]})
  except (OSError,EOFError,ValueError):pass
  finally:
   done.set();self.feed.leave(viewer);phone.close()
   with self.lock:self.phones-=1;self.pads.discard(phone);self.closers.pop(key,None);self.sayers.pop(key,None)
