"""A controller on the PC, read with what Windows already has, and the keyboard in the live view. It moves around the grid, and once
"Play on your PS5" is on in Settings it plays: a small companion payload of its own (PlayBridge-Controller.elf, UDP 9078, apart from the
video payload) adds a controller on the PS5 for each PC or phone that sends to it."""
import ctypes,queue,socket,struct,threading,time
from ctypes import wintypes
from typing import NamedTuple
from secure_link import PadLink

PAD_PORT=9078
L3,R3,OPTIONS,UP,RIGHT,DOWN,LEFT,L2,R2,L1,R1=0x2,0x4,0x8,0x10,0x20,0x40,0x80,0x100,0x200,0x400,0x800
TRIANGLE,CIRCLE,CROSS,SQUARE,PS,TOUCHPAD=0x1000,0x2000,0x4000,0x8000,0x10000,0x100000
# The console's Create button is not a game input: here it only stays on the PC, for the way back to the grid.
CREATE=0x1
CONSOLE_BUTTONS=0x0011fffe
TRIGGER_PRESS=30
class PadState(NamedTuple):
 buttons:int=0;lx:int=128;ly:int=128;rx:int=128;ry:int=128;l2:int=0;r2:int=0
NEUTRAL=PadState()
def wire(sequence,state):
 """The packet the payload's controller port reads."""
 return struct.pack('<4sIIBBBBBBH',b'PBP1',sequence&0xffffffff,state.buttons&CONSOLE_BUTTONS,state.lx,state.ly,state.rx,state.ry,state.l2,state.r2,0)
# This PC or phone stops playing: the console side lets go of everything and removes its controller at once. The companion itself
# stays, so the next press plays at once, and ends after ten minutes with no controller in use.
QUIT=b'PBQ1'+bytes(4)
# Asks whether a companion runs, without making a controller: what a new companion sends when it finds the port taken.
PROBE=b'PBH1'+bytes(4)
# The console side answers the controller packets with where it stands, so the app can say when it is not there. It is never waited for:
# 'PBS2', the state, an error code, the newest sequence it took and which of its controllers is this PC's (1 to 4, 0 before it has one).
# Each PC or phone gets a controller of its own, up to the four a PS5 takes.
STATUS_MAGIC=b'PBS2';STATUS_SIZE=20
STARTING,READY,FAILED=0,1,2
LINK_STATES=('starting','ready','failed')
# The console side's own code for "four controllers are in use already".
PAD_FULL=0x50420005
def status_wire(state,error,sequence,player=1):return struct.pack('<4sIiII',STATUS_MAGIC,state,error,sequence&0xffffffff,player)
def read_status(data):
 """(state, error, newest sequence, player) from the console side's answer, or None for anything else."""
 if len(data)!=STATUS_SIZE or data[:4]!=STATUS_MAGIC:return None
 return struct.unpack_from('<IiII',data,4)
XINPUT_BUTTONS=((0x1,UP),(0x2,DOWN),(0x4,LEFT),(0x8,RIGHT),(0x10,OPTIONS),(0x20,CREATE),(0x40,L3),(0x80,R3),(0x100,L1),(0x200,R1),(0x400,PS),(0x1000,CROSS),(0x2000,CIRCLE),(0x4000,SQUARE),(0x8000,TRIANGLE))
def from_xinput(buttons,left_trigger,right_trigger,lx,ly,rx,ry):
 """Xbox layout: sticks count upward from -32768, the console's count downward from 0."""
 bits=sum(bit for mask,bit in XINPUT_BUTTONS if buttons&mask)
 if left_trigger>=TRIGGER_PRESS:bits|=L2
 if right_trigger>=TRIGGER_PRESS:bits|=R2
 return PadState(bits,(lx+32768)>>8,255-((ly+32768)>>8),(rx+32768)>>8,255-((ry+32768)>>8),left_trigger,right_trigger)
JOYSTICK_BUTTONS=(SQUARE,CROSS,CIRCLE,TRIANGLE,L1,R1,L2,R2,CREATE,OPTIONS,L3,R3,PS,TOUCHPAD)
def pov_bits(pov):
 """A hat reads hundredths of a degree, or 65535 at rest."""
 if pov>=36000:return 0
 bits=0
 if pov>=31500 or pov<=4500:bits|=UP
 if 4500<=pov<=13500:bits|=RIGHT
 if 13500<=pov<=22500:bits|=DOWN
 if 22500<=pov<=31500:bits|=LEFT
 return bits
