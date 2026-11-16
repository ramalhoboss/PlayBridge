"""The connection to the PS5, for the stats: Wi-Fi or cable, and where the picture stopped arriving. Over Wi-Fi, fast motion can need
more than the connection carries, and the picture stops again and again while it lasts."""
import ctypes,socket,struct
from ctypes import byref,c_void_p,wintypes

WIFI=71;ETHERNET=6
# MIB_IF_ROW2: its size, and where the interface index goes in and its type comes out.
IF_ROW_SIZE=1352;IF_INDEX=8;IF_TYPE=1128
# MIB_IPFORWARDROW: its size, where the interface index and the route's kind sit, and the kind of a route with no router on the way.
ROUTE_ROW_SIZE=56;ROUTE_INDEX=16;ROUTE_DIRECT=3
# Video further apart than this means the picture stopped for a moment: three frames at 60 fps.
STREAM_GAP=.05

def _iphlpapi():return ctypes.windll.iphlpapi
def _interface_kind(api,index):
 api.GetIfEntry2.argtypes=[c_void_p]
 row=(ctypes.c_ubyte*IF_ROW_SIZE)();struct.pack_into('<I',row,IF_INDEX,index)
 if api.GetIfEntry2(byref(row)):return None
 return struct.unpack_from('<I',row,IF_TYPE)[0]

def link(address,api=None):
 """'Wi-Fi', 'cable' or 'other' for the connection that reaches this IPv4 address, or None where Windows does not say."""
 try:
  api=api or _iphlpapi()
  api.GetBestInterface.argtypes=[wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]
  index=wintypes.DWORD()
  if api.GetBestInterface(struct.unpack('<I',socket.inet_aton(address))[0],byref(index)):return None
  kind=_interface_kind(api,index.value)
  if kind is None:return None
  return 'Wi-Fi' if kind==WIFI else 'cable' if kind==ETHERNET else 'other'
 except Exception:return None

def nearby(address,api=None):
 """Whether this IPv4 address is on this PC's own network: True when it is reached straight over Wi-Fi or a cable, False when a
 router or a tunnel (a VPN, a Tailscale route home) is on the way, None where Windows does not say. A PS5 that answers through a
 Tailscale route is away from this PC, even though its home address works."""
 try:
  api=api or _iphlpapi()
  api.GetBestRoute.argtypes=[wintypes.DWORD,wintypes.DWORD,c_void_p]
  row=(ctypes.c_ubyte*ROUTE_ROW_SIZE)()
  if api.GetBestRoute(struct.unpack('<I',socket.inet_aton(address))[0],0,byref(row)):return None
  index,route=struct.unpack_from('<II',row,ROUTE_INDEX)
  if route!=ROUTE_DIRECT:return False
  kind=_interface_kind(api,index)
  return None if kind is None else kind in (WIFI,ETHERNET)
 except Exception:return None
