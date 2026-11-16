"""The secured link between this PC and its payloads (payload/secure-rules.h is the console side, and says how it works).

This PC keeps a pairing key of its own, sealed for this Windows user. Before it sends PlayBridge.elf or the controller companion, it
writes that key into the payload's slot, so the payload takes no connection that cannot prove it, and everything between the two is
encrypted with AES-256-GCM: the picture and sound, the game library and power, the microphone and the controller. A payload loaded by
hand has no key and works as before, open, on the home network only.

AES-GCM comes from Windows itself (CNG), or from the cryptography package elsewhere; without either, payloads go out without a key."""
import hashlib,hmac,secrets,socket,struct,threading,time

SLOT_MAGIC=b'PBKEYSLOT1'+bytes(6)
SLOT_SIZE=64;KEY_AT=16;FLAGS_AT=48
FLAG_AWAY=1
# Trace: the payload writes its logs back over the ELF loader's connection as well. Only the trial tool sets it, never the app.
FLAG_TRACE=2
RECORD_MAX=65536;TAG=16
VIDEO,CONTROL,MIC,PAD,VIDEO_UDP=1,2,3,4,5
HANDSHAKE_SECONDS=5.0
# A controller companion that has said nothing for this long while this PC sends to it is asked again who it is.
PAD_SILENT=2.0;PAD_HELLO_EVERY=0.5

class SecureError(ValueError):
 """The other side is not the payload this PC sent, or what came was not sealed with its key."""

class _Cng:
 """AES-256-GCM from Windows' own cryptography (bcrypt.dll)."""
 STATUS_AUTH_TAG_MISMATCH=0xC000A002
 def __init__(self):
  import ctypes
  from ctypes import wintypes
  self.ctypes=ctypes;self.bcrypt=ctypes.WinDLL('bcrypt')
  class Info(ctypes.Structure):
   _fields_=[('cbSize',wintypes.ULONG),('dwInfoVersion',wintypes.ULONG),('pbNonce',ctypes.c_void_p),('cbNonce',wintypes.ULONG),('pbAuthData',ctypes.c_void_p),
    ('cbAuthData',wintypes.ULONG),('pbTag',ctypes.c_void_p),('cbTag',wintypes.ULONG),('pbMacContext',ctypes.c_void_p),('cbMacContext',wintypes.ULONG),
    ('cbAAD',wintypes.ULONG),('cbData',ctypes.c_ulonglong),('dwFlags',wintypes.ULONG)]
  self.Info=Info;self.alg=ctypes.c_void_p()
  for name in ('BCryptOpenAlgorithmProvider','BCryptSetProperty','BCryptGenerateSymmetricKey','BCryptEncrypt','BCryptDecrypt','BCryptDestroyKey'):
   getattr(self.bcrypt,name).restype=ctypes.c_uint32
  self.bcrypt.BCryptEncrypt.argtypes=self.bcrypt.BCryptDecrypt.argtypes=[ctypes.c_void_p,ctypes.c_void_p,wintypes.ULONG,ctypes.c_void_p,ctypes.c_void_p,wintypes.ULONG,
   ctypes.c_void_p,wintypes.ULONG,ctypes.POINTER(wintypes.ULONG),wintypes.ULONG]
  self.bcrypt.BCryptDestroyKey.argtypes=[ctypes.c_void_p]
  if self.bcrypt.BCryptOpenAlgorithmProvider(ctypes.byref(self.alg),'AES',None,0):raise OSError('AES is not available')
  mode=ctypes.create_unicode_buffer('ChainingModeGCM')
  if self.bcrypt.BCryptSetProperty(self.alg,'ChainingMode',mode,ctypes.sizeof(mode),0):raise OSError('GCM is not available')
 def key(self,key):
  handle=self.ctypes.c_void_p();blob=self.ctypes.create_string_buffer(bytes(key),len(key))
  if self.bcrypt.BCryptGenerateSymmetricKey(self.alg,self.ctypes.byref(handle),None,0,blob,len(key),0):raise OSError('The key could not be made')
  return handle
 def drop(self,handle):
  if handle:self.bcrypt.BCryptDestroyKey(handle)
 def _info(self,nonce,aad,tag):
  ctypes=self.ctypes;info=self.Info();info.cbSize=ctypes.sizeof(info);info.dwInfoVersion=1
  # The structure only points at its buffers: they go back with it, so they live until the call is done.
  kept=[ctypes.create_string_buffer(bytes(nonce),12)];info.pbNonce=ctypes.cast(kept[0],ctypes.c_void_p);info.cbNonce=12;info.pbTag=ctypes.cast(tag,ctypes.c_void_p);info.cbTag=TAG
  if aad:kept.append(ctypes.create_string_buffer(bytes(aad),len(aad)));info.pbAuthData=ctypes.cast(kept[1],ctypes.c_void_p);info.cbAuthData=len(aad)
  return info,kept
 def seal(self,handle,nonce,aad,data):
  ctypes=self.ctypes;n=len(data);source=ctypes.create_string_buffer(bytes(data),max(1,n));out=ctypes.create_string_buffer(max(1,n));tag=ctypes.create_string_buffer(TAG)
  info,kept=self._info(nonce,aad,tag);done=ctypes.c_ulong()
  status=self.bcrypt.BCryptEncrypt(handle,source,n,ctypes.byref(info),None,0,out,n,ctypes.byref(done),0)
  if status:raise OSError(f'AES-GCM failed ({status:#010x})')
  return out.raw[:n]+tag.raw
 def open(self,handle,nonce,aad,sealed):
  ctypes=self.ctypes;n=len(sealed)-TAG
  if n<0:return None
  source=ctypes.create_string_buffer(bytes(sealed[:n]),max(1,n));out=ctypes.create_string_buffer(max(1,n));tag=ctypes.create_string_buffer(bytes(sealed[n:]),TAG)
  info,kept=self._info(nonce,aad,tag);done=ctypes.c_ulong()
  status=self.bcrypt.BCryptDecrypt(handle,source,n,ctypes.byref(info),None,0,out,n,ctypes.byref(done),0)
  if status==self.STATUS_AUTH_TAG_MISMATCH:return None
  if status:raise OSError(f'AES-GCM failed ({status:#010x})')
  return out.raw[:n]

