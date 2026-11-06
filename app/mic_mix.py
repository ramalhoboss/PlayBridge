"""Your microphone in recordings, instant replays and Go live. While it is on, the console's sound is decoded, your voice is added and the
mix is encoded to AAC again, one console frame at a time, so the recorder and the live output take it like the console's own sound.
While it is off nothing here runs, and the console's sound is copied untouched as before."""
import collections,threading
from fractions import Fraction
import numpy as np

RATE=48000;FRAME=1024
# The microphone runs on its own clock, so its buffer drifts against the console's. Above HIGH the oldest sound is dropped down to TARGET,
# and below one frame the missing part is silence: either is a few milliseconds of voice, far less than drift would cost over an hour.
TARGET=int(RATE*.04);HIGH=int(RATE*.12)
LEVEL_MAX=2.0
WASAPI='Windows WASAPI'

def adts(raw):
 """A raw AAC-LC frame with the 7-byte ADTS header of a 48 kHz stereo stream, as the console sends it."""
 size=len(raw)+7
 return bytes([0xff,0xf1,0x4c,0x80|(size>>11),(size>>3)&0xff,((size&7)<<5)|0x1f,0xfc])+raw

def inputs(sd):
 """Microphones Windows offers through WASAPI, as (index, name)."""
 try:apis=sd.query_hostapis();devices=sd.query_devices()
 except Exception:return []
 return [(i,d['name']) for i,d in enumerate(devices) if d['max_input_channels']>0 and apis[d['hostapi']]['name']==WASAPI]

class VoiceBuffer:
 """Microphone samples between the sound card's thread and the mixer, mono, at 48 kHz."""
 def __init__(self):
  self.lock=threading.Lock();self.parts=collections.deque();self.held=0;self.dropped=0;self.short=0
 def add(self,samples):
  with self.lock:
   self.parts.append(np.asarray(samples,np.float32).reshape(-1));self.held+=len(self.parts[-1])
   if self.held>HIGH:self.drop(self.held-TARGET)
 def drop(self,count):
  self.dropped+=count
  while count>0 and self.parts:
   first=self.parts[0]
   if len(first)<=count:self.parts.popleft();self.held-=len(first);count-=len(first)
   else:self.parts[0]=first[count:];self.held-=count;count=0
 def take(self,count):
  """Exactly count samples, the oldest first, with silence where the microphone has not delivered them."""
  out=np.zeros(count,np.float32);at=0
  with self.lock:
   while at<count and self.parts:
    first=self.parts[0];n=min(len(first),count-at);out[at:at+n]=first[:n];at+=n;self.held-=n
    if n==len(first):self.parts.popleft()
    else:self.parts[0]=first[n:]
   if at<count:self.short+=count-at
  return out
 def clear(self):
  with self.lock:self.parts.clear();self.held=0

class MicMix:
 """Mixes the voice into each console sound packet. Codecs are made on first use, in the network thread that calls mix()."""
 def __init__(self,av_module=None):
  self.av=av_module;self.voice=VoiceBuffer();self.level=1.0;self.decoder=None;self.encoder=None;self.waiting=collections.deque();self.mixed=0;self.peak=0.0
 def reset(self):
  """A new session: the codecs start again so no sound from the last one comes out of the next."""
  self.decoder=self.encoder=None;self.waiting.clear();self.voice.clear()
 def open_codecs(self):
  av=self.av
  if av is None:import av;self.av=av
  self.decoder=self.av.CodecContext.create('aac','r')
  encoder=self.av.CodecContext.create('aac','w');encoder.sample_rate=RATE;encoder.layout='stereo';encoder.format='fltp';encoder.bit_rate=192000;encoder.time_base=Fraction(1,RATE);encoder.open()
  self.encoder=encoder;self.next_pts=0
 def mix(self,payload,pts):
  """Returns the mixed packets as (ADTS bytes, 90 kHz timestamp). The encoder holds one frame back, so each packet takes the timestamp of the
  console packet that went in one call earlier, and the first call returns none."""
  if self.encoder is None:self.open_codecs()
  out=[]
  for packet in self.decoder.parse(payload):
   for frame in self.decoder.decode(packet):
    game=frame.to_ndarray().astype(np.float32,copy=False)
    if game.ndim==1:game=game.reshape(1,-1)
    if game.shape[0]==1:game=np.repeat(game,2,axis=0)
    voice=self.voice.take(game.shape[1])*self.level
    mixed=np.clip(game[:2]+voice,-1,1).astype(np.float32);self.peak=max(self.peak*.98,float(np.abs(voice).max(initial=0)))
    fresh=self.av.AudioFrame.from_ndarray(np.ascontiguousarray(mixed),format='fltp',layout='stereo');fresh.sample_rate=RATE;fresh.pts=self.next_pts;fresh.time_base=Fraction(1,RATE);self.next_pts+=mixed.shape[1]
    self.waiting.append(pts)
    for encoded in self.encoder.encode(fresh):
     if self.waiting:out.append((adts(bytes(encoded)),self.waiting.popleft()))
  self.mixed+=len(out)
  return out

class Microphone:
 """The microphone that feeds a MicMix while it is on. Opening it is what turns the mix on, and closing it turns the mix off."""
 def __init__(self,mix,sd=None):
  self.mix=mix;self.sd=sd;self.stream=None;self.name='';self.error=''
 @property
 def on(self):return self.stream is not None
 def open(self,wanted=''):
  """Opens the chosen microphone, or Windows' default one. Returns True when it is open; otherwise error says why."""
  sd=self.sd
  if sd is None:import sounddevice as sd;self.sd=sd
  self.close();self.error=''
  choices=[index for index,name in inputs(sd) if name==wanted]+[None]
  for device in choices:
   try:
    settings=sd.WasapiSettings(auto_convert=True)
    stream=sd.InputStream(device=device,samplerate=RATE,channels=1,dtype='float32',blocksize=480,latency='low',extra_settings=settings,callback=self.callback)
    stream.start()
   except Exception as problem:self.error=str(problem).split(' [PaErrorCode')[0];continue
   self.stream=stream;self.mix.voice.clear()
   try:self.name=sd.query_devices(device if device is not None else sd.default.device[0])['name']
   except Exception:self.name='Microphone'
   return True
  if not self.error:self.error='No microphone found'
  return False
 def callback(self,data,frames,timing,status):self.mix.voice.add(data[:,0] if data.ndim>1 else data)
 def close(self):
  stream,self.stream=self.stream,None
  if stream is not None:
   try:stream.stop();stream.close()
   except Exception:pass
  self.mix.voice.clear()
