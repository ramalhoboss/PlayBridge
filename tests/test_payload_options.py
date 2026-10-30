"""Runs the sender's option logic on the PC: compiled from the payload header without the PS5 SDK."""
import ctypes,os,shutil,struct,subprocess,tempfile,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HARNESS=r'''
#include <stdint.h>
void*memcpy(void*d,const void*s,unsigned long long n){char*a=d;const char*b=s;while(n--)*a++=*b++;return d;}
static void u32(unsigned char*p,int o,uint32_t v){memcpy(p+o,&v,4);}
static void u64(unsigned char*p,int o,uint64_t v){memcpy(p+o,&v,8);}
#include "capture-options.h"
__declspec(dllexport) int pb_valid(uint32_t r,uint32_t b){return valid_target(r,b);}
__declspec(dllexport) uint32_t pb_supported(uint32_t r,uint32_t m){return supported_resolution(r,m);}
__declspec(dllexport) uint32_t pb_apply(unsigned char*p,uint32_t r,uint32_t f,uint32_t b){return apply_resolution(p,r,f,b);}
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
   for m in ok:self.assertTrue(self.lib.pb_valid(r,m*1000000),(r,m))
   for m in bad:self.assertFalse(self.lib.pb_valid(r,m*1000000),(r,m))
  self.assertFalse(self.lib.pb_valid(0,8000000));self.assertFalse(self.lib.pb_valid(7,80000000))
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
if __name__=='__main__':unittest.main()