class _Package:
 """AES-256-GCM from the cryptography package, where Windows' own is not there."""
 def __init__(self):
  from cryptography.exceptions import InvalidTag
  from cryptography.hazmat.primitives.ciphers.aead import AESGCM
  self.AESGCM=AESGCM;self.InvalidTag=InvalidTag
 def key(self,key):return self.AESGCM(bytes(key))
 def drop(self,handle):pass
 def seal(self,handle,nonce,aad,data):return handle.encrypt(nonce,bytes(data),aad or None)
 def open(self,handle,nonce,aad,sealed):
  try:return handle.decrypt(nonce,bytes(sealed),aad or None)
  except self.InvalidTag:return None

def _backend():
 for kind in (_Cng,_Package):
  try:return kind()
  except Exception:continue
 return None
BACKEND=_backend()
def available():return BACKEND is not None

def derive(key,label,channel,ns,nc):
 """HMAC-SHA256(key, label with its zero byte, channel, Ns, Nc), as the payload makes it."""
 return hmac.new(bytes(key),label.encode('ascii')+b'\0'+bytes((channel,))+bytes(ns)+bytes(nc),hashlib.sha256).digest()
def nonce(count):return bytes(4)+struct.pack('<Q',count)

class Direction:
 """One direction of a connection: its AES-GCM key and the number of its next record (or of the lowest one still taken)."""
 def __init__(self,key):self.handle=BACKEND.key(key);self.count=0
 def seal(self,aad,data,count=None):
  count=self.count if count is None else count;self.count=count+1
  return BACKEND.seal(self.handle,nonce(count),aad,data)
 def open(self,aad,sealed,count=None):
  count=self.count if count is None else count
  plain=BACKEND.open(self.handle,nonce(count),aad,sealed)
  if plain is not None:self.count=count+1
  return plain
 def close(self):BACKEND.drop(self.handle);self.handle=None

def keys(key,channel,ns,nc):
 """(this PC to the payload, the payload to this PC)."""
 return Direction(derive(key,'PlayBridge 1 c2s',channel,ns,nc)),Direction(derive(key,'PlayBridge 1 s2c',channel,ns,nc))

def read_exact(sock,size):
 data=bytearray()
 while len(data)<size:
  part=sock.recv(size-len(data))
  if not part:raise EOFError('The PS5 closed the connection')
  data+=part
 return bytes(data)

def seal_record(direction,data):
 head=struct.pack('<I',len(data));return head+direction.seal(head,data)

