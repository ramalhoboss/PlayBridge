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
__declspec(dllexport) size_t pb_headers(unsigned char*o,const unsigned char*h,uint32_t c){return codec_headers(o,h,c);}
__declspec(dllexport) size_t pb_delimiter(unsigned char*o,uint32_t c){return delimiter(o,c);}
__declspec(dllexport) int pb_title(const char*t,size_t n){return valid_title(t,n);}
__declspec(dllexport) int pb_file(const char*p,size_t n){return allowed_file(p,n);}
__declspec(dllexport) int pb_pad(const unsigned char*w,size_t n,uint32_t*q,uint32_t*b,unsigned char*s){return read_pad_wire(w,n,q,b,s);}
__declspec(dllexport) int pb_newer(uint32_t a,uint32_t b){return newer_sequence(a,b);}
__declspec(dllexport) void pb_fill(unsigned char*d,uint32_t b,const unsigned char*s,uint64_t t){fill_pad_data(d,b,s,t);}
__declspec(dllexport) uint32_t pb_supported(uint32_t r,uint32_t m){return supported_resolution(r,m);}
__declspec(dllexport) uint32_t pb_apply(unsigned char*p,uint32_t r,uint32_t f,uint32_t b){return apply_resolution(p,r,f,b);}
__declspec(dllexport) int pb_reopen(uint32_t c){return read_needs_reopen(c);}
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
  for name in ('pb_valid','pb_supported','pb_apply'):getattr(cls.lib,name).restype=ctypes.c_uint32
  for name in ('pb_headers','pb_delimiter','pb_title','pb_file'):getattr(cls.lib,name).restype=ctypes.c_size_t
  for name in ('pb_title','pb_file'):getattr(cls.lib,name).argtypes=[ctypes.c_char_p,ctypes.c_size_t]
  cls.lib.pb_fill.argtypes=[ctypes.c_char_p,ctypes.c_uint32,ctypes.c_char_p,ctypes.c_uint64]
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
  for path in (b'/user/catalog_downloader/appmeta/PPSA01234/pic0.png',b'/user/catalog_downloader/appmeta/PPSA01234/icon0.png',b'/system_data/priv/mms/app.db',b'/system_data/priv/mms/app.db-wal',b'/user/appmeta/PPSA01234/icon0.png',b'/user/appmeta/external/CUSA00001/icon0.png',b'/mnt/ext0/user/appmeta/PPSA01234/icon0.png',b'/mnt/ext1/user/appmeta/PPSA01234/icon0.png',b'/data/playbridge-control.txt',b'/data/playbridge-control.old.txt',b'/data/ps5screen-av3.txt',b'/user/appmeta/CUSA00001/pic0.dds',b'/user/appmeta/CUSA00001/pic0.png',b'/user/appmeta/CUSA00001/snd0.at9',b'/user/app/PPSA01234/sce_sys/pic0.dds',b'/user/app/PPSA01234/sce_sys/snd0.at9',b'/user/app/PPSA01234/sce_sys/icon0.png',b'/mnt/ext1/user/app/PPSA01234/sce_sys/pic0.dds'):
   self.assertTrue(self.lib.pb_file(path,len(path)),path)
  for path in (b'/user/catalog_downloader/appmeta/PPSA01234/param.json',b'/user/catalog_downloader/PPSA01234/pic0.png',b'/user/catalog_downloader/appmeta/../PPSA01234/pic0.png',b'',b'/',b'/system_data/priv/mms/app.db-shm',b'/system_data/priv/mms/app.db\x00.txt',b'/system_data/priv/mms/',b'/user/appmeta/PPSA01234/param.json',b'/user/appmeta/PPSA01234/../../home/icon0.png',b'/user/appmeta/../PPSA01234/icon0.png',b'/user/appmeta/ppsa01234/icon0.png',b'/user/appmeta/PPSA01234/icon0.png/',b'/data/other.txt',b'/user/home/PPSA01234/icon0.png',b'/user/app/PPSA01234/pic0.dds',b'/user/app/PPSA01234/eboot.bin',b'/user/app/PPSA01234/sce_sys/param.json',b'/user/app/PPSA01234/sce_sys/../eboot.bin',b'/user/app/PPSA01234/sce_sys',b'/user/appmeta/PPSA01234/sce_sys/pic0.dds',b'/user/app/ppsa01234/sce_sys/pic0.dds'):
   self.assertFalse(self.lib.pb_file(path,len(path)),path)
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
if __name__=='__main__':unittest.main()
