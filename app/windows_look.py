"""What Windows itself is set to for motion and contrast, so PlayBridge starts the same way until its own Appearance settings say
otherwise. Away from Windows, or when Windows does not say, the answers are animations on and contrast off."""
import ctypes,sys

SPI_GETHIGHCONTRAST=0x0042;HCF_HIGHCONTRASTON=0x1
SPI_GETCLIENTAREAANIMATION=0x1042

class HIGHCONTRAST(ctypes.Structure):
 _fields_=[('cbSize',ctypes.c_uint),('dwFlags',ctypes.c_uint),('lpszDefaultScheme',ctypes.c_void_p)]

def animations():
 """False when Windows' Animation effects are off (Settings › Accessibility › Visual effects)."""
 if sys.platform!='win32':return True
 try:
  on=ctypes.c_int(1)
  if not ctypes.windll.user32.SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION,0,ctypes.byref(on),0):return True
  return bool(on.value)
 except (OSError,AttributeError):return True

def high_contrast():
 """True when a Windows contrast theme is on."""
 if sys.platform!='win32':return False
 try:
  info=HIGHCONTRAST(ctypes.sizeof(HIGHCONTRAST),0,None)
  if not ctypes.windll.user32.SystemParametersInfoW(SPI_GETHIGHCONTRAST,ctypes.sizeof(info),ctypes.byref(info),0):return False
  return bool(info.dwFlags&HCF_HIGHCONTRASTON)
 except (OSError,AttributeError):return False
