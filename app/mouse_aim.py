"""The mouse in the live view as the right stick, for aiming. Click the picture to aim: the pointer hides and stays put, and the mouse's
own movement moves the right stick; Escape, or leaving the window, lets go. The mouse is read with Windows' Raw Input, as the counts the
mouse itself reports, without the pointer's acceleration, and only while you aim.
A stick says how fast to turn, a mouse how far it moved, so the stick follows how fast the mouse moves: the counts of the last few
milliseconds. Games bend their stick (a small push turns much slower than half of a full one) and ignore a small push altogether, so each
game keeps its own settings for that: how fast, the game's own curve, which is undone so turning follows the mouse evenly, and its dead
zone, which the stick jumps past as soon as the mouse moves."""
import collections,ctypes,json,math,struct,sys,threading,time
from pathlib import Path
import pad_input as pads

# Mouse counts a second that push the stick all the way at sensitivity 1: a brisk sweep with an 800 DPI mouse.
FULL_SPEED=4000.0
# The counts of this many last seconds make the stick's position: a few reports even from a 125 Hz mouse, and little delay.
WINDOW=.02
DEFAULTS=dict(sensitivity=1.0,curve=1.0,deadzone=.1,invert=False)
LIMITS=dict(sensitivity=(.1,5.0),curve=(1.0,3.0),deadzone=(0.0,.4))
# Raw Input's button flags: (pressed, let go, which).
MOUSE_BUTTONS=((0x1,0x2,'left'),(0x4,0x8,'right'),(0x10,0x20,'middle'),(0x40,0x80,'back'),(0x100,0x200,'forward'))
# What each button presses: the triggers, where shooters fire and aim, the right stick's click and the shoulder buttons.
PRESSES={'left':pads.R2,'right':pads.L2,'middle':pads.R3,'back':pads.L1,'forward':pads.R1}
MOUSE_HELP='Left button R2 · right button L2 · middle R3 · side buttons L1 and R1'

def clean(profile):
 """A game's aim settings within their limits, with the defaults for anything missing or odd."""
 out=dict(DEFAULTS)
 if isinstance(profile,dict):
  for name,(low,high) in LIMITS.items():
   value=profile.get(name)
   if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value):out[name]=min(high,max(low,float(value)))
  if isinstance(profile.get('invert'),bool):out['invert']=profile['invert']
 return out

def axis(value):return max(0,min(255,round(127.5+127.5*value)))

def stick(vx,vy,profile):
 """Where the right stick points for a mouse moving at (vx, vy) counts a second, right and down: (rx, ry), 0 to 255, 128 at rest."""
 speed=math.hypot(vx,vy)
 if speed<=0:return 128,128
 push=min(1.0,speed*profile['sensitivity']/FULL_SPEED)
 # The game's curve undone, then past its dead zone.
 push=profile['deadzone']+(1-profile['deadzone'])*push**(1/profile['curve'])
 x,y=vx/speed*push,vy/speed*push
 return axis(x),axis(-y if profile['invert'] else y)

class MouseAim:
 """The mouse while you aim: the raw input thread adds its counts and buttons, the controller thread reads a controller state."""
 def __init__(self,clock=time.monotonic):
  self.clock=clock;self.lock=threading.Lock();self.moves=collections.deque();self.held=set();self.on=False;self.profile=dict(DEFAULTS);self.used_at=None
 def start(self,profile):
  with self.lock:self.on=True;self.profile=clean(profile);self.moves.clear();self.held.clear();self.used_at=self.clock()
 def stop(self):
  with self.lock:self.on=False;self.moves.clear();self.held.clear()
 def set_profile(self,profile):
  with self.lock:self.profile=clean(profile)
 def move(self,dx,dy):
  now=self.clock()
  with self.lock:
   if not self.on:return
   self.moves.append((now,dx,dy));self.used_at=now
 def buttons(self,flags):
  with self.lock:
   if not self.on:return
   for down,up,name in MOUSE_BUTTONS:
    if flags&down:self.held.add(name)
    elif flags&up:self.held.discard(name)
   if flags:self.used_at=self.clock()
 def in_use(self,now):
  with self.lock:return self.on and (bool(self.held) or (self.used_at is not None and now-self.used_at<pads.Keyboard.USED))
 def state(self,now=None):
  """The right stick and the buttons held, as a controller with nothing else on it."""
  now=self.clock() if now is None else now
  with self.lock:
   if not self.on:return pads.NEUTRAL
   while self.moves and now-self.moves[0][0]>WINDOW:self.moves.popleft()
   dx=sum(m[1] for m in self.moves);dy=sum(m[2] for m in self.moves);held=set(self.held);profile=self.profile
  rx,ry=stick(dx/WINDOW,dy/WINDOW,profile);buttons=0
  for name in held:buttons|=PRESSES[name]
  return pads.PadState(buttons,128,128,rx,ry,255 if buttons&pads.L2 else 0,255 if buttons&pads.R2 else 0)

