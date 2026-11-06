"""Even video pacing: one clock step per monitor refresh, so the network's uneven arrival does not reach the screen."""
import collections,ctypes,math,threading,time

CAPTURE_FRAME=1001/60000
# Gaps in a row that disagree with the refresh length before it is learnt again: one screen rate gave way to another.
RELEARN=20

class FramePacer:
 """Prepared frames wait here for their turn on a playback clock. The clock moves by whole refreshes rather than wall time, so a frame's turn cannot flip between two refreshes."""
 def __init__(self,stats,lead=1.5,max_lead=3,capacity=6,window=3,spare=.25):
  # In frames, except the window in seconds. A half-frame lead keeps each frame's turn away from a refresh boundary, and steps of a whole frame keep it there.
  self.stats=stats;self.lead=lead*CAPTURE_FRAME;self.max_lead=max_lead*CAPTURE_FRAME;self.capacity=capacity;self.window=window;self.spare=spare*CAPTURE_FRAME;self.items=collections.deque()
  # Refreshes where the next frame was due and not there, for the stats.
  self.missing=0;self.clear()
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
  late=item is None and self.shown is not None and self.clock>=self.shown+self.spacing
  # The next frame is due and not there: the network or the decoder held it up.
  if late:self.missing+=1
  if late and now-self.clock-self.fastest<self.max_lead:
   # The next frame is late. Waiting for it leaves a larger margin for the ones after it.
   self.clock-=seconds;self.stats['video_late_waits']+=1
  if self.elapsed>=self.window:
   # Frames kept arriving this far ahead of the clock for the whole window: give a frame of delay back.
   if self.lowest>=self.spare:self.clock+=CAPTURE_FRAME
   self.fastest=self.recent;self.recent=math.inf;self.lowest=math.inf;self.elapsed=0
  return item
 def due(self):
  """Seconds until the next frame's turn on the playback clock, or None when no frame is waiting. For a screen with variable refresh,
  where each frame is shown at its own time rather than on the next refresh."""
  if self.clock is None or not self.items:return None
  return self.items[0][0]-self.clock

def precise_sleep():
 """A sleep that ends within about half a millisecond, from a high-resolution waitable timer. time.sleep can overshoot by a whole
 millisecond or more, which a screen that follows each frame would show."""
 try:
  kernel=ctypes.WinDLL('kernel32');kernel.CreateWaitableTimerExW.restype=ctypes.c_void_p;kernel.CreateWaitableTimerExW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32]
  kernel.SetWaitableTimer.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_longlong),ctypes.c_long,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int];kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
  # CREATE_WAITABLE_TIMER_HIGH_RESOLUTION, with TIMER_ALL_ACCESS.
  timer=kernel.CreateWaitableTimerExW(None,None,2,0x1F0003)
  if not timer:return time.sleep
 except (AttributeError,OSError):return time.sleep
 def sleep(seconds):
  due=ctypes.c_longlong(-max(1,int(seconds*1e7)))
  if kernel.SetWaitableTimer(timer,ctypes.byref(due),0,None,None,0):kernel.WaitForSingleObject(timer,1000)
  else:time.sleep(seconds)
 return sleep

class FrameTimer:
 """For a screen with variable refresh: wakes when the next frame's turn comes instead of on each refresh, so a 59.94 fps stream is shown
 every 16.7 ms on a 144 Hz screen too, rather than alternating 13.9 and 20.8 ms. Same use as RefreshClock: after() runs on its thread."""
 # While no frame waits, it looks again this often, so a late frame shows as soon as it is ready.
 IDLE=.002
 # It wakes this much after a frame's turn, so the clock is past the frame's timestamp when it looks: waking on it exactly, rounding
 # could leave the clock a hair short, and the pacer would take the frame for late and hold its clock back.
 SLACK=.0002
 def __init__(self,stop,due,period=CAPTURE_FRAME,sleep=None,start=True,spacing=None):
  # spacing: the shortest time between two frames, as the screen's own refresh. After the network held frames up they come close
  # together, and one sent while the screen still draws the last would tear. last: when the last frame was shown.
  self.stop=stop;self.due=due;self.period=period;self.spacing=spacing or (lambda:0.0);self.last=None;self.synced=False;self.read_at=time.perf_counter();self.after=None
  self.sleep=sleep or precise_sleep()
  if start:threading.Thread(target=self.run,name='PlayBridge frame timer',daemon=True).start()
 def wait(self):
  """How long to sleep before the next look: until the next frame's turn, never longer than a frame."""
  try:left=self.due()
  except Exception:left=None
  if left is None:return self.IDLE
  if self.last is not None:left=max(left,self.last+self.spacing()-time.perf_counter())
  if left<=0:return 0.0
  return min(left+self.SLACK,self.period)
 def run(self):
  while not self.stop.is_set():
   left=self.wait()
   if left>0:self.sleep(left)
   if self.after:self.after()
 def elapsed(self,now):
  """Wall time since the last call: there are no refreshes to count."""
  seconds=now-self.read_at;self.read_at=now;return seconds

