"""Which video encoders this PC really has, found by trying them, and the settings each one gets.
The PS5 only sends H.264 (HEVC at most 1080p30), so AV1 and HEVC can only be made here. FFmpeg lists every encoder it was built with,
whether or not this PC has the hardware, so each one is tried on two small frames before it is offered, once per run of the app."""
import threading
from fractions import Fraction
import av

# Graphics cards first: they cost the processor almost nothing. AV1 needs an RTX 40, an Intel Arc or a recent Intel processor.
# AMD's AV1 (RX 7000 and later) comes after its HEVC: its picture height has to be a multiple of 64, and 1080, 1440 and 2160 are not.
HARDWARE=('av1_nvenc','av1_qsv','hevc_nvenc','hevc_qsv','hevc_amf','av1_amf')
# The processor's AV1 runs anywhere, too slowly for a live 4K stream but fine for a file that can take its time.
SOFTWARE=('libsvtav1',)
NAMES={'av1_nvenc':'AV1 on the NVIDIA card','av1_qsv':'AV1 on the Intel graphics','av1_amf':'AV1 on the AMD card','hevc_nvenc':'HEVC on the NVIDIA card','hevc_qsv':'HEVC on the Intel graphics','hevc_amf':'HEVC on the AMD card','libsvtav1':'AV1 on the processor'}

_lock=threading.Lock();_found=None

def kind(name):return 'av1' if 'av1' in name else 'hevc'

def pixel_format(name,live=False):
 """The input format the encoder takes. Every graphics card takes NV12, which is what a graphics card's decoder hands back, so a live
 stream needs no conversion. Files are decoded on the processor as yuv420p, which all but Intel's take as they are."""
 if name.endswith('_qsv') or (live and name in HARDWARE):return 'nv12'
 return 'yuv420p'

def options(name,live=False):
 """Quality-leaning settings, with the live ones kept fast enough for 60 fps."""
 if name.endswith('_nvenc'):return {'preset':'p4' if live else 'p6','tune':'ll' if live else 'hq','rc':'vbr'}
 if name.endswith('_amf'):return {'usage':'lowlatency' if live else 'transcoding','quality':'balanced' if live else 'quality','rc':'vbr_peak'}
 if name.endswith('_qsv'):return {'preset':'faster' if live else 'slower'}
 if name=='libsvtav1':return {'preset':'10' if live else '8'}
 return {}

def _works(name):
 """Opens the encoder and gives it two frames, because some open and only fail on the first frame."""
 try:
  context=av.CodecContext.create(name,'w');context.width=context.height=256;context.pix_fmt=pixel_format(name);context.time_base=Fraction(1,60);context.framerate=Fraction(60,1);context.bit_rate=1000000
  context.options={key:value for key,value in options(name).items() if key in ('preset','usage')}
  context.open()
  frame=av.VideoFrame(256,256,pixel_format(name))
  for plane in frame.planes:plane.update(bytes(plane.buffer_size))
  packets=0
  for index in range(2):
   frame.pts=index;packets+=len(context.encode(frame))
  packets+=len(context.encode(None))
  return packets>0
 except Exception:return False

def found():
 """Every encoder that works here, in the order they are preferred. Tried once, in whichever thread asks first."""
 global _found
 with _lock:
  if _found is None:_found=[name for name in HARDWARE+SOFTWARE if _works(name)]
  return list(_found)

def for_live():
 """The encoder for a live stream: a graphics card's, or None. The processor's AV1 would take the cores the picture needs."""
 return next((name for name in found() if name in HARDWARE),None)

def for_files():
 """The encoder for making recordings smaller: a graphics card's when there is one, otherwise the processor's AV1."""
 return next(iter(found()),None)

def bitrate(name,height,source=0,live=False):
 """Bits per second: AV1 needs about a third less than HEVC for the same picture, and both far less than the PS5's H.264.
 Never more than the source had, since the picture cannot gain what the PS5 left out."""
 steps=((1080,6_000_000,8_000_000),(1440,10_000_000,14_000_000),(2160,16_000_000,22_000_000))
 av1_rate,hevc_rate=next(((a,h) for top,a,h in steps if height<=top),steps[-1][1:])
 rate=av1_rate if kind(name)=='av1' else hevc_rate
 if not live:rate=rate*5//4
 if source:rate=min(rate,int(source*.8))
 return max(rate,1_000_000)