class AimProfiles:
 """Each game's own aim settings, kept on this PC, and the ones for every game without its own (under '')."""
 def __init__(self,path):
  self.path=Path(path);self.saved={}
  try:saved=json.loads(self.path.read_text(encoding='utf-8'))
  except (OSError,ValueError):saved={}
  if isinstance(saved,dict):self.saved={str(title):clean(profile) for title,profile in saved.items() if isinstance(profile,dict)}
 def get(self,title):return clean(self.saved.get(title or '') or self.saved.get(''))
 def own(self,title):return bool(title) and title in self.saved
 def set(self,title,**changes):
  profile=self.get(title);profile.update(changes);self.saved[title or '']=clean(profile);return self.saved[title or '']
 def save(self):
  try:
   self.path.parent.mkdir(parents=True,exist_ok=True);temporary=self.path.with_suffix('.tmp')
   temporary.write_text(json.dumps(self.saved,indent=1),encoding='utf-8');temporary.replace(self.path)
  except OSError:pass

# ---- Windows: Raw Input on a message window of its own thread, and the pointer kept in one place.
RIM_TYPEMOUSE=0;MOUSE_MOVE_ABSOLUTE=1
HEADER=8+2*ctypes.sizeof(ctypes.c_void_p)
def read_raw(data,header=HEADER):
 """A mouse's report as Raw Input gives it: (button flags, dx, dy), or None for another device. A pen or a remote desktop reports
 where it is, not how far it moved, which says nothing about aiming: its buttons count, its position does not."""
 if len(data)<header+24 or struct.unpack_from('<I',data,0)[0]!=RIM_TYPEMOUSE:return None
 flags,button_flags,_,_,dx,dy=struct.unpack_from('<H2xHhIii',data,header)
 if flags&MOUSE_MOVE_ABSOLUTE:dx=dy=0
 return button_flags,dx,dy

