"""Telling the player something while PlayBridge is not in front: a Windows notification from an icon in the notification area, and
the taskbar button flashing until the window is brought back. Windows only; elsewhere nothing happens. The icon is there only while a
notification shows, and goes once it has had time to be read, so PlayBridge does not sit in the notification area for nothing."""
import ctypes,sys,time
from ctypes import wintypes

NIM_ADD=0;NIM_MODIFY=1;NIM_DELETE=2;NIF_ICON=2;NIF_TIP=4;NIF_INFO=0x10;NIIF_USER=4;NIIF_LARGE_ICON=0x20
IMAGE_ICON=1;LR_LOADFROMFILE=0x10;LR_DEFAULTSIZE=0x40
FLASHW_ALL=3;FLASHW_TIMERNOFG=12
# A notification shows for a few seconds and then waits in the notification centre: the icon stays that long, then goes.
ICON_SECONDS=20

class NotifyIconData(ctypes.Structure):
 _fields_=[('cbSize',wintypes.DWORD),('hWnd',wintypes.HWND),('uID',wintypes.UINT),('uFlags',wintypes.UINT),('uCallbackMessage',wintypes.UINT),
  ('hIcon',wintypes.HICON),('szTip',wintypes.WCHAR*128),('dwState',wintypes.DWORD),('dwStateMask',wintypes.DWORD),('szInfo',wintypes.WCHAR*256),
  ('uVersion',wintypes.UINT),('szInfoTitle',wintypes.WCHAR*64),('dwInfoFlags',wintypes.DWORD),('guidItem',ctypes.c_byte*16),('hBalloonIcon',wintypes.HICON)]
class FlashInfo(ctypes.Structure):
 _fields_=[('cbSize',wintypes.UINT),('hwnd',wintypes.HWND),('dwFlags',wintypes.DWORD),('uCount',wintypes.UINT),('dwTimeout',wintypes.DWORD)]

def libraries():
 """Their own copies, so the argument types set here reach no other module's calls."""
 shell=ctypes.WinDLL('shell32',use_last_error=True);user=ctypes.WinDLL('user32',use_last_error=True)
 shell.Shell_NotifyIconW.argtypes=[wintypes.DWORD,ctypes.POINTER(NotifyIconData)];shell.Shell_NotifyIconW.restype=wintypes.BOOL
 user.LoadImageW.argtypes=[wintypes.HINSTANCE,wintypes.LPCWSTR,wintypes.UINT,ctypes.c_int,ctypes.c_int,wintypes.UINT];user.LoadImageW.restype=wintypes.HANDLE
 user.DestroyIcon.argtypes=[wintypes.HICON];user.DestroyIcon.restype=wintypes.BOOL
 user.FlashWindowEx.argtypes=[ctypes.POINTER(FlashInfo)];user.FlashWindowEx.restype=wintypes.BOOL
 return shell,user

class DesktopNotice:
 def __init__(self,hwnd,icon_path,clock=time.monotonic):
  self.hwnd=hwnd;self.icon_path=str(icon_path);self.clock=clock;self.shown_until=None;self.icon=None
  self.calls=libraries() if sys.platform=='win32' else None
 def data(self,flags):
  data=NotifyIconData(cbSize=ctypes.sizeof(NotifyIconData),hWnd=self.hwnd,uID=1,uFlags=flags,hIcon=self.icon)
  data.szTip='PlayBridge';return data
 def show(self,title,text):
  """A notification now, and the taskbar button flashing until the window comes to the front. False where it could not be shown."""
  if self.calls is None:return False
  shell,user=self.calls
  user.FlashWindowEx(ctypes.byref(FlashInfo(ctypes.sizeof(FlashInfo),self.hwnd,FLASHW_ALL|FLASHW_TIMERNOFG,0,0)))
  if self.icon is None:self.icon=user.LoadImageW(None,self.icon_path,IMAGE_ICON,0,0,LR_LOADFROMFILE|LR_DEFAULTSIZE) or None
  if self.shown_until is None:
   if not shell.Shell_NotifyIconW(NIM_ADD,ctypes.byref(self.data(NIF_ICON|NIF_TIP))):return False
  data=self.data(NIF_ICON|NIF_TIP|NIF_INFO);data.szInfoTitle=title[:63];data.szInfo=text[:255];data.dwInfoFlags=(NIIF_USER|NIIF_LARGE_ICON) if self.icon else 0
  done=bool(shell.Shell_NotifyIconW(NIM_MODIFY,ctypes.byref(data)));self.shown_until=self.clock()+ICON_SECONDS;return done
 def tick(self):
  """Once a second: the icon goes once its notification has been up long enough."""
  if self.shown_until is not None and self.clock()>=self.shown_until:self.remove()
 def remove(self):
  if self.calls is None or self.shown_until is None:return
  shell,user=self.calls;shell.Shell_NotifyIconW(NIM_DELETE,ctypes.byref(self.data(0)));self.shown_until=None
  if self.icon:user.DestroyIcon(self.icon);self.icon=None
