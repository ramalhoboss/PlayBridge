"""A PSN voice message played on PlayBridge's sound output, beside the game's sound and the library's: one at a time, stopped by the next one
or by the player. The file is decoded whole first (they are short), so the sound output never waits on the decoder."""
import threading
import numpy as np
import sounddevice as sd
from audio_output import output_settings
from sound_board import RATE,read_audio

class VoiceNote:
 """device() is the sound output the game plays on. playing is the message playing now ('' when none)."""
 def __init__(self,device=lambda:None,opener=None):
  self.device=device;self.opener=opener or (lambda **settings:sd.OutputStream(**settings))
  self.lock=threading.Lock();self.stream=None;self.samples=None;self.at=0;self.playing='';self.token=None
 def play(self,key,path):
  """Plays one voice message from the start. Returns '' when it plays, else what went wrong, in words."""
  try:samples=read_audio(path)
  except Exception:return 'PlayBridge could not read this voice message.'
  self.stop();token=object()
  def feed(outdata,frames,timing,status):
   with self.lock:
    part=samples[self.at:self.at+frames] if self.token is token else samples[:0]
    self.at+=frames
   outdata[:len(part)]=part;outdata[len(part):]=0
   if len(part)<frames:raise sd.CallbackStop
  def ended():
   # Only this message's own end: one started since has its own token.
   with self.lock:
    if self.token is token:self.playing='';self.stream=None;self.token=None
  try:
   device=self.device()
   stream=self.opener(device=device,samplerate=RATE,channels=2,dtype='float32',extra_settings=output_settings(device),callback=feed,finished_callback=ended)
   with self.lock:self.samples=samples;self.at=0;self.playing=key;self.stream=stream;self.token=token
   stream.start()
  except Exception:
   with self.lock:self.playing='';self.stream=None;self.token=None
   return 'PlayBridge could not open the sound output for this voice message.'
  return ''
 def stop(self):
  with self.lock:stream,self.stream=self.stream,None;self.playing='';self.token=None
  if stream is not None:
   try:stream.abort();stream.close()
   except Exception:pass
