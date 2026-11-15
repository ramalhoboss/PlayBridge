"""Smooth motion: which refreshes get an in-between picture, how early the pacer needs the next frame for one, and when they stop."""
import collections,random,sys,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from frame_pacing import CAPTURE_FRAME as F,FramePacer
import smooth_motion as s

class Timings:
 def __init__(self):self.added=collections.defaultdict(list)
 def add(self,name,value):self.added[name].append(value)
class Output:
 """What SmoothMotion reads from the D3D11 output, and its in-between pictures as calls."""
 def __init__(self,name='d3d11',smooth=True):
  self.smooth=smooth;self.smooth_failed=None;self.frame=SimpleNamespace(format=SimpleNamespace(name=name));self.calls=[];self.answer=True
 def between(self,a,b,t):self.calls.append((a,b,round(t,3)));return self.answer

def play(arrivals,refresh=F/2,ahead=None):
 """A 60 fps stream on a faster screen: each refresh shows the frame whose turn came, or else the in-between picture the pacer picks.
 Returns one entry a refresh: ('frame', n), ('between', n, n+1, t) or None."""
 stats=collections.Counter();p=FramePacer(stats);screen=[];next_frame=0;t=arrivals[0];count=0;end=arrivals[-1]+.3
 ahead=F-refresh if ahead is None else ahead
 while t<end and not (screen and screen[-1]==('frame',len(arrivals)-1)):
  while next_frame<len(arrivals) and arrivals[next_frame]<=t:p.add(next_frame*F,next_frame,arrivals[next_frame]);next_frame+=1
  shown=p.advance(refresh,t,ahead)
  if shown is not None:screen.append(('frame',shown))
  else:
   pick=p.between(refresh)
   screen.append(('between',pick[1],pick[2],round(pick[0],2)) if pick else None)
  count+=1;t=arrivals[0]+count*refresh
 first=next(i for i,x in enumerate(screen) if x and x[0]=='frame')
 return screen[first:],stats

class PacerTests(unittest.TestCase):
 def test_at_120_hz_every_frame_is_followed_by_the_picture_half_way_to_the_next(self):
  screen,stats=play([10+i*F for i in range(600)])
  frames=[x[1] for x in screen if x and x[0]=='frame'];betweens=[x for x in screen if x and x[0]=='between']
  self.assertEqual(frames,sorted(frames));self.assertGreaterEqual(len(frames),598)
  self.assertGreaterEqual(len(betweens),len(frames)-3);self.assertEqual(stats['between_waits'],0)
  for _,a,b,t in betweens:self.assertEqual((b-a,t),(1,.5))
 def test_at_144_hz_the_pictures_fall_at_their_own_place_between_the_frames(self):
  screen,_=play([10+i*F for i in range(600)],refresh=1/144)
  # Two refreshes until the next frame give it the middle; three give a third and two thirds, so no picture shows twice.
  ts=sorted({x[3] for x in screen if x and x[0]=='between'});self.assertEqual(ts,[.33,.5,.67])
  self.assertNotIn(None,screen[:-1])
  self.assertGreater(sum(1 for x in screen if x and x[0]=='between'),300)
 def test_a_screen_as_slow_as_the_stream_gets_no_in_between_pictures(self):
  stats=collections.Counter();p=FramePacer(stats)
  for i in range(4):p.add(i*F,i,0)
  self.assertEqual(p.advance(1.5*F,0),0);self.assertIsNone(p.advance(F/2,0))
  self.assertIsNone(p.between(F));self.assertEqual(round(p.between(F/2)[0],2),.5)
 def test_a_jittery_stream_still_shows_every_frame_in_order(self):
  rng=random.Random(2);arrivals=[];last=0
  for i in range(1200):last=max(last,10+i*F+rng.uniform(0,.012));arrivals.append(last)
  screen,stats=play(arrivals)
  frames=[x[1] for x in screen if x and x[0]=='frame'];self.assertEqual(frames,sorted(frames));self.assertGreaterEqual(len(frames),1190)
  self.assertGreater(sum(1 for x in screen if x and x[0]=='between'),1000)
 def test_a_frame_needed_early_and_not_here_holds_the_clock(self):
  stats=collections.Counter();p=FramePacer(stats);p.add(0,'a',0);p.add(F,'b',0)
  while p.advance(F/2,0,F/2)!='a':pass
  while p.advance(F/2,0,F/2)!='b':pass
  # The next frame, 'c', is not here a refresh after 'b' showed: the clock waits for it instead of reaching the middle without it.
  clock=p.clock;self.assertIsNone(p.advance(F/2,0,F/2));self.assertEqual(p.clock,clock);self.assertEqual(stats['between_waits'],1)
  p.add(2*F,'c',0);self.assertIsNone(p.advance(F/2,0,F/2));pick=p.between(F/2);self.assertEqual((round(pick[0],2),pick[1],pick[2]),(.5,'b','c'))
 def test_variable_refresh_wakes_at_the_middle_then_at_the_next_frame(self):
  stats=collections.Counter();p=FramePacer(stats);p.add(0,'a',0);p.add(F,'b',0)
  p.advance(p.due(),0);due=p.due(middle=True);self.assertAlmostEqual(due,F/2,places=6)
  p.advance(due,0);pick=p.between(1/144,vrr=True);self.assertEqual((round(pick[0],2),pick[1],pick[2]),(.5,'a','b'))
  self.assertAlmostEqual(p.due(middle=True),F/2,places=6)
 def test_a_middle_that_went_by_never_makes_the_timer_spin(self):
  stats=collections.Counter();p=FramePacer(stats);p.add(0,'a',0);p.add(F,'b',0)
  p.advance(p.due(),0);p.advance(.75*F,0)
  self.assertAlmostEqual(p.due(middle=True),.25*F,places=6);self.assertGreater(p.due(middle=True),0)

