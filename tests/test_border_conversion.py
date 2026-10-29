import sys,json,time
from pathlib import Path
import os
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import av,numpy as np
from video_convert import reformat_for_display
src=np.zeros((1080,1920,3),dtype=np.uint8);src[:]=[10,20,30]
f=av.VideoFrame.from_ndarray(src,format='rgb24').reformat(format='yuv420p',threads=1)
results=[]
for width,height in [(1468,826),(1470,828),(1280,720),(1467,825),(1920,1080),(902,507)]:
 for fmt in ['bgr0','rgb24']:
  times=[];bright=0
  for i in range(12):
   t=time.perf_counter();b=reformat_for_display(f,width,height,fmt);times.append((time.perf_counter()-t)*1000)
   p=b.planes[0];channels=4 if fmt=='bgr0' else 3
   pixels=np.frombuffer(p,np.uint8).reshape(height,p.line_size)[:,:width*channels].reshape(height,width,channels)[:,:,:3]
   bright+=int(np.count_nonzero(pixels.max(axis=2)>60))
  assert bright==0,(width,height,fmt,bright)
  results.append({'size':[width,height],'format':fmt,'frames':12,'unexpected_bright_pixels':bright,'mean_ms':round(sum(times[2:])/len(times[2:]),3)})
# Reproduce the defect using the previous default path, with its own reformatter.
from av.video.reformatter import VideoReformatter
r=VideoReformatter();baseline=0
for _ in range(20):
 b=r.reformat(f,width=1468,height=826,format='bgr0');p=b.planes[0];a=np.frombuffer(p,np.uint8).reshape(826,p.line_size)
 baseline+=int(np.sum(a[:,:3].max(axis=1)>60))
# The old-path defect is hardware/build dependent; corrected pixels must always pass.
report={'baseline_unexpected_edge_pixels':baseline,'corrected_cases':results}
output=Path(__file__).resolve().parents[1]/'build'/'validation-border-conversion.json'
output.parent.mkdir(exist_ok=True);output.write_text(json.dumps(report,indent=2))
print(json.dumps(report))
