"""Runs the controller companion's loop on the PC, compiled from payload/pad-rules.h without the PS5 SDK. A scripted clock, PC and console
stand in for the real ones, so ten minutes of the loop take a moment."""
import ctypes,os,re,shutil,struct,subprocess,sys,tempfile,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import pad_input as pad

HARNESS=r'''
#include <stddef.h>
#include <stdint.h>
void*memcpy(void*d,const void*s,unsigned long long n){char*a=d;const char*b=s;while(n--)*a++=*b++;return d;}
#include "pad-rules.h"
__declspec(dllexport) int pb_pad(const unsigned char*w,size_t n,uint32_t*q,uint32_t*b,unsigned char*s){return read_pad_wire(w,n,q,b,s);}
__declspec(dllexport) int pb_newer(uint32_t a,uint32_t b){return newer_sequence(a,b);}
__declspec(dllexport) void pb_fill(unsigned char*d,uint32_t b,const unsigned char*s,uint64_t t){fill_pad_data(d,b,s,t);}
__declspec(dllexport) void pb_status(unsigned char*w,uint32_t s,int32_t e,uint32_t q){pad_status_wire(w,s,e,q);}
__declspec(dllexport) void pb_constants(int64_t*o){o[0]=PAD_PORT;o[1]=PAD_WIRE_SIZE;o[2]=PAD_STATUS_SIZE;o[3]=PAD_STARTING;o[4]=PAD_READY;o[5]=PAD_FAILED;o[6]=PAD_START_HUNG;}
/* The PC: each packet arrives at its time, the clock moving on to it, or by the whole wait when none is due. A size below 0 breaks the socket. */
struct fake_packet{uint64_t at;int32_t size;unsigned char data[24];};
struct fake_state{uint64_t at;int32_t state;int32_t error;};
struct fake_answer{uint64_t at;unsigned char wire[16];};
struct fake_insert{uint64_t at;uint32_t buttons;unsigned char sticks[6];unsigned char spare[2];};
static const struct fake_packet*packets;static const struct fake_state*states;static struct fake_answer*answers;static struct fake_insert*inserts;
static int packet_count,next_packet,state_count,answer_room,answer_count,insert_room,insert_count,insert_result;static uint64_t clock_us;
static int fake_receive(unsigned char*w,size_t cap,int timeout_ms){
 uint64_t until=clock_us+(uint64_t)timeout_ms*1000;
 if(next_packet<packet_count&&packets[next_packet].at<=until){
  const struct fake_packet*p=&packets[next_packet++];if(p->at>clock_us)clock_us=p->at;
  if(p->size<0)return -1;
  size_t n=(size_t)p->size<cap?(size_t)p->size:cap;memcpy(w,p->data,n);return (int)n;
 }
 clock_us=until;return 0;
}
static void fake_answer(const unsigned char*w,size_t n){if(answer_count<answer_room){answers[answer_count].at=clock_us;memcpy(answers[answer_count].wire,w,n<16?n:16);}answer_count++;}
static uint64_t fake_now(void){return clock_us;}
/* The console's start-up thread: STARTING until the first scripted change, then the latest one due. */
static int fake_progress(int32_t*error){int state=PAD_STARTING;*error=0;for(int i=0;i<state_count;i++)if(states[i].at<=clock_us){state=states[i].state;*error=states[i].error;}return state;}
static int fake_insert(const unsigned char*r){
 if(insert_count<insert_room){struct fake_insert*i=&inserts[insert_count];i->at=clock_us;memcpy(&i->buttons,r,4);memcpy(i->sticks,r+4,6);}
 insert_count++;return insert_result;
}
__declspec(dllexport) int pb_companion(const struct fake_packet*p,int np,const struct fake_state*s,int ns,int result,struct fake_answer*a,int na,struct fake_insert*i,int ni,uint64_t*out){
 packets=p;packet_count=np;next_packet=0;states=s;state_count=ns;insert_result=result;answers=a;answer_room=na;answer_count=0;inserts=i;insert_room=ni;insert_count=0;clock_us=0;
 struct pad_calls c={fake_receive,fake_answer,fake_now,fake_progress,fake_insert};struct pad_report r={0,0,0,0,0,0,0};
 int end=pad_run(&c,&r);
 out[0]=clock_us;out[1]=(uint64_t)answer_count;out[2]=(uint64_t)insert_count;out[3]=r.packets;out[4]=r.inserted;out[5]=r.neutral;out[6]=r.answers;out[7]=r.ignored;out[8]=r.insert_failed;out[9]=(uint32_t)r.first_insert_error;
 return end;
}
'''
def compiler():
 found=shutil.which('clang')
 if found:return found
 default=Path(os.environ.get('LLVM_BIN',r'C:\Program Files\LLVM\bin'))/'clang.exe'
 return str(default) if default.is_file() else None

