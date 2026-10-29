"""Windows DIB presenter. All calls run on the Tk UI thread; no frame copy."""
import ctypes
from ctypes import wintypes

class BitmapInfoHeader(ctypes.Structure):
 _fields_=[('size',wintypes.DWORD),('width',wintypes.LONG),('height',wintypes.LONG),('planes',wintypes.WORD),('bits',wintypes.WORD),('compression',wintypes.DWORD),('image_size',wintypes.DWORD),('xppm',wintypes.LONG),('yppm',wintypes.LONG),('colors',wintypes.DWORD),('important',wintypes.DWORD)]

class GdiPresenter:
 def __init__(self,canvas):
  self.canvas=canvas;self.frame=None;self.dirty=False
  self.user=ctypes.WinDLL('user32',use_last_error=True);self.gdi=ctypes.WinDLL('gdi32',use_last_error=True)
  self.user.GetDC.argtypes=[wintypes.HWND];self.user.GetDC.restype=wintypes.HDC
  self.user.ReleaseDC.argtypes=[wintypes.HWND,wintypes.HDC];self.user.ReleaseDC.restype=ctypes.c_int
  self.gdi.StretchDIBits.argtypes=[wintypes.HDC]+[ctypes.c_int]*8+[ctypes.c_void_p,ctypes.POINTER(BitmapInfoHeader),wintypes.UINT,wintypes.DWORD]
  self.gdi.StretchDIBits.restype=ctypes.c_int
  canvas.bind('<Expose>',lambda _:setattr(self,'dirty',True),add='+')
 def draw(self,frame):
  plane=frame.planes[0];width,height=frame.width,frame.height
  # DIB storage width follows FFmpeg's padded stride; source rectangle excludes padding.
  if frame.format.name!='bgr0' or plane.line_size%4:raise ValueError('Invalid DIB frame layout')
  header=BitmapInfoHeader(ctypes.sizeof(BitmapInfoHeader),plane.line_size//4,-height,1,32,0,plane.buffer_size,0,0,0,0)
  data=(ctypes.c_ubyte*plane.buffer_size).from_buffer(plane)
  hwnd=self.canvas.winfo_id();dc=self.user.GetDC(hwnd)
  if not dc:raise ctypes.WinError(ctypes.get_last_error())
  try:
   x=(self.canvas.winfo_width()-width)//2;y=(self.canvas.winfo_height()-height)//2
   result=self.gdi.StretchDIBits(dc,x,y,width,height,0,0,width,height,data,ctypes.byref(header),0,0x00CC0020)
   if result in (0,-1):raise RuntimeError('StretchDIBits failed')
  finally:self.user.ReleaseDC(hwnd,dc)
  self.frame=frame;self.dirty=False
 def refresh(self):
  if self.dirty and self.frame is not None:self.draw(self.frame)
