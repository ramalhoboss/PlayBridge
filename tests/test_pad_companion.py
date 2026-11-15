"""Runs the controller companion's loop on the PC, compiled from payload/pad-rules.h without the PS5 SDK. A scripted clock, senders and
console stand in for the real ones, so ten minutes of the loop take a moment."""
import base64,ctypes,hashlib,os,re,shutil,struct,subprocess,sys,tempfile,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import pad_input as pad

HARNESS=r'''
#include <stddef.h>
#include <stdint.h>
void*memcpy(void*d,const void*s,unsigned long long n){char*a=d;const char*b=s;while(n--)*a++=*b++;return d;}
void*memset(void*d,int v,unsigned long long n){char*a=d;while(n--)*a++=(char)v;return d;}
#include "pad-rules.h"
__declspec(dllexport) int pb_pad(const unsigned char*w,size_t n,uint32_t*q,uint32_t*b,unsigned char*s){return read_pad_wire(w,n,q,b,s);}
__declspec(dllexport) int pb_newer(uint32_t a,uint32_t b){return newer_sequence(a,b);}
__declspec(dllexport) void pb_fill(unsigned char*d,uint32_t b,const unsigned char*s){fill_pad_state(d,b,s);}
__declspec(dllexport) void pb_describe(unsigned char*d,uint32_t user){pad_description(d,user);}
__declspec(dllexport) int pb_quit(const unsigned char*w,size_t n){return is_pad_quit(w,n);}
__declspec(dllexport) void pb_status(unsigned char*w,uint32_t s,int32_t e,uint32_t q,uint32_t p){pad_status_wire(w,s,e,q,p);}
__declspec(dllexport) void pb_constants(int64_t*o){o[0]=PAD_PORT;o[1]=PAD_WIRE_SIZE;o[2]=PAD_STATUS_SIZE;o[3]=PAD_STARTING;o[4]=PAD_READY;o[5]=PAD_FAILED;o[6]=PAD_START_HUNG;o[7]=PAD_QUIT_SIZE;o[8]=PAD_BLOCK_SIZE;o[9]=PAD_SLOTS;o[10]=PAD_FULL;}
/* Where each request keeps its fields: the kernel reads them at these places. */
__declspec(dllexport) void pb_layout(int64_t*o){
 o[0]=sizeof(struct pad_add_request);o[1]=offsetof(struct pad_add_request,description);o[2]=offsetof(struct pad_add_request,handle);
 o[3]=sizeof(struct pad_insert_request);o[4]=offsetof(struct pad_insert_request,state);o[5]=offsetof(struct pad_insert_request,zero);
 o[6]=sizeof(struct pad_delete_request);o[7]=offsetof(struct pad_delete_request,handle);o[8]=PAD_HID_ADD;o[9]=PAD_HID_INSERT;o[10]=PAD_HID_DELETE;
 o[11]=PAD_OP_ADD;o[12]=PAD_OP_DELETE;o[13]=PAD_STEP(PAD_STEP_ADD);o[14]=PAD_ERRNO(13);
}
/* The senders: each packet arrives at its time, the clock moving on to it, or by the whole wait when none is due. A size below 0 breaks
   the socket. The console: the start-up's scripted states, scripted answers to each add (0 makes a controller), and every call noted. */
struct fake_packet{uint64_t at;uint64_t sender;int32_t size;unsigned char data[24];};
struct fake_state{uint64_t at;int32_t state;int32_t error;};
struct fake_answer{uint64_t at;uint64_t sender;unsigned char wire[20];unsigned char spare[4];};
struct fake_insert{uint64_t at;int32_t handle;uint32_t buttons;unsigned char sticks[6];unsigned char spare[2];};
struct fake_event{uint64_t at;int32_t kind;int32_t handle;};
static const struct fake_packet*packets;static const struct fake_state*states;static const int32_t*adds;static struct fake_answer*answers;static struct fake_insert*inserts;static struct fake_event*events;
static int packet_count,next_packet,state_count,add_count,adds_made,answer_room,answer_count,insert_room,insert_count,event_room,event_count,insert_result,next_handle;static uint64_t clock_us;
static int fake_receive(unsigned char*w,size_t cap,int timeout_ms,uint64_t*sender){
 uint64_t until=clock_us+(uint64_t)timeout_ms*1000;
 if(next_packet<packet_count&&packets[next_packet].at<=until){
  const struct fake_packet*p=&packets[next_packet++];if(p->at>clock_us)clock_us=p->at;
  if(p->size<0)return -1;
  *sender=p->sender;size_t n=(size_t)p->size<cap?(size_t)p->size:cap;memcpy(w,p->data,n);return (int)n;
 }
 clock_us=until;return 0;
}
static void fake_answer(uint64_t sender,const unsigned char*w,size_t n){if(answer_count<answer_room){answers[answer_count].at=clock_us;answers[answer_count].sender=sender;memcpy(answers[answer_count].wire,w,n<20?n:20);}answer_count++;}
static uint64_t fake_now(void){return clock_us;}
/* The console's start-up thread: STARTING until the first scripted change, then the latest one due. */
static int fake_progress(int32_t*error){int state=PAD_STARTING;*error=0;for(int i=0;i<state_count;i++)if(states[i].at<=clock_us){state=states[i].state;*error=states[i].error;}return state;}
static void note(int kind,int handle){if(event_count<event_room){events[event_count].at=clock_us;events[event_count].kind=kind;events[event_count].handle=handle;}event_count++;}
static int32_t fake_add(int*handle){int32_t rv=adds_made<add_count?adds[adds_made]:0;adds_made++;if(rv)return rv;*handle=next_handle++;note(1,*handle);return 0;}
static int32_t fake_insert(int handle,const unsigned char*r){
 if(insert_count<insert_room){struct fake_insert*i=&inserts[insert_count];i->at=clock_us;i->handle=handle;memcpy(&i->buttons,r+0x0c,4);memcpy(i->sticks,r+0x10,6);}
 insert_count++;return insert_result;
}
static int32_t fake_remove(int handle){note(2,handle);return 0;}
/* The console's answer to each seat in turn (0: seated), every seat noted. */
static const int32_t*seats;static int seat_count,seats_made;static int32_t seat_inserts[16];
__declspec(dllexport) void pb_seats(const int32_t*s,int n){seats=s;seat_count=n;}
__declspec(dllexport) void pb_seat_inserts(int32_t*o,int n){for(int k=0;k<n&&k<16;k++)o[k]=seat_inserts[k];}
static int32_t fake_seat(int handle){if(seats_made<16)seat_inserts[seats_made]=insert_count;int32_t rv=seats_made<seat_count?seats[seats_made]:0;seats_made++;note(3,handle);return rv;}
__declspec(dllexport) int pb_companion(const struct fake_packet*p,int np,const struct fake_state*s,int ns,const int32_t*a,int na_,int result,struct fake_answer*a_out,int na,struct fake_insert*i,int ni,struct fake_event*e,int ne,uint64_t*out){
 packets=p;packet_count=np;next_packet=0;states=s;state_count=ns;adds=a;add_count=na_;adds_made=0;insert_result=result;next_handle=100;seats_made=0;
 answers=a_out;answer_room=na;answer_count=0;inserts=i;insert_room=ni;insert_count=0;events=e;event_room=ne;event_count=0;clock_us=0;
 struct pad_calls c={fake_receive,fake_answer,fake_now,fake_progress,fake_add,fake_insert,fake_remove,fake_seat};struct pad_report r;memset(&r,0,sizeof r);
 int end=pad_run(&c,&r);
 out[0]=clock_us;out[1]=(uint64_t)answer_count;out[2]=(uint64_t)insert_count;out[3]=(uint64_t)event_count;out[4]=r.packets;out[5]=r.inserted;out[6]=r.neutral;out[7]=r.answers;out[8]=r.ignored;out[9]=r.insert_failed;out[10]=(uint32_t)r.first_insert_error;out[11]=r.added;out[12]=r.removed;out[13]=r.refused;
 out[14]=r.seated;out[15]=r.seat_failed;out[16]=(uint32_t)r.first_seat_error;
 return end;
}
/* Mbus for pad_seat: "no such device" this many times, then the bind's answer; the record's answer and the owner it names. */
static int mbus_missing,mbus_binds,mbus_pauses,mbus_info_calls;static int32_t mbus_bind_answer,mbus_info_answer;static uint32_t mbus_owner;static uint64_t mbus_device;static int32_t mbus_user;
static int32_t fake_bind(uint64_t device,int32_t user){mbus_binds++;mbus_device=device;mbus_user=user;return mbus_binds<=mbus_missing?PAD_MBUS_NO_DEVICE:mbus_bind_answer;}
static int32_t fake_info(uint64_t device,void*record,uint32_t size){
 mbus_info_calls++;if(device!=mbus_device||size!=PAD_INFO_SIZE)return -1;
 unsigned char*r=record;for(uint32_t k=0;k<size;k++)if(r[k])return -2;
 memcpy(r+PAD_INFO_OWNER,&mbus_owner,4);return mbus_info_answer;
}
static void fake_pause(void){mbus_pauses++;}
__declspec(dllexport) int32_t pb_seat(int missing,int32_t bind_answer,int32_t info_answer,uint32_t named,int handle,uint32_t user,int64_t*o){
 mbus_missing=missing;mbus_bind_answer=bind_answer;mbus_info_answer=info_answer;mbus_owner=named;mbus_binds=mbus_pauses=mbus_info_calls=0;
 struct pad_mbus m={fake_bind,fake_info,fake_pause};uint32_t owner=0xdeadbeef;int tries=0;
 int32_t rv=pad_seat(&m,handle,user,&owner,&tries);
 o[0]=tries;o[1]=mbus_binds;o[2]=mbus_pauses;o[3]=mbus_info_calls;o[4]=owner;o[5]=(int64_t)mbus_device;o[6]=(uint32_t)mbus_user;
 return rv;
}
'''
def compiler():
 found=shutil.which('clang')
 if found:return found
 default=Path(os.environ.get('LLVM_BIN',r'C:\Program Files\LLVM\bin'))/'clang.exe'
 return str(default) if default.is_file() else None