class Packet(ctypes.Structure):_fields_=[('at',ctypes.c_uint64),('size',ctypes.c_int32),('data',ctypes.c_ubyte*24)]
class State(ctypes.Structure):_fields_=[('at',ctypes.c_uint64),('state',ctypes.c_int32),('error',ctypes.c_int32)]
class Answer(ctypes.Structure):_fields_=[('at',ctypes.c_uint64),('wire',ctypes.c_ubyte*16)]
class Insert(ctypes.Structure):_fields_=[('at',ctypes.c_uint64),('buttons',ctypes.c_uint32),('sticks',ctypes.c_ubyte*6),('spare',ctypes.c_ubyte*2)]
END_IDLE,END_FAILED,END_SOCKET=1,2,3
HUNG=0x50420004
CENTRED=(128,128,128,128,0,0)

def signed(value):return struct.unpack('<i',struct.pack('<I',value&0xffffffff))[0]
def playing(start,end,every=.05,first=1,state=pad.PadState(pad.CROSS)):
 """The PC sending a held state every so often, as it does while a controller plays, with rising sequences."""
 out=[];at=start;sequence=first
 while at<=end+1e-9:out.append((at,pad.wire(sequence,state)));at=round(at+every,6);sequence+=1
 return out

@unittest.skipUnless(os.name=='nt' and compiler(),'needs clang on Windows')
class CompanionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();source=Path(cls.tmp.name)/'harness.c';source.write_text(HARNESS,encoding='ascii');out=Path(cls.tmp.name)/'companion.dll'
  subprocess.run([compiler(),'--target=x86_64-pc-windows-msvc','-O1','-ffreestanding','-fno-builtin','-nostdlib','-shared','-fuse-ld=lld','-Wl,/noentry','-Wall','-Wextra','-Werror','-I',str(ROOT/'payload'),str(source),'-o',str(out)],check=True)
  cls.lib=ctypes.WinDLL(str(out));cls.lib.pb_fill.argtypes=[ctypes.c_char_p,ctypes.c_uint32,ctypes.c_char_p,ctypes.c_uint64]
 @classmethod
 def tearDownClass(cls):
  # Unload first: Windows keeps a loaded DLL's file locked.
  ctypes.windll.kernel32.FreeLibrary.argtypes=[ctypes.c_void_p];ctypes.windll.kernel32.FreeLibrary(cls.lib._handle);cls.tmp.cleanup()
 def run_companion(self,packets,states=(),insert_result=0):
  """packets: (seconds, bytes) or (seconds, None) for a broken socket. states: (seconds, state, error)."""
  p=(Packet*max(1,len(packets)))()
  for k,(at,data) in enumerate(packets):
   p[k].at=round(at*1e6)
   if data is None:p[k].size=-1
   else:p[k].size=len(data);ctypes.memmove(p[k].data,data,len(data))
  s=(State*max(1,len(states)))()
  for k,(at,state,error) in enumerate(states):s[k].at=round(at*1e6);s[k].state=state;s[k].error=signed(error)
  a=(Answer*4096)();i=(Insert*4096)();out=(ctypes.c_uint64*10)()
  end=self.lib.pb_companion(p,len(packets),s,len(states),insert_result,a,4096,i,4096,out)
  self.assertLessEqual(out[1],4096);self.assertLessEqual(out[2],4096)
  answers=[(a[k].at/1e6,)+pad.read_status(bytes(a[k].wire)) for k in range(out[1])]
  inserts=[(i[k].at/1e6,i[k].buttons,tuple(i[k].sticks)) for k in range(out[2])]
  report=dict(zip(('packets','inserted','neutral','answers','ignored','insert_failed','first_insert_error'),list(out[3:10])))
  return end,out[0]/1e6,answers,inserts,report

 def test_the_c_and_python_sides_agree_on_the_wire(self):
  values=(ctypes.c_int64*7)();self.lib.pb_constants(values)
  self.assertEqual(list(values),[pad.PAD_PORT,len(pad.wire(0,pad.NEUTRAL)),pad.STATUS_SIZE,pad.STARTING,pad.READY,pad.FAILED,HUNG])
  out=ctypes.create_string_buffer(16)
  for state,error,sequence in ((pad.READY,0,7),(pad.FAILED,signed(0x80920001),0xffffffff),(pad.STARTING,HUNG,0)):
   self.lib.pb_status(out,state,error,sequence);self.assertEqual(out.raw,pad.status_wire(state,error,sequence))
  sequence=ctypes.c_uint32();buttons=ctypes.c_uint32();sticks=(ctypes.c_ubyte*6)()
  data=pad.wire(41,pad.PadState(pad.CROSS|pad.R2,lx=10,ly=20,rx=30,ry=40,l2=50,r2=255))
  self.assertTrue(self.lib.pb_pad(data,len(data),ctypes.byref(sequence),ctypes.byref(buttons),sticks))
  self.assertEqual((sequence.value,buttons.value,bytes(sticks)),(41,pad.CROSS|pad.R2,bytes((10,20,30,40,50,255))))
 def test_controller_packets_are_checked_and_masked(self):
  sequence=ctypes.c_uint32();buttons=ctypes.c_uint32();sticks=(ctypes.c_ubyte*6)()
  good=struct.pack('<4sIIBBBBBBH',b'PBP1',7,0xffffffff,1,2,3,4,5,6,0)
  self.assertTrue(self.lib.pb_pad(good,20,ctypes.byref(sequence),ctypes.byref(buttons),sticks))
  self.assertEqual((sequence.value,buttons.value,bytes(sticks)),(7,0x0011fffe,bytes((1,2,3,4,5,6))))
  self.assertFalse(self.lib.pb_pad(good,19,ctypes.byref(sequence),ctypes.byref(buttons),sticks));self.assertFalse(self.lib.pb_pad(b'XXXX'+good[4:],20,ctypes.byref(sequence),ctypes.byref(buttons),sticks))
 def test_an_old_controller_packet_is_not_newer_even_across_the_wrap(self):
  self.assertTrue(self.lib.pb_newer(5,4));self.assertFalse(self.lib.pb_newer(4,5));self.assertFalse(self.lib.pb_newer(4,4));self.assertTrue(self.lib.pb_newer(1,0xffffffff))
 def test_the_pad_record_has_the_layout_the_console_reads(self):
  data=ctypes.create_string_buffer(0x100);self.lib.pb_fill(data,0x4000,bytes((1,2,3,4,5,6)),0x1122334455667788);d=data.raw
  self.assertEqual(struct.unpack_from('<I',d,0)[0],0x4000);self.assertEqual(d[4:10],bytes((1,2,3,4,5,6)))
  self.assertEqual(struct.unpack_from('<4f',d,0xc),(0.0,0.0,0.0,1.0));self.assertEqual(d[0x4c],1);self.assertEqual(struct.unpack_from('<Q',d,0x50)[0],0x1122334455667788)

 def test_it_answers_starting_then_ready_and_hands_states_over_only_once_ready(self):
  sent=playing(.1,3.0)
  end,clock,answers,inserts,report=self.run_companion(sent,[(1.0,pad.READY,0)])
  self.assertEqual(answers[0][:2],(.1,pad.STARTING))
  self.assertTrue(all(state==pad.STARTING for at,state,_,_ in answers if at<1.0))
  first_ready=next(answer for answer in answers if answer[1]==pad.READY)
  # The change is answered with the first packet after it, not after the usual spacing.
  self.assertAlmostEqual(first_ready[0],1.0,places=6)
  self.assertTrue(all(state==pad.READY and error==0 for at,state,error,_ in answers if at>=1.0))
  # At most about ten answers a second, each with the newest sequence taken.
  same=[b[0]-a[0] for a,b in zip(answers,answers[1:]) if a[1]==b[1]];self.assertGreaterEqual(min(same),.1-1e-6)
  for at,_,_,sequence in answers:self.assertEqual(sequence,1+round((at-.1)/.05))
  # Nothing reaches the console before it is ready, then every state does.
  held=[insert for insert in inserts if insert[1]];self.assertEqual(len(held),sum(1 for at,_ in sent if at>=1.0))
  self.assertGreaterEqual(min(at for at,_,_ in held),1.0);self.assertTrue(all(buttons==pad.CROSS for _,buttons,_ in held))
  # When the PC goes quiet, the buttons are let go once.
  self.assertEqual(report['neutral'],1);at,buttons,sticks=inserts[-1]
  self.assertEqual((buttons,sticks),(0,CENTRED));self.assertGreaterEqual(at,3.25);self.assertLess(at,3.35)
  self.assertEqual(end,END_IDLE);self.assertAlmostEqual(clock,3.0+600,delta=.06)
 def test_a_start_up_that_never_returns_is_answered_as_failed_and_the_companion_ends(self):
  end,clock,answers,inserts,_=self.run_companion(playing(0,60))
  # Starting may take 8 s: scePadInit's own Mbus retries take 5 s before it gives up with a code of its own.
  self.assertTrue(all(state==pad.STARTING for at,state,_,_ in answers if at<8))
  self.assertTrue(all((state,error&0xffffffff)==(pad.FAILED,HUNG) for at,state,error,_ in answers if at>=8))
  self.assertEqual(inserts,[])
  # It ends 30 s after failing, even though the PC is still sending.
  self.assertEqual(end,END_FAILED);self.assertAlmostEqual(clock,38,delta=.06)
  # With no PC at all, it ends 10 s after failing.
  end,clock,answers,_,_=self.run_companion([])
  self.assertEqual((end,answers),(END_FAILED,[]));self.assertAlmostEqual(clock,18,delta=.06)
 def test_a_failed_start_is_answered_with_its_code_and_ends_once_the_pc_is_quiet(self):
  end,clock,answers,inserts,_=self.run_companion(playing(0,2),[(.5,pad.FAILED,0x80920001)])
  self.assertEqual(answers[-1][1:3],(pad.FAILED,signed(0x80920001)));self.assertEqual(inserts,[])
  self.assertEqual(end,END_FAILED);self.assertAlmostEqual(clock,12,delta=.06)
 def test_a_start_up_that_comes_back_late_still_counts(self):
  end,clock,answers,inserts,_=self.run_companion(playing(0,13),[(10.0,pad.READY,0)])
  self.assertEqual([state for at,state,_,_ in answers if 8.5<at<9.5],[pad.FAILED]*len([at for at,*_ in answers if 8.5<at<9.5]))
  self.assertEqual(answers[-1][1],pad.READY);self.assertGreaterEqual(min(at for at,_,_ in inserts),10.0)
  self.assertEqual(end,END_IDLE)
 def test_a_refusal_after_the_mbus_retries_keeps_its_own_code(self):
  # scePadInit gives up by itself after its 5 s of Mbus retries: that code reaches the PC, not the companion's own hang code.
  end,clock,answers,inserts,_=self.run_companion(playing(0,8),[(5.2,pad.FAILED,0x809b00ff)])
  self.assertEqual({(state,error&0xffffffff) for at,state,error,_ in answers if at>=5.2},{(pad.FAILED,0x809b00ff)});self.assertEqual(inserts,[])
  self.assertEqual(end,END_FAILED)
 def test_old_packets_are_skipped_and_a_restarted_pc_is_followed(self):
  def state(sequence):return pad.wire(sequence,pad.PadState(lx=sequence*10))
  sent=[(.1,state(5)),(.15,state(6)),(.2,state(4)),(.25,state(7)),(2.0,state(1)),(2.05,state(2))]
  end,clock,answers,inserts,report=self.run_companion(sent,[(0,pad.READY,0)])
  self.assertEqual([sticks[0] for _,_,sticks in inserts],[50,60,70,128,10,20,128])
  # The restarted PC is answered with its own sequence, not the old one's.
  self.assertEqual(report['ignored'],1);self.assertEqual(answers[-1][::3],(2.0,1))
 def test_noise_is_neither_answered_nor_taken_for_the_pc(self):
  good=pad.wire(1,pad.NEUTRAL)
  noise=[(float(k),data) for k in range(20) for data in (good[:19],good+b'\0',b'XXXX'+good[4:])]
  end,clock,answers,inserts,report=self.run_companion(noise,[(0,pad.READY,0)])
  self.assertEqual((answers,inserts,report['packets']),([],[],0))
  self.assertEqual(end,END_IDLE);self.assertAlmostEqual(clock,600,delta=.06)
 def test_a_broken_socket_ends_it_at_once(self):
  end,clock,*_=self.run_companion([(.5,pad.wire(1,pad.NEUTRAL)),(1.0,None),(1.5,pad.wire(2,pad.NEUTRAL))],[(0,pad.READY,0)])
  self.assertEqual(end,END_SOCKET);self.assertAlmostEqual(clock,1.0)
 def test_a_console_that_refuses_the_states_says_so_and_carries_on(self):
  refused=signed(0x80920003)
  end,clock,answers,inserts,report=self.run_companion(playing(0,1),[(0,pad.READY,0)],insert_result=refused)
  self.assertTrue(all((state,error)==(pad.READY,refused) for _,state,error,_ in answers))
  self.assertEqual(report['insert_failed'],len(inserts));self.assertEqual(report['first_insert_error'],0x80920003)
  self.assertEqual(end,END_IDLE)

