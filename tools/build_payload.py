"""Build the firmware-13.60 payload with an external PS5 homebrew SDK."""
import argparse,os,shutil,subprocess
from pathlib import Path

def main():
 root=Path(__file__).resolve().parents[1]
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--sdk',default=os.environ.get('PS5_PAYLOAD_SDK'),help='ps5-payload-sdk root; or set PS5_PAYLOAD_SDK')
 ap.add_argument('--llvm',default=os.environ.get('LLVM_BIN'),help='LLVM bin directory; otherwise use PATH')
 ap.add_argument('--output',type=Path,default=root/'PlayBridge.elf')
 args=ap.parse_args()
 if not args.sdk:ap.error('Set --sdk or PS5_PAYLOAD_SDK to your installed PS5 payload SDK.')
 sdk=Path(args.sdk).resolve();out=args.output.resolve();out.parent.mkdir(parents=True,exist_ok=True)
 work=root/'build/payload';work.mkdir(parents=True,exist_ok=True);obj=work/'stream-av3.o'
 def tool(name):
  suffix='.exe' if os.name=='nt' else ''
  p=str(Path(args.llvm)/(name+suffix)) if args.llvm else shutil.which(name)
  if not p or not Path(p).is_file():ap.error('Missing LLVM tool: '+name)
  return p
 for required in ['target/include/ps5/kernel.h','target/lib/crt1.o','ldscripts/elf_x86_64.x']:
  if not (sdk/required).is_file():ap.error('SDK file not found: '+str(sdk/required))
 subprocess.run([tool('clang'),'-target','x86_64-sie-ps5','-std=c11','-O2','-fno-stack-protector','-fno-plt','-femulated-tls','-Wall','-Wextra','-Werror','-isystem',str(sdk/'target/include'),'-c',str(root/'payload/stream-av3.c'),'-o',str(obj)],check=True)
 subprocess.run([tool('ld.lld'),'-m','elf_x86_64','-pie','--eh-frame-hdr','-z','max-page-size=0x4000','-L',str(sdk/'target/lib'),'-T',str(sdk/'ldscripts/elf_x86_64.x'),'-o',str(out),'-lc',str(sdk/'target/lib/crt1.o'),str(obj),'-lkernel_web','-lSceLibcInternal','-lSceNet','--hash-style=gnu'],check=True)
 subprocess.run([tool('llvm-readobj'),'--file-headers',str(out)],check=True)
 print('Built: '+str(out))
if __name__=='__main__':main()
