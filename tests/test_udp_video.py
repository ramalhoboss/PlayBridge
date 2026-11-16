"""Play away from home, the stream over UDP: the payload's C (payload/fec-rules.h, away-rules.h and the socket-free part of
video-udp.h, built here as a DLL) against the PC's side (app/udp_video.py). The fragments and parity match byte for byte, every block
comes back from any of its fragments as long as enough arrived, records come out in order with a lost picture holding the next ones
until a keyframe, and a real stream over UDP on this PC, sealed by the C and with one datagram in ten lost, arrives whole."""
import ctypes,json,os,random,re,socket,struct,subprocess,sys,tempfile,threading,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'));sys.path.insert(0,str(ROOT/'tests'))
import secure_link,udp_video
from test_secure_link import compiler

HARNESS=r'''
#include <stddef.h>
#include <stdint.h>
void*memcpy(void*d,const void*s,size_t n){char*a=d;const char*b=s;while(n--)*a++=*b++;return d;}
void*memset(void*d,int c,size_t n){char*a=d;while(n--)*a++=(char)c;return d;}
#include "secure-rules.h"
#define VIDEO_UDP_RULES_ONLY
#include "video-udp.h"
#define OUT __declspec(dllexport)
OUT int pb_away_local(uint32_t a){return away_local(a);}
OUT uint32_t pb_away_hours(uint32_t f){return away_hours(f);}
OUT int pb_away_on(int keyed,uint32_t f){return away_on(keyed,f);}
OUT int pb_away_admit(int keyed,uint32_t a){return away_admit(keyed,a);}
OUT int pb_away_heard(uint64_t now,uint64_t started,uint64_t heard){return away_pc_heard(now,started,heard);}
/* Every plain fragment of a record, each FEC_DATAGRAM apart, their sizes in sizes; returns how many. */
static unsigned char parity[FEC_BLOCK*FEC_FRAGMENT];
OUT int pb_fragments(const unsigned char*record,uint32_t size,unsigned percent,uint32_t number,unsigned char*out,uint32_t*sizes,int most){
 fec_init();struct fec_plan p;fec_plan(&p,size,percent);int n=0;
 for(uint32_t b=0;b<p.blocks;b++){
  unsigned k=fec_data_in(&p,b),m=fec_parity_in(&p,b);if(m)fec_parity(&p,record,b,parity);
  for(unsigned i=0;i<k+m;i++){if(n>=most)return -1;sizes[n]=(uint32_t)fec_fragment(&p,number,record,parity,b,i,out+(size_t)n*FEC_DATAGRAM);n++;}
 }
 return n;
}
static struct video_udp u;
struct sink{unsigned char*out;uint32_t*sizes;int n,most;};
static int keep(void*ctx,const unsigned char*d,size_t n){struct sink*s=ctx;if(s->n>=s->most)return -1;memcpy(s->out+(size_t)s->n*(FEC_DATAGRAM+SECURE_DATAGRAM_EXTRA),d,n);s->sizes[s->n++]=(uint32_t)n;return 0;}
OUT void pb_udp_keys(const unsigned char*key,const unsigned char*ns,const unsigned char*nc){video_udp_keys(&u,key,ns,nc,1000);}
OUT int pb_udp_record(const unsigned char*record,uint32_t size,unsigned char*out,uint32_t*sizes,int most){struct sink s={out,sizes,0,most};return video_udp_record(&u,record,size,keep,&s)<0?-1:s.n;}
OUT int pb_udp_take(unsigned char*w,size_t n,uint32_t address,uint16_t port,uint64_t now,uint32_t*state){
 int r=video_udp_take(&u,w,n,address,port,now);state[0]=u.percent;state[1]=u.peer;state[2]=u.peer_address;state[3]=u.peer_port;state[4]=(uint32_t)u.heard_ms;state[5]=(uint32_t)u.reports;return r;
}
OUT int pb_report(const unsigned char*w,long n,unsigned*percent){return fec_report(w,n,percent);}
'''
DATAGRAM=udp_video.HEADER+udp_video.FRAGMENT
SEALED=DATAGRAM+28

