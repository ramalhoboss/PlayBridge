"""Picture and sound over UDP for play away from home: the PC side of payload/fec-rules.h.

Over the internet a lost TCP segment holds every byte after it until it is sent again, so the picture stops while the line has
room. Over UDP each record (a 32-byte PSAV header and its packet) comes in fragments with Reed-Solomon parity: a block of up to 32
fragments is rebuilt from any 32 of its fragments, whichever were lost. A record that cannot be rebuilt is left out; after a lost
picture the next ones wait for a keyframe, as after a decoder that fell behind, so the screen holds the last good picture instead of
smearing. This PC tells the payload four times a second how much parity it needs for the loss it sees.

The datagrams are sealed with keys of their own, made from the secured TCP connection's handshake (secure_link), and the TCP
connection stays open: the payload closes it when the stream ends."""
import collections,select,socket,struct,threading,time
import secure_link

FRAGMENT=1152;BLOCK=32;HEADER=16;MOST_PERCENT=100
HEAD=struct.Struct('<IIHBBBBH')
REPORT=struct.Struct('<4sB3xII')
RECORD_MOST=32+0x200200
# How long a record that is not whole waits once a later one has begun, for fragments that took another path.
LATE=0.04
# How long one waits at most, from its first fragment.
RECORD_WAIT=0.3
# How long the pictures after a lost one wait for a keyframe before they are shown anyway.
KEY_WAIT=3.0
REPORT_EVERY=0.25
# Until the payload's first datagram arrives, reports go this often: the payload waits for one before its capture starts, and may open
# its port only after the first ones were sent.
FIRST_REPORT_EVERY=0.05
# Datagram numbers further back than this are refused, as a replay.
WINDOW=8192
LEAST_PERCENT=10;START_PERCENT=20;MOST_ASKED=60

EXP=[0]*512;LOG=[0]*256
_x=1
for _i in range(255):
 EXP[_i]=_x;LOG[_x]=_i;_x<<=1
 if _x&0x100:_x^=0x11d
for _i in range(255,512):EXP[_i]=EXP[_i-255]
def mul(a,b):return EXP[LOG[a]+LOG[b]] if a and b else 0
def inverse(a):return EXP[255-LOG[a]]
def coefficient(row,column):return inverse((BLOCK+row)^column)
_TIMES={}
def times(c):
 """The table that multiplies every byte by c, for bytes.translate."""
 table=_TIMES.get(c)
 if table is None:table=_TIMES[c]=bytes(mul(c,b) for b in range(256))
 return table
def _int(data):return int.from_bytes(data,'little')