def from_joystick(buttons,pov,x,y,z,r,u,v):
 """DualSense and DualShock 4 as Windows reports them, with axes from 0 to 65535."""
 bits=sum(bit for index,bit in enumerate(JOYSTICK_BUTTONS) if buttons>>index&1)|pov_bits(pov)
 return PadState(bits,x>>8,y>>8,z>>8,r>>8,u>>8,v>>8)

# The keyboard in the live view, as a controller. Names are what the window reports; nothing here clashes with PlayBridge's own keys
# (F6 to F11, Escape and the Ctrl shortcuts). Opposite stick keys held together cancel out.
KEY_BUTTONS={'up':UP,'down':DOWN,'left':LEFT,'right':RIGHT,'enter':CROSS,'space':CROSS,'backspace':CIRCLE,'q':SQUARE,'e':TRIANGLE,
 '1':L1,'2':L2,'3':R1,'4':R2,'f':L3,'h':R3,'tab':OPTIONS,'t':TOUCHPAD,'home':PS}
KEY_STICKS={'a':(1,0),'d':(1,255),'w':(2,0),'s':(2,255),'j':(3,0),'l':(3,255),'i':(4,0),'k':(4,255)}
KEY_NAMES=frozenset(KEY_BUTTONS)|frozenset(KEY_STICKS)
KEYBOARD_HELP='W A S D left stick · I J K L right stick · arrows D-pad · Enter or Space ✕ · Backspace ○ · Q □ · E △ · 1 L1 · 2 L2 · 3 R1 · 4 R2 · F L3 · H R3 · Tab Options · T touch pad · Home PS'
class Keyboard:
 """The keys held in the live view. The window's thread presses and releases; the controller thread reads."""
 # After the last key, the keyboard counts as in use this long, so the controller thread does not stop to look for a pad meanwhile.
 USED=10.0
 def __init__(self):self.held=set();self.lock=threading.Lock();self.used_at=None
 def press(self,name,now):
  if name not in KEY_NAMES:return False
  with self.lock:self.held.add(name);self.used_at=now
  return True
 def release(self,name,now):
  if name not in KEY_NAMES:return False
  with self.lock:self.held.discard(name);self.used_at=now
  return True
 def clear(self):
  """Everything let go, as when the window loses focus: a key released elsewhere is never reported."""
  with self.lock:self.held.clear()
 def in_use(self,now):
  with self.lock:return bool(self.held) or (self.used_at is not None and now-self.used_at<self.USED)
 def state(self):
  with self.lock:held=set(self.held)
  values=[0,128,128,128,128,0,0]
  for name in held:values[0]|=KEY_BUTTONS.get(name,0)
  for name,(field,value) in KEY_STICKS.items():
   if name in held:values[field]=value if values[field]==128 else 128
  if values[0]&L2:values[5]=255
  if values[0]&R2:values[6]=255
  return PadState(*values)
def merge(pad_state,keys):
 """A controller and the keyboard at once: buttons from both, each stick from whichever is pushed, the deeper trigger."""
 sticks=[k if k!=128 else p for p,k in zip(pad_state[1:5],keys[1:5])]
 return PadState(pad_state.buttons|keys.buttons,*sticks,max(pad_state.l2,keys.l2),max(pad_state.r2,keys.r2))

class Navigator:
 """Turns a controller's state into grid moves: a press moves once and a held direction repeats."""
 FIRST=.4;REPEAT=.14
 BUTTONS=((UP,'up'),(DOWN,'down'),(LEFT,'left'),(RIGHT,'right'),(CROSS,'accept'),(CIRCLE,'back'),(L1,'previous'),(R1,'next'),(SQUARE,'refresh'))
 def __init__(self):self.held={}
 def update(self,state,now):
  active={name for bit,name in self.BUTTONS if state.buttons&bit}
  if state.ly<64:active.add('up')
  elif state.ly>192:active.add('down')
  if state.lx<64:active.add('left')
  elif state.lx>192:active.add('right')
  events=[]
  for name in active:
   due=self.held.get(name)
   if due is None:events.append(name);self.held[name]=now+self.FIRST
   elif now>=due and name in ('up','down','left','right'):events.append(name);self.held[name]=now+self.REPEAT
  for name in set(self.held)-active:del self.held[name]
  return events
class HomeCombo:
 """Holding Options and Create leaves the game's video, on controllers without a usable PS button too."""
 HOLD=1.0
 def __init__(self):self.since=None
 def update(self,state,now):
  if state.buttons&OPTIONS and state.buttons&CREATE:
   if self.since is None:self.since=now
   elif self.since is not False and now-self.since>=self.HOLD:self.since=False;return True
  else:self.since=None
  return False

