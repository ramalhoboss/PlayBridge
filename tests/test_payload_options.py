"""Runs the sender's option logic on the PC: compiled from the payload header without the PS5 SDK."""
import ctypes,os,shutil,struct,subprocess,tempfile,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HARNESS=r'''
#include <stddef.h>
#include <stdint.h>
void*memcpy(void*d,const void*s,unsigned long long n){char*a=d;const char*b=s;while(n--)*a++=*b++;return d;}
static void u32(unsigned char*p,int o,uint32_t v){memcpy(p+o,&v,4);}
static void u64(unsigned char*p,int o,uint64_t v){memcpy(p+o,&v,8);}
#include "capture-options.h"
#include "control-rules.h"
__declspec(dllexport) int pb_valid(uint32_t r,uint32_t b,uint32_t c){return valid_target(r,b,c);}
__declspec(dllexport) int pb_split(uint32_t w,uint32_t*parts){return split_target(w,parts,parts+1,parts+2);}
__declspec(dllexport) size_t pb_headers(unsigned char*o,const unsigned char*h,uint32_t c){return codec_headers(o,h,c);}
__declspec(dllexport) size_t pb_delimiter(unsigned char*o,uint32_t c){return delimiter(o,c);}
__declspec(dllexport) int pb_title(const char*t,size_t n){return valid_title(t,n);}
__declspec(dllexport) int pb_file(const char*p,size_t n){return allowed_file(p,n);}
__declspec(dllexport) int pb_folder(const char*p,size_t n){return allowed_folder(p,n);}
__declspec(dllexport) uint32_t pb_supported(uint32_t r,uint32_t m){return supported_resolution(r,m);}
__declspec(dllexport) uint32_t pb_apply(unsigned char*p,uint32_t r,uint32_t f,uint32_t b){return apply_resolution(p,r,f,b);}
__declspec(dllexport) int pb_reopen(uint32_t c){return read_needs_reopen(c);}
/* Stand-ins for the console: each status check and each open takes the next scripted answer, the last one repeating. */
static const unsigned char*fake_flags;static const uint32_t*fake_opens;static int fake_flag_count,fake_open_count,fake_checks,fake_open_calls,fake_waited,fake_status_result;static uint32_t fake_mode;
static int fake_caps(uint32_t*m){*m=fake_mode;return 0;}
static int fake_status(void*a){unsigned char*b=a;int i=fake_checks++;b[0x14]=fake_flags[i<fake_flag_count?i:fake_flag_count-1];return fake_status_result;}
static int fake_open(int64_t*h,void*p,int f){(void)p;(void)f;int i=fake_open_calls++;uint32_t r=fake_opens[i<fake_open_count?i:fake_open_count-1];if(r<0x80000000u)*h=0x1234;return (int)r;}
static void fake_wait(int ms){fake_waited+=ms;}
__declspec(dllexport) uint32_t pb_ready(const unsigned char*flags,int nf,const uint32_t*opens,int no,uint32_t mode,int status_result,uint32_t resolution,unsigned char*p,int*counts){
 fake_flags=flags;fake_flag_count=nf;fake_opens=opens;fake_open_count=no;fake_mode=mode;fake_status_result=status_result;fake_checks=fake_open_calls=fake_waited=0;
 struct capture_calls c={fake_caps,fake_status,fake_open,fake_wait};struct reopen_report r;unsigned char*z=(unsigned char*)&r;for(unsigned i=0;i<sizeof r;i++)z[i]=0;
 int64_t h=0;uint32_t caps=0;uint32_t rv=open_when_ready(&c,&h,p,resolution,&caps,&r);
 counts[0]=fake_checks;counts[1]=fake_open_calls;counts[2]=fake_waited;counts[3]=r.waited_ms;counts[4]=r.not_ready;counts[5]=r.busy;counts[6]=(int)caps;counts[7]=h!=0;counts[8]=r.checks;
 return rv;
}
/* Stand-ins for the viewer wait: each accept and each options read takes the next scripted answer, the last one repeating, and each
   accept moves the clock on by a set cost. */
static const int*fake_accepts;static const int*fake_answers;static int fake_accept_count,fake_answer_count,fake_accept_calls,fake_option_calls,fake_drops,fake_last_dropped,fake_timeouts[8];static uint64_t fake_clock,fake_accept_cost;
static int fake_accept(int t){int i=fake_accept_calls++;if(i<8)fake_timeouts[i]=t;fake_clock+=fake_accept_cost;return fake_accepts[i<fake_accept_count?i:fake_accept_count-1];}
static int fake_options(int fd){(void)fd;int i=fake_option_calls++;return fake_answers[i<fake_answer_count?i:fake_answer_count-1];}
static void fake_drop(int fd){fake_drops++;fake_last_dropped=fd;}
static uint64_t fake_now(void){return fake_clock;}
__declspec(dllexport) int pb_viewer(const int*accepts,int na,const int*answers,int nb,uint32_t cost,int*counts){
 fake_accepts=accepts;fake_accept_count=na;fake_answers=answers;fake_answer_count=nb;fake_accept_cost=cost;fake_clock=1000;fake_accept_calls=fake_option_calls=fake_drops=0;fake_last_dropped=-1;
 for(int i=0;i<8;i++)fake_timeouts[i]=0;
 struct viewer_calls c={fake_accept,fake_options,fake_drop,fake_now};int dropped=0,invalid=-1;int fd=first_viewer(&c,&dropped,&invalid);
 counts[0]=fake_accept_calls;counts[1]=fake_option_calls;counts[2]=dropped;counts[3]=fake_drops;counts[4]=fake_last_dropped;counts[5]=invalid;
 for(int i=0;i<8;i++)counts[6+i]=fake_timeouts[i];
 return fd;
}
'''
def compiler():
 found=shutil.which('clang')
 if found:return found
 default=Path(os.environ.get('LLVM_BIN',r'C:\Program Files\LLVM\bin'))/'clang.exe'
 return str(default) if default.is_file() else None

