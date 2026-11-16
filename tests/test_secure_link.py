"""The secured link: the payload's C (payload/secure-rules.h, built here as a DLL) against the published SHA-256, HMAC and AES-GCM test
vectors and against Windows' own AES-GCM, then the PC side (app/secure_link.py) against that same C: the handshake both ways, records
both ways, a wrong key, a replayed datagram, a payload without a key, and the key written into a payload."""
import ctypes,hashlib,hmac,os,shutil,socket,struct,subprocess,sys,tempfile,threading,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
import secure_link

HARNESS=r'''
#include <stddef.h>
#include <stdint.h>
void*memcpy(void*d,const void*s,size_t n){char*a=d;const char*b=s;while(n--)*a++=*b++;return d;}
void*memset(void*d,int c,size_t n){char*a=d;while(n--)*a++=(char)c;return d;}
#include "secure-rules.h"
#define OUT __declspec(dllexport)
OUT void pb_sha(const unsigned char*p,size_t n,unsigned char*out){struct secure_sha s;secure_sha_init(&s);secure_sha_add(&s,p,n);secure_sha_end(&s,out);}
OUT void pb_hmac(const unsigned char*k,size_t kn,const unsigned char*p,size_t n,unsigned char*out){struct secure_hmac m;secure_hmac_init(&m,k,kn);secure_sha_add(&m.inner,p,n);secure_hmac_end(&m,out);}
OUT void pb_derive(const unsigned char*k,const char*label,int channel,const unsigned char*ns,const unsigned char*nc,unsigned char*out){secure_derive(k,label,channel,ns,nc,out);}
static struct secure_gcm gcm;
OUT void pb_seal(const unsigned char*k,const unsigned char*iv,const unsigned char*aad,size_t an,const unsigned char*in,size_t n,unsigned char*out,unsigned char*tag){secure_gcm_init(&gcm,k);secure_gcm_seal(&gcm,iv,aad,an,in,n,out,tag);}
OUT int pb_open(const unsigned char*k,const unsigned char*iv,const unsigned char*aad,size_t an,const unsigned char*in,size_t n,const unsigned char*tag,unsigned char*out){secure_gcm_init(&gcm,k);return secure_gcm_open(&gcm,iv,aad,an,in,n,tag,out);}
static struct secure_dir from_pc,to_pc;
OUT void pb_hello(unsigned char*out,int channel,const unsigned char*ns){secure_hello(out,channel,ns);}
OUT int pb_answer(const unsigned char*k,int channel,const unsigned char*ns,const unsigned char*in,unsigned char*proof){return secure_check_answer(k,channel,ns,in,&from_pc,&to_pc,proof);}
OUT size_t pb_seal_record(const unsigned char*in,uint32_t n,unsigned char*out){return secure_seal_record(&to_pc,in,n,out);}
OUT uint32_t pb_record_length(const unsigned char*head){return secure_record_length(head);}
OUT int pb_open_record(unsigned char*rec,uint32_t n){return secure_open_record(&from_pc,rec,n);}
OUT int pb_pad_hello(const unsigned char*k,const unsigned char*in,size_t n,const unsigned char*ns,unsigned char*reply){return secure_pad_hello(k,in,n,ns,reply,&from_pc,&to_pc);}
OUT size_t pb_seal_datagram(const unsigned char*in,size_t n,unsigned char*out){return secure_seal_datagram(&to_pc,in,n,out);}
OUT long pb_open_datagram(unsigned char*w,size_t n){return secure_open_datagram(&from_pc,w,n);}
OUT int pb_key_of(const unsigned char*slot,unsigned char*key,uint32_t*flags){return secure_key_of(slot,key,flags);}
'''
def compiler():
 found=shutil.which('clang')
 if found:return found
 default=Path(os.environ.get('LLVM_BIN',r'C:\Program Files\LLVM\bin'))/'clang.exe'
 return str(default) if default.is_file() else None

def read_exact(sock,size):
 data=b''
 while len(data)<size:
  part=sock.recv(size-len(data))
  if not part:raise EOFError
  data+=part
 return data

