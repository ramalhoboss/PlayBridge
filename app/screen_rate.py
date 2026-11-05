"""Matching the screen's refresh rate to the stream. The PS5 sends 59.94 frames a second. On a 144 or 165 Hz screen some frames then stay up
for two refreshes and some for three, which shows as judder however steady the stream is. At 120 or 60 Hz every frame stays up as long as
the others. Gaming laptops often have such screens, so PlayBridge switches to a steady rate while the stream fills the screen."""
import ctypes,sys
from ctypes import byref,c_long,c_void_p,c_wchar,sizeof
from ctypes import wintypes

STREAM_FPS=60000/1001
SLACK=.005
ENUM_CURRENT=-1;CDS_FULLSCREEN=4;DISP_CHANGE_SUCCESSFUL=0
DM_BITSPERPEL=0x40000;DM_PELSWIDTH=0x80000;DM_PELSHEIGHT=0x100000;DM_DISPLAYFREQUENCY=0x400000

def steady(hz,fps=STREAM_FPS):
 """True when every frame stays up for the same whole number of refreshes. Windows gives whole numbers, 59 for 59.94 Hz and 119 for 119.88,
 so a rate of N stands for anything from N up to N+1. An unknown rate counts as steady, so nothing changes."""
 if not hz:return True
 near=max(1,round(hz/fps))
 return any(hz*(1-SLACK)<=whole*fps<(hz+1)*(1+SLACK) for whole in (near-1,near,near+1) if whole>=1)
def best(modes,current,fps=STREAM_FPS):
 """The fastest steady rate the screen offers at its present size and colour depth, or None where it already runs steady or offers none.
 Modes and the current one are (width, height, bits, hz)."""
 if current is None or steady(current[3],fps):return None
 rates=[mode[3] for mode in modes if mode[:3]==current[:3] and steady(mode[3],fps)]
 return max(rates) if rates else None

class DEVMODE(ctypes.Structure):
 _fields_=[('dmDeviceName',c_wchar*32),('dmSpecVersion',wintypes.WORD),('dmDriverVersion',wintypes.WORD),('dmSize',wintypes.WORD),('dmDriverExtra',wintypes.WORD),
           ('dmFields',wintypes.DWORD),('dmPositionX',c_long),('dmPositionY',c_long),('dmDisplayOrientation',wintypes.DWORD),('dmDisplayFixedOutput',wintypes.DWORD),
           ('dmColor',ctypes.c_short),('dmDuplex',ctypes.c_short),('dmYResolution',ctypes.c_short),('dmTTOption',ctypes.c_short),('dmCollate',ctypes.c_short),
           ('dmFormName',c_wchar*32),('dmLogPixels',wintypes.WORD),('dmBitsPerPel',wintypes.DWORD),('dmPelsWidth',wintypes.DWORD),('dmPelsHeight',wintypes.DWORD),
           ('dmDisplayFlags',wintypes.DWORD),('dmDisplayFrequency',wintypes.DWORD),('dmICMMethod',wintypes.DWORD),('dmICMIntent',wintypes.DWORD),('dmMediaType',wintypes.DWORD),
           ('dmDitherType',wintypes.DWORD),('dmReserved1',wintypes.DWORD),('dmReserved2',wintypes.DWORD),('dmPanningWidth',wintypes.DWORD),('dmPanningHeight',wintypes.DWORD)]
class MONITORINFOEX(ctypes.Structure):
 _fields_=[('cbSize',wintypes.DWORD),('rcMonitor',wintypes.RECT),('rcWork',wintypes.RECT),('dwFlags',wintypes.DWORD),('szDevice',c_wchar*32)]