class SmoothTests(unittest.TestCase):
 def smooth(self,on=True):return s.SmoothMotion(collections.Counter(),Timings(),on)
 def test_it_starts_only_on_a_screen_half_again_as_fast_as_the_stream(self):
  smooth=self.smooth();output=Output()
  for hz,ready in ((120,True),(144,True),(165,True),(90,True),(60,False),(75,False)):self.assertEqual(smooth.ready(output,1/hz,F),ready,hz)
  # A 30 fps stream has room for one on a 60 Hz screen.
  self.assertTrue(smooth.ready(output,1/60,2*F))
 def test_it_waits_for_frames_from_the_graphics_card_and_a_working_output(self):
  smooth=self.smooth()
  self.assertFalse(smooth.ready(Output('nv12'),1/120,F));self.assertFalse(smooth.ready(Output(smooth=False),1/120,F))
  failed=Output();failed.smooth_failed='OSError: lost';self.assertFalse(smooth.ready(failed,1/120,F))
  empty=Output();empty.frame=None;self.assertFalse(smooth.ready(empty,1/120,F));self.assertFalse(self.smooth(False).ready(Output(),1/120,F))
  self.assertFalse(smooth.ready(SimpleNamespace(frame=None),1/120,F))
 def test_the_next_frame_is_needed_a_refresh_after_its_turn_or_by_the_middle_with_variable_refresh(self):
  smooth=self.smooth();output=Output()
  self.assertAlmostEqual(smooth.ahead(output,1/120,F),F-1/120);self.assertAlmostEqual(smooth.ahead(output,1/144,F,vrr=True),F/2)
  self.assertEqual(smooth.ahead(output,1/60,F),0);self.assertTrue(smooth.active is False)
 def test_each_picture_is_made_once_and_counted(self):
  smooth=self.smooth();output=Output();a=('A',0,0);b=('B',0,0)
  for _ in range(3):self.assertTrue(smooth.show(output,(.5,a,b)))
  self.assertEqual(output.calls,[('A','B',.5)]);self.assertEqual(smooth.stats['between_presented'],1);self.assertEqual(len(smooth.timings.added['between_ms']),1)
  output.answer=False;self.assertFalse(smooth.show(output,(.25,a,b)));self.assertEqual(smooth.stats['between_presented'],1)
 def test_a_pc_that_keeps_missing_pictures_stops_them_for_the_session(self):
  smooth=self.smooth();output=Output();smooth.ready(output,1/120,F);timeouts=0
  self.assertEqual(smooth.second(output,timeouts),'on')
  for _ in range(s.SECONDS):timeouts+=s.TIMEOUTS;line=smooth.second(output,timeouts)
  self.assertEqual(line,'stopped: the screen kept waiting for pictures');self.assertFalse(smooth.ready(output,1/120,F))
  smooth.turn(output,True);self.assertTrue(smooth.ready(output,1/120,F))
 def test_a_few_misses_do_not_stop_them(self):
  smooth=self.smooth();output=Output();smooth.ready(output,1/120,F);timeouts=0;smooth.second(output,0)
  for second in range(30):timeouts+=s.TIMEOUTS if second%2 else 1;smooth.second(output,timeouts)
  self.assertIsNone(smooth.stopped)
 def test_the_stats_say_what_it_does(self):
  output=Output();smooth=self.smooth()
  self.assertEqual(smooth.state(output),'waiting for a screen faster than the stream')
  smooth.ready(output,1/120,F);self.assertEqual(smooth.state(output),'on')
  output.smooth_failed='OSError: device lost at 0x1234';self.assertEqual(smooth.state(output),'stopped: OSError')
  self.assertEqual(self.smooth(False).state(Output()),'off')
 def test_turning_it_off_and_on_reaches_the_output(self):
  smooth=self.smooth();output=Output();output.smooth_failed='OSError: lost'
  smooth.turn(output,False);self.assertFalse(output.smooth);self.assertEqual(output.smooth_failed,'OSError: lost')
  smooth.turn(output,True);self.assertTrue(output.smooth);self.assertIsNone(output.smooth_failed);smooth.turn(None,False)

if __name__=='__main__':unittest.main()
