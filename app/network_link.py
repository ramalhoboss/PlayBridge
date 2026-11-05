"""The connection to the PS5, for the stats: Wi-Fi or cable, and where the picture stopped arriving. Over Wi-Fi, fast motion can need
more than the connection carries, and the picture stops again and again while it lasts."""
import ctypes,socket,struct
from ctypes import byref,c_void_p,wintypes

WIFI=71;ETHERNET=6
# MIB_IF_ROW2: its size, and where the interface index goes in and its type comes out.
IF_ROW_SIZE=1352;IF_INDEX=8;IF_TYPE=1128
# Video further apart than this means the picture stopped for a moment: three frames at 60 fps.
STREAM_GAP=.05

def link(address):
 """'Wi-Fi', 'cable' or 'other' for the connection that reaches this IPv4 address, or None where Windows does not say."""
 try:
  api=ctypes.windll.iphlpapi
  api.GetBestInterface.argtypes=[wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)];api.GetIfEntry2.argtypes=[c_void_p]
  index=wintypes.DWORD()
  if api.GetBestInterface(struct.unpack('<I',socket.inet_aton(address))[0],byref(index)):return None
  row=(ctypes.c_ubyte*IF_ROW_SIZE)();struct.pack_into('<I',row,IF_INDEX,index.value)
  if api.GetIfEntry2(byref(row)):return None
  kind=struct.unpack_from('<I',row,IF_TYPE)[0]
  return 'Wi-Fi' if kind==WIFI else 'cable' if kind==ETHERNET else 'other'
 except Exception:return None