class PayloadSplitTests(unittest.TestCase):
 """The owner's rule: the controller must never be able to stop the stream, so its code stays out of the video payload."""
 def code(self,name):
  # Comments may name the other payload; the code may not.
  text=(ROOT/'payload'/name).read_text(encoding='utf-8');return re.sub(r'/\*.*?\*/','',text,flags=re.S)
 def test_the_video_payload_holds_no_controller_code(self):
  for name in ('stream-av3.c','console-control.h','control-rules.h','capture-options.h','av-wire.h'):
   code=self.code(name)
   for word in ('scePad','libScePad','PAD_PORT','pad-rules.h','9078'):self.assertNotIn(word,code,(name,word))
 def test_the_companion_stays_off_the_capture_and_the_other_ports(self):
  code=self.code('pad-companion.c')
  for word in ('Avcap','9076','9077','CONTROL_PORT','console-control.h','setsockopt'):self.assertNotIn(word,code,word)
  self.assertIn('#include "pad-rules.h"',code);self.assertIn('htons(PAD_PORT)',code)
  # Start-up runs on its own thread, and the main thread never waits for it.
  self.assertIn('pthread_create(&thread,0,start_pad,0)',code);self.assertNotIn('pthread_join',code)

if __name__=='__main__':unittest.main()