class Packet(ctypes.Structure):_fields_=[('at',ctypes.c_uint64),('sender',ctypes.c_uint64),('size',ctypes.c_int32),('data',ctypes.c_ubyte*24)]
class State(ctypes.Structure):_fields_=[('at',ctypes.c_uint64),('state',ctypes.c_int32),('error',ctypes.c_int32)]
class Answer(ctypes.Structure):_fields_=[('at',ctypes.c_uint64),('sender',ctypes.c_uint64),('wire',ctypes.c_ubyte*20),('spare',ctypes.c_ubyte*4)]
class Insert(ctypes.Structure):_fields_=[('at',ctypes.c_uint64),('handle',ctypes.c_int32),('buttons',ctypes.c_uint32),('sticks',ctypes.c_ubyte*6),('spare',ctypes.c_ubyte*2)]
class Event(ctypes.Structure):_fields_=[('at',ctypes.c_uint64),('kind',ctypes.c_int32),('handle',ctypes.c_int32)]
END_IDLE,END_FAILED,END_SOCKET=1,2,3
HUNG,FULL=0x50420004,0x50420005
ADDED,REMOVED,SEATED,INSERTED=1,2,3,4
NO_SEAT,SEAT_OTHER,MBUS_NO_DEVICE=0x50420006,0x50420007,0x809b0005
CENTRED=(128,128,128,128,0,0)