@unittest.skipUnless(os.name=='nt' and compiler(),'needs clang on Windows')
class PayloadSideTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(ignore_cleanup_errors=True);source=Path(cls.tmp.name)/'harness.c';source.write_text(HARNESS,encoding='ascii');out=Path(cls.tmp.name)/'udp.dll'
  subprocess.run([compiler(),'--target=x86_64-pc-windows-msvc','-O2','-ffreestanding','-fno-builtin','-nostdlib','-shared','-fuse-ld=lld','-Wl,/noentry','-Wall','-Wextra','-Werror','-I',str(ROOT/'payload'),str(source),'-o',str(out)],check=True)
  cls.lib=lib=ctypes.WinDLL(str(out))
  lib.pb_fragments.argtypes=[ctypes.c_char_p,ctypes.c_uint32,ctypes.c_uint,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int]
  lib.pb_udp_record.argtypes=[ctypes.c_char_p,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int]
  lib.pb_udp_take.argtypes=[ctypes.c_char_p,ctypes.c_size_t,ctypes.c_uint32,ctypes.c_uint16,ctypes.c_uint64,ctypes.c_void_p]
  lib.pb_udp_keys.argtypes=[ctypes.c_char_p]*3
  lib.pb_away_heard.argtypes=[ctypes.c_uint64]*3
  lib.pb_away_local.argtypes=[ctypes.c_uint32];lib.pb_away_admit.argtypes=[ctypes.c_int,ctypes.c_uint32]
  lib.pb_away_hours.argtypes=[ctypes.c_uint32];lib.pb_away_hours.restype=ctypes.c_uint32;lib.pb_away_on.argtypes=[ctypes.c_int,ctypes.c_uint32]
  lib.pb_report.argtypes=[ctypes.c_char_p,ctypes.c_long,ctypes.c_void_p]
  cls.lock=threading.Lock()
 @classmethod
 def tearDownClass(cls):
  ctypes.windll.kernel32.FreeLibrary.argtypes=[ctypes.c_void_p];ctypes.windll.kernel32.FreeLibrary(cls.lib._handle);cls.tmp.cleanup()
 def fragments(self,record,percent,number=7):
  most=4096;out=ctypes.create_string_buffer(most*DATAGRAM);sizes=(ctypes.c_uint32*most)()
  n=self.lib.pb_fragments(record,len(record),percent,number,out,sizes,most);self.assertGreaterEqual(n,0)
  return [out.raw[i*DATAGRAM:i*DATAGRAM+sizes[i]] for i in range(n)]
 def sealed(self,record):
  most=4096;out=ctypes.create_string_buffer(most*SEALED);sizes=(ctypes.c_uint32*most)()
  with self.lock:n=self.lib.pb_udp_record(record,len(record),out,sizes,most)
  self.assertGreaterEqual(n,0);return [out.raw[i*SEALED:i*SEALED+sizes[i]] for i in range(n)]

 def test_the_c_and_the_pc_make_the_same_fragments_and_parity(self):
  rng=random.Random(5)
  for size in (1,40,1151,1152,1153,32*1152,32*1152+1,70000,300001):
   record=bytes(rng.getrandbits(8) for _ in range(size))
   for percent in (0,1,10,20,50,100,250):
    self.assertEqual(self.fragments(record,percent),udp_video.encode(7,record,percent),(size,percent))

 def test_any_fragments_up_to_the_parity_rebuild_every_block(self):
  rng=random.Random(9)
  for size,percent in ((1,20),(5000,20),(32*1152,25),(100000,30),(37*1152+5,100)):
   record=bytes(rng.getrandbits(8) for _ in range(size))
   for trial in range(6):
    assembler=udp_video.Assembler();fragments=self.fragments(record,percent,number=trial)
    by_block={}
    for f in fragments:by_block.setdefault(struct.unpack_from('<H',f,8)[0],[]).append(f)
    kept=[]
    for block,items in by_block.items():
     k=items[0][11];m=items[0][12];lose=rng.sample(range(k+m),m)
     kept+=[f for i,f in enumerate(items) if i not in lose]
    rng.shuffle(kept)
    for f in kept:assembler.add(f)
    self.assertEqual(assembler.take(),record,(size,percent,trial))
    self.assertEqual(assembler.stats['records_lost'],0)
  # One fragment more than the parity of a block lost: that record is given up, the next one still comes.
  record=bytes(range(256))*20;clock=[0.0];assembler=udp_video.Assembler(clock=lambda:clock[0]);first=self.fragments(record,20,number=1)
  for f in first[:-2]:assembler.add(f)
  for f in self.fragments(record,20,number=2):assembler.add(f)
  # It waits while the next record has only just begun, then gives up on it.
  clock[0]=.02;assembler.poll();self.assertEqual(assembler.take(),b'');self.assertEqual(assembler.stats['records_lost'],0)
  clock[0]=.1;assembler.poll();self.assertEqual(assembler.take(),record);self.assertEqual(assembler.stats['records_lost'],1)

 def test_after_a_lost_picture_the_next_ones_wait_for_a_keyframe_and_sound_goes_on(self):
  def record(kind,body):return b'PSAV'+bytes((1,kind,0,0))+struct.pack('<IQQI',len(body),0,0,0)+body
  clock=[0.0];assembler=udp_video.Assembler(keyframe=lambda p:p.startswith(b'KEY'),clock=lambda:clock[0])
  items=[record(1,b'pic one'),record(1,b'lost picture'),record(2,b'sound'),record(1,b'not a keyframe'),record(1,b'KEY frame'),record(1,b'after')]
  for n,data in enumerate(items):
   if n==1:continue
   for f in udp_video.encode(n,data,0):assembler.add(f)
  clock[0]=1.0;assembler.poll()
  out=assembler.take();self.assertEqual(out,items[0]+items[2]+items[4]+items[5])
  self.assertEqual((assembler.stats['records_lost'],assembler.stats['pictures_skipped']),(1,1))
  # Without a keyframe for three seconds, the pictures are shown anyway.
  for f in udp_video.encode(7,record(1,b'gap'),0)[:0]:assembler.add(f)
  clock[0]=2.0
  for f in udp_video.encode(8,record(1,b'still no key'),0):assembler.add(f)
  clock[0]=2.1;assembler.poll();assembler.take()
  clock[0]=5.5
  for f in udp_video.encode(9,record(1,b'shown'),0):assembler.add(f)
  self.assertEqual(assembler.take(),record(1,b'shown'))

 def test_fragments_that_are_not_well_formed_are_refused(self):
  assembler=udp_video.Assembler();good=udp_video.encode(0,b'x'*3000,20)
  bad=[good[0][:10],b'\0'*16,good[0][:13]+b'\x02'+good[0][14:],good[0][:11]+b'\x05'+good[0][12:],good[0]+b'more']
  for f in bad:assembler.add(f)
  self.assertEqual(assembler.stats['refused'],len(bad));self.assertEqual(assembler.take(),b'')

 def test_the_away_rules(self):
  ip=lambda text:struct.unpack('>I',socket.inet_aton(text))[0]
  for text in ('10.1.2.3','172.16.0.1','172.31.255.254','192.168.1.50','169.254.9.9','127.0.0.1','100.64.0.1','100.127.255.255'):self.assertTrue(self.lib.pb_away_local(ip(text)),text)
  for text in ('8.8.8.8','172.32.0.1','172.15.255.255','192.169.0.1','100.128.0.1','100.63.255.255','1.1.1.1'):self.assertFalse(self.lib.pb_away_local(ip(text)),text)
  self.assertTrue(self.lib.pb_away_admit(1,ip('8.8.8.8')));self.assertFalse(self.lib.pb_away_admit(0,ip('8.8.8.8')));self.assertTrue(self.lib.pb_away_admit(0,ip('192.168.1.20')))
  self.assertEqual([self.lib.pb_away_hours(f) for f in (1,1|6<<8,1|200<<8,1|72<<8)],[12,6,72,72])
  self.assertEqual([self.lib.pb_away_on(k,f) for k,f in ((1,1),(0,1),(1,0),(1,0x601))],[1,0,0,1])
  # The first report within 10 s of the start, then one at least every 8 s.
  self.assertEqual([self.lib.pb_away_heard(n,1000,h) for n,h in ((10999,0),(11000,0),(12999,5000),(13000,5000))],[1,0,1,0])

 def test_a_stream_over_udp_on_this_pc_arrives_whole_with_one_datagram_in_ten_lost(self):
  key=os.urandom(32);ns=os.urandom(16);nc=os.urandom(16);self.lib.pb_udp_keys(key,ns,nc)
  out,into=secure_link.keys(key,secure_link.VIDEO_UDP,ns,nc)
  payload=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);payload.bind(('127.0.0.1',0));payload.settimeout(.05)
  tcp_payload,tcp_pc=socket.socketpair()
  # No keyframe wait here: every record that came whole is counted.
  video=udp_video.UdpVideo(tcp_pc,payload.getsockname(),(out,into),bind=('127.0.0.1',0));video.settimeout(5)
  rng=random.Random(3);records=[]
  for n in range(40):
   kind=2 if n%3==2 else 1;body=(b'K' if n%15==0 else b'P')+bytes(rng.getrandbits(8) for _ in range(rng.choice((200,4000,30000,90000))))
   records.append(b'PSAV'+bytes((1,kind,0,0))+struct.pack('<IQQI',len(body),n,n,0)+body)
  got=[];state=(ctypes.c_uint32*6)();stop=threading.Event();heard=[]
  def console():
   # Waits for the PC's first report, as the payload does, then streams with the parity it asks for, losing one datagram in ten.
   peer=None;loss=random.Random(11)
   while peer is None and not stop.is_set():
    try:data,peer_at=payload.recvfrom(256)
    except socket.timeout:continue
    with self.lock:taken=self.lib.pb_udp_take(data,len(data),struct.unpack('<I',socket.inet_aton(peer_at[0]))[0],socket.htons(peer_at[1]),2000,state)
    if taken:peer=peer_at;heard.append(list(state))
   for r in records:
    for d in self.sealed(r):
     if loss.random()>=.1:payload.sendto(d,peer)
    time.sleep(.005)
  thread=threading.Thread(target=console,daemon=True);thread.start()
  try:
   data=b''
   want=sum(len(r) for r in records)
   end=time.monotonic()+20
   while len(data)<want and time.monotonic()<end:
    try:part=video.recv(65536)
    except socket.timeout:break
    if not part:break
    data+=part
   stats=video.stats()
  finally:
   stop.set();thread.join(5);video.close();payload.close();tcp_payload.close()
  self.assertEqual(heard[0][:2],[udp_video.START_PERCENT,1],'the report gave the parity and the address')
  # With 20 % parity and 10 % loss nearly every block comes back; whatever was lost left only whole records, in order.
  at=0;delivered=[]
  while at<len(data):
   size=struct.unpack_from('<I',data,at+8)[0];delivered.append(data[at:at+32+size]);at+=32+size
  self.assertTrue(all(d in records for d in delivered))
  self.assertEqual(delivered,[r for r in records if r in delivered])
  self.assertGreaterEqual(len(delivered),36,stats);self.assertGreater(stats['blocks_rebuilt'],0,stats)

 def test_a_datagram_seen_before_or_sealed_with_another_key_is_not_taken(self):
  key=os.urandom(32);ns=os.urandom(16);nc=os.urandom(16);self.lib.pb_udp_keys(key,ns,nc)
  out,into=secure_link.keys(key,secure_link.VIDEO_UDP,ns,nc);state=(ctypes.c_uint32*6)()
  head=b'PBX1'+struct.pack('<Q',out.count);report=head+out.seal(head,udp_video.REPORT.pack(b'PBH1',35,1,0))
  with self.lock:
   self.assertEqual(self.lib.pb_udp_take(report,len(report),0x0100007f,0x1234,3000,state),1);self.assertEqual(state[0],35)
   self.assertEqual(self.lib.pb_udp_take(report,len(report),0x0100007f,0x1234,3001,state),0)
  other,_=secure_link.keys(os.urandom(32),secure_link.VIDEO_UDP,ns,nc);head=b'PBX1'+struct.pack('<Q',5)
  forged=head+other.seal(head,udp_video.REPORT.pack(b'PBH1',90,0,0),5)
  with self.lock:self.assertEqual(self.lib.pb_udp_take(forged,len(forged),0x0100007f,0x1234,3002,state),0);self.assertEqual(state[0],35)
  # The PC's side: a sealed fragment taken once, a replay of it refused.
  tcp_a,tcp_b=socket.socketpair()
  video=udp_video.UdpVideo(tcp_b,('127.0.0.1',9),(out,into),bind=('127.0.0.1',0))
  try:
   d=self.sealed(b'PSAV'+bytes(28)+b'abc')[0]
   self.assertIsNotNone(video._open(d));self.assertIsNone(video._open(d))
  finally:video.close();tcp_a.close()

 def test_the_app_away_from_home_streams_over_udp_from_a_payload_that_holds_its_key(self):
  # The real app, headless and away from home (a loopback console is never found on the network), against a stand-in payload: the
  # handshake in Python as the payload does it, the stream sealed by the payload's own C, one datagram in twenty lost.
  import argparse
  from unittest.mock import patch
  import playbridge as core
  from media_fixture import packets
  key=os.urandom(32);ns=os.urandom(16)
  tcp=socket.socket();tcp.bind(('127.0.0.1',0));port=tcp.getsockname()[1];tcp.listen(1);tcp.settimeout(10)
  udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);udp.bind(('127.0.0.1',port));udp.settimeout(.05)
  media=packets(3);seen={}
  def wire(kind,data,pts=0,dts=0):return struct.pack('<4sBBHIQQI',b'PSAV',1,kind,0,len(data),pts,dts,0)+data
  def payload():
   conn,_=tcp.accept();conn.settimeout(10)
   try:
    conn.sendall(b'PBK1'+bytes((1,secure_link.VIDEO,0,0))+ns);answer=secure_link.read_exact(conn,52);nc=answer[4:20]
    seen['proof']=answer[:4]==b'PBK2' and answer[20:]==secure_link.derive(key,'PlayBridge 1 client',secure_link.VIDEO,ns,nc)
    conn.sendall(b'PBK3'+secure_link.derive(key,'PlayBridge 1 server',secure_link.VIDEO,ns,nc))
    into,out=secure_link.keys(key,secure_link.VIDEO,ns,nc)
    head=secure_link.read_exact(conn,4);seen['request']=struct.unpack('<4sIII',into.open(head,secure_link.read_exact(conn,struct.unpack('<I',head)[0]+16)))
    with self.lock:self.lib.pb_udp_keys(key,ns,nc)
    state=(ctypes.c_uint32*6)();peer=None;end=time.monotonic()+5
    while peer is None and time.monotonic()<end:
     try:data,peer_at=udp.recvfrom(256)
     except socket.timeout:continue
     with self.lock:taken=self.lib.pb_udp_take(data,len(data),struct.unpack('<I',socket.inet_aton(peer_at[0]))[0],socket.htons(peer_at[1]),2000,state)
     if taken:peer=peer_at
    seen['peer']=peer is not None
    ack=dict(protocol=2,confirmed=True,fps_target=60,bitrate_target=8000000,resource_profile=14,resolution=4,resolution_requested=4,output_mode=16,refused_by=0,transport='udp',away=12)
    conn.sendall(secure_link.seal_record(out,wire(3,json.dumps(ack).encode())))
    loss=random.Random(5)
    for kind,data,pts,dts in media:
     for d in self.sealed(wire(kind,data,pts,dts)):
      if loss.random()>=.05:udp.sendto(d,peer)
     time.sleep(.004)
    time.sleep(.5)
   finally:conn.close()
  thread=threading.Thread(target=payload,daemon=True);thread.start()
  away=dict(on=True,method='manual',address='127.0.0.1',first=port,hours=12,transport='udp',profile='balanced')
  real=core.config
  p=core.Player(argparse.Namespace(renderer='gdi',profile='uhd_maximum',auto_reconnect=False,device=None,connect_only=False,host='127.0.0.1',record=False,preview=False,headless=True,seconds=0))
  p.payload_pairing.key=lambda:key
  try:
   with patch.object(core,'config',lambda:{**real(),'away':away,'ps5_notices':False}):p.network_session()
  finally:thread.join(10);tcp.close();udp.close()
  self.assertTrue(seen.get('proof'),'the app proved this PC\'s key');self.assertTrue(seen.get('peer'),'its reports reached the payload')
  self.assertEqual(seen['request'],(b'PBO1',60,8000000,core.UDP_FLAG),'the away quality and UDP were asked for, not the home 4K profile')
  self.assertTrue(p.away_active);self.assertEqual(p.capture_info.get('transport'),'udp')
  self.assertIn('Picture and sound over UDP, with error correction',[text for _,text in p.events])
  self.assertGreater(p.stats['video_decoded'],60,p.stats);self.assertGreater(p.stats['audio_packets'],20,p.stats)
  self.assertEqual(p.snapshot()['away']['active'],True)

 def test_the_report_format(self):
  percent=ctypes.c_uint()
  self.assertEqual(self.lib.pb_report(udp_video.REPORT.pack(b'PBH1',40,0,0),16,ctypes.byref(percent)),1);self.assertEqual(percent.value,40)
  self.assertEqual(self.lib.pb_report(udp_video.REPORT.pack(b'PBH1',255,0,0),16,ctypes.byref(percent)),1);self.assertEqual(percent.value,100)
  self.assertEqual(self.lib.pb_report(udp_video.REPORT.pack(b'PBH2',40,0,0),16,ctypes.byref(percent)),0)
  self.assertEqual(self.lib.pb_report(udp_video.REPORT.pack(b'PBH1',40,0,0),15,ctypes.byref(percent)),0)

