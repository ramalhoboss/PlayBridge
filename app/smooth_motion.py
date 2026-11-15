"""Smooth motion: on a screen faster than the stream, such as 60 fps on a 120 or 144 Hz monitor, the refreshes between two frames show
pictures the graphics card makes from the motion between them (in_between.py) instead of the same frame again. This decides, refresh by
refresh, when such a picture is wanted, and stops them for the session on a PC that cannot keep up."""
import time

NOTE=('On a screen faster than the stream, such as 60 fps on a 120 or 144 Hz monitor, the graphics card makes a picture between every two '
      'frames from the motion in them, so the game moves as smoothly as the screen can show. It starts by itself on such a screen, and a '
      'screen that can go to 120 Hz is switched to it while the game streams. Adds about half a frame of delay.')
# Swap chains not ready in time, in one second, for so many seconds in a row while in-between pictures are on: the card or the screen
# cannot keep up with the extra pictures, so the stream goes back to one picture a frame.
TIMEOUTS=4;SECONDS=3

class SmoothMotion:
 def __init__(self,stats,timings,on=True):
  self.on=bool(on);self.stats=stats;self.timings=timings
  # active: in-between pictures were wanted on the last refresh. stopped: why they ended for this session, when they did.
  self.active=False;self.stopped=None;self.last=None;self.seen_timeouts=None;self.bad=0
 def ready(self,output,period,spacing):
  """True when the next refreshes can show in-between pictures: they are on and have not stopped, the output can make them, the last
  frame was decoded on the graphics card, and the screen is at least half again as fast as the stream. period: the screen's refresh;
  spacing: the time between two frames of the stream."""
  frame=getattr(output,'frame',None)
  self.active=bool(self.on and self.stopped is None and getattr(output,'smooth',False) and getattr(output,'smooth_failed',None) is None
                   and frame is not None and getattr(frame.format,'name','')=='d3d11' and period>0 and period*1.5<=spacing)
  return self.active
 def can_run(self,output):
  """True while in-between pictures could be made whatever the rates: they are on and have not stopped, and the output makes them from
  frames decoded on the graphics card. A game's repeated frames are left out only then (repeat_frames.py)."""
  frame=getattr(output,'frame',None)
  return bool(self.on and self.stopped is None and getattr(output,'smooth',False) and getattr(output,'smooth_failed',None) is None
              and frame is not None and getattr(frame.format,'name','')=='d3d11')
 def ahead(self,output,period,spacing,vrr=False):
  """How long before its turn the pacer needs the next frame: by the first refresh after the shown frame on a fixed screen, by the
  middle between the two with variable refresh. 0 when there will be no in-between picture."""
  if not self.ready(output,period,spacing):return 0.0
  return spacing/2 if vrr else spacing-period
 def show(self,output,pick):
  """Shows the in-between picture the pacer chose, (t, shown item, next item). True when the screen has it or already had it."""
  t,first,second=pick;key=(id(first[0]),id(second[0]),round(t,3))
  if key==self.last:return True
  started=time.perf_counter();shown=output.between(first[0],second[0],t)
  self.timings.add('between_ms',(time.perf_counter()-started)*1000)
  if shown:self.last=key;self.stats['between_presented']=self.stats.get('between_presented',0)+1
  return shown
 def second(self,output,timeouts):
  """Once a second, with the output's count of swap chains not ready in time. Returns the stats line."""
  if self.seen_timeouts is not None and self.active and self.stopped is None:
   self.bad=self.bad+1 if timeouts-self.seen_timeouts>=TIMEOUTS else 0
   if self.bad>=SECONDS:self.stopped='the screen kept waiting for pictures';self.active=False
  self.seen_timeouts=timeouts
  return self.state(output)
 def state(self,output):
  failed=getattr(output,'smooth_failed',None)
  if not self.on:return 'off'
  # Only the kind of fault, as diagnostics leave error messages out.
  if failed or self.stopped:return 'stopped: '+(self.stopped or str(failed).split(':')[0])
  if not getattr(output,'smooth',False):return 'off'
  return 'on' if self.active else 'waiting for a screen faster than the stream'
 def turn(self,output,on):
  """The setting changed. Turning it on again gives a session that stopped another try."""
  self.on=bool(on);self.stopped=None;self.bad=0;self.last=None
  if output is not None and hasattr(output,'smooth'):
   output.smooth=self.on
   if self.on:output.smooth_failed=None
