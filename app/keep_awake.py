"""Keeps the screen on while a PS5 session runs, as a video player does. Playing with the controller in hand never touches the PC,
so without this Windows turned the display off after its idle time, and later could put the PC to sleep in the middle of a game. It also says when the battery is what holds the picture back."""
import ctypes,sys

ES_CONTINUOUS=0x80000000;ES_SYSTEM_REQUIRED=0x00000001;ES_DISPLAY_REQUIRED=0x00000002
AWAKE=ES_CONTINUOUS|ES_SYSTEM_REQUIRED|ES_DISPLAY_REQUIRED;RELEASED=ES_CONTINUOUS

def windows_call():
 """SetThreadExecutionState, or None away from Windows."""
 if sys.platform!='win32':return None
 call=ctypes.windll.kernel32.SetThreadExecutionState;call.argtypes=[ctypes.c_uint32];call.restype=ctypes.c_uint32
 return call

class PowerStatus(ctypes.Structure):
 _fields_=[('ACLineStatus',ctypes.c_ubyte),('BatteryFlag',ctypes.c_ubyte),('BatteryLifePercent',ctypes.c_ubyte),('SystemStatusFlag',ctypes.c_ubyte),('BatteryLifeTime',ctypes.c_uint32),('BatteryFullLifeTime',ctypes.c_uint32)]
def on_battery():
 """True on a laptop running from its battery. False on mains power, on a PC without a battery, or when Windows cannot say."""
 if sys.platform!='win32':return False
 status=PowerStatus()
 try:
  if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):return False
 except (AttributeError,OSError):return False
 return status.ACLineStatus==0

HINT='This laptop is on battery, so Windows slows it down and frames are being lost. Plug it in for a smooth picture.'
class BatteryHint:
 """The battery is something the app cannot fix, so it says so: once a session, and only after frames have fallen short for a few seconds
 in a row while on battery, never just because a laptop is unplugged."""
 def __init__(self,check=on_battery,seconds=5):
  self.check=check;self.seconds=seconds;self.short=0;self.told=False;self.on=False
 def second(self,linked,shown_fps,wanted_fps):
  """Called once a second. Returns the hint the one time it is due."""
  self.on=bool(self.check())
  if not linked:self.short=0;self.told=False;return None
  self.short=self.short+1 if self.on and shown_fps<wanted_fps*.9 else 0
  if self.short>=self.seconds and not self.told:self.told=True;return HINT
  return None

class KeepAwake:
 """Tells Windows only when the wish changes. The request belongs to the thread that makes it, so it is always made from the window's thread,
 and it ends by itself when that thread ends."""
 def __init__(self,call=None):
  self.call=windows_call() if call is None else call;self.on=False
 def want(self,on):
  on=bool(on)
  if on==self.on:return
  self.on=on
  if self.call is None:return
  try:self.call(AWAKE if on else RELEASED)
  except Exception:pass