class XINPUT_GAMEPAD(ctypes.Structure):
 _fields_=[('buttons',wintypes.WORD),('left_trigger',ctypes.c_ubyte),('right_trigger',ctypes.c_ubyte),('lx',ctypes.c_short),('ly',ctypes.c_short),('rx',ctypes.c_short),('ry',ctypes.c_short)]
class XINPUT_STATE(ctypes.Structure):
 _fields_=[('packet',wintypes.DWORD),('pad',XINPUT_GAMEPAD)]
class JOYINFOEX(ctypes.Structure):
 _fields_=[(name,wintypes.DWORD) for name in ('size','flags','x','y','z','r','u','v','buttons','number','pov','reserved1','reserved2')]
class WindowsPads:
 """XInput first, then the older joystick API, which is where a DualSense appears without extra drivers."""
 def __init__(self):
  self.read_xinput=None;self.joystick=None;self.source=None;self.state=XINPUT_STATE();self.info=JOYINFOEX(size=ctypes.sizeof(JOYINFOEX),flags=0xff)
  for name in ('xinput1_4','xinput9_1_0'):
   try:library=ctypes.WinDLL(name)
   except OSError:continue
   # Ordinal 100 is the same call with the Guide button included.
   try:self.read_xinput=library[100]
   except (AttributeError,OSError,ValueError):self.read_xinput=getattr(library,'XInputGetState',None)
   break
  try:self.joystick=ctypes.WinDLL('winmm').joyGetPosEx
  except (OSError,AttributeError):pass
 def find(self):
  """The first connected controller. It can take a while with nothing attached, so the caller does this rarely."""
  for index in range(4):
   if self.read_xinput is not None and self.read_xinput(index,ctypes.byref(self.state))==0:self.source=('xinput',index);return 'Xbox controller'
  for index in range(16):
   if self.joystick is not None and self.joystick(index,ctypes.byref(self.info))==0:self.source=('joystick',index);return 'Controller'
  self.source=None;return ''
 def read(self):
  """The current state, or None once the controller is gone."""
  if self.source is None:return None
  kind,index=self.source
  if kind=='xinput':
   if self.read_xinput(index,ctypes.byref(self.state))!=0:self.source=None;return None
   p=self.state.pad;return from_xinput(p.buttons,p.left_trigger,p.right_trigger,p.lx,p.ly,p.rx,p.ry)
  if self.joystick(index,ctypes.byref(self.info))!=0:self.source=None;return None
  i=self.info;return from_joystick(i.buttons,i.pov,i.x&0xffff,i.y&0xffff,i.z&0xffff,i.r&0xffff,i.u&0xffff,i.v&0xffff)

STICK_REST=32
def at_rest(state):
 """A controller nobody is touching: no button the console sees, sticks near the middle (a worn stick drifts a little) and
 triggers up. Only something else counts as use, so a pad lying on the table never adds a controller on the PS5."""
 return not state.buttons&CONSOLE_BUTTONS and all(abs(v-128)<STICK_REST for v in state[1:5]) and state.l2<TRIGGER_PRESS and state.r2<TRIGGER_PRESS

