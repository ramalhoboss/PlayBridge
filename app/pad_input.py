"""A controller on the PC, read with what Windows already has. It moves around the grid, and is sent to the console over the video once the console can take it."""
import ctypes,queue,socket,struct,threading,time
from ctypes import wintypes
from typing import NamedTuple

PAD_PORT=9078
# Matches VIRTUAL_PAD_ENABLED in the payload, which leaves this off until the console's controller service can be started from it.
CONSOLE_PAD_READY=False
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

class PadBridge:
 """Reads the controller on its own thread. On the grid it navigates; over the video it plays."""
 INTERVAL=.008;KEEP_ALIVE=.05;LOOK_AGAIN=3
 def __init__(self,host,stop,pads=None):
  self.host=host;self.stop=stop;self.pads=pads;self.events=queue.SimpleQueue();self.name='';self.sending=False;self.navigating=False;self.ps_leaves=False
  self.navigator=Navigator();self.combo=HomeCombo();self.sequence=0;self.sent=None;self.sent_at=0;self.pressed=0;self.thread=None
 def start(self):
  self.thread=threading.Thread(target=self.run,name='PlayBridge controller',daemon=True);self.thread.start()
 def run(self):
  if self.pads is None:self.pads=WindowsPads()
  with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
   while not self.stop.is_set():
    state=self.pads.read()
    if state is None:
     self.name=self.pads.find()
     if not self.name:self.stop.wait(self.LOOK_AGAIN)
     continue
    self.step(state,time.monotonic(),udp)
    self.stop.wait(self.INTERVAL)
 def step(self,state,now,udp):
  ps_pressed=state.buttons&PS and not self.pressed&PS;self.pressed=state.buttons
  if self.combo.update(state,now):self.events.put('leave')
  if self.navigating:
   for event in self.navigator.update(state,now):self.events.put(event)
   if ps_pressed:self.events.put('leave')
   return
  if self.ps_leaves:
   if ps_pressed:self.events.put('leave')
   state=state._replace(buttons=state.buttons&~PS)
  if self.sending and (state!=self.sent or now-self.sent_at>=self.KEEP_ALIVE):self.send(state,now,udp)
 def send(self,state,now,udp):
  try:udp.sendto(wire(self.sequence,state),(self.host(),PAD_PORT))
  except OSError:return
  self.sequence+=1;self.sent=state;self.sent_at=now
