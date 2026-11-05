"""The library's sounds: quiet background music and small cues for moving between covers. They play on their own output, open only while the library shows, so the game's audio path stays as it was."""
import ctypes,threading
import numpy as np
import sounddevice as sd
from audio_output import output_settings
from luxury_theme import skin_path

RATE=48000;BLOCK=1024;FADE_IN=1.4;FADE_OUT=.7;VOICES=4;GAME_LEVEL=.075;GAME_PEAK=.8;KEPT_TRACKS=4

def decay(seconds,speed):
 return np.exp(-np.arange(int(seconds*RATE),dtype=np.float32)/RATE*speed)
def ping(frequency,seconds,speed,level,overtones=((2.0,.3),(3.01,.08))):
 """A soft struck note. A few samples of fade keep its start from clicking."""
 time=np.arange(int(seconds*RATE),dtype=np.float32)/RATE;tone=np.sin(2*np.pi*frequency*time)
 for ratio,share in overtones:tone+=share*np.sin(2*np.pi*frequency*ratio*time)
 tone*=decay(seconds,speed)*level;tone[:48]*=np.linspace(0,1,48,dtype=np.float32);tone[-96:]*=np.linspace(1,0,96,dtype=np.float32)
 return tone
def layered(*notes):
 """Notes that start at set times, as (seconds, samples)."""
 output=np.zeros(max(int(at*RATE)+len(note) for at,note in notes),dtype=np.float32)
 for at,note in notes:output[int(at*RATE):int(at*RATE)+len(note)]+=note
 return np.column_stack((output,output))
def cue_sounds():
 """The app's own navigation sounds, made here and not taken from anywhere."""
 return {
  'move':layered((0,ping(1568,.07,70,.10)),(0,ping(392,.05,90,.06,()))),
  'edge':layered((0,ping(196,.09,48,.14,((2.0,.15),)))),
  'accept':layered((0,ping(659.25,.5,9,.13)),(.07,ping(987.77,.6,8,.13)),(.14,ping(1318.5,.7,8,.07))),
  'back':layered((0,ping(659.25,.16,24,.1)),(.06,ping(440,.22,18,.1))),
  'error':layered((0,ping(155.6,.14,30,.2,())),(.13,ping(130.8,.2,24,.2,()))),
 }
def ambient_loop(seconds=64):
 """Slow, soft chords that join up exactly when they repeat: every wave fits a whole number of times into the loop. Worked out at a quarter of the rate, since nothing in it is high."""
 rate=RATE//4;count=seconds*rate;time=np.arange(count,dtype=np.float32)/rate;turn=2*np.pi*time/seconds;picker=np.random.default_rng(7)
 def chord(notes):
  sides=[]
  for _ in (0,1):
   side=np.zeros(count,dtype=np.float32)
   for frequency,level in notes:
    cycles=round(frequency*seconds)+int(picker.integers(-2,3));swell=.62+.38*np.sin(turn*int(picker.integers(2,6))+picker.uniform(0,6.28))
    side+=level*swell*np.sin(turn*cycles+picker.uniform(0,6.28))
   sides.append(side)
  return np.column_stack(sides)
 first=chord(((73.42,.42),(110,.5),(146.83,.6),(185,.6),(220,.65),(293.66,.5),(329.63,.42),(440,.24),(659.25,.09)))
 second=chord(((61.74,.42),(92.5,.5),(123.47,.6),(146.83,.6),(185,.65),(246.94,.5),(277.18,.42),(369.99,.24),(554.37,.09)))
 mix=(.5+.5*np.cos(turn))[:,None];music=first*mix+second*(1-mix)
 positions=np.arange(seconds*RATE)/RATE*rate;wide=np.column_stack([np.interp(positions,np.arange(count+1),np.append(music[:,side],music[0,side])) for side in (0,1)]).astype(np.float32)
 return wide*(.075/max(1e-6,float(np.sqrt(np.mean(wide**2)))))
def read_audio(path):
 """Any audio file as stereo floats at the board's rate."""
 import av
 parts=[];change=av.AudioResampler(format='fltp',layout='stereo',rate=RATE)
 with av.open(str(path)) as source:
  for frame in source.decode(audio=0):parts+=[piece.to_ndarray() for piece in change.resample(frame)]
 parts+=[piece.to_ndarray() for piece in change.resample(None)]
 # In C order: np.take would otherwise copy the whole track for every block of sound, and the output would run dry.
 return np.concatenate(parts,axis=1).T.astype(np.float32,order='C')
def music_track():
 """A local file if this copy of the app has one, otherwise the app's own music."""
 for name in ('ambient.flac','ambient.wav','ambient.ogg'):
  path=skin_path('sounds/'+name)
  if path:
   try:return read_audio(path)
   except Exception:pass
 return ambient_loop()