class Windows:
 """The few display calls this needs."""
 def __init__(self):
  user32=ctypes.windll.user32;self.user32=user32
  user32.MonitorFromWindow.argtypes=[wintypes.HWND,wintypes.DWORD];user32.MonitorFromWindow.restype=c_void_p
  user32.GetMonitorInfoW.argtypes=[c_void_p,c_void_p];user32.GetMonitorInfoW.restype=wintypes.BOOL
  user32.EnumDisplaySettingsExW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,c_void_p,wintypes.DWORD];user32.EnumDisplaySettingsExW.restype=wintypes.BOOL
  user32.ChangeDisplaySettingsExW.argtypes=[wintypes.LPCWSTR,c_void_p,wintypes.HWND,wintypes.DWORD,c_void_p];user32.ChangeDisplaySettingsExW.restype=c_long
 def screen(self,hwnd):
  """The display device that shows this window, such as \\\\.\\DISPLAY1."""
  info=MONITORINFOEX(cbSize=sizeof(MONITORINFOEX))
  if not self.user32.GetMonitorInfoW(self.user32.MonitorFromWindow(hwnd,2),byref(info)):return None
  return info.szDevice
 def mode(self,device,index):
  mode=DEVMODE(dmSize=sizeof(DEVMODE))
  if not self.user32.EnumDisplaySettingsExW(device,index&0xffffffff,byref(mode),0):return None
  return mode
 def current(self,device):
  mode=self.mode(device,ENUM_CURRENT)
  return None if mode is None else (mode.dmPelsWidth,mode.dmPelsHeight,mode.dmBitsPerPel,mode.dmDisplayFrequency)
 def modes(self,device):
  found=[];index=0
  while (mode:=self.mode(device,index)) is not None:found.append((mode.dmPelsWidth,mode.dmPelsHeight,mode.dmBitsPerPel,mode.dmDisplayFrequency));index+=1
  return found
 def switch(self,device,hz):
  """Sets the rate for this app's time only: Windows puts the screen back if the app ends without doing so."""
  mode=self.mode(device,ENUM_CURRENT)
  if mode is None:return False
  mode.dmDisplayFrequency=hz;mode.dmFields=DM_BITSPERPEL|DM_PELSWIDTH|DM_PELSHEIGHT|DM_DISPLAYFREQUENCY
  return self.user32.ChangeDisplaySettingsExW(device,byref(mode),None,CDS_FULLSCREEN,None)==DISP_CHANGE_SUCCESSFUL
 def restore(self,device):
  self.user32.ChangeDisplaySettingsExW(device,None,None,0,None)

class ScreenRate:
 """Switches the window's screen to a steady rate while the stream fills it, and back as soon as it no longer does."""
 def __init__(self,system=None):
  self.system=system if system is not None else (Windows() if sys.platform=='win32' else None)
  # What it found the last time it looked, for the stats: a PC we cannot see then tells why its screen was or was not switched.
  self.changed=None;self.tried=set();self.note=None
 def want(self,on,hwnd):
  """Returns (from Hz, to Hz) when it switches the screen, otherwise None."""
  if self.system is None:return None
  try:
   if not on:
    if self.changed:self.system.restore(self.changed[0]);self.changed=None
    return None
   if self.changed:return None
   device=self.system.screen(hwnd)
   # A screen that refused once is not asked again, so a failing driver cannot make the picture flash every quarter second.
   if not device or device in self.tried:return None
   self.tried.add(device);current=self.system.current(device);hz=best(self.system.modes(device),current)
   if current is None:self.note='Windows did not give the screen mode'
   elif steady(current[3]):self.note=f'{current[3]} Hz already fits 60 fps'
   elif not hz:self.note=f'{current[3]} Hz, and no rate that fits 60 fps at {current[0]}x{current[1]}'
   elif self.system.switch(device,hz):
    self.changed=(device,current[3],hz);self.tried.discard(device);self.note=f'{current[3]} -> {hz} Hz';return current[3],hz
   else:self.note=f'Windows refused {hz} Hz'
  except Exception as error:self.note=f'Could not read the screen: {error}'
  return None
 def label(self):
  """For the stats: the switch in effect, if any."""
  return f'{self.changed[1]} -> {self.changed[2]} Hz' if self.changed else None