class HitchWatch:
 """Names why a frame stayed up longer than the stream asked for, so a stutter on a PC nobody here can see still has a cause in the stats.
 On a 144 Hz screen a frame that stays up 20.8 ms instead of 16.7 is that screen's judder: a hitch is a whole refresh more than that."""
 CAUSES=('present','stream','busy')
 def __init__(self,keep=30):
  self.counts={cause:0 for cause in (*self.CAUSES,'other')};self.log=collections.deque(maxlen=keep);self.seen=set();self.last=None
 def refresh(self,steps,missing,slow_paint):
  """Once a refresh: how many refreshes passed since the last call, whether the next frame was due and not there, and whether
  the last paint took longer than a refresh, as when the swap chain kept it waiting."""
  if steps>=2:self.seen.add('present' if slow_paint else 'busy')
  if missing:self.seen.add('stream')
 def unpresented(self):self.seen.add('present')
 def shown(self,done,period,at):
  """A frame reached the screen. Returns the cause when the one before it stayed up a refresh too long."""
  last,self.last=self.last,done;seen,self.seen=self.seen,set()
  if last is None or done-last>=.25:return None
  gap=done-last
  if gap<CAPTURE_FRAME+.9*period:return None
  cause=next((name for name in self.CAUSES if name in seen),'other')
  self.counts[cause]+=1;self.log.append((round(at,1),round(gap*1000,1),cause));return cause

class RefreshClock:
 """Counts monitor refreshes on its own thread, because waiting for one would block the Tk loop."""
 def __init__(self,stop,flush=None):
  self.stop=stop;self.count=0;self.seen=0;self.samples=0;self.odd=0;self.period=1/60;self.synced=False;self.read_at=time.perf_counter();self.flush=flush;self.after=None
  if flush is None:
   try:self.flush=ctypes.windll.dwmapi.DwmFlush
   except (AttributeError,OSError):pass
  if self.flush is not None:threading.Thread(target=self.run,name='PlayBridge refresh clock',daemon=True).start()
 def run(self):
  last=time.perf_counter();partial=True
  while not self.stop.is_set():
   failed=self.flush();now=time.perf_counter();gap=now-last;last=now
   # Without composition, as on a locked session, the call returns at once.
   if failed or gap<.002:self.synced=False;partial=True;self.stop.wait(.005);last=time.perf_counter()
   else:self.measure(gap,partial);partial=False
   if self.after:self.after()
 def measure(self,gap,partial=False):
  """Counts the refreshes in one gap. The first gap after a start or a pause is part of a refresh. Later only a gap of about one refresh
  measures its length: a missed refresh would stretch it for seconds, and the clock would run fast and skip frames. A long run of gaps
  that all disagree means the screen now runs at another rate, as when PlayBridge or Windows switches it, so the length is learnt again."""
  if not partial:
   if self.samples<10 or abs(gap-self.period)<self.period/4:self.samples=min(self.samples+1,50);self.period+=(gap-self.period)/self.samples;self.odd=0
   else:
    self.odd+=1
    if self.odd>=RELEARN:self.samples=0;self.odd=0
  self.count+=max(1,round(gap/self.period));self.synced=True
 def elapsed(self,now):
  """The time to move the playback clock: whole refreshes when they can be counted, otherwise wall time."""
  if self.synced:
   steps=self.count-self.seen;self.seen+=steps;self.read_at=now
   return steps*self.period
  seconds=now-self.read_at;self.read_at=now;self.seen=self.count
  return seconds
