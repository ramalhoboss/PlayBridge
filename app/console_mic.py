"""The DualSense's microphone, heard through the PS5: the payload opens the console's own microphone library while PlayBridge listens on
PORT and sends what it hears, 16-bit mono, a block at a time. Here it becomes 48 kHz samples for the same voice buffer the PC's microphone
fills, so recordings, instant replays and Go live take it the same way. The payload listens only while a stream runs, so this keeps
trying while it is on, and says why when the PS5 cannot open the microphone.

Measured on the PS5 on 2026-11-16: opening the microphone from a payload gets the whole payload stopped by the system, so today's
payload never opens it and answers STAYS_CLOSED; the DualSense's microphone then comes over USB to the PC instead."""
import socket,struct,threading,time
import numpy as np

PORT=9079;MAGIC=b'PBM1'
HEAD=struct.Struct('<4siiii');BLOCK=struct.Struct('<HH')
NAME='DualSense on your PS5'
RATE=48000
# The payload's answer in place of a handle when it keeps the microphone closed (payload/mic-rules.h).
STAYS_CLOSED=0x8eb00001
STAYS_CLOSED_NOTE=('The PS5 stops PlayBridge if it opens the DualSense microphone, so it stays closed. Connect the DualSense to this PC '
 'with a USB cable and pick its microphone in Settings.')
# sceAudioInGetSilentState's flags.
NO_DEVICE=0x01;PRIORITY_LOW=0x02;NO_FORMAT=0x08
# Seconds between tries while the PS5 does not answer, and the most samples in one block.
AGAIN=2.0;GRAIN_MOST=4096

def read_exact(sock,size):
 data=bytearray()
 while len(data)<size:
  part=sock.recv(size-len(data))
  if not part:raise EOFError('The PS5 closed the microphone')
  data.extend(part)
 return bytes(data)

class Upsampler:
 """Linear steps from the microphone's rate to 48 kHz. Output sample k sits at input sample k*rate/RATE, counted in whole numbers from
 the first block, so blocks join with no gap, repeat or drift; the last sample of each block carries over to the next."""
 def __init__(self,rate):self.rate=rate;self.k=0;self.taken=0;self.last=0.0
 def __call__(self,samples):
  n=len(samples)
  if self.rate==RATE or not n:return samples
  end=((self.taken+n-1)*RATE)//self.rate;ks=np.arange(self.k,end+1,dtype=np.int64)
  # Places in the block with the carried sample in front: index 0 is input sample taken-1.
  places=(ks*self.rate-(self.taken-1)*RATE)/RATE
  out=np.interp(places,np.arange(n+1),np.concatenate(([self.last],samples))).astype(np.float32)
  self.k=end+1;self.taken+=n;self.last=float(samples[-1]);return out

def silence_note(flags):
 if flags&NO_DEVICE:return 'The PS5 hears no microphone: is the DualSense on and its microphone not muted?'
 if flags&PRIORITY_LOW:return 'Another app on the PS5 has the microphone, such as party chat, so PlayBridge hears silence.'
 return ''

class ConsoleMic:
 """Feeds voice (mic_mix.VoiceBuffer) from the DualSense while it runs. host(): the console's address. stop() ends it."""
 def __init__(self,host,voice,notify=None,connect=None):
  # connect(host, port): sealed when the payload holds this PC's key (secure_link.Pairing.connect).
  self.connect=connect or (lambda host,port:socket.create_connection((host,port),2))
  self.host=host;self.voice=voice;self.notify=notify or (lambda text:None);self.stopping=threading.Event();self.sock=None
  self.state='Waiting for the PS5…';self.rate=0;self.way=-1;self.silent=0;self.blocks=0;self.told=''
  self.thread=threading.Thread(target=self.run,name='DualSense microphone',daemon=True);self.thread.start()
 def tell(self,text):
  self.state=text
  if text!=self.told:self.told=text;self.notify(text)
 def run(self):
  while not self.stopping.is_set():
   try:
    with self.connect(self.host(),PORT) as sock:
     self.sock=sock;sock.settimeout(5);self.serve(sock)
   except (OSError,EOFError,ValueError,struct.error):pass
   finally:self.sock=None
   if self.blocks and not self.stopping.is_set():self.state='Waiting for the PS5…'
   self.stopping.wait(AGAIN)
 def serve(self,sock):
  magic,handle,rate,grain,way=HEAD.unpack(read_exact(sock,HEAD.size))
  if magic!=MAGIC:raise ValueError('Not the PlayBridge microphone')
  if handle<0:
   code=handle&0xffffffff
   self.tell(STAYS_CLOSED_NOTE if code==STAYS_CLOSED else f'The PS5 did not open the DualSense microphone ({code:08x}).');self.stopping.wait(30);return
  if not 0<grain<=GRAIN_MOST or rate<=0:raise ValueError('Odd microphone blocks')
  self.rate,self.way=rate,way;upsample=Upsampler(rate);self.tell(f'DualSense microphone on, at {rate//1000} kHz.')
  while not self.stopping.is_set():
   count,silent=BLOCK.unpack(read_exact(sock,BLOCK.size))
   if count!=grain:raise ValueError('Odd microphone block')
   samples=np.frombuffer(read_exact(sock,count*2),'<i2').astype(np.float32)/32768
   self.voice.add(upsample(samples));self.blocks+=1
   if silent!=self.silent:
    self.silent=silent;note=silence_note(silent)
    self.tell(note or f'DualSense microphone on, at {rate//1000} kHz.')
 def stop(self):
  self.stopping.set();sock=self.sock
  if sock is not None:
   try:sock.shutdown(socket.SHUT_RDWR)
   except OSError:pass
 def close(self):self.stop()