def signed(value):return struct.unpack('<i',struct.pack('<I',value&0xffffffff))[0]
def playing(start,end,every=.05,first=1,state=pad.PadState(pad.CROSS),sender=1):
 """A PC sending a held state every so often, as it does while a controller plays, with rising sequences."""
 out=[];at=start;sequence=first
 while at<=end+1e-9:out.append((at,pad.wire(sequence,state),sender));at=round(at+every,6);sequence+=1
 return out

@unittest.skipUnless(os.name=='nt' and compiler(),'needs clang on Windows')
class CompanionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();source=Path(cls.tmp.name)/'harness.c';source.write_text(HARNESS,encoding='ascii');out=Path(cls.tmp.name)/'companion.dll'
  subprocess.run([compiler(),'--target=x86_64-pc-windows-msvc','-O1','-ffreestanding','-fno-builtin','-nostdlib','-shared','-fuse-ld=lld','-Wl,/noentry','-Wall','-Wextra','-Werror','-I',str(ROOT/'payload'),str(source),'-o',str(out)],check=True)
  cls.lib=ctypes.WinDLL(str(out));cls.lib.pb_fill.argtypes=[ctypes.c_char_p,ctypes.c_uint32,ctypes.c_char_p];cls.lib.pb_describe.argtypes=[ctypes.c_char_p,ctypes.c_uint32]
  cls.lib.pb_quit.argtypes=[ctypes.c_char_p,ctypes.c_size_t]
 @classmethod
 def tearDownClass(cls):
  # Unload first: Windows keeps a loaded DLL's file locked.
  ctypes.windll.kernel32.FreeLibrary.argtypes=[ctypes.c_void_p];ctypes.windll.kernel32.FreeLibrary(cls.lib._handle);cls.tmp.cleanup()
 def run_companion(self,packets,states=(),insert_result=0,adds=(),seats=()):
  """packets: (seconds, bytes[, sender]) or (seconds, None) for a broken socket. states: (seconds, state, error). adds: the console's
  answer to each add in turn, 0 for a controller. seats: its answer to each seat in turn, 0 for seated."""
  seat_answers=(ctypes.c_int32*max(1,len(seats)))(*[signed(v) for v in seats]);self.lib.pb_seats(seat_answers,len(seats))
  packets=sorted(packets,key=lambda item:item[0])
  p=(Packet*max(1,len(packets)))()
  for k,item in enumerate(packets):
   at,data=item[:2];p[k].at=round(at*1e6);p[k].sender=item[2] if len(item)>2 else 1
   if data is None:p[k].size=-1
   else:p[k].size=len(data);ctypes.memmove(p[k].data,data,len(data))
  s=(State*max(1,len(states)))()
  for k,(at,state,error) in enumerate(states):s[k].at=round(at*1e6);s[k].state=state;s[k].error=signed(error)
  a=(ctypes.c_int32*max(1,len(adds)))(*[signed(v) for v in adds])
  answers=(Answer*8192)();i=(Insert*8192)();e=(Event*64)();out=(ctypes.c_uint64*17)()
  end=self.lib.pb_companion(p,len(packets),s,len(states),a,len(adds),insert_result,answers,8192,i,8192,e,64,out)
  self.assertLessEqual(out[1],8192);self.assertLessEqual(out[2],8192);self.assertLessEqual(out[3],64)
  said=[(answers[k].at/1e6,)+pad.read_status(bytes(answers[k].wire))+(answers[k].sender,) for k in range(out[1])]
  inserts=[(i[k].at/1e6,i[k].buttons,tuple(i[k].sticks),i[k].handle) for k in range(out[2])]
  events=[(e[k].at/1e6,e[k].kind,e[k].handle) for k in range(out[3])]
  report=dict(zip(('packets','inserted','neutral','answers','ignored','insert_failed','first_insert_error','added','removed','refused','seated','seat_failed','first_seat_error'),list(out[4:17])))
  # The seats are noted apart, so the tests written before seats existed still see only adds and removals.
  self.seats=[event for event in events if event[1]==SEATED];events=[event for event in events if event[1]!=SEATED]
  # How many states had been handed over when each seat was asked for.
  before=(ctypes.c_int32*16)();self.lib.pb_seat_inserts(before,16);self.inserts_before_seat=list(before)[:min(16,len(self.seats))]
  self.events=events
  return end,out[0]/1e6,said,inserts,report

 def test_the_c_and_python_sides_agree_on_the_wire(self):
  values=(ctypes.c_int64*11)();self.lib.pb_constants(values)
  self.assertEqual(list(values),[pad.PAD_PORT,len(pad.wire(0,pad.NEUTRAL)),pad.STATUS_SIZE,pad.STARTING,pad.READY,pad.FAILED,HUNG,len(pad.QUIT),0xA8,4,FULL])
  self.assertTrue(self.lib.pb_quit(pad.QUIT,len(pad.QUIT)));self.assertFalse(self.lib.pb_quit(pad.QUIT[:7],7));self.assertFalse(self.lib.pb_quit(pad.wire(0,pad.NEUTRAL)[:8],8))
  out=ctypes.create_string_buffer(20)
  for state,error,sequence,player in ((pad.READY,0,7,1),(pad.FAILED,signed(0x80920001),0xffffffff,0),(pad.STARTING,HUNG,0,0),(pad.READY,0,3,4)):
   self.lib.pb_status(out,state,error,sequence,player);self.assertEqual(out.raw,pad.status_wire(state,error,sequence,player))
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
 def test_the_state_block_has_the_layout_the_console_reads(self):
  data=ctypes.create_string_buffer(b'\xee'*0xA8,0xA8);self.lib.pb_fill(data,0x4000,bytes((1,2,3,4,5,6)));d=data.raw
  # Buttons, the sticks then the triggers, present, a level controller at rest (orientation 0,0,0,1, no turning, gravity 0,1,0).
  self.assertEqual(struct.unpack_from('<I',d,0x0c)[0],0x4000);self.assertEqual(d[0x10:0x16],bytes((1,2,3,4,5,6)));self.assertEqual(d[0x17],1)
  self.assertEqual(struct.unpack_from('<4f',d,0x78),(0.0,0.0,0.0,1.0));self.assertEqual(struct.unpack_from('<3f',d,0x88),(0.0,0.0,0.0));self.assertEqual(struct.unpack_from('<3f',d,0x94),(0.0,1.0,0.0))
  # Nothing else is left over from before: no touch on the touchpad, every other byte clear.
  known=set(range(0x0c,0x16))|{0x17}|set(range(0x84,0x88))|set(range(0x98,0x9c))
  self.assertEqual([k for k in range(0xA8) if k not in known and d[k]],[])
 def test_the_controller_added_is_a_standard_one_for_the_user(self):
  data=ctypes.create_string_buffer(b'\xee'*0xA8,0xA8);self.lib.pb_describe(data,0x1a2b3c4d);d=data.raw
  self.assertEqual((d[0],struct.unpack_from('<I',d,0x1c)[0],d[0x20]),(3,0x1a2b3c4d,1))
  self.assertEqual([k for k in range(0xA8) if k not in (0,0x1c,0x1d,0x1e,0x1f,0x20) and d[k]],[])
 def test_the_requests_have_the_sizes_their_numbers_carry(self):
  o=(ctypes.c_int64*15)();self.lib.pb_layout(o);o=list(o)
  for size,number in ((o[0],o[8]),(o[3],o[9]),(o[6],o[10])):self.assertEqual(size,(number>>16)&0x1fff)
  # Pointers sit on 8-byte boundaries after the 4-byte fields, as the kernel reads them.
  self.assertEqual((o[1],o[2],o[4],o[5],o[7]),(8,16,8,16,8))
  self.assertEqual((o[8],o[9],o[10]),(0xC018482A,0x8018482C,0x80104850));self.assertEqual((o[11],o[12]),(3,5))
  self.assertEqual((o[13]&0xffffffff,o[14]&0xffffffff),(0x50530005,0x5045000d))

 def test_it_answers_starting_then_ready_and_hands_states_over_only_once_ready(self):
  sent=playing(.1,3.0)
  end,clock,answers,inserts,report=self.run_companion(sent,[(1.0,pad.READY,0)])
  self.assertEqual(answers[0][:2],(.1,pad.STARTING))
  self.assertTrue(all(state==pad.STARTING and player==0 for at,state,_,_,player,_ in answers if at<1.0))
  first_ready=next(answer for answer in answers if answer[1]==pad.READY)
  # The change is answered with the first packet after it, not after the usual spacing, and names the controller made for it.
  self.assertAlmostEqual(first_ready[0],1.0,places=6);self.assertEqual(first_ready[4],1)
  self.assertTrue(all(state==pad.READY and error==0 and player==1 for at,state,error,_,player,_ in answers if at>=1.0))
  # At most about ten answers a second, each with the newest sequence taken.
  same=[b[0]-a[0] for a,b in zip(answers,answers[1:]) if a[1]==b[1]];self.assertGreaterEqual(min(same),.1-1e-6)
  for at,_,_,sequence,_,_ in answers:self.assertEqual(sequence,1+round((at-.1)/.05))
  # The controller is made with the first state once ready; nothing reaches the console before, then every state does.
  self.assertEqual(self.events[0][:2],(1.0,ADDED))
  held=[insert for insert in inserts if insert[1]];self.assertEqual(len(held),sum(1 for at,*_ in sent if at>=1.0))
  self.assertGreaterEqual(min(at for at,*_ in held),1.0);self.assertTrue(all(buttons==pad.CROSS for _,buttons,_,_ in held))
  # When the PC goes quiet, the buttons are let go once, and after a longer silence its controller goes.
  self.assertEqual(report['neutral'],1);neutral=[insert for insert in inserts if not insert[1]][-1]
  self.assertEqual(neutral[2],CENTRED);self.assertGreaterEqual(neutral[0],3.25);self.assertLess(neutral[0],3.35)
  self.assertEqual(self.events[-1][1],REMOVED);self.assertAlmostEqual(self.events[-1][0],3.0+90,delta=.06)
  self.assertEqual(end,END_IDLE);self.assertAlmostEqual(clock,3.0+600,delta=.06)
 def test_a_start_up_that_never_returns_is_answered_as_failed_and_the_companion_ends(self):
  end,clock,answers,inserts,_=self.run_companion(playing(0,60),[(.2,pad.STARTING,0x50530003)])
  # Starting may take 8 s, and meanwhile the PC hears the step under way, so a start that hangs still says where.
  self.assertTrue(all(state==pad.STARTING for at,state,*_ in answers if at<8))
  self.assertEqual({error&0xffffffff for at,state,error,*_ in answers if .2<=at<8},{0x50530003})
  self.assertTrue(all((state,error&0xffffffff)==(pad.FAILED,HUNG) for at,state,error,*_ in answers if at>=8))
  self.assertEqual((inserts,self.events),([],[]))
  # It ends 30 s after failing, even though the PC is still sending.
  self.assertEqual(end,END_FAILED);self.assertAlmostEqual(clock,38,delta=.06)
  # With no PC at all, it ends 10 s after failing.
  end,clock,answers,_,_=self.run_companion([])
  self.assertEqual((end,answers),(END_FAILED,[]));self.assertAlmostEqual(clock,18,delta=.06)
 def test_a_failed_start_is_answered_with_its_code_and_ends_once_the_pc_is_quiet(self):
  end,clock,answers,inserts,_=self.run_companion(playing(0,2),[(.5,pad.FAILED,0x5045000d)])
  self.assertEqual(answers[-1][1:3],(pad.FAILED,signed(0x5045000d)));self.assertEqual(inserts,[])
  self.assertEqual(end,END_FAILED);self.assertAlmostEqual(clock,12,delta=.06)
 def test_a_start_up_that_comes_back_late_still_counts(self):
  end,clock,answers,inserts,_=self.run_companion(playing(0,13),[(10.0,pad.READY,0)])
  self.assertEqual({state for at,state,*_ in answers if 8.5<at<9.5},{pad.FAILED})
  self.assertEqual(answers[-1][1],pad.READY);self.assertGreaterEqual(min(at for at,*_ in inserts),10.0)
  self.assertEqual(end,END_IDLE)
 def test_a_controller_the_console_refuses_is_asked_for_again(self):
  end,clock,answers,inserts,report=self.run_companion(playing(0,5),[(0,pad.READY,0)],adds=(0x5045000d,0x5045000d))
  # Refused at once and two seconds later, made at four seconds: until then the PC hears the refusal and no state is handed over.
  self.assertEqual({(state,error&0xffffffff,player) for at,state,error,_,player,_ in answers if at<4},{(pad.FAILED,0x5045000d,0)})
  self.assertEqual(report['refused'],2);self.assertAlmostEqual(self.events[0][0],4.0,places=6);self.assertGreaterEqual(min(at for at,*_ in inserts),4.0)
  self.assertEqual(answers[-1][1:3],(pad.READY,0))
 def test_old_packets_are_skipped_and_a_restarted_pc_is_followed(self):
  def state(sequence):return pad.wire(sequence,pad.PadState(lx=sequence*10))
  sent=[(.1,state(5)),(.15,state(6)),(.2,state(4)),(.25,state(7)),(2.0,state(1)),(2.05,state(2))]
  end,clock,answers,inserts,report=self.run_companion(sent,[(0,pad.READY,0)])
  self.assertEqual([sticks[0] for _,_,sticks,_ in inserts],[50,60,70,128,10,20,128])
  # The restarted PC is answered with its own sequence, not the old one's.
  self.assertEqual(report['ignored'],1);self.assertEqual((answers[-1][0],answers[-1][3]),(2.0,1))
 def test_noise_is_neither_answered_nor_taken_for_a_pc(self):
  good=pad.wire(1,pad.NEUTRAL)
  noise=[(float(k),data) for k in range(20) for data in (good[:19],good+b'\0',b'XXXX'+good[4:])]
  end,clock,answers,inserts,report=self.run_companion(noise,[(0,pad.READY,0)])
  self.assertEqual((answers,inserts,report['packets'],self.events),([],[],0,[]))
  self.assertEqual(end,END_IDLE);self.assertAlmostEqual(clock,600,delta=.06)
 def test_a_broken_socket_ends_it_at_once_and_removes_the_controllers(self):
  end,clock,*_=self.run_companion([(.5,pad.wire(1,pad.NEUTRAL)),(1.0,None),(1.5,pad.wire(2,pad.NEUTRAL))],[(0,pad.READY,0)])
  self.assertEqual(end,END_SOCKET);self.assertAlmostEqual(clock,1.0)
  self.assertEqual([event[1:] for event in self.events],[(ADDED,100),(REMOVED,100)])
 def test_a_console_that_refuses_the_states_says_so_and_carries_on(self):
  refused=signed(0x80920003)
  end,clock,answers,inserts,report=self.run_companion(playing(0,1),[(0,pad.READY,0)],insert_result=refused)
  self.assertTrue(all((state,error)==(pad.READY,refused) for _,state,error,*_ in answers))
  self.assertEqual(report['insert_failed'],len(inserts));self.assertEqual(report['first_insert_error'],0x80920003)
  self.assertEqual(end,END_IDLE)
 def test_quit_lets_go_and_removes_that_controller_at_once_and_the_companion_stays_for_the_next_press(self):
  sent=playing(.1,1.0)+[(1.02,pad.QUIT),(1.5,pad.wire(99,pad.PadState(pad.CROSS)))]
  end,clock,answers,inserts,report=self.run_companion(sent,[(0,pad.READY,0)])
  let_go=[insert for insert in inserts if insert[0]==1.02];self.assertEqual([insert[1:3] for insert in let_go],[(0,CENTRED)])
  self.assertEqual(self.events[:2],[(.1,ADDED,100),(1.02,REMOVED,100)])
  # The next press makes a controller again at once, seated in the user in front again since no other one here is.
  self.assertEqual(self.events[2][:2],(1.5,ADDED));self.assertEqual([at for at,_,_ in self.seats],[.1,1.5])
  # Nobody plays after that, so it ends after the usual idle time.
  self.assertEqual(end,END_IDLE);self.assertAlmostEqual(clock,1.5+600,delta=.06)
  # Before anything is made there is nothing to let go of, and a leave message alone does not end it.
  end,clock,answers,inserts,report=self.run_companion([(.1,pad.QUIT)],[(0,pad.READY,0)])
  self.assertEqual((inserts,report['neutral'],self.events),([],0,[]));self.assertEqual(end,END_IDLE);self.assertAlmostEqual(clock,.1+600,delta=.06)

 def test_each_pc_gets_a_controller_of_its_own(self):
  one=playing(.1,2.0,state=pad.PadState(pad.CROSS),sender=1);two=playing(.12,2.0,state=pad.PadState(pad.CIRCLE),sender=2)
  end,clock,answers,inserts,report=self.run_companion(one+two+[(2.5,pad.QUIT,1),(3.0,pad.QUIT,2)],[(0,pad.READY,0)])
  handles={sender:{player for at,state,error,_,player,who in answers if who==sender and state==pad.READY} for sender in (1,2)}
  self.assertEqual(handles,{1:{1},2:{2}})
  # Each one's states go to its own controller only.
  by_handle={}
  for at,buttons,sticks,handle in inserts:
   if buttons:by_handle.setdefault(handle,set()).add(buttons)
  self.assertEqual(by_handle,{100:{pad.CROSS},101:{pad.CIRCLE}})
  # One leaving takes only its controller; the other plays on. With both gone the companion waits for the next press.
  self.assertEqual([event[1:] for event in self.events],[(ADDED,100),(ADDED,101),(REMOVED,100),(REMOVED,101)])
  self.assertEqual(end,END_IDLE);self.assertAlmostEqual(clock,3.0+600,delta=.06)
 def test_a_fifth_pc_is_told_there_is_no_room(self):
  sent=[item for sender in range(1,6) for item in playing(.1+sender/100,1.0,sender=sender)]
  end,clock,answers,inserts,report=self.run_companion(sent,[(0,pad.READY,0)])
  self.assertEqual(report['added'],4)
  self.assertEqual({(state,error&0xffffffff,player) for at,state,error,_,player,who in answers if who==5},{(pad.FAILED,FULL,0)})
  self.assertEqual({who for *_,player,who in answers if player},{1,2,3,4})
 def test_a_pc_that_goes_quiet_loses_its_controller_and_the_place_is_free_again(self):
  sent=playing(.1,1.0,sender=1)+playing(.1,100.0,every=1.0,sender=2)+playing(95.0,96.0,sender=3)
  end,clock,answers,inserts,report=self.run_companion(sent,[(0,pad.READY,0)])
  removed=[event for event in self.events if event[1]==REMOVED]
  self.assertAlmostEqual(removed[0][0],1.0+90,delta=.06);self.assertEqual(removed[0][2],100)
  # The third PC takes the first one's place.
  self.assertEqual({player for at,state,error,_,player,who in answers if who==3 and state==pad.READY},{1})
 def test_a_probe_is_answered_with_the_state_and_makes_no_controller(self):
  quiet=self.run_companion([],[(0,pad.READY,0)])[1]
  end,clock,answers,inserts,report=self.run_companion([(.1,pad.PROBE,7)],[(0,pad.READY,0)])
  self.assertEqual([(state,player,who) for at,state,error,_,player,who in answers],[(pad.READY,0,7)])
  self.assertEqual((report['added'],inserts,report['packets']),(0,[],0))
  # It does not keep the companion from ending when nobody plays.
  self.assertEqual((end,clock),(END_IDLE,quiet))
  end,clock,answers,inserts,report=self.run_companion([(.1,pad.PROBE,7)])
  self.assertEqual([(state,player) for at,state,error,_,player,who in answers],[(pad.STARTING,0)])

 def test_only_the_first_controller_is_seated_in_the_user_in_front_before_its_first_state(self):
  one=playing(.1,2.0,sender=1);two=playing(.12,2.0,state=pad.PadState(pad.CIRCLE),sender=2)
  end,clock,answers,inserts,report=self.run_companion(one+two+[(2.5,pad.QUIT,1),(3.0,pad.QUIT,2)],[(0,pad.READY,0)])
  # The PS5 would otherwise ask who is using it; the second PC is another player, whom the PS5 asks.
  self.assertEqual([handle for _,_,handle in self.seats],[100]);self.assertEqual(self.inserts_before_seat,[0])
  self.assertEqual((report['seated'],report['seat_failed'],report['added']),(1,0,2))
 def test_a_seat_that_fails_leaves_a_controller_that_plays(self):
  sent=playing(.1,1.0)
  end,clock,answers,inserts,report=self.run_companion(sent+[(1.5,pad.QUIT)],[(0,pad.READY,0)],seats=(NO_SEAT,))
  self.assertEqual((report['seated'],report['seat_failed'],report['first_seat_error']),(0,1,NO_SEAT))
  # The PC hears nothing of it, and every state still reaches the console.
  self.assertTrue(all((state,error)==(pad.READY,0) for at,state,error,*_ in answers))
  self.assertEqual(sum(1 for insert in inserts if insert[1]),len(sent));self.assertEqual(end,END_IDLE)
 def test_the_seat_goes_to_the_next_controller_once_no_controller_here_has_it(self):
  # The first PC's seat fails, so the second one gets it; the third joins while that one is seated and gets none.
  sent=playing(.1,3.0,sender=1)+playing(.5,3.0,sender=2)+playing(1.0,3.0,sender=3)+[(3.5,pad.QUIT,1),(3.6,pad.QUIT,2),(3.7,pad.QUIT,3)]
  self.run_companion(sent,[(0,pad.READY,0)],seats=(NO_SEAT,0))
  self.assertEqual([handle for _,_,handle in self.seats],[100,101])
  # Once the seated one has left, the next new controller takes the seat; one already playing keeps what it has.
  sent=playing(.1,2.0,sender=1)+playing(.5,5.0,sender=2)+[(2.5,pad.QUIT,1)]+playing(3.0,5.0,sender=3)+[(5.5,pad.QUIT,2),(6.0,pad.QUIT,3)]
  end,clock,answers,inserts,report=self.run_companion(sent,[(0,pad.READY,0)])
  self.assertEqual([handle for _,_,handle in self.seats],[100,102]);self.assertEqual(report['seated'],2)
 def test_a_seat_is_asked_for_each_millisecond_until_mbus_knows_the_controller(self):
  seat=self.lib.pb_seat;seat.argtypes=[ctypes.c_int,ctypes.c_int32,ctypes.c_int32,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32,ctypes.POINTER(ctypes.c_int64)];seat.restype=ctypes.c_int32
  user=0x1a2b3c4d;o=(ctypes.c_int64*7)()
  # Three "no such device", then seated: the record read once, the owner it names returned, the handle and user passed as they are.
  self.assertEqual(seat(3,0,0,user,459533,user,o),0);self.assertEqual(list(o),[4,4,3,1,user,459533,user])
  # It gives up after 30 tries with the console's answer, and reads no record.
  self.assertEqual(seat(100,0,0,user,459533,user,o)&0xffffffff,MBUS_NO_DEVICE);self.assertEqual(list(o)[:5],[30,30,29,0,0])
  # Any other refusal ends it at once.
  self.assertEqual(seat(0,signed(0x809b0001),0,user,459533,user,o)&0xffffffff,0x809b0001);self.assertEqual(list(o)[:5],[1,1,0,0,0])
  # The console naming someone else, or a record it will not give, is not a seat.
  self.assertEqual(seat(0,0,0,0x11111111,459533,user,o),SEAT_OTHER);self.assertEqual(o[4],0x11111111)
  self.assertEqual(seat(0,0,signed(0x809b0002),user,459533,user,o)&0xffffffff,0x809b0002);self.assertEqual(o[4],0)

