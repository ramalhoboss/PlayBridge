"""Finds out where the window's thread is when it stops answering, for the session timeline on this PC."""
import collections,os,sys,threading,time

def where(frame,depth=4):
 """The innermost calls of a stack, as file:line function, innermost first."""
 calls=[]
 while frame is not None and len(calls)<depth:
  code=frame.f_code;calls.append(f'{os.path.basename(code.co_filename)}:{frame.f_lineno} {code.co_name}');frame=frame.f_back
 return ' < '.join(calls)

class HangWatch:
 """Looks at a thread's stack while it has not called beat() for longer than threshold seconds.
 beat() returns where it was most of that time, or an empty string when it never stopped."""
 def __init__(self,ident,stop,threshold=.25,every=.1,limit=8):
  self.ident=ident;self.stop=stop;self.threshold=threshold;self.every=every;self.limit=limit
  self.lock=threading.Lock();self.last=time.perf_counter();self.samples=[]
  threading.Thread(target=self.run,name='PlayBridge hang watch',daemon=True).start()
 def beat(self):
  with self.lock:
   self.last=time.perf_counter();samples,self.samples=self.samples,[]
  if not samples:return ''
  place,count=collections.Counter(samples).most_common(1)[0]
  return place if count==len(samples) else f'{place} ({count} of {len(samples)} looks)'
 def run(self):
  while not self.stop.wait(self.every):
   with self.lock:
    if time.perf_counter()-self.last<self.threshold or len(self.samples)>=self.limit:continue
   frame=sys._current_frames().get(self.ident)
   if frame is None:return
   place=where(frame);del frame
   with self.lock:
    if time.perf_counter()-self.last>=self.threshold:self.samples.append(place)
