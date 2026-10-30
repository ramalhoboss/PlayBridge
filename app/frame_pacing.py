"""Even video pacing: one clock step per monitor refresh, so the network's uneven arrival does not reach the screen."""
import collections,ctypes,math,threading,time

CAPTURE_FRAME=1001/60000

class FramePacer:
 """Prepared frames wait here for their turn on a playback clock. The clock moves by whole refreshes rather than wall time, so a frame's turn cannot flip between two refreshes."""
 def __init__(self,stats,lead=1.5,max_lead=3,capacity=6,window=3,spare=.25):
  # In frames, except the window in seconds. A half-frame lead keeps each frame's turn away from a refresh boundary, and steps of a whole frame keep it there.
  self.stats=stats;self.lead=lead*CAPTURE_FRAME;self.max_lead=max_lead*CAPTURE_FRAME;self.capacity=capacity;self.window=window;self.spare=spare*CAPTURE_FRAME;self.items=collections.deque();self.clear()
 def clear(self):
  self.items.clear();self.clock=None;self.newest=None;self.shown=None;self.spacing=CAPTURE_FRAME;self.fastest=self.recent=math.inf;self.lowest=math.inf;self.elapsed=0
 def add(self,pts,item,now):
  # The first frame, or a jump in the timestamps, restarts the clock.
  if self.clock is None or not 0<pts-self.newest<1:self.clock=pts-self.lead;self.shown=None;self.fastest=self.recent=now-pts
  else:self.spacing=pts-self.newest
  self.newest=pts;self.items.append((pts,item));self.fastest=min(self.fastest,now-pts);self.recent=min(self.recent,now-pts)
  if len(self.items)>self.capacity:
   # Too far behind the stream: skip ahead instead of adding delay.
   self.items.popleft();self.stats['prepared_replaced']+=1;self.clock=max(self.clock,self.items[0][0]-self.lead)
 def advance(self,seconds,now):
  """Moves the clock by whole refreshes and returns the frame whose turn has come, or None to keep the current picture."""
  if self.clock is None:return None
  self.clock+=seconds;item=None
  while self.items and self.items[0][0]<=self.clock:
   if item is not None:self.stats['prepared_replaced']+=1
   self.shown,item=self.items.popleft()
  self.lowest=min(self.lowest,self.newest-self.clock);self.elapsed+=seconds
  if item is None and self.shown is not None and self.clock>=self.shown+self.spacing and now-self.clock-self.fastest<self.max_lead:
   # The next frame is late. Waiting for it leaves a larger margin for the ones after it.
   self.clock-=seconds;self.stats['video_late_waits']+=1
  if self.elapsed>=self.window:
   # Frames kept arriving this far ahead of the clock for the whole window: give a frame of delay back.
   if self.lowest>=self.spare:self.clock+=CAPTURE_FRAME
   self.fastest=self.recent;self.recent=math.inf;self.lowest=math.inf;self.elapsed=0
  return item

class RefreshClock:
 """Counts monitor refreshes on its own thread, because waiting for one would block the Tk loop."""
 def __init__(self,stop,flush=None):
  self.stop=stop;self.count=0;self.seen=0;self.samples=0;self.period=1/60;self.synced=False;self.read_at=time.perf_counter();self.flush=flush
  if flush is None:
   try:self.flush=ctypes.windll.dwmapi.DwmFlush
   except (AttributeError,OSError):pass
  if self.flush is not None:threading.Thread(target=self.run,name='PlayBridge refresh clock',daemon=True).start()
 def run(self):
  last=time.perf_counter()
  while not self.stop.is_set():
   failed=self.flush();now=time.perf_counter();gap=now-last;last=now
   # Without composition, as on a locked session, the call returns at once.
   if failed or gap<.002:self.synced=False;self.stop.wait(.005);last=time.perf_counter();continue
   if gap<.05:self.samples=min(self.samples+1,50);self.period+=(gap-self.period)/self.samples
   self.count+=max(1,round(gap/self.period));self.synced=True
 def elapsed(self,now):
  """The time to move the playback clock: whole refreshes when they can be counted, otherwise wall time."""
  if self.synced:
   steps=self.count-self.seen;self.seen+=steps;self.read_at=now
   return steps*self.period
  seconds=now-self.read_at;self.read_at=now;self.seen=self.count
  return seconds