class SecureSocket:
 """A connected socket to a payload that holds this PC's key: the handshake, then sealed records both ways. It reads and writes like
 the socket it wraps (recv, sendall, timeouts), so the code above it stays as it is."""
 def __init__(self,sock,key,channel,timeout=HANDSHAKE_SECONDS):
  self.sock=sock;self.channel=channel;self.raw=bytearray();self.plain=bytearray();self.lock=threading.Lock();self.out=self.into=None
  before=sock.gettimeout();sock.settimeout(timeout)
  try:
   hello=read_exact(sock,24)
   if hello[:4]!=b'PBK1' or hello[4]!=1:raise SecureError('This is not a PlayBridge payload that holds a key.')
   if hello[5]!=channel:raise SecureError('The payload answered for another port.')
   ns=hello[8:24];nc=secrets.token_bytes(16)
   sock.sendall(b'PBK2'+nc+derive(key,'PlayBridge 1 client',channel,ns,nc))
   try:proof=read_exact(sock,36)
   except EOFError:raise SecureError('The PlayBridge payload on this PS5 was sent by another PC.') from None
   if proof[:4]!=b'PBK3' or not hmac.compare_digest(proof[4:],derive(key,'PlayBridge 1 server',channel,ns,nc)):raise SecureError('The payload did not prove it holds this PC\'s key.')
  finally:sock.settimeout(before)
  self.out,self.into=keys(key,channel,ns,nc);self.key=key;self.ns=ns;self.nc=nc
 def udp_keys(self):
  """(this PC to the payload, the payload to this PC) for the stream over UDP, from this connection's handshake."""
  return keys(self.key,VIDEO_UDP,self.ns,self.nc)
 def _record(self):
  """Reads until one whole record is in, and opens it. A timeout keeps what had arrived, so the next read goes on from there."""
  while True:
   if len(self.raw)>=4:
    (size,)=struct.unpack_from('<I',self.raw)
    if not 0<size<=RECORD_MAX:raise SecureError('A record of a size the payload never sends')
    end=4+size+TAG
    if len(self.raw)>=end:
     head=bytes(self.raw[:4]);plain=self.into.open(head,self.raw[4:end]);del self.raw[:end]
     if plain is None:raise SecureError('A record that was not sealed with this PC\'s key')
     self.plain+=plain;return True
   part=self.sock.recv(262144)
   if not part:return False
   self.raw+=part
 def recv(self,size):
  if not self.plain and not self._record():return b''
  data=bytes(self.plain[:size]);del self.plain[:size];return data
 def sendall(self,data):
  view=memoryview(bytes(data))
  with self.lock:
   for at in range(0,len(view),RECORD_MAX):self.sock.sendall(seal_record(self.out,view[at:at+RECORD_MAX]))
 def settimeout(self,value):self.sock.settimeout(value)
 def gettimeout(self):return self.sock.gettimeout()
 def setsockopt(self,*args):return self.sock.setsockopt(*args)
 def getsockopt(self,*args):return self.sock.getsockopt(*args)
 def getpeername(self):return self.sock.getpeername()
 def getsockname(self):return self.sock.getsockname()
 def fileno(self):return self.sock.fileno()
 def shutdown(self,how):return self.sock.shutdown(how)
 def close(self):
  self.sock.close()
  for direction in (self.out,self.into):
   if direction is not None and direction.handle is not None:direction.close()
 def __enter__(self):return self
 def __exit__(self,*exc):self.close()

def stamp(data,key,flags=0):
 """The payload with this PC's key and flags in its slot, and whether it had one: an ELF without exactly one empty slot goes as it is."""
 empty=SLOT_MAGIC+bytes(SLOT_SIZE-len(SLOT_MAGIC));at=data.find(empty)
 if at<0 or data.find(empty,at+1)>=0 or len(key)!=32:return data,False
 out=bytearray(data);out[at+KEY_AT:at+KEY_AT+32]=key;out[at+FLAGS_AT:at+FLAGS_AT+4]=struct.pack('<I',flags);return bytes(out),True

