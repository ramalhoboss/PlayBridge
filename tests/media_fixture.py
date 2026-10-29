"""Small local encoder fixture: no console dump or network is needed."""
from fractions import Fraction
import av,numpy as np

def packets(seconds=2):
 v=av.CodecContext.create('libx264','w');v.width=160;v.height=96;v.pix_fmt='yuv420p';v.time_base=Fraction(1,30);v.framerate=Fraction(30,1);v.options={'preset':'ultrafast','tune':'zerolatency','x264-params':'keyint=10:min-keyint=10:scenecut=0:repeat-headers=1'};v.open()
 a=av.CodecContext.create('aac','w');a.sample_rate=48000;a.layout='stereo';a.format='fltp';a.bit_rate=128000;a.time_base=Fraction(1,48000);a.open()
 result=[]
 for i in range(seconds*30):
  rgb=np.zeros((96,160,3),dtype=np.uint8);rgb[:]=[i%180,50,120]
  f=av.VideoFrame.from_ndarray(rgb,format='rgb24').reformat(format='yuv420p');f.pts=i;f.time_base=Fraction(1,30)
  for p in v.encode(f):result.append((1,bytes(p),int(p.pts*p.time_base*90000),int(p.dts*p.time_base*90000)))
 for p in v.encode(None):result.append((1,bytes(p),int(p.pts*p.time_base*90000),int(p.dts*p.time_base*90000)))
 def add_audio(p):
  if p.pts is None or p.pts<0:return
  b=bytes(p);n=len(b)+7;adts=bytes([255,241,76,128|(n>>11),(n>>3)&255,((n&7)<<5)|31,252])+b
  result.append((2,adts,int(p.pts*p.time_base*90000),int(p.dts*p.time_base*90000)))
 for i in range((seconds*48000+1023)//1024):
  f=av.AudioFrame.from_ndarray(np.zeros((2,1024),dtype=np.float32),format='fltp',layout='stereo');f.sample_rate=48000;f.pts=i*1024;f.time_base=Fraction(1,48000)
  for p in a.encode(f):add_audio(p)
 for p in a.encode(None):add_audio(p)
 return sorted(result,key=lambda x:(x[3],x[0]))