class PcSideTests(unittest.TestCase):
 def test_the_parity_asked_for_follows_the_worst_second(self):
  self.assertEqual(udp_video.wanted_percent([]),10);self.assertEqual(udp_video.wanted_percent([0.0,0.0]),10)
  self.assertEqual(udp_video.wanted_percent([0.0,0.05]),25);self.assertEqual(udp_video.wanted_percent([0.5]),60)
 def test_the_loss_comes_from_the_datagram_numbers(self):
  loss=udp_video.Loss()
  for count in (10,11,13,14,19):loss.add(count)
  self.assertAlmostEqual(loss.share(),0.5);self.assertEqual(udp_video.Loss().share(),0.0)
 def test_a_closed_tcp_connection_ends_the_stream_after_what_arrived(self):
  tcp_a,tcp_b=socket.socketpair();out,into=secure_link.keys(os.urandom(32),secure_link.VIDEO_UDP,os.urandom(16),os.urandom(16))
  video=udp_video.UdpVideo(tcp_b,('127.0.0.1',9),(out,into),bind=('127.0.0.1',0));video.settimeout(3)
  try:
   tcp_a.close();self.assertEqual(video.recv(10),b'')
  finally:video.close()
 def test_nothing_arriving_times_out_as_a_socket_would(self):
  tcp_a,tcp_b=socket.socketpair();out,into=secure_link.keys(os.urandom(32),secure_link.VIDEO_UDP,os.urandom(16),os.urandom(16))
  video=udp_video.UdpVideo(tcp_b,('127.0.0.1',9),(out,into),bind=('127.0.0.1',0));video.settimeout(.3)
  try:
   with self.assertRaises(socket.timeout):video.recv(10)
  finally:video.close();tcp_a.close()
 def test_reports_come_quickly_until_the_payload_is_heard(self):
  # The payload waits for the first report before its capture starts (payload/away-rules.h), and may open its port after the PC's
  # first reports went out; so until a datagram arrives they go every FIRST_REPORT_EVERY, not every REPORT_EVERY.
  self.assertLess(udp_video.FIRST_REPORT_EVERY,udp_video.REPORT_EVERY)
  rules=(ROOT/'payload'/'away-rules.h').read_text(encoding='utf8')
  self.assertGreaterEqual(int(re.search(r'#define UDP_FIRST_REPORT_WAIT_MS (\d+)u',rules).group(1)),4*udp_video.REPORT_EVERY*1000)
  tcp_a,tcp_b=socket.socketpair();out,into=secure_link.keys(os.urandom(32),secure_link.VIDEO_UDP,os.urandom(16),os.urandom(16))
  payload=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);payload.bind(('127.0.0.1',0));payload.settimeout(.05)
  video=udp_video.UdpVideo(tcp_b,payload.getsockname(),(out,into),bind=('127.0.0.1',0))
  try:
   reports=0;end=time.monotonic()+.5
   while time.monotonic()<end:
    try:payload.recvfrom(256);reports+=1
    except socket.timeout:pass
   self.assertGreaterEqual(reports,6)
  finally:video.close();tcp_a.close();payload.close()

if __name__=='__main__':unittest.main()
