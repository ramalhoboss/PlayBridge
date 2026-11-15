"""Alert me when: the player asks to be told when something happens on the PS5, and PlayBridge watches for it from real readings only,
then says so on the PC with a Windows notification, the taskbar button flashing and a notice in the window. Each alert is used once:
it turns off when it fires, and the player sets it again.

The picture moves again, for queues, loading screens and match searches. The console's encoder spends its bits on what changes, so
a still screen arrives as frames with little in them, and a moving one as large frames. Keyframes are left out: they carry the whole
picture whatever it shows. The picture counts as still when, for STILL_SECONDS, every second carried about the same and well under
the stream's own rate (a loading screen's turning logo is still in this sense). It moves again when two seconds in a row each carry
several times what the still ones did, and a fair share of the stream's rate.

The game slows down: the console counts the frames the game draws (console_control.GameRate). Under SLOW_SHARE of its usual rate,
the middle of the last minute, for SLOW_SECONDS in a row.

The CPU reaches a temperature: the console's own sensor, as the payload reads it.

A trophy unlocks: the player's own trophy record on the console, read again while the game runs (console_control.watch_trophies)."""
import threading,collections

STILL_SECONDS=8
# A still picture: its busiest second carries at most this many times its usual one, and its usual one under this share of the stream's rate.
STILL_SPREAD=2.5;STILL_SHARE=.25
# Moving again: this many seconds in a row, each carrying this many times the still picture's usual second and this share of the stream's rate.
MOVING_SECONDS=2;MOVING_TIMES=4;MOVING_SHARE=.10
# The least a second of a still picture counts as, so that one with almost nothing in it is not set off by a blinking cursor.
STILL_FLOOR=4096
SLOW_SHARE=.8;SLOW_SECONDS=3
# Quarter-second counts of the game's rate needed before its usual rate is known: ten seconds of them.
USUAL_POINTS=40
HOT_CHOICES=(70,80,90);HOT_DEFAULT=80
KINDS=('moves','slow','hot','trophy')

class MotionMeter:
 """Fed by the receiving thread with each video packet; read once a second by the window."""
 def __init__(self):self.lock=threading.Lock();self.bytes=0;self.frames=0
 def add(self,size,key):
  with self.lock:
   self.frames+=1
   if not key:self.bytes+=size
 def take(self):
  """The bytes of the frames other than keyframes, and the frames, since the last call."""
  with self.lock:taken=(self.bytes,self.frames);self.bytes=0;self.frames=0
  return taken

def middle(values):
 ordered=sorted(values);return ordered[len(ordered)//2]

class Alerts:
 """What the player asked to be told about, and what the readings say about it. second() runs once a second on the window's thread."""
 def __init__(self,hot_at=HOT_DEFAULT):
  self.wanted=dict.fromkeys(KINDS,False);self.hot_at=hot_at if hot_at in HOT_CHOICES else HOT_DEFAULT
  self.seconds=collections.deque(maxlen=STILL_SECONDS+MOVING_SECONDS);self.slow_for=0;self.state=dict.fromkeys(KINDS,'')
 def arm(self,kind,on):
  if kind not in self.wanted:return
  self.wanted[kind]=bool(on);self.state[kind]=''
  if kind=='moves':self.seconds.clear()
  if kind=='slow':self.slow_for=0
 def any(self):return any(self.wanted.values())
 def still(self,seconds,rate):
  """True for seconds of a still picture, as described above, and their usual second."""
  usual=max(STILL_FLOOR,middle(seconds))
  return max(seconds)<=STILL_SPREAD*usual and (rate is None or usual<=STILL_SHARE*rate),usual
 def second(self,motion,rate,linked,view):
  """motion: (bytes other than keyframes, frames) of the last second, from MotionMeter. rate: the stream's own rate in bytes a
  second, or None. view: PerformanceLog.view(). Returns the alerts that fired, as (kind, title, text), and turns them off."""
  fired=[]
  sent,frames=motion
  if not linked or not frames:
   self.seconds.clear();self.state['moves']='Waiting for the picture'
  else:
   self.seconds.append(sent)
   if self.wanted['moves']:fired+=self.check_moves(rate)
  if self.wanted['slow']:fired+=self.check_slow(view)
  if self.wanted['hot']:fired+=self.check_hot(view)
  if self.wanted['trophy']:self.state['trophy']='Watching for the next trophy you earn'
  for kind,_,_ in fired:self.wanted[kind]=False
  return fired
 def trophies(self,game,earned):
  """Trophies just earned in game, as console_control gives them: the alert, when it was asked for, which then turns off."""
  if not self.wanted['trophy']:return []
  self.wanted['trophy']=False;named=[trophy['name'] for trophy in earned if trophy['name']]
  title=f'{len(earned)} trophies earned' if len(earned)>1 else 'Trophy earned: '+named[0] if named else 'Trophy earned'
  return [('trophy',title,f'In {game}.')]
 def check_moves(self,rate):
  seconds=list(self.seconds)
  if len(seconds)<STILL_SECONDS:self.state['moves']='Waiting for the picture to be still';return []
  if len(seconds)==STILL_SECONDS+MOVING_SECONDS:
   before,recent=seconds[:STILL_SECONDS],seconds[STILL_SECONDS:]
   still,usual=self.still(before,rate)
   if still and all(value>=max(MOVING_TIMES*usual,MOVING_SHARE*rate if rate else 0) for value in recent):
    self.seconds.clear();return [('moves','The picture moves again','Something changed on your PS5 screen.')]
  still,_=self.still(seconds[-STILL_SECONDS:],rate)
  self.state['moves']='Watching: the picture is still' if still else 'Waiting for the picture to be still'
  return []
 def check_slow(self,view):
  known=[value for value in view.get('points',[]) if value is not None];fps=view.get('game_fps')
  if fps is None or len(known)<USUAL_POINTS:self.slow_for=0;self.state['slow']="Waiting for the game's frame count";return []
  usual=middle(known);self.slow_for=self.slow_for+1 if fps<SLOW_SHARE*usual else 0
  name=view.get('name') or 'The game'
  if self.slow_for>=SLOW_SECONDS:
   self.slow_for=0;return [('slow',f'{name} slowed down',f'It draws {fps:.0f} frames a second, against its usual {usual:.0f}.')]
  self.state['slow']=f'Watching: usually {usual:.0f} fps, now {fps:.0f}';return []
 def check_hot(self,view):
  status=view.get('status') or {};cpu=status.get('cpu_c')
  if type(cpu) is not int or cpu<=0:self.state['hot']="Waiting for the PS5's temperature";return []
  if cpu>=self.hot_at:return [('hot',f'Your PS5 reached {cpu} °C',f'Its CPU passed the {self.hot_at} °C you set.')]
  self.state['hot']=f'Watching: the CPU is at {cpu} °C';return []