def fragments_of(size):return -(-size//FRAGMENT)
def length(size,fragment):return min(FRAGMENT,size-fragment*FRAGMENT)
def data_in(size,block):return min(BLOCK,fragments_of(size)-block*BLOCK)
def parity_in(size,block,percent):
 k=data_in(size,block);percent=min(percent,MOST_PERCENT)
 if not percent:return 0
 return max(1,min((k*percent+99)//100,k))

def parity(record,block,percent):
 """A block's parity fragments, as the payload makes them."""
 size=len(record);k=data_in(size,block);m=parity_in(size,block,percent);first=block*BLOCK;width=length(size,first);out=[]
 for j in range(m):
  value=0
  for i in range(k):
   at=(first+i)*FRAGMENT;data=record[at:at+length(size,first+i)]
   value^=_int(data.translate(times(coefficient(j,i))))
  out.append(value.to_bytes(width,'little'))
 return out

def encode(number,record,percent):
 """Every fragment of a record, with its header, in the order the payload sends them: each block's data, then its parity."""
 size=len(record);out=[]
 for block in range(-(-fragments_of(size)//BLOCK)):
  k=data_in(size,block);extra=parity(record,block,percent);m=len(extra);first=block*BLOCK
  for index in range(k+m):
   if index<k:at=(first+index)*FRAGMENT;body=record[at:at+length(size,first+index)]
   else:body=extra[index-k]
   out.append(HEAD.pack(number,size,block,index,k,m,1,0)+body)
 return out

def invert(matrix):
 """The inverse of a square matrix over GF(256), by Gauss-Jordan."""
 n=len(matrix);rows=[list(row)+[1 if i==j else 0 for j in range(n)] for i,row in enumerate(matrix)]
 for col in range(n):
  pivot=next(r for r in range(col,n) if rows[r][col])
  rows[col],rows[pivot]=rows[pivot],rows[col]
  scale=inverse(rows[col][col]);rows[col]=[mul(scale,v) for v in rows[col]]
  for r in range(n):
   if r!=col and rows[r][col]:
    f=rows[r][col];rows[r]=[v^mul(f,w) for v,w in zip(rows[r],rows[col])]
 return [row[n:] for row in rows]

def rebuild(size,block,data,extra):
 """A block's data fragments from what arrived: data {index: bytes}, extra {parity row: bytes}; None while too few came."""
 k=data_in(size,block);missing=[i for i in range(k) if i not in data]
 if not missing:return [data[i] for i in range(k)]
 rows=sorted(extra)[:len(missing)]
 if len(rows)<len(missing):return None
 first=block*BLOCK;width=length(size,first);syndromes=[]
 for j in rows:
  value=_int(extra[j])
  for i,fragment in data.items():value^=_int(fragment.translate(times(coefficient(j,i))))
  syndromes.append(value.to_bytes(width,'little'))
 solve=invert([[coefficient(j,i) for i in missing] for j in rows]);whole=dict(data)
 for c,i in enumerate(missing):
  value=0
  for r,syndrome in enumerate(syndromes):
   if solve[c][r]:value^=_int(syndrome.translate(times(solve[c][r])))
  whole[i]=value.to_bytes(width,'little')[:length(size,first+i)]
 return [whole[i] for i in range(k)]

class _Record:
 def __init__(self,size,now):
  self.size=size;self.seen=now;self.blocks={};self.done={};self.kind=None
 def add(self,block,index,k,m,body):
  if block in self.done:return
  data,extra=self.blocks.setdefault(block,({},{}))
  if index<k:
   data[index]=body
   if block==0 and index==0 and len(body)>=6:self.kind=body[5]
  else:extra[index-k]=body
  if len(data)+len(extra)>=k:
   whole=rebuild(self.size,block,data,extra)
   if whole is not None:
    self.done[block]=whole;del self.blocks[block]
    if len(data)<k:return 'rebuilt'
    return 'block'
 def whole(self):return len(self.done)==-(-fragments_of(self.size)//BLOCK)
 def bytes(self):return b''.join(b''.join(self.done[b]) for b in sorted(self.done))

class Assembler:
 """Fragments in, whole records out, in their order. keyframe(packet) says whether a picture can be decoded on its own."""
 def __init__(self,keyframe=None,clock=time.monotonic,start_on_key=False):
  self.keyframe=keyframe;self.clock=clock;self.records={};self.next=None;self.out=collections.deque()
  # A stream joined after its start waits for a keyframe too, as the decoder could not use what comes before one.
  self.need_key=start_on_key;self.lost_at=clock() if start_on_key else None
  self.stats=dict(records=0,records_lost=0,blocks_rebuilt=0,pictures_skipped=0,fragments=0,refused=0)
 def _behind(self,number):return ((number-self.next)&0xffffffff)>=0x80000000
 def add(self,fragment):
  now=self.clock()
  if len(fragment)<HEADER:self.stats['refused']+=1;return
  number,size,block,index,k,m,version,_=HEAD.unpack_from(fragment);body=fragment[HEADER:]
  if version!=1 or not 0<size<=RECORD_MOST or block*BLOCK>=fragments_of(size) or k!=data_in(size,block) or m>k or index>=k+m:self.stats['refused']+=1;return
  if len(body)!=(length(size,block*BLOCK+index) if index<k else length(size,block*BLOCK)):self.stats['refused']+=1;return
  if self.next is None:self.next=number
  if self._behind(number):return
  record=self.records.get(number)
  if record is None:record=self.records[number]=_Record(size,now)
  if record.size!=size:self.stats['refused']+=1;return
  self.stats['fragments']+=1
  if record.add(block,index,k,m,body)=='rebuilt':self.stats['blocks_rebuilt']+=1
  self.poll(now)
 def poll(self,now=None):
  """Hands on every record that is whole, in order, and gives up on the next one once it is late."""
  now=self.clock() if now is None else now
  while self.next is not None:
   record=self.records.get(self.next)
   if record is not None and record.whole():
    del self.records[self.next];self.next=(self.next+1)&0xffffffff;self._emit(record,now);continue
   later=[r.seen for n,r in self.records.items() if n!=self.next]
   if record is not None:
    if now-record.seen<RECORD_WAIT and not (later and now-min(later)>=LATE):break
    del self.records[self.next];self._lost(record.kind,now);self.next=(self.next+1)&0xffffffff;continue
   # Nothing of it came at all: given up once a later record has waited long enough.
   if not later or now-min(later)<LATE:break
   self._lost(None,now);self.next=(self.next+1)&0xffffffff
 def _lost(self,kind,now):
  self.stats['records_lost']+=1
  # A lost record whose kind is unknown may have been a picture.
  if kind!=2:self.need_key=True;self.lost_at=now
 def _emit(self,record,now):
  data=record.bytes();self.stats['records']+=1
  if self.need_key and record.kind==1:
   if self.keyframe is None or self.keyframe(data[32:]) or now-self.lost_at>=KEY_WAIT:self.need_key=False
   else:self.stats['pictures_skipped']+=1;return
  self.out.append(data)
 def take(self):
  out=b''.join(self.out);self.out.clear();return out

class Loss:
 """The share of datagrams lost, from the payload's datagram numbers, which go up by one for each datagram it sends."""
 def __init__(self):self.first=None;self.last=None;self.got=0
 def add(self,count):
  if self.first is None or count<self.first:self.first=count
  if self.last is None or count>self.last:self.last=count
  self.got+=1
 def share(self):
  if self.first is None:return 0.0
  sent=self.last-self.first+1;return max(0.0,1-self.got/sent)

def wanted_percent(losses):
 """The parity to ask for, from the loss of the last seconds: enough over the worst second to rebuild a typical block."""
 worst=max(losses) if losses else 0.0
 return int(min(MOST_ASKED,max(LEAST_PERCENT,round(LEAST_PERCENT+worst*300))))

class UdpVideo:
 """The stream over UDP, read like the TCP socket it replaces (recv, timeouts, close), so the loop that reads records stays as it
 is. tcp: the secured connection, kept open, which the payload closes when the stream ends. address: the payload's UDP port as this
 PC reaches it. keys: (this PC to the payload, the payload to this PC), from SecureSocket.udp_keys().
 It starts reporting at once, so the payload knows where to send before its first picture; the TCP connection is only watched once
 take_over() says the acknowledgement was read from it, and detach() gives it back when the payload stays on TCP."""
 def __init__(self,tcp,address,keys,keyframe=None,clock=time.monotonic,bind=('0.0.0.0',0),watch=True):
  self.tcp=tcp;self.address=address;self.out,self.into=keys;self.clock=clock;self.watching=watch
  self.udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
  try:self.udp.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,8<<20)
  except OSError:pass
  self.udp.bind(bind);self.udp.settimeout(.05)
  self.assembler=Assembler(keyframe,clock,start_on_key=keyframe is not None);self.buffer=bytearray();self.cond=threading.Condition();self.timeout=None
  self.closed=False;self.ended=False;self.error=None;self.percent=START_PERCENT;self.losses=collections.deque(maxlen=5);self.loss=Loss();self.loss_at=clock()
  self.seen=set();self.top=-1;self.datagrams=0
  self.thread=threading.Thread(target=self._run,name='PlayBridge UDP video',daemon=True);self.thread.start()
 def stats(self):
  s=dict(self.assembler.stats);s.update(percent=self.percent,datagrams=self.datagrams,loss=round(max(self.losses) if self.losses else 0.0,4));return s
 def _report(self):
  s=self.assembler.stats;head=b'PBX1'+struct.pack('<Q',self.out.count)
  body=REPORT.pack(b'PBH1',self.percent,s['records']&0xffffffff,s['records_lost']&0xffffffff)
  try:self.udp.sendto(head+self.out.seal(head,body),self.address)
  except OSError:pass
 def _open(self,data):
  if data[:4]!=b'PBX1' or len(data)<12+secure_link.TAG:return None
  (count,)=struct.unpack_from('<Q',data,4)
  if count<=self.top-WINDOW or count in self.seen:return None
  plain=self.into.open(data[:12],data[12:],count)
  if plain is None:return None
  self.seen.add(count)
  if count>self.top:
   self.top=count
   if len(self.seen)>2*WINDOW:self.seen={c for c in self.seen if c>self.top-WINDOW}
  self.loss.add(count);return plain
 def _tcp_closed(self):
  try:readable,_,_=select.select([self.tcp.fileno()],[],[],0)
  except (OSError,ValueError):return True
  if not readable:return False
  try:return not self.tcp.recv(65536)
  except socket.timeout:return False
  except (OSError,ValueError,secure_link.SecureError):return True
 def _run(self):
  report_at=0.0;tcp_at=0.0
  while not self.closed:
   now=self.clock()
   if now>=report_at:self._report();report_at=now+(REPORT_EVERY if self.datagrams else FIRST_REPORT_EVERY)
   if now-self.loss_at>=1:
    self.losses.append(self.loss.share());self.loss=Loss();self.loss_at=now;self.percent=wanted_percent(self.losses)
   try:data,_=self.udp.recvfrom(4096)
   except socket.timeout:data=None
   except OSError as error:
    if self.closed:break
    # Windows reports an earlier datagram the other side refused as an error on the next read: it is no reason to stop.
    if getattr(error,'winerror',None)==10054:continue
    with self.cond:self.error=error;self.cond.notify_all()
    break
   if data:
    plain=self._open(data)
    if plain is not None:self.datagrams+=1;self.assembler.add(plain)
   else:self.assembler.poll()
   got=self.assembler.take()
   if self.watching and now>=tcp_at:
    tcp_at=now+.1
    if self._tcp_closed():
     with self.cond:
      if got:self.buffer+=got
      self.ended=True;self.cond.notify_all()
     break
   if got:
    with self.cond:self.buffer+=got;self.cond.notify_all()
 def recv(self,size):
  end=None if self.timeout is None else self.clock()+self.timeout
  with self.cond:
   while not self.buffer:
    if self.error is not None:raise self.error
    if self.ended or self.closed:return b''
    left=None if end is None else end-self.clock()
    if left is not None and left<=0:raise socket.timeout('timed out')
    self.cond.wait(.25 if left is None else min(left,.25))
   data=bytes(self.buffer[:size]);del self.buffer[:size];return data
 def take_over(self):self.watching=True
 def detach(self):
  """Stops the UDP side and leaves the TCP connection as it is, for a payload that stays on TCP."""
  self.closed=True
  try:self.udp.close()
  except OSError:pass
  if self.thread is not threading.current_thread():self.thread.join(timeout=1)
  for direction in (self.out,self.into):
   if direction is not None and direction.handle is not None:direction.close()
 def sendall(self,data):self.tcp.sendall(data)
 def settimeout(self,value):self.timeout=value
 def gettimeout(self):return self.timeout
 def setsockopt(self,*args):return self.tcp.setsockopt(*args)
 def getpeername(self):return self.tcp.getpeername()
 def fileno(self):return self.tcp.fileno()
 def close(self):
  self.closed=True
  with self.cond:self.cond.notify_all()
  try:self.udp.close()
  except OSError:pass
  if self.thread is not threading.current_thread():self.thread.join(timeout=1)
  self.tcp.close()
  for direction in (self.out,self.into):
   if direction is not None and direction.handle is not None:direction.close()
 def __enter__(self):return self
 def __exit__(self,*exc):self.close()