class PadBridge:
 """Reads the controller on its own thread. On the grid it navigates; over the video it plays.
 This PC's controller is on the PS5 only while it is in use: it joins with the first press in the live view and leaves at once when
 the live view closes or after two minutes with nothing pressed. A controller left on the PS5 holds the user in front's seat and can
 keep their own DualSense from connecting. attached: "Play on your PS5" is on and the console is connected; then the companion is
 sent once nothing answers, so the first press plays at once. sending: the live view is showing."""
 # Read every 4 ms, as often as a DualSense reports. A wait on an Event rounds up to Windows' 15.6 ms timer (measured: 8 ms asked,
 # 15.6 ms waited), so the short wait is a sleep, which Python makes on a high-resolution timer.
 INTERVAL=.004;KEEP_ALIVE=.05;LOOK_AGAIN=3
 # Without an answer for this long while the controller plays, the console side is taken as not there.
 SILENT=2.0
 # With nothing pressed for this long in the live view, this PC's controller leaves the PS5; the next press brings it back.
 IDLE=120.0
 # The leave message goes twice: a lost one would leave the controller there until the companion's 90 s silence limit.
 QUIT_COPIES=2
 # While attached and not playing, whether a companion runs is asked this often. Asking makes no controller and does not keep an
 # idle companion from ending.
 PROBE_EVERY=1.0
 # The companion is sent at most this many times in a row, this far apart: one that fails says why, and resending it every few
 # seconds would only fill the PS5 with processes. Once one has started well, it may be sent again after it ends.
 COMPANION_TRIES=2;COMPANION_AGAIN=60.0
 def __init__(self,host,stop,pads=None,companion=None,send_elf=None,wanted=None,key=None):
  # The datagrams to the companion: sealed once it proves it holds this PC's key (key() gives it), as they are for one without.
  self.wire_link=PadLink(key)
  # reach(host, port): where the companion's port is from here (away from home, through the way Settings keeps). away(): this PC is away,
  # so nothing can be sent to the loader.
  self.reach=lambda host,port:(host,port);self.away=lambda:False
  self.host=host;self.stop=stop;self.pads=pads;self.events=queue.SimpleQueue();self.name='';self.sending=False;self.navigating=False;self.ps_leaves=False
  self.navigator=Navigator();self.combo=HomeCombo();self.sequence=0;self.sent=None;self.sent_at=0;self.pressed=0;self.thread=None
  self.live=False;self.playing=False;self.joined=False;self.used_at=None;self.since=0.0;self.answer=None;self.heard_at=None
  self.keyboard=Keyboard();self.keys_on=False;self.attached=False;self.attached_at=None;self.warm=False;self.missing_since=None;self.probed_at=None
  # companion: the ELF's bytes, or None when it is missing. send_elf(host, data): the loader on 9021. wanted(now): a phone plays.
  self.companion=companion;self.send_elf=send_elf;self.wanted=wanted;self.companion_tries=0;self.companion_at=None;self.companion_note=''
  # The last reading, so a page can follow the right stick without taking any of its events.
  self.state=NEUTRAL;self.presses=0
  # The mouse while you aim (mouse_aim.MouseAim), set by the window: it plays with the keyboard.
  self.mouse=None
  # The game's controller profile (pad_profiles.apply bound to it), set by the window; None plays the controller as it is.
  self.change=None
 def start(self):
  self.thread=threading.Thread(target=self.run,name='PlayBridge controller',daemon=True);self.thread.start()
 def run(self):
  if self.pads is None:self.pads=WindowsPads()
  looked=None
  with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
   # Never blocks: the answers are read when they are there, and sending does not wait for them.
   udp.setblocking(False)
   while not self.stop.is_set():
    now=time.monotonic();self.listen(udp,now);self.watch_companion(now,udp)
    state=self.pads.read()
    if state is None:
     # Looking for a controller can take a while with none attached, so it is done rarely, and never while the keyboard plays.
     if not (self.keys_on and (self.keyboard.in_use(now) or (self.mouse is not None and self.mouse.in_use(now)))) and (looked is None or now-looked>=self.LOOK_AGAIN):
      looked=now;self.name=self.pads.find()
      if self.name:continue
     self.name=''
     if not self.keys_on:
      # A controller unplugged while it played: its controller on the PS5 leaves too.
      if self.playing:self.playing=False;self.used_at=None;self.quit(udp)
      self.stop.wait(self.PROBE_EVERY if self.attached else self.LOOK_AGAIN);continue
     state=NEUTRAL
    if self.keys_on:
     state=merge(state,self.keyboard.state())
     if self.mouse is not None:state=merge(state,self.mouse.state())
    self.step(state,time.monotonic(),udp)
    # With only the keyboard, off the live view, there is nothing to read quickly.
    wait=self.INTERVAL if self.name or self.sending else .25
    if wait<.02:time.sleep(wait)
    else:self.stop.wait(wait)
   self.quit(udp)
 def step(self,state,now,udp):
  self.state=state;live=self.sending and not self.navigating
  # Leaving the live view lets go of the keyboard, and this PC's controller leaves the PS5 below: the next press there brings it back.
  if self.live and not live:self.keyboard.clear();self.used_at=None
  self.live=live
  ps_pressed=state.buttons&PS and not self.pressed&PS
  # Buttons that went down while playing, counted for a recording's highlights.
  fresh=state.buttons&~self.pressed
  if live and fresh:self.presses+=bin(fresh).count('1')
  self.pressed=state.buttons
  if self.combo.update(state,now):self.events.put('leave')
  if self.navigating:
   for event in self.navigator.update(state,now):self.events.put(event)
   if ps_pressed:self.events.put('leave')
  elif self.ps_leaves:
   if ps_pressed:self.events.put('leave')
   state=state._replace(buttons=state.buttons&~PS)
  change=self.change
  if live and change is not None:state=change(state,now)
  # Create held is the way back to the grid being reached for, which is no reason to add a controller on the PS5.
  if live and not at_rest(state) and not state.buttons&CREATE:self.used_at=now
  playing=live and self.used_at is not None and now-self.used_at<self.IDLE
  if playing and not self.playing:self.since=now
  if self.playing and not playing:self.quit(udp)
  self.playing=playing
  if playing and (state!=self.sent or now-self.sent_at>=self.KEEP_ALIVE):self.send(state,now,udp)
 def send(self,state,now,udp):
  if not self.put(udp,wire(self.sequence,state)):return
  self.sequence+=1;self.sent=state;self.sent_at=now;self.joined=True
 def put(self,udp,data):
  """Sends data to the companion, sealed when it holds this PC's key. False when the network refused it."""
  try:
   for datagram in self.wire_link.datagrams(data):udp.sendto(datagram,self.reach(self.host(),PAD_PORT))
  except OSError:return False
  return True
 def quit(self,udp):
  """This PC's controller leaves the PS5 at once. Nothing neutral goes first: the companion lets go of what was held itself, and a
  state arriving after the leave message would only make a new controller."""
  if not self.joined:return
  for _ in range(self.QUIT_COPIES):self.put(udp,QUIT)
  self.joined=False;self.sent=None
 def watch_companion(self,now,udp):
  """Sends the companion when one is needed and nothing answers: just after attaching, so the first press plays at once, and
  whenever this PC or a phone plays. It never waits: the loader is reached on its own thread. Once no longer attached, this PC's
  controller leaves the PS5 at once."""
  if not self.attached:
   if self.attached_at is not None:self.playing=False;self.used_at=None;self.quit(udp)
   self.attached_at=None;self.warm=False;self.missing_since=None;self.probed_at=None;self.companion_tries=0;self.companion_at=None;return
  if self.attached_at is None:self.attached_at=now;self.warm=True
  if not self.playing and (self.probed_at is None or now-self.probed_at>=self.PROBE_EVERY):
   self.probed_at=now;self.put(udp,PROBE)
  if self.wire_link.foreign:self.companion_note='The controller payload on your PS5 was sent by another PC. It ends after ten minutes without use.'
  if self.heard_at is not None and now-self.heard_at<=self.SILENT:
   self.warm=False;self.missing_since=None
   if self.answer[0]==READY:self.companion_tries=0
   return
  if not (self.warm or self.playing or (self.wanted is not None and self.wanted(now))):self.missing_since=None;return
  if self.missing_since is None:self.missing_since=now
  if not self.wants_companion(now):return
  if self.away():
   self.companion_note='Away from home the controller payload cannot be sent: it goes when away play is turned on at home.';self.companion_at=now;return
  data=self.companion() if self.companion else None
  self.companion_tries+=1;self.companion_at=now;self.warm=False
  if not data:self.companion_note='PlayBridge-Controller.elf is missing. Reinstall the complete PlayBridge package.';return
  host=self.host();self.companion_note='Sending the controller payload…'
  def send():
   try:self.send_elf(host,data);self.companion_note='Controller payload sent.'
   except (OSError,ValueError) as error:self.companion_note=f'The controller payload could not be sent: {error}'
  threading.Thread(target=send,name='PlayBridge controller payload',daemon=True).start()
 def wants_companion(self,now):
  if self.send_elf is None or self.missing_since is None or now-self.missing_since<self.SILENT:return False
  if self.companion_tries>=self.COMPANION_TRIES:return False
  return self.companion_at is None or now-self.companion_at>=self.COMPANION_AGAIN
 def listen(self,udp,now):
  """Takes the console side's answers that are waiting, without waiting for any."""
  for _ in range(32):
   # 128: the companion's answer to a hello is 68 bytes, and Windows drops a datagram larger than the read.
   try:data,_=udp.recvfrom(128)
   except (BlockingIOError,InterruptedError):return
   # Windows reports a closed port on the console as an error on the next read; the reads after it go on.
   except OSError:continue
   data=self.wire_link.take(data)
   answer=read_status(data) if data is not None else None
   if answer is not None:self.answer=answer;self.heard_at=now
 def player(self):
  """Which of the console's controllers is this PC's, 1 to 4, or 0 before it has one."""
  return self.answer[3] if self.answer else 0
 def link(self,now):
  """Where the console side stands while the controller plays: off, waiting, starting, ready, refused, full, failed or unavailable.
  Refused is ready with an error: the console turned down the last state it was given. Full: four controllers are in use already."""
  if not self.playing:return 'off'
  if self.heard_at is not None and now-self.heard_at<=self.SILENT:
   state,error,_,_=self.answer
   if state==READY and error:return 'refused'
   if state==FAILED and error&0xffffffff==PAD_FULL:return 'full'
   return LINK_STATES[state] if state<len(LINK_STATES) else 'unavailable'
  return 'waiting' if now-self.since<self.SILENT else 'unavailable'