def game_track(path):
 """A game's own music, brought to the level of the library's music without clipping and faded at its ends, since few of them are made to loop."""
 track=read_audio(path);level=float(np.sqrt(np.mean(track**2)));peak=float(np.abs(track).max())
 if level>0:track=track*min(GAME_LEVEL/level,GAME_PEAK/peak)
 edge=min(len(track)//4,int(RATE*.4));ramp=np.linspace(0,1,edge,dtype=np.float32)[:,None];track[:edge]*=ramp;track[-edge:]*=ramp[::-1]
 return track

class SoundBoard:
 def __init__(self,device=lambda:None,music=True,effects=True,volume=.6):
  self.device=device;self.music_on=music;self.effects_on=effects;self.volume=volume
  self.shown=False;self.music_wanted=False;self.stream=None;self.track=None;self.swap=None;self.leaving=None;self.at=0;self.gain=0.0;self.voices=[];self.broken=False;self.cues=cue_sounds()
  self.wanted_file=None;self.playing_file=False;self.own_track=None;self.kept={}
  self.stop=threading.Event();self.changed=threading.Event();threading.Thread(target=self.manage,name='Library sound',daemon=True).start()
 def show(self,on):
  if on!=self.shown:self.shown=on;self.changed.set()
 def want_music(self,on):
  if on!=self.music_wanted:self.music_wanted=on;self.changed.set()
 def set_music(self,on):
  self.music_on=on;self.changed.set()
 def want_track(self,path):
  """The file the music comes from, or None for the app's own."""
  if path!=self.wanted_file:self.wanted_file=path;self.changed.set()
 def play(self,name):
  """Starts a cue. Called from the window's thread, and small enough to change between two blocks of sound."""
  if self.effects_on and self.shown and name in self.cues:self.voices=(self.voices+[[self.cues[name],0]])[-VOICES:]
 def goal(self):
  return 1.0 if self.shown and self.music_on and self.music_wanted else 0.0
 def mix(self,frames):
  """The next block of sound."""
  output=np.zeros((frames,2),dtype=np.float32);goal=self.goal()
  if self.swap is not None:
   # The new music comes in as the old goes.
   if self.track is not None and self.gain>0:self.leaving=[self.track,self.at,self.gain]
   self.track,self.swap=self.swap,None;self.at=0;self.gain=0.0
  track=self.track
  if track is not None and (goal>0 or self.gain>0):
   change=frames/RATE/(FADE_IN if goal>self.gain else FADE_OUT);gain=min(goal,self.gain+change) if goal>self.gain else max(goal,self.gain-change)
   output+=np.take(track,np.arange(self.at,self.at+frames),axis=0,mode='wrap')*np.linspace(self.gain,gain,frames,endpoint=False,dtype=np.float32)[:,None]
   self.at=(self.at+frames)%len(track);self.gain=gain
  if self.leaving is not None:
   old,at,gain=self.leaving;lower=max(0.0,gain-frames/RATE/FADE_OUT)
   output+=np.take(old,np.arange(at,at+frames),axis=0,mode='wrap')*np.linspace(gain,lower,frames,endpoint=False,dtype=np.float32)[:,None]
   self.leaving=[old,(at+frames)%len(old),lower] if lower>0 else None
  alive=[]
  for voice in self.voices:
   piece=voice[0][voice[1]:voice[1]+frames];output[:len(piece)]+=piece;voice[1]+=frames
   if voice[1]<len(voice[0]):alive.append(voice)
  self.voices=alive
  return np.clip(output*self.volume,-1,1)
 def callback(self,outdata,frames,timing,status):
  outdata[:]=self.mix(frames)
 def quiet(self):
  return self.gain<=0 and not self.voices and self.leaving is None
 def manage(self):
  """Opens the output only while something can sound, on this thread, because opening a device can take a moment. The Windows audio system needs COM on the thread that opens it."""
  try:ctypes.windll.ole32.CoInitializeEx(None,0)
  except (AttributeError,OSError):pass
  while not self.stop.is_set():
   self.changed.wait(.5 if self.stream is not None else None);self.changed.clear()
   if self.stop.is_set():break
   if self.shown and self.stream is None and not self.broken:self.open()
   elif not self.shown and self.stream is not None and self.quiet():self.shut()
   if self.shown and self.music_on and self.music_wanted:self.load_track()
 def load_track(self):
  """Gets the wanted music ready, on this thread, because decoding takes a moment. A file that will not decode leaves the app's own music playing."""
  wanted=self.wanted_file
  if wanted==self.playing_file:return
  track=self.kept.get(wanted)
  if track is None and wanted:
   try:track=game_track(wanted);self.kept[wanted]=track
   except Exception:track=None
   while len(self.kept)>KEPT_TRACKS:del self.kept[next(iter(self.kept))]
  if track is None:
   if self.own_track is None:self.own_track=music_track()
   track=self.own_track
  self.playing_file=wanted
  if track is not self.track:self.swap=track
 def open(self):
  try:
   device=self.device();self.stream=sd.OutputStream(device=device,samplerate=RATE,channels=2,dtype='float32',blocksize=BLOCK,latency='low',extra_settings=output_settings(device),callback=self.callback);self.stream.start()
  except Exception:self.stream=None;self.broken=True
 def shut(self):
  stream,self.stream=self.stream,None
  if stream is not None:
   try:stream.stop();stream.close()
   except Exception:pass
 def reopen(self):
  """After the audio output changes."""
  self.broken=False;self.shut();self.changed.set()
 def close(self):
  self.stop.set();self.changed.set();self.shut()
