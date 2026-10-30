import collections,random,sys,threading,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from frame_pacing import CAPTURE_FRAME as F,FramePacer,RefreshClock

def play(arrivals,refresh=F,every=1,**options):
 """Feeds frames as they arrive and asks for a picture on each refresh. Returns one entry per refresh: the frame shown, or None."""
 stats=collections.Counter();p=FramePacer(stats,**options);screen=[];delays={};next_frame=0;t=arrivals[0];end=arrivals[-1]+.3;count=0
 # Stops at the last frame: after it, the pacer would rightly start waiting for one that never comes.
 while t<end and (not screen or screen[-1]!=len(arrivals)-1):
  while next_frame<len(arrivals) and arrivals[next_frame]<=t:p.add(next_frame*every*F,next_frame,arrivals[next_frame]);next_frame+=1
  shown=p.advance(refresh,t);screen.append(shown)
  if shown is not None:delays[shown]=t-arrivals[shown]
  count+=1;t=arrivals[0]+count*refresh
 return screen,stats,delays,p

def steady(count,spacing=F,start=10.):return [start+i*spacing for i in range(count)]
def in_order(values):
 running=0;result=[]
 for value in values:running=max(running,value);result.append(running)
 return result
def trim(screen):
 first=next(i for i,x in enumerate(screen) if x is not None);last=len(screen)-next(i for i,x in enumerate(reversed(screen)) if x is not None)
 return screen[first:last]

class PacerTests(unittest.TestCase):
 def test_steady_stream_shows_every_frame_once_per_refresh(self):
  screen,stats,_,_=play(steady(600));shown=trim(screen)
  # One frame at most is skipped, when the unused part of the starting delay is given back.
  self.assertNotIn(None,shown);self.assertEqual(shown,sorted(shown));self.assertEqual(len(shown),600-stats['prepared_replaced']);self.assertLessEqual(stats['prepared_replaced'],1);self.assertEqual(stats['video_late_waits'],0)
 def test_arrival_jitter_does_not_reach_the_screen(self):
  rng=random.Random(1);arrivals=in_order(10+i*F+rng.uniform(0,.012) for i in range(1800));screen,stats,delays,_=play(arrivals);shown=trim(screen)
  self.assertEqual(stats['prepared_replaced'],0);self.assertEqual([x for x in shown if x is not None],list(range(1800)))
  self.assertLess(shown.count(None),10);self.assertLess(max(delays.values()),5*F)
 def test_a_late_frame_is_waited_for_and_leaves_more_margin(self):
  arrivals=steady(240);arrivals=in_order(a+(.04 if i==120 else 0) for i,a in enumerate(arrivals));screen,stats,delays,_=play(arrivals)
  self.assertEqual(stats['prepared_replaced'],0);self.assertEqual([x for x in trim(screen) if x is not None],list(range(240)));self.assertGreater(stats['video_late_waits'],0);self.assertLess(max(delays.values()),6*F)
 def test_delay_is_given_back_when_the_stream_is_steady_again(self):
  arrivals=steady(1200);arrivals=in_order(a+(.04 if i==120 else 0) for i,a in enumerate(arrivals));_,stats,delays,_=play(arrivals)
  self.assertLess(delays[1190],delays[130]);self.assertLessEqual(delays[1190],2.5*F);self.assertLessEqual(stats['prepared_replaced'],4)
 def test_a_long_stall_skips_ahead_and_the_delay_stays_bounded(self):
  arrivals=in_order(a+(.5 if i==300 else 0) for i,a in enumerate(steady(1200)));screen,stats,delays,_=play(arrivals)
  self.assertGreater(stats['prepared_replaced'],0);self.assertLess(max(delays.values()),8*F);self.assertLessEqual(delays[1190],2.5*F)
  shown=[x for x in screen if x is not None];self.assertEqual(shown,sorted(shown))
 def test_a_faster_monitor_still_shows_every_frame(self):
  screen,stats,_,_=play(steady(600),refresh=1/144);shown=trim(screen);holds=collections.Counter();run=0
  for x in shown:
   run+=1
   if x is not None:holds[run]+=1;run=0
  self.assertEqual([x for x in shown if x is not None],list(range(600)));self.assertEqual(stats['prepared_replaced'],0);self.assertLessEqual(max(holds),3)
 def test_a_slightly_faster_monitor_holds_rarely_and_keeps_its_margin(self):
  screen,stats,delays,_=play(steady(18000),refresh=1/60);shown=trim(screen)
  self.assertLess(stats['prepared_replaced'],12);self.assertLess(shown.count(None),40);self.assertLess(delays[17990],4*F)
 def test_a_slightly_slower_monitor_skips_rarely_and_keeps_its_margin(self):
  screen,stats,delays,_=play(steady(18000),refresh=1/59.9);shown=trim(screen)
  self.assertLess(stats['prepared_replaced'],30);self.assertLess(shown.count(None),5);self.assertLess(delays[17990],3*F)
 def test_the_playback_cap_keeps_its_own_spacing(self):
  screen,stats,_,_=play(steady(300,2*F),every=2);shown=trim(screen)
  self.assertEqual([x for x in shown if x is not None],list(range(300)));self.assertEqual(stats['video_late_waits'],0);self.assertEqual(stats['prepared_replaced'],0)
  self.assertEqual(sum(x is None for x in shown),299)
 def test_the_queue_is_bounded_when_nothing_reads_it(self):
  stats=collections.Counter();p=FramePacer(stats)
  for i in range(50):p.add(i*F,i,10+i*F)
  self.assertLessEqual(len(p.items),p.capacity);self.assertEqual(stats['prepared_replaced'],50-p.capacity)
  # It skips close to the newest frames instead of freezing on the old clock.
  self.assertIsNone(p.advance(F,10+50*F));self.assertEqual(p.advance(F,10+51*F),44)
 def test_a_new_session_and_a_timestamp_jump_restart_the_clock(self):
  stats=collections.Counter();p=FramePacer(stats)
  p.add(5.,'a',10.);p.clear();self.assertIsNone(p.advance(F,10.));p.add(900.,'b',10.);self.assertEqual(p.advance(2*F,10.03),'b')
  p.add(5000.,'c',10.05);self.assertEqual(p.advance(2*F,10.08),'c')
 def test_nothing_is_shown_before_the_first_frame(self):
  self.assertIsNone(FramePacer(collections.Counter()).advance(F,1.))

