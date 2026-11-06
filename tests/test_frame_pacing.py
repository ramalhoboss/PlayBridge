import collections,random,sys,threading,time,unittest,unittest.mock
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from frame_pacing import CAPTURE_FRAME as F,RELEARN,FramePacer,FrameTimer,HitchWatch,RefreshClock,precise_sleep

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

def stalls(count,every,size,start=10.):
 """A stream that stops for a moment every so often, as Wi-Fi does while it scans."""
 return in_order(a+(size if i%every==every//2 else 0) for i,a in enumerate(steady(count,start=start)))

class MissingTests(unittest.TestCase):
 def test_a_frame_that_is_due_and_missing_is_counted(self):
  _,_,_,p=play(steady(240));self.assertEqual(p.missing,0)
  _,_,_,p=play(stalls(240,120,.05));self.assertGreater(p.missing,0)

class HitchTests(unittest.TestCase):
 def frames(self,watch,gaps,period,seen=()):
  done=1.;causes=[]
  watch.shown(done,period,done)
  for gap in gaps:
   for name in seen:
    if name=='missing':watch.refresh(1,True,False)
    elif name=='slow':watch.refresh(2,False,True)
    elif name=='busy':watch.refresh(2,False,False)
    elif name=='unpresented':watch.unpresented()
   done+=gap;causes.append(watch.shown(done,period,done))
  return causes
 def test_steady_frames_and_a_fast_screens_judder_are_not_hitches(self):
  watch=HitchWatch()
  self.assertEqual(self.frames(watch,[F]*120,1/60),[None]*120)
  self.assertEqual(self.frames(watch,[1/144*2,1/144*3]*60,1/144),[None]*120)
  self.assertEqual(self.frames(watch,[F]*60,1/120),[None]*60);self.assertEqual(sum(watch.counts.values()),0)
 def test_a_frame_held_a_refresh_longer_is_a_hitch_with_its_cause(self):
  for seen,cause in ((('missing',),'stream'),(('slow',),'present'),(('unpresented',),'present'),(('busy',),'busy'),((),'other'),(('busy','missing'),'stream')):
   watch=HitchWatch();self.assertEqual(self.frames(watch,[2*F],1/60,seen),[cause]);self.assertEqual(watch.counts[cause],1)
  watch=HitchWatch();self.assertEqual(self.frames(watch,[F+1/120],1/120,('missing',)),['stream'])
 def test_a_pause_behind_another_page_is_not_a_hitch(self):
  watch=HitchWatch();self.assertEqual(self.frames(watch,[.4],1/60,('missing',)),[None])
 def test_the_log_keeps_the_latest_hitches_with_their_time(self):
  watch=HitchWatch(keep=3);self.frames(watch,[2*F]*5,1/60,('missing',))
  self.assertEqual(len(watch.log),3);self.assertEqual(watch.counts['stream'],5);self.assertEqual(watch.log[-1][1:],(33.4,'stream'))
 def test_what_was_seen_belongs_to_one_frame_only(self):
  watch=HitchWatch();watch.shown(1,1/60,1);watch.refresh(1,True,False);watch.shown(1+F,1/60,1)
  self.assertEqual(watch.shown(1+3*F,1/60,1),'other')

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
 def test_a_missed_refresh_counts_twice_without_stretching_the_measured_length(self):
  calls=[0];stop=threading.Event();self.addCleanup(stop.set)
  def flush():
   calls[0]+=1;time.sleep(.04 if calls[0]>12 and calls[0]%3==0 else .02);return 0
  clock=RefreshClock(stop,flush=flush);self.wait_for(lambda:calls[0]>=40);counted=clock.count;stop.set()
  # With every third refresh missed, an average over all the gaps would be over 26 ms.
  self.assertLess(clock.period,.023);self.assertGreater(clock.period,.019);self.assertGreater(counted,calls[0]+5)
 def test_the_first_gap_after_a_start_is_not_measured(self):
  calls=[0];stop=threading.Event();self.addCleanup(stop.set)
  def flush():
   calls[0]+=1;time.sleep(.005 if calls[0]==1 else .02);return 0
  clock=RefreshClock(stop,flush=flush);self.wait_for(lambda:clock.samples>=3)
  self.assertGreater(clock.period,.0175)
 def test_falls_back_to_wall_time_without_composition(self):
  stop=threading.Event();self.addCleanup(stop.set);clock=RefreshClock(stop,flush=lambda:0);time.sleep(.03)
  self.assertFalse(clock.synced);started=time.perf_counter();clock.elapsed(started);self.assertAlmostEqual(clock.elapsed(started+.25),.25,places=6)
 def test_a_failed_flush_also_falls_back(self):
  stop=threading.Event();self.addCleanup(stop.set);clock=RefreshClock(stop,flush=lambda:time.sleep(.02) or -1);time.sleep(.1);self.assertFalse(clock.synced);self.assertEqual(clock.count,0)
 def test_runs_the_work_it_is_given_with_or_without_composition(self):
  for result in (0,1):
   stop=threading.Event();self.addCleanup(stop.set);clock=RefreshClock(stop,flush=lambda:time.sleep(.01) or result);ticks=[];clock.after=lambda:ticks.append(clock.count)
   self.wait_for(lambda:len(ticks)>=3);clock.after=None;stop.set()
class RelearnTests(unittest.TestCase):
 def clock(self):
  # Stopped before it starts, so only the gaps given here count.
  stop=threading.Event();stop.set();return RefreshClock(stop,flush=lambda:0)
 def test_a_new_screen_rate_is_learnt_after_a_run_of_gaps_that_disagree(self):
  clock=self.clock()
  for _ in range(60):clock.measure(1/165)
  self.assertAlmostEqual(clock.period,1/165,delta=.0002)
  for _ in range(RELEARN+15):clock.measure(1/120)
  self.assertAlmostEqual(clock.period,1/120,delta=.0003)
 def test_a_missed_refresh_now_and_then_keeps_the_length(self):
  clock=self.clock()
  for i in range(200):clock.measure(2/60 if i%5==4 else 1/60)
  self.assertAlmostEqual(clock.period,1/60,delta=.0003)
 def test_the_count_keeps_time_while_the_rate_changes(self):
  clock=self.clock()
  for _ in range(60):clock.measure(1/165)
  start=clock.count*clock.period
  for _ in range(240):clock.measure(1/120)
  self.assertAlmostEqual(clock.count*clock.period-start,2,delta=.25)

def play_on_time(arrivals,**options):
 """As with variable refresh: each wake is when the next frame is due, or a short look later while none waits. Returns the times frames
 were shown, as (frame, time)."""
 stats=collections.Counter();p=FramePacer(stats,**options);timer=FrameTimer(threading.Event(),p.due,start=False,sleep=lambda s:None)
 shown=[];next_frame=0;t=arrivals[0];end=arrivals[-1]+.3;timer.read_at=t
 while t<end:
  while next_frame<len(arrivals) and arrivals[next_frame]<=t:p.add(next_frame*F,next_frame,arrivals[next_frame]);next_frame+=1
  item=p.advance(timer.elapsed(t),t)
  if item is not None:shown.append((item,t))
  # The timer sleeps until the next frame's turn, but not past the next arrival, as when it looks again while none waits.
  left=timer.wait();t+=max(left,1e-4)
  if next_frame<len(arrivals):t=min(t,max(arrivals[next_frame],t-left+1e-4))
 return shown,stats

class FrameTimerTests(unittest.TestCase):
 def test_due_counts_down_to_the_next_frame(self):
  p=FramePacer(collections.Counter());self.assertIsNone(p.due())
  p.add(1.0,'a',1.0);self.assertAlmostEqual(p.due(),1.5*F)
  p.advance(F,1.0);self.assertAlmostEqual(p.due(),.5*F)
  p.advance(F,1.0);self.assertIsNone(p.due())
 def test_it_sleeps_until_the_turn_and_never_longer_than_a_frame(self):
  left=[None];timer=FrameTimer(threading.Event(),lambda:left[0],start=False,sleep=lambda s:None)
  self.assertEqual(timer.wait(),FrameTimer.IDLE)
  left[0]=.004;self.assertAlmostEqual(timer.wait(),.004+FrameTimer.SLACK);left[0]=-.01;self.assertEqual(timer.wait(),0);left[0]=5;self.assertAlmostEqual(timer.wait(),F)
 def test_a_steady_stream_shows_every_16_7_ms(self):
  shown,stats=play_on_time(steady(600))
  frames=[f for f,_ in shown];gaps=[(b-a)*1000 for (_,a),(_,b) in zip(shown,shown[1:])]
  self.assertEqual(frames,sorted(frames));self.assertGreaterEqual(len(frames),598)
  # Not the 13.9 and 20.8 ms of a 144 Hz screen counting refreshes: every gap is one stream frame, except the two in which the
  # unused part of the starting delay is given back, once.
  steady_gaps=gaps[5:-5];self.assertLessEqual(sum(1 for g in steady_gaps if abs(g-F*1000)>.5),2);self.assertAlmostEqual(sum(steady_gaps)/len(steady_gaps),F*1000,delta=.1)
 def test_uneven_arrival_still_shows_evenly(self):
  random.seed(7);arrivals=in_order([10+i*F+random.uniform(0,.006) for i in range(600)])
  shown,stats=play_on_time(arrivals);gaps=[(b-a)*1000 for (_,a),(_,b) in zip(shown,shown[1:])][5:-5]
  self.assertGreater(sum(1 for g in gaps if abs(g-F*1000)<.5)/len(gaps),.97)
 def test_a_late_frame_shows_as_soon_as_it_comes(self):
  arrivals=steady(120);arrivals[60:]=[a+.03 for a in arrivals[60:]]
  shown,stats=play_on_time(arrivals);at=dict(shown)
  self.assertLess(at[60]-arrivals[60],F);self.assertGreater(stats['video_late_waits'],0)
 def test_frames_never_come_closer_than_the_spacing(self):
  left=[0.0];timer=FrameTimer(threading.Event(),lambda:left[0],start=False,sleep=lambda s:None,spacing=lambda:.007)
  self.assertEqual(timer.wait(),0)
  timer.last=time.perf_counter();self.assertAlmostEqual(timer.wait(),.007+FrameTimer.SLACK,delta=.001)
  # A frame due later than the spacing keeps its own time.
  left[0]=.012;self.assertAlmostEqual(timer.wait(),.012+FrameTimer.SLACK,delta=.0005)
 def test_after_a_stall_frames_are_spaced_but_none_is_lost(self):
  arrivals=steady(240);arrivals[100:110]=[arrivals[110]]*10
  stats=collections.Counter();p=FramePacer(stats);now=[arrivals[0]]
  timer=FrameTimer(threading.Event(),p.due,start=False,sleep=lambda s:None,spacing=lambda:1/144)
  shown=[];nf=0;timer.read_at=now[0]
  with unittest.mock.patch('frame_pacing.time.perf_counter',lambda:now[0]):
   while now[0]<arrivals[-1]+.05:
    while nf<len(arrivals) and arrivals[nf]<=now[0]:p.add(nf*F,nf,arrivals[nf]);nf+=1
    item=p.advance(timer.elapsed(now[0]),now[0])
    if item is not None:shown.append(now[0]);timer.last=now[0]
    left=timer.wait();step=max(left,1e-4)
    if nf<len(arrivals):step=min(step,max(arrivals[nf]-now[0],1e-4))
    now[0]+=step
  gaps=[b-a for a,b in zip(shown,shown[1:])];self.assertGreaterEqual(min(gaps),1/144-1e-6)
 def test_the_run_loop_paints_after_each_wake(self):
  stop=threading.Event();woke=[];timer=FrameTimer(stop,lambda:.001,start=False,sleep=lambda s:woke.append(round(s,6)))
  def paint():
   if len(woke)>=3:stop.set()
  timer.after=paint;timer.run();self.assertEqual(woke,[.0012]*3)
 def test_the_precise_sleep_ends_near_its_time(self):
  sleep=precise_sleep();took=[]
  for _ in range(20):start=time.perf_counter();sleep(.005);took.append(time.perf_counter()-start)
  took.sort();self.assertGreaterEqual(took[0],.0045);self.assertLess(took[len(took)//2],.0065)

if __name__=='__main__':unittest.main()