class RawMouse:
 """Reads the mouse for MouseAim while you aim. owner(): the window that must be in front for anything to count."""
 WM_INPUT=0x00FF;WM_CLOSE=0x0010;WM_DESTROY=0x0002;WM_START=0x8001;WM_STOP=0x8002
 RIDEV_REMOVE=0x1;RIDEV_INPUTSINK=0x100;RID_INPUT=0x10000003
 def __init__(self,aim,owner):
  self.aim=aim;self.owner=owner;self.thread=None;self.hwnd=None;self.ready=threading.Event();self.registered=False;self.error=''
 def begin(self):
  """The message window, once. False where Windows does not give one."""
  if self.thread is None:
   self.thread=threading.Thread(target=self._run,name='PlayBridge mouse',daemon=True);self.thread.start()
  self.ready.wait(2);return bool(self.hwnd)
 def start(self):return bool(self.hwnd) and bool(self.user32.PostMessageW(self.hwnd,self.WM_START,0,0))
 def stop(self):
  if self.hwnd:self.user32.PostMessageW(self.hwnd,self.WM_STOP,0,0)
 def close(self):
  if self.hwnd:self.user32.PostMessageW(self.hwnd,self.WM_CLOSE,0,0)
 def _register(self,on,hwnd):
  from ctypes import wintypes
  class DEVICE(ctypes.Structure):_fields_=[('usUsagePage',wintypes.USHORT),('usUsage',wintypes.USHORT),('dwFlags',wintypes.DWORD),('hwndTarget',wintypes.HWND)]
  device=DEVICE(1,2,self.RIDEV_INPUTSINK if on else self.RIDEV_REMOVE,hwnd if on else None)
  done=bool(self.user32.RegisterRawInputDevices(ctypes.byref(device),1,ctypes.sizeof(DEVICE)))
  if on:self.registered=done
  elif done:self.registered=False
  if not done:self.error=f'Windows refused the mouse ({ctypes.get_last_error()}).'
 def _run(self):
  from ctypes import wintypes
  LRESULT=ctypes.c_ssize_t
  user32=ctypes.WinDLL('user32',use_last_error=True);kernel32=ctypes.WinDLL('kernel32',use_last_error=True);self.user32=user32
  WNDPROC=ctypes.WINFUNCTYPE(LRESULT,wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM)
  class WNDCLASS(ctypes.Structure):
   _fields_=[('style',wintypes.UINT),('lpfnWndProc',WNDPROC),('cbClsExtra',ctypes.c_int),('cbWndExtra',ctypes.c_int),('hInstance',wintypes.HINSTANCE),
    ('hIcon',wintypes.HICON),('hCursor',wintypes.HANDLE),('hbrBackground',wintypes.HBRUSH),('lpszMenuName',wintypes.LPCWSTR),('lpszClassName',wintypes.LPCWSTR)]
  user32.DefWindowProcW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM];user32.DefWindowProcW.restype=LRESULT
  user32.CreateWindowExW.argtypes=[wintypes.DWORD,wintypes.LPCWSTR,wintypes.LPCWSTR,wintypes.DWORD,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.HWND,wintypes.HMENU,wintypes.HINSTANCE,wintypes.LPVOID]
  user32.CreateWindowExW.restype=wintypes.HWND
  user32.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
  user32.GetRawInputData.argtypes=[wintypes.HANDLE,wintypes.UINT,wintypes.LPVOID,ctypes.POINTER(wintypes.UINT),wintypes.UINT];user32.GetRawInputData.restype=wintypes.UINT
  user32.GetForegroundWindow.restype=wintypes.HWND
  user32.GetMessageW.argtypes=[ctypes.POINTER(wintypes.MSG),wintypes.HWND,wintypes.UINT,wintypes.UINT]
  user32.RegisterRawInputDevices.argtypes=[wintypes.LPVOID,wintypes.UINT,wintypes.UINT]
  kernel32.GetModuleHandleW.restype=wintypes.HMODULE
  buffer=ctypes.create_string_buffer(64);size=wintypes.UINT()
  def procedure(hwnd,message,wparam,lparam):
   if message==self.WM_INPUT:
    size.value=len(buffer)
    if user32.GetRawInputData(lparam,self.RID_INPUT,buffer,ctypes.byref(size),HEADER)!=0xFFFFFFFF:
     report=read_raw(buffer.raw[:size.value])
     owner=self.owner()
     if report and owner and user32.GetForegroundWindow()==owner:
      flags,dx,dy=report
      if dx or dy:self.aim.move(dx,dy)
      if flags:self.aim.buttons(flags)
    return user32.DefWindowProcW(hwnd,message,wparam,lparam)
   if message==self.WM_START:self._register(True,hwnd);return 0
   if message==self.WM_STOP:self._register(False,hwnd);return 0
   if message==self.WM_CLOSE:
    if self.registered:self._register(False,hwnd)
    user32.DestroyWindow(hwnd);return 0
   if message==self.WM_DESTROY:user32.PostQuitMessage(0);return 0
   return user32.DefWindowProcW(hwnd,message,wparam,lparam)
  self.procedure=WNDPROC(procedure);instance=kernel32.GetModuleHandleW(None);name=f'PlayBridgeMouse{id(self)}'
  user32.RegisterClassW(ctypes.byref(WNDCLASS(0,self.procedure,0,0,instance,None,None,None,None,name)))
  # A message-only window: never shown, it only hears the mouse.
  self.hwnd=user32.CreateWindowExW(0,name,name,0,0,0,0,0,wintypes.HWND(-3),None,instance,None)
  self.ready.set()
  if not self.hwnd:self.error='Windows gave no window for the mouse.';return
  message=wintypes.MSG()
  while user32.GetMessageW(ctypes.byref(message),None,0,0)>0:
   user32.TranslateMessage(ctypes.byref(message));user32.DispatchMessageW(ctypes.byref(message))
  self.hwnd=None

def hold_pointer(hwnd):
 """Keeps the pointer on one spot in the middle of the window while you aim, so it never wanders onto another window or a button."""
 if sys.platform!='win32':return False
 from ctypes import wintypes
 user32=ctypes.WinDLL('user32',use_last_error=True)
 user32.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)];user32.ClientToScreen.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.POINT)]
 user32.ClipCursor.argtypes=[ctypes.POINTER(wintypes.RECT)];user32.SetCursorPos.argtypes=[ctypes.c_int,ctypes.c_int]
 area=wintypes.RECT()
 if not user32.GetClientRect(hwnd,ctypes.byref(area)):return False
 middle=wintypes.POINT(area.right//2,area.bottom//2)
 if not user32.ClientToScreen(hwnd,ctypes.byref(middle)):return False
 user32.SetCursorPos(middle.x,middle.y)
 return bool(user32.ClipCursor(ctypes.byref(wintypes.RECT(middle.x,middle.y,middle.x+1,middle.y+1))))

def free_pointer():
 if sys.platform!='win32':return
 user32=ctypes.WinDLL('user32',use_last_error=True);user32.ClipCursor.argtypes=[ctypes.c_void_p];user32.ClipCursor(None)