class RefreshClockTests(unittest.TestCase):
 def wait_for(self,check):
  until=time.perf_counter()+3
  while not check() and time.perf_counter()<until:time.sleep(.005)
  self.assertTrue(check())
 def test_counts_whole_refreshes_and_measures_their_length(self):
  stop=threading.Event();self.addCleanup(stop.set);clock=RefreshClock(stop,flush=lambda:time.sleep(.02) or 0)
  self.wait_for(lambda:clock.samples>=10);seconds=clock.elapsed(time.perf_counter())
  self.assertTrue(clock.synced);self.assertAlmostEqual(clock.period,.02,delta=.01);self.assertAlmostEqual(seconds/clock.period,round(seconds/clock.period),places=6);self.assertGreater(seconds,0)
  self.assertLess(clock.elapsed(time.perf_counter()),clock.period*2)
 def test_falls_back_to_wall_time_without_composition(self):
  stop=threading.Event();self.addCleanup(stop.set);clock=RefreshClock(stop,flush=lambda:0);time.sleep(.03)
  self.assertFalse(clock.synced);started=time.perf_counter();clock.elapsed(started);self.assertAlmostEqual(clock.elapsed(started+.25),.25,places=6)
 def test_a_failed_flush_also_falls_back(self):
  stop=threading.Event();self.addCleanup(stop.set);clock=RefreshClock(stop,flush=lambda:time.sleep(.02) or -1);time.sleep(.1);self.assertFalse(clock.synced);self.assertEqual(clock.count,0)
if __name__=='__main__':unittest.main()