def nid(name):
 """A console library symbol's NID: the first 8 bytes of SHA-1 over the name and a fixed suffix, reversed, in base64 with - for /."""
 digest=hashlib.sha1(name.encode()+bytes.fromhex('518D64A635DED8C1E6B039B1C3E55230')).digest()[:8][::-1]
 return base64.b64encode(digest).decode().replace('/','-')[:11]

class PayloadSplitTests(unittest.TestCase):
 """The owner's rule: the controller must never be able to stop the stream, so its code stays out of the video payload."""
 def code(self,name):
  # Comments may name the other payload; the code may not.
  text=(ROOT/'payload'/name).read_text(encoding='utf-8');return re.sub(r'/\*.*?\*/','',text,flags=re.S)
 def test_the_companion_loads_libsceipmi_before_the_user_service(self):
  code=self.code('pad-companion.c')
  self.assertLess(code.index('module(load,"libSceIpmi.sprx")'),code.index('module(load,"libSceUserService.sprx")'))
 def test_a_copy_that_finds_the_port_taken_ends_only_a_silent_earlier_one(self):
  code=self.code('pad-companion.c');main=code[code.index('int main(void)'):]
  # It asks first; only a copy that does not answer, named by the old log with no end line and still a payload, is ended.
  self.assertLess(main.index('running_copy_answers()'),main.index('silent_copy(earlier[k])'));self.assertLess(main.index('silent_copy(earlier[k])'),main.index('kill(old,SIGKILL)'))
  self.assertIn('strncmp(line,"end=",4)',code);self.assertIn('strcmp(name,"payload.elf")',code)
  # Both earlier logs are read before they move on, and every early exit writes its end line, so it is never taken for a running copy.
  self.assertLess(main.index('unended_copy("/data/playbridge-pad.old.txt")'),main.index('rename("/data/playbridge-pad.txt"'))
  self.assertEqual(main.count('end=taken'),2);self.assertIn('end=firmware',main)
 def test_the_video_payload_holds_no_controller_code(self):
  for name in ('stream-av3.c','console-control.h','control-rules.h','capture-options.h','av-wire.h'):
   code=self.code(name)
   for word in ('scePad','libScePad','PAD_PORT','pad-rules.h','9078','/dev/hid'):self.assertNotIn(word,code,(name,word))
 def test_the_companion_stays_off_the_capture_and_the_other_ports(self):
  code=self.code('pad-companion.c')
  for word in ('Avcap','9076','9077','CONTROL_PORT','console-control.h','setsockopt','scePad'):self.assertNotIn(word,code,word)
  self.assertIn('#include "pad-rules.h"',code);self.assertIn('htons(PAD_PORT)',code)
  # Start-up runs on its own thread, and the main thread never waits for it.
  self.assertIn('pthread_create(&thread,0,start_pad,0)',code);self.assertNotIn('pthread_join',code)
 def test_the_mbus_calls_are_found_by_the_nids_of_their_names(self):
  code=self.code('pad-companion.c')
  # The way of working them out gives the NID the companion already uses for the loader.
  self.assertEqual(nid('sceKernelLoadStartModule'),'wzvqT4UqKX8');self.assertIn('"wzvqT4UqKX8"',code)
  for name in ('sceMbusInit','sceMbusBindDeviceWithUserId','sceMbusGetDeviceInfo_'):self.assertIn(f'"{nid(name)}","{name}"',code)
 def test_mbus_starts_on_its_own_thread_and_is_waited_for_a_second_at_most(self):
  code=self.code('pad-companion.c');main=code[code.index('int main(void)'):]
  # Looked up in the main thread before any other thread exists, like every other symbol.
  self.assertLess(main.index('module(load,"libSceMbus.sprx")'),main.index('pthread_create(&thread,0,start_pad,0)'))
  start=code[code.index('static void start_seats(void)'):];start=start[:start.index('\n}\n')]
  self.assertIn('pthread_create(&thread,0,start_mbus,0)',start);self.assertIn('i<200',start);self.assertIn('usleep(5000)',start)
  # A seat is only asked for once Mbus has started; until then the controller plays without one.
  seat=code[code.index('static int32_t seat_controller(int handle)'):];self.assertLess(seat.index('MBUS_READY'),seat.index('pad_seat('))

if __name__=='__main__':unittest.main()