@unittest.skipUnless(os.name=='nt' and compiler(),'needs clang on Windows')
class PayloadCryptoTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  # Windows can hold the DLL's file a moment after it is unloaded: a folder left behind is no failure.
  cls.tmp=tempfile.TemporaryDirectory(ignore_cleanup_errors=True);source=Path(cls.tmp.name)/'harness.c';source.write_text(HARNESS,encoding='ascii');out=Path(cls.tmp.name)/'secure.dll'
  subprocess.run([compiler(),'--target=x86_64-pc-windows-msvc','-O2','-ffreestanding','-fno-builtin','-nostdlib','-shared','-fuse-ld=lld','-Wl,/noentry','-Wall','-Wextra','-Werror','-I',str(ROOT/'payload'),str(source),'-o',str(out)],check=True)
  cls.lib=ctypes.WinDLL(str(out))
  for name in ('pb_seal_record','pb_seal_datagram'):getattr(cls.lib,name).restype=ctypes.c_size_t
  cls.lib.pb_record_length.restype=ctypes.c_uint32;cls.lib.pb_open_datagram.restype=ctypes.c_long
  cls.lib.pb_seal_record.argtypes=[ctypes.c_char_p,ctypes.c_uint32,ctypes.c_char_p];cls.lib.pb_open_record.argtypes=[ctypes.c_char_p,ctypes.c_uint32]
  cls.lib.pb_seal_datagram.argtypes=[ctypes.c_char_p,ctypes.c_size_t,ctypes.c_char_p];cls.lib.pb_open_datagram.argtypes=[ctypes.c_char_p,ctypes.c_size_t]
  cls.lib.pb_pad_hello.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_size_t,ctypes.c_char_p,ctypes.c_char_p]
  for name in ('pb_sha',):getattr(cls.lib,name).argtypes=[ctypes.c_char_p,ctypes.c_size_t,ctypes.c_char_p]
  cls.lib.pb_hmac.argtypes=[ctypes.c_char_p,ctypes.c_size_t,ctypes.c_char_p,ctypes.c_size_t,ctypes.c_char_p]
  cls.lib.pb_seal.argtypes=[ctypes.c_char_p]*3+[ctypes.c_size_t,ctypes.c_char_p,ctypes.c_size_t,ctypes.c_char_p,ctypes.c_char_p]
  cls.lib.pb_open.argtypes=[ctypes.c_char_p]*3+[ctypes.c_size_t,ctypes.c_char_p,ctypes.c_size_t,ctypes.c_char_p,ctypes.c_char_p]
 @classmethod
 def tearDownClass(cls):
  ctypes.windll.kernel32.FreeLibrary.argtypes=[ctypes.c_void_p];ctypes.windll.kernel32.FreeLibrary(cls.lib._handle);cls.tmp.cleanup()
 def sha(self,data):out=ctypes.create_string_buffer(32);self.lib.pb_sha(data,len(data),out);return out.raw
 def seal(self,key,iv,aad,data):
  out=ctypes.create_string_buffer(max(1,len(data)));tag=ctypes.create_string_buffer(16);self.lib.pb_seal(key,iv,aad,len(aad),data,len(data),out,tag)
  return out.raw[:len(data)],tag.raw
 def open(self,key,iv,aad,data,tag):
  out=ctypes.create_string_buffer(max(1,len(data)));ok=self.lib.pb_open(key,iv,aad,len(aad),data,len(data),tag,out);return out.raw[:len(data)] if ok else None
 def test_sha256_and_hmac_match_the_standards(self):
  self.assertEqual(self.sha(b'abc').hex(),'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
  self.assertEqual(self.sha(b'').hex(),'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')
  for size in (55,56,63,64,65,119,120,1000):
   data=os.urandom(size);self.assertEqual(self.sha(data),hashlib.sha256(data).digest(),size)
  # RFC 4231, test case 2.
  out=ctypes.create_string_buffer(32);self.lib.pb_hmac(b'Jefe',4,b'what do ya want for nothing?',28,out)
  self.assertEqual(out.raw.hex(),'5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843')
  key=os.urandom(32);data=os.urandom(300);self.lib.pb_hmac(key,32,data,300,out);self.assertEqual(out.raw,hmac.new(key,data,hashlib.sha256).digest())
  ns,nc=os.urandom(16),os.urandom(16);self.lib.pb_derive(key,b'PlayBridge 1 c2s',2,ns,nc,out)
  self.assertEqual(out.raw,secure_link.derive(key,'PlayBridge 1 c2s',2,ns,nc))
 def test_aes_gcm_matches_the_published_vectors(self):
  # The GCM specification's test cases 13 and 14 (AES-256, all-zero key and nonce).
  zero=bytes(32);iv=bytes(12)
  self.assertEqual(self.seal(zero,iv,b'',b''),(b'',bytes.fromhex('530f8afbc74536b9a963b4f1c4cb738b')))
  self.assertEqual(self.seal(zero,iv,b'',bytes(16)),(bytes.fromhex('cea7403d4d606b6e074ec5d3baf39d18'),bytes.fromhex('d0d1c8a799996bf0265b98b5d48ab919')))
 @unittest.skipUnless(secure_link.available(),'no AES-GCM on this PC')
 def test_aes_gcm_agrees_with_this_pcs_own(self):
  for size in (0,1,15,16,17,31,32,33,255,4096,65536,70001):
   key,iv,aad,data=os.urandom(32),os.urandom(12),os.urandom(size%23),os.urandom(size)
   sealed,tag=self.seal(key,iv,aad,data);handle=secure_link.BACKEND.key(key)
   try:
    if data:self.assertEqual(sealed+tag,secure_link.BACKEND.seal(handle,iv,aad,data),size)
    self.assertEqual(self.open(key,iv,aad,sealed,tag),data)
    if data:self.assertEqual(secure_link.BACKEND.open(handle,iv,aad,sealed+tag),data)
   finally:secure_link.BACKEND.drop(handle)
   # One bit changed anywhere, or another nonce or header, and nothing opens.
   if data:self.assertIsNone(self.open(key,iv,aad,bytes([sealed[0]^1])+sealed[1:],tag))
   self.assertIsNone(self.open(key,iv,aad,sealed,tag[:15]+bytes([tag[15]^0x80])))
   self.assertIsNone(self.open(key,os.urandom(12),aad,sealed,tag))
   self.assertIsNone(self.open(key,iv,aad+b'x',sealed,tag))
 def payload(self,conn,key,channel,results,messages=1,answer_with=None):
  """What the payload does with a connection, on its thread: the hello, the PC's answer, then records."""
  try:
   ns=os.urandom(16);hello=ctypes.create_string_buffer(24);self.lib.pb_hello(hello,channel,ns);conn.sendall(hello.raw)
   answer=read_exact(conn,52);proof=ctypes.create_string_buffer(36)
   if not self.lib.pb_answer(key,channel,ns,answer,proof):results.append('refused');conn.close();return
   conn.sendall(proof.raw)
   for _ in range(messages):
    head=read_exact(conn,4);size=self.lib.pb_record_length(head)
    if not size:results.append('bad length');return
    record=ctypes.create_string_buffer(head+read_exact(conn,size+16),4+size+16)
    if not self.lib.pb_open_record(record,size):results.append('did not open');return
    results.append(record.raw[4:4+size])
   for reply in (answer_with or []):
    # As the payload writes: records of at most 64 KiB, each sent in two halves with a pause, as a slow network would.
    for at in range(0,len(reply),65536):
     part=reply[at:at+65536];out=ctypes.create_string_buffer(len(part)+20);n=self.lib.pb_seal_record(part,len(part),out)
     conn.sendall(out.raw[:n//2]);time.sleep(.15);conn.sendall(out.raw[n//2:n])
  except (OSError,EOFError) as error:results.append(repr(error))
  finally:conn.close()
 @unittest.skipUnless(secure_link.available(),'no AES-GCM on this PC')
 def test_the_pc_and_the_payload_agree_both_ways(self):
  key=os.urandom(32);results=[];pc,ps5=socket.socketpair()
  reply=os.urandom(150000)
  thread=threading.Thread(target=self.payload,args=(ps5,key,secure_link.VIDEO,results,2,[b'PSAV'+bytes(28),reply]));thread.start()
  with secure_link.SecureSocket(pc,key,secure_link.VIDEO) as link:
   link.sendall(b'PBO1'+bytes(12));link.sendall(b'x'*70000)
   link.settimeout(.05);got=b''
   # A read that times out in the middle of a record goes on where it was.
   timeouts=0
   while len(got)<32+len(reply):
    try:part=link.recv(32+len(reply)-len(got))
    except socket.timeout:timeouts+=1;continue
    self.assertTrue(part);got+=part
  thread.join(5)
  self.assertEqual(results[:2],[b'PBO1'+bytes(12),b'x'*65536]);self.assertEqual(got,b'PSAV'+bytes(28)+reply);self.assertGreater(timeouts,0)
 @unittest.skipUnless(secure_link.available(),'no AES-GCM on this PC')
 def test_another_key_or_another_port_is_refused(self):
  key=os.urandom(32);results=[];pc,ps5=socket.socketpair()
  thread=threading.Thread(target=self.payload,args=(ps5,key,secure_link.CONTROL,results));thread.start()
  with self.assertRaisesRegex(secure_link.SecureError,'another PC'):secure_link.SecureSocket(pc,os.urandom(32),secure_link.CONTROL)
  thread.join(5);pc.close();self.assertEqual(results,['refused'])
  pc,ps5=socket.socketpair();results=[]
  thread=threading.Thread(target=self.payload,args=(ps5,key,secure_link.MIC,results));thread.start()
  with self.assertRaisesRegex(secure_link.SecureError,'another port'):secure_link.SecureSocket(pc,key,secure_link.CONTROL)
  pc.close();thread.join(5)
  # A payload without a key says nothing first: the PC gives up after its wait.
  pc,ps5=socket.socketpair()
  with self.assertRaises((socket.timeout,TimeoutError)):secure_link.SecureSocket(pc,key,secure_link.VIDEO,timeout=.2)
  pc.close();ps5.close()
 @unittest.skipUnless(secure_link.available(),'no AES-GCM on this PC')
 def test_controller_datagrams_hello_then_sealed_and_never_twice(self):
  key=os.urandom(32);clock=[100.0];link=secure_link.PadLink(lambda:key,lambda:clock[0])
  state=b'PBP1'+bytes(16);first=link.datagrams(state)
  self.assertEqual(first[0],state,'until the companion is known, the state goes as it is too');self.assertEqual(first[1][:4],b'PBK4')
  hello=first[1];ns=os.urandom(16);reply=ctypes.create_string_buffer(68)
  self.assertTrue(self.lib.pb_pad_hello(key,hello,len(hello),ns,reply))
  self.assertIsNone(link.take(reply.raw));self.assertTrue(link.sealed())
  sealed=link.datagrams(state);self.assertEqual(len(sealed),1);self.assertEqual(sealed[0][:4],b'PBX1')
  w=ctypes.create_string_buffer(sealed[0],len(sealed[0]));self.assertEqual(self.lib.pb_open_datagram(w,len(sealed[0])),20);self.assertEqual(w.raw[12:32],state)
  # The same datagram again is one seen before.
  w=ctypes.create_string_buffer(sealed[0],len(sealed[0]));self.assertEqual(self.lib.pb_open_datagram(w,len(sealed[0])),-1)
  status=b'PBS2'+bytes(16);out=ctypes.create_string_buffer(64);n=self.lib.pb_seal_datagram(status,20,out)
  self.assertEqual(link.take(out.raw[:n]),status);self.assertIsNone(link.take(out.raw[:n]),'a status answer seen before')
  self.assertIsNone(link.take(b'PBS2'+bytes(16)),'a plain answer is not taken once sealed')
  # A companion that went quiet is asked again; another PC's companion proves another key.
  clock[0]+=secure_link.PAD_SILENT+1;again=link.datagrams(state);self.assertEqual([d[:4] for d in again],[b'PBP1',b'PBK4'])
  other=ctypes.create_string_buffer(68);self.lib.pb_pad_hello(os.urandom(32),again[1],20,ns,other)
  self.assertIsNone(link.take(other.raw));self.assertTrue(link.foreign);clock[0]+=1;self.assertEqual([d[:4] for d in link.datagrams(state)],[b'PBK4'],'nothing for another PC\'s companion')
 @unittest.skipUnless(secure_link.available(),'no AES-GCM on this PC')
 def test_the_pc_controller_plays_through_a_companion_that_holds_the_key(self):
  import pad_input
  from unittest import mock
  key=os.urandom(32);companion=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);companion.bind(('127.0.0.1',0));companion.settimeout(2)
  bridge=pad_input.PadBridge(lambda:'127.0.0.1',threading.Event(),key=lambda:key)
  with companion,mock.patch.object(pad_input,'PAD_PORT',companion.getsockname()[1]),socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
   udp.bind(('127.0.0.1',0));udp.setblocking(False)
   # The probe goes as it is and with a hello; the companion, which holds the key, answers the hello only.
   self.assertTrue(bridge.put(udp,pad_input.PROBE))
   plain,sender=companion.recvfrom(128);hello,_=companion.recvfrom(128)
   self.assertEqual((plain,hello[:4]),(pad_input.PROBE,b'PBK4'))
   reply=ctypes.create_string_buffer(68);self.assertTrue(self.lib.pb_pad_hello(key,hello,len(hello),os.urandom(16),reply));companion.sendto(reply.raw,sender)
   time.sleep(.1);bridge.listen(udp,1.0);self.assertTrue(bridge.wire_link.sealed())
   state=pad_input.PadState(pad_input.CROSS,10,20,30,40,50,60);bridge.send(state,1.0,udp)
   sealed,_=companion.recvfrom(128);w=ctypes.create_string_buffer(sealed,len(sealed))
   self.assertEqual(self.lib.pb_open_datagram(w,len(sealed)),20);self.assertEqual(w.raw[12:32],pad_input.wire(0,state))
   status=pad_input.status_wire(pad_input.READY,0,0,1);out=ctypes.create_string_buffer(64);n=self.lib.pb_seal_datagram(status,20,out);companion.sendto(out.raw[:n],sender)
   time.sleep(.1);bridge.listen(udp,1.1);self.assertEqual(bridge.answer,(pad_input.READY,0,0,1));self.assertEqual(bridge.player(),1)
 def test_a_companion_without_a_key_plays_as_before(self):
  link=secure_link.PadLink(lambda:bytes(32),lambda:5.0);state=b'PBP1'+bytes(16)
  self.assertEqual(link.datagrams(state)[0],state);status=b'PBS2'+bytes(16)
  self.assertEqual(link.take(status),status);self.assertEqual(link.mode,'plain');self.assertEqual(link.datagrams(state),[state])
  self.assertEqual(secure_link.PadLink().datagrams(state),[state],'no key: nothing but the state')
 def test_the_key_goes_into_the_slot_once(self):
  key=os.urandom(32);elf=b'\x7fELF'+os.urandom(100)+secure_link.SLOT_MAGIC+bytes(48)+os.urandom(50)
  stamped,done=secure_link.stamp(elf,key,secure_link.FLAG_AWAY);self.assertTrue(done);self.assertEqual(len(stamped),len(elf))
  at=elf.find(secure_link.SLOT_MAGIC);slot=stamped[at:at+64];found=ctypes.create_string_buffer(32);flags=ctypes.c_uint32()
  self.assertTrue(self.lib.pb_key_of(slot,found,ctypes.byref(flags)));self.assertEqual((found.raw,flags.value),(key,1))
  self.assertFalse(self.lib.pb_key_of(elf[at:at+64],found,ctypes.byref(flags)),'an empty slot holds no key')
  self.assertEqual(secure_link.stamp(stamped,key),(stamped,False),'a slot already written is not written again')
  self.assertEqual(secure_link.stamp(elf+elf,key),(elf+elf,False),'two slots: which one the payload reads is not known')
  self.assertEqual(secure_link.stamp(b'\x7fELF'+bytes(300),key),(b'\x7fELF'+bytes(300),False),'an older payload has no slot')

class PairingTests(unittest.TestCase):
 def test_the_key_is_made_once_and_kept_sealed(self):
  kept={};pairing=secure_link.Pairing(lambda:kept.get('key',''),lambda text:kept.__setitem__('key',text),lambda text:'sealed:'+text,lambda text:text[7:] if text.startswith('sealed:') else '')
  key=pairing.key();self.assertEqual(len(key),32);self.assertEqual(kept['key'],'sealed:'+key.hex())
  again=secure_link.Pairing(lambda:kept['key'],lambda text:None,lambda text:'sealed:'+text,lambda text:text[7:]);self.assertEqual(again.key(),key)
  # Sealed by another Windows user: unreadable here, so a new key is made.
  other=secure_link.Pairing(lambda:'sealed:'+key.hex(),lambda text:kept.__setitem__('key',text),lambda text:'sealed:'+text,lambda text:'');self.assertNotEqual(other.key(),key)
 def test_connections_are_plain_until_a_payload_with_the_key_runs(self):
  server=socket.socket();server.bind(('127.0.0.1',0));server.listen(1);port=server.getsockname()[1]
  pairing=secure_link.Pairing(lambda:'',lambda text:None,lambda text:'',lambda text:'')
  with pairing.connect('127.0.0.1',port,secure_link.CONTROL) as sock:self.assertIsInstance(sock,socket.socket)
  server.accept()[0].close();server.close()

if __name__=='__main__':unittest.main()