class Pairing:
 """This PC's pairing key, and whether the payloads running on the PS5 now hold it. load() and save(text) keep the key sealed in the
 settings; seal(text) and unseal(text) are DPAPI's (live_broadcast). A key that cannot be read back, as for another Windows user, is
 replaced: the next payload sent carries the new one."""
 def __init__(self,load,save,seal,unseal):
  self.load=load;self.save=save;self.seal=seal;self.unseal=unseal;self.lock=threading.Lock();self.cached=None
  # Whether the video payload running now was sent from here with the key; the controller companion's datagrams find out for themselves (PadLink).
  self.video=False
 def key(self):
  with self.lock:
   if self.cached is None:
    text=self.unseal(self.load() or '')
    try:key=bytes.fromhex(text)
    except ValueError:key=b''
    if len(key)!=32:
     key=secrets.token_bytes(32);sealed=self.seal(key.hex())
     if sealed:self.save(sealed)
    self.cached=key
   return self.cached
 def stamp(self,data,flags=0):
  """The payload to send and whether it carries the key; without AES-GCM on this PC it goes as it is."""
  if not available():return data,False
  return stamp(data,self.key(),flags)
 def pad_key(self):
  """The key for the controller companion's datagrams, or None without AES-GCM on this PC."""
  return self.key() if available() else None
 def connect(self,host,port,channel,timeout=2.0):
  """A connection to one of the video payload's ports: secured when the payload running there was sent with the key."""
  sock=socket.create_connection((host,port),timeout)
  if not self.video:return sock
  try:return SecureSocket(sock,self.key(),channel,max(timeout,HANDSHAKE_SECONDS))
  except BaseException:sock.close();raise
 def wrap(self,sock,channel):
  """The video connection, once open: secured when the payload holds the key."""
  if not self.video:return sock
  return SecureSocket(sock,self.key(),channel)

class PadLink:
 """The datagrams of one sender to the controller companion. With no key they go as they are. With one, the sender says hello and,
 once the companion proved it holds the same key, seals every datagram; until then it sends both ways, so a companion loaded by hand,
 which has no key, still plays. A companion that proves another key was sent by another PC: this one is told and sends it nothing.
 key(): this PC's key, or None; clock(): seconds."""
 def __init__(self,key=None,clock=time.monotonic):
  self.key=key;self.clock=clock;self.nc=None;self.out=self.into=None;self.hello_at=None;self.heard_at=None;self.foreign=False;self.mode='unknown'
 def sealed(self):return self.mode=='sealed'
 def datagrams(self,data):
  """What to send for data: sealed once the companion proved the key; otherwise the data, then a hello now and then."""
  if self.key is None or self.key() is None:return [data]
  now=self.clock()
  # A companion that went quiet (it ended, or a new one started) is asked again who it is.
  if self.mode!='unknown' and (self.heard_at is None or now-self.heard_at>PAD_SILENT) and (self.hello_at is None or now-self.hello_at>PAD_SILENT):self.forget()
  if self.mode=='sealed':
   head=b'PBX1'+struct.pack('<Q',self.out.count);return [head+self.out.seal(head,data)]
  out=[] if self.mode=='foreign' else [data]
  if self.hello_at is None or now-self.hello_at>=PAD_HELLO_EVERY:
   self.hello_at=now;self.nc=secrets.token_bytes(16);out.append(b'PBK4'+self.nc)
  return out
 def forget(self):
  for direction in (self.out,self.into):
   if direction is not None and direction.handle is not None:direction.close()
  self.out=self.into=None;self.mode='unknown';self.foreign=False;self.heard_at=None
 def take(self,data):
  """A datagram from the companion: the plain bytes to read, or None for one that was only for this link or did not open."""
  now=self.clock()
  if data[:4]==b'PBK5' and len(data)==68 and self.key is not None and self.nc is not None and data[4:20]==self.nc:
   key=self.key();ns=data[20:36]
   if key is not None and hmac.compare_digest(data[36:68],derive(key,'PlayBridge 1 server',PAD,ns,self.nc)):
    self.forget();self.out,self.into=keys(key,PAD,ns,self.nc);self.mode='sealed'
   elif self.mode!='sealed':self.mode='foreign';self.foreign=True
   self.heard_at=now;return None
  # A late answer to an earlier hello, or one meant for another sender.
  if data[:3]==b'PBK':return None
  if data[:4]==b'PBX1':
   if self.mode!='sealed' or len(data)<12+TAG:return None
   (count,)=struct.unpack_from('<Q',data,4)
   if count<self.into.count:return None
   plain=self.into.open(data[:12],data[12:],count)
   if plain is not None:self.heard_at=now
   return plain
  # A plain answer: the companion holds no key, so it is played as it is.
  if self.mode=='unknown':self.mode='plain'
  if self.mode=='plain':self.heard_at=now;return data
  return None