@unittest.skipUnless(os.name=='nt' and compiler(),'needs clang on Windows')
class PayloadOptionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();source=Path(cls.tmp.name)/'harness.c';source.write_text(HARNESS,encoding='ascii');out=Path(cls.tmp.name)/'options.dll'
  subprocess.run([compiler(),'--target=x86_64-pc-windows-msvc','-O1','-ffreestanding','-fno-builtin','-nostdlib','-shared','-fuse-ld=lld','-Wl,/noentry','-Wall','-Wextra','-Werror','-I',str(ROOT/'payload'),str(source),'-o',str(out)],check=True)
  cls.lib=ctypes.WinDLL(str(out))
  for name in ('pb_valid','pb_supported','pb_apply','pb_ready'):getattr(cls.lib,name).restype=ctypes.c_uint32
  for name in ('pb_headers','pb_delimiter','pb_title','pb_file'):getattr(cls.lib,name).restype=ctypes.c_size_t
  for name in ('pb_title','pb_file','pb_folder'):getattr(cls.lib,name).argtypes=[ctypes.c_char_p,ctypes.c_size_t]
 @classmethod
 def tearDownClass(cls):
  # Unload first: Windows keeps a loaded DLL's file locked.
  ctypes.windll.kernel32.FreeLibrary.argtypes=[ctypes.c_void_p];ctypes.windll.kernel32.FreeLibrary(cls.lib._handle);cls.tmp.cleanup()
 def apply(self,resolution,bitrate):
  p=(ctypes.c_ubyte*0x2e8)();rate=self.lib.pb_apply(p,resolution,60,bitrate);data=bytes(p)
  field=lambda o:struct.unpack_from('<I',data,o)[0]
  return rate,{name:field(o) for name,o in (('resolution',0x18),('profile',0x28),('rate',0xc8),('peak',0xcc),('frame_bits',0xd0),('frame_budget',0x10c),('paste_w',0x20c),('paste_h',0x210),('paste_stride',0x214),('paste_size',0x218))}
 def test_bitrate_lists_follow_resolution(self):
  for r,ok,bad in ((4,(4,8,12,16,20,30),(40,80)),(5,(20,30,50),(8,80)),(6,(40,60,80),(30,100))):
   for m in ok:self.assertTrue(self.lib.pb_valid(r,m*1000000,0),(r,m))
   for m in bad:self.assertFalse(self.lib.pb_valid(r,m*1000000,0),(r,m))
  self.assertFalse(self.lib.pb_valid(0,8000000,0));self.assertFalse(self.lib.pb_valid(7,80000000,0))
 def test_hevc_has_its_own_bitrate_list_and_no_other_codec_passes(self):
  for r,ok,bad in ((4,(8,12,16),(20,30)),(5,(15,20,30),(50,)),(6,(20,30,40),(60,80))):
   for m in ok:self.assertTrue(self.lib.pb_valid(r,m*1000000,1),(r,m))
   for m in bad:self.assertFalse(self.lib.pb_valid(r,m*1000000,1),(r,m))
  self.assertFalse(self.lib.pb_valid(6,40000000,2))
 def split(self,word):
  parts=(ctypes.c_uint32*3)();known=self.lib.pb_split(word,parts);return known,tuple(parts)
 def test_the_third_word_splits_into_resolution_codec_and_flags(self):
  self.assertEqual(self.split(0),(1,(0,0,0)))
  self.assertEqual(self.split(0x106),(1,(6,1,0)))
  # The notice flag passes; any flag this payload does not know refuses the options, as an older payload refuses them all.
  self.assertEqual(self.split(0x10106),(1,(6,1,1)))
  self.assertEqual(self.split(0x20004)[0],0)
  self.assertEqual(self.split(0x80000000)[0],0)
 def headers(self,sets,codec):
  block=bytearray(0x1a8)
  for (length_at,body_at),data in zip(((0x10,0x18),(0x98,0xa0),(0x120,0x128)),sets):
   struct.pack_into('<Q',block,length_at,len(data));block[body_at:body_at+len(data)]=data
  out=ctypes.create_string_buffer(396);n=self.lib.pb_headers(out,bytes(block),codec);return out.raw[:n]
 def test_h264_headers_keep_their_order_with_start_codes(self):
  # A low nal_ref_idc can make the picture set's first byte the smaller one: the order must not depend on it.
  self.assertEqual(self.headers((b'\x67\x01',b'\x28\x02'),0),b'\0\0\0\1\x67\x01\0\0\0\1\x28\x02')
 def test_hevc_headers_come_out_in_nal_type_order(self):
  self.assertEqual(self.headers((b'\x44\x01',b'\x40\x01',b'\x42\x01'),1),b'\0\0\0\1\x40\x01\0\0\0\1\x42\x01\0\0\0\1\x44\x01')
 def test_a_missing_or_oversized_header_gives_nothing(self):
  self.assertEqual(self.headers((b'\x67',b''),0),b'');self.assertEqual(self.headers((b'\x40',b'\x42',b''),1),b'');self.assertEqual(self.headers((b'\x67',b'\x68'*129),0),b'')
 def test_each_codec_has_its_own_frame_delimiter(self):
  for codec,expected in ((0,bytes((0,0,0,1,9,0xf0))),(1,bytes((0,0,0,1,0x46,1,0x50)))):
   out=ctypes.create_string_buffer(8);size=self.lib.pb_delimiter(out,codec);self.assertEqual(out.raw[:size],expected)
 def test_only_well_formed_titles_are_accepted(self):
  for title in (b'PPSA01234',b'CUSA00001'):self.assertTrue(self.lib.pb_title(title,len(title)),title)
  for title in (b'',b'PPSA0123',b'PPSA012345',b'ppsa01234',b'PPSA0123X',b'../../etc',b'PPS\x0001234'):self.assertFalse(self.lib.pb_title(title,len(title)),title)
 def test_only_the_game_list_and_each_games_art_and_music_can_be_read(self):
  for path in (b'/user/catalog_downloader/appmeta/PPSA01234/pic0.png',b'/user/catalog_downloader/appmeta/PPSA01234/icon0.png',b'/system_data/priv/mms/app.db',b'/system_data/priv/mms/app.db-wal',b'/user/appmeta/PPSA01234/icon0.png',b'/user/appmeta/external/CUSA00001/icon0.png',b'/mnt/ext0/user/appmeta/PPSA01234/icon0.png',b'/mnt/ext1/user/appmeta/PPSA01234/icon0.png',b'/data/playbridge-control.txt',b'/data/playbridge-control.old.txt',b'/data/ps5screen-av3.txt',b'/data/playbridge-pad.txt',b'/data/playbridge-pad.old.txt',b'/user/appmeta/CUSA00001/pic0.dds',b'/user/appmeta/CUSA00001/pic0.png',b'/user/appmeta/CUSA00001/snd0.at9',b'/user/app/PPSA01234/sce_sys/pic0.dds',b'/user/app/PPSA01234/sce_sys/snd0.at9',b'/user/app/PPSA01234/sce_sys/icon0.png',b'/mnt/ext1/user/app/PPSA01234/sce_sys/pic0.dds'):
   self.assertTrue(self.lib.pb_file(path,len(path)),path)
  for path in (b'/user/catalog_downloader/appmeta/PPSA01234/param.json',b'/user/catalog_downloader/PPSA01234/pic0.png',b'/user/catalog_downloader/appmeta/../PPSA01234/pic0.png',b'',b'/',b'/system_data/priv/mms/app.db-shm',b'/system_data/priv/mms/app.db\x00.txt',b'/system_data/priv/mms/',b'/user/appmeta/PPSA01234/param.json',b'/user/appmeta/PPSA01234/../../home/icon0.png',b'/user/appmeta/../PPSA01234/icon0.png',b'/user/appmeta/ppsa01234/icon0.png',b'/user/appmeta/PPSA01234/icon0.png/',b'/data/other.txt',b'/data/playbridge-pad.txt.bak',b'/user/home/PPSA01234/icon0.png',b'/user/app/PPSA01234/pic0.dds',b'/user/app/PPSA01234/eboot.bin',b'/user/app/PPSA01234/sce_sys/param.json',b'/user/app/PPSA01234/sce_sys/../eboot.bin',b'/user/app/PPSA01234/sce_sys',b'/user/appmeta/PPSA01234/sce_sys/pic0.dds',b'/user/app/ppsa01234/sce_sys/pic0.dds'):
   self.assertFalse(self.lib.pb_file(path,len(path)),path)
 def test_the_consoles_own_captures_can_be_listed_and_read_and_nothing_beside_them(self):
  for path in (b'/user/av_contents',b'/user/av_contents/content',b'/user/av_contents/content/Some Game',b'/mnt/ext0/user/av_contents',b'/mnt/ext1/user/av_contents/content'):
   self.assertTrue(self.lib.pb_folder(path,len(path)),path)
  for path in (b'',b'/',b'/user',b'/user/av_contents/',b'/user/av_contents/../app',b'/user/av_contents/content/..',b'/user/av_contents//x',b'/user/av_contents/./x',b'/user/av_contentsx',bytes([47])+b'user/av_contents/a'+bytes([92])+b'b',b'/user/av_contents/a'+bytes([10])+b'b',b'/user/home',b'/mnt/ext2/user/av_contents',b'user/av_contents'):
   self.assertFalse(self.lib.pb_folder(path,len(path)),path)
  for path in (b'/user/av_contents/content/Game/shot.jpg',b'/user/av_contents/content/Game/shot.JPG',b'/user/av_contents/x/clip.webm',b'/user/av_contents/x/clip.mp4',b'/user/av_contents/x/shot.png',b'/user/av_contents/x/shot.webp',b'/mnt/ext0/user/av_contents/x/clip.mp4'):
   self.assertTrue(self.lib.pb_file(path,len(path)),path)
  for path in (b'/user/av_contents/x/db.sqlite',b'/user/av_contents/x/../../app/PPSA01234/eboot.bin.mp4',b'/user/av_contents/.jpg',b'/user/av_contents/x/.mp4x',b'/user/av_contents/x/shot.jpg/',b'/user/home/shot.jpg',b'/user/av_contents/x'+bytes([1])+b'/shot.jpg'):
   self.assertFalse(self.lib.pb_file(path,len(path)),path)
 def test_output_mode_limits_resolution(self):
  # 0x10 was measured on a 1080p output and 0x13c on a 4K output.
  for mode,want,got in ((0x10,6,4),(0x10,5,4),(0x10,4,4),(0x30,6,5),(0x30,5,5),(0x13c,6,6),(0x13c,5,5),(0x13c,4,4)):
   self.assertEqual(self.lib.pb_supported(want,mode),got,(hex(mode),want))
 def test_1080p_keeps_the_tested_parameters(self):
  rate,f=self.apply(4,8000000)
  self.assertEqual(rate,8000000)
  self.assertEqual(f,{'resolution':4,'profile':14,'rate':8000000,'peak':8000000,'frame_bits':133466,'frame_budget':0x100000,'paste_w':384,'paste_h':320,'paste_stride':512,'paste_size':0x3c000})
 def test_frame_bits_follow_bitrate(self):
  for mbps,expected in ((4,66733),(12,200200),(30,500500)):self.assertEqual(self.apply(4,mbps*1000000)[1]['frame_bits'],expected)
 def test_frame_budget_stays_above_keyframes_and_below_the_start_limit(self):
  # A one-frame budget skips frames after every keyframe (about 200 KB at 1080p); Start refuses 2 MiB.
  for r,mbps in ((4,4),(4,30),(5,50),(6,80)):
   budget=self.apply(r,mbps*1000000)[1]['frame_budget'];self.assertGreater(budget,1000000);self.assertLess(budget,0x200000)
 def test_higher_resolutions_use_their_resource_and_buffer(self):
  _,f=self.apply(5,30000000);self.assertEqual((f['resolution'],f['profile'],f['paste_w'],f['paste_h'],f['paste_stride'],f['paste_size']),(5,11,512,464,512,0x58000))
  _,f=self.apply(6,60000000);self.assertEqual((f['resolution'],f['profile'],f['paste_w'],f['paste_h'],f['paste_stride'],f['paste_size']),(6,10,768,720,768,0xcc000))
 def test_step_down_lowers_bitrate_to_the_new_limit(self):
  self.assertEqual(self.apply(4,80000000)[0],30000000);self.assertEqual(self.apply(5,80000000)[0],50000000);self.assertEqual(self.apply(4,20000000)[0],20000000)
 def test_only_encoder_failures_reopen_the_capture(self):
  for code in (0x81950003,0x81950008,0x81950009,0x8195000d):self.assertTrue(self.lib.pb_reopen(code),hex(code))
  for code in (0x81950002,0x81950004,0x8195000e,0x81950001):self.assertFalse(self.lib.pb_reopen(code),hex(code))
 BUSY,NOT_READY,MODE_LOST=0x81950008,0x8195fff2,0x8195fff1
 def ready(self,flags,opens,mode=0x13c,resolution=6,status_result=0):
  f=(ctypes.c_ubyte*len(flags))(*flags);o=(ctypes.c_uint32*len(opens))(*opens);p=(ctypes.c_ubyte*0x2e8)();counts=(ctypes.c_int*9)()
  rv=self.lib.pb_ready(f,len(flags),o,len(opens),ctypes.c_uint32(mode),status_result,ctypes.c_uint32(resolution),p,counts)
  seen=dict(zip(('checks','opens','waited','reported_wait','not_ready','busy','caps','handle','reported_checks'),counts));seen['params_mode']=struct.unpack_from('<I',bytes(p),0x2a8)[0]
  self.assertEqual((seen['waited'],seen['checks']),(seen['reported_wait'],seen['reported_checks']))
  return rv,seen
 def test_a_reopen_opens_at_once_when_the_console_says_it_can(self):
  rv,s=self.ready([0],[0]);self.assertEqual((rv,s['checks'],s['opens'],s['waited'],s['handle']),(0,1,1,0,1))
  self.assertEqual((s['caps'],s['params_mode']),(0x13c,0x13c))
 def test_a_reopen_waits_16_ms_while_the_console_says_it_cannot_open(self):
  rv,s=self.ready([1]*40+[0],[0]);self.assertEqual((rv,s['checks'],s['not_ready'],s['opens'],s['waited']),(0,41,40,1,640))
 def test_a_busy_open_is_tried_again_16_ms_later(self):
  rv,s=self.ready([0],[self.BUSY]*3+[0]);self.assertEqual((rv,s['opens'],s['busy'],s['waited']),(0,4,3,48))
 def test_any_other_open_answer_is_final(self):
  rv,s=self.ready([0],[0x81950009]);self.assertEqual((rv,s['opens'],s['waited'],s['handle']),(0x81950009,1,0,0))
 def test_it_gives_up_after_two_seconds(self):
  rv,s=self.ready([1],[0]);self.assertEqual((rv,s['opens'],s['checks'],s['waited']),(self.NOT_READY,0,125,2000))
  rv,s=self.ready([0],[self.BUSY]);self.assertEqual((rv,s['opens'],s['waited']),(self.BUSY,125,2000))
 def test_an_output_mode_without_the_resolution_ends_the_wait_before_any_open(self):
  rv,s=self.ready([0],[0],mode=0x134,resolution=6);self.assertEqual((rv,s['checks'],s['opens']),(self.MODE_LOST,0,0))
  rv,s=self.ready([0],[0],mode=0x114,resolution=5);self.assertEqual((rv,s['opens']),(self.MODE_LOST,0))
  rv,s=self.ready([0],[0],mode=0,resolution=4);self.assertEqual((rv,s['opens'],s['params_mode']),(0,1,0))
 def test_a_failed_status_query_ends_the_wait_without_an_open(self):
  rv,s=self.ready([0],[0],status_result=-0x7e6affff);self.assertEqual((rv,s['checks'],s['opens']),(0x81950001,1,0))
 READ,INVALID,DROPPED,NO_VIEWER,VIEWER_INVALID=0,-1,-2,-1,-2
 def viewer(self,accepts,answers,cost=0):
  a=(ctypes.c_int*len(accepts))(*accepts);b=(ctypes.c_int*len(answers))(*answers);counts=(ctypes.c_int*14)()
  fd=self.lib.pb_viewer(a,len(accepts),b,len(answers),ctypes.c_uint32(cost),counts)
  return fd,dict(zip(('accepts','option_reads','dropped','drops','last_dropped','invalid'),counts[:6])),list(counts[6:])
 def test_a_connection_that_leaves_before_its_options_is_dropped_and_the_next_viewer_is_taken(self):
  fd,seen,timeouts=self.viewer([7,8],[self.DROPPED,self.READ],cost=500)
  self.assertEqual(fd,8);self.assertEqual((seen['dropped'],seen['drops'],seen['last_dropped'],seen['invalid']),(1,1,7,-1))
  self.assertEqual(timeouts[:2],[60000,59500])
 def test_a_viewer_whose_options_are_not_valid_ends_the_wait(self):
  fd,seen,_=self.viewer([7,8],[self.INVALID,self.READ])
  self.assertEqual(fd,self.VIEWER_INVALID);self.assertEqual((seen['invalid'],seen['drops'],seen['accepts']),(7,0,1))
 def test_the_wait_ends_when_nobody_comes_or_the_minute_is_over(self):
  fd,seen,_=self.viewer([-1],[self.READ]);self.assertEqual((fd,seen['option_reads']),(self.NO_VIEWER,0))
  fd,seen,timeouts=self.viewer([7,8,9,10],[self.DROPPED],cost=25000)
  self.assertEqual((fd,seen['accepts'],seen['drops']),(self.NO_VIEWER,3,3));self.assertEqual(timeouts[:3],[60000,35000,10000])
if __name__=='__main__':unittest.main()
