"""Repeated frames: a game slower than the stream sends each of its frames two or three times, and the copies are left out so smooth
motion can make the pictures between the game's own frames."""
import collections,sys,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from frame_pacing import CAPTURE_FRAME as F,FramePacer
import repeat_frames as r
import smooth_motion as s

BIG=90000;TINY=700
STEP=90000*1001/60000
def stream(game_frames,copies_each=1,copy=lambda size:TINY,lose=()):
 """The 60 fps stream of a slower game: each of its frames, then that many copies of it, as (pts, size, keyframe, game frame).
 copy gives a copy's size from its frame's. Stream frames numbered in lose never arrive."""
 out=[];n=0
 for game in range(game_frames):
  size=BIG+(game%5)*4000
  for copy_number in range(copies_each+1):
   if n not in lose:out.append((round(n*STEP),size if copy_number==0 else copy(size),n==0,game))
   n+=1
 return out

def filtered(frames,game_fps=30,wanted=True):
 stats=collections.Counter();repeats=r.RepeatFrames(stats);repeats.wanted=wanted
 kept=[(i,frame) for i,frame in enumerate(frames) if not repeats.skip(frame[0],frame[1],frame[2],game_fps)]
 return kept,stats,repeats

class RepeatTests(unittest.TestCase):
 def settled(self,kept,after=r.RECENT):
  return [frame[3] for i,frame in kept if i>=after]
 def assert_each_game_frame_once(self,kept,last):
  games=self.settled(kept);self.assertEqual(games,list(range(games[0],last)))
 def test_a_30_fps_game_keeps_each_of_its_frames_once(self):
  kept,stats,repeats=filtered(stream(60));self.assert_each_game_frame_once(kept,60);self.assertGreaterEqual(stats['repeats_skipped'],45)
  self.assertEqual(repeats.state(),'leaving out copies: the game draws 30 a second')
 def test_copies_the_encoder_spends_on_sharpening_are_still_found(self):
  # x264 gave the copies of a stand-in 70% of the size of the game's own frames.
  kept,stats,_=filtered(stream(60,copy=lambda size:int(size*.7)));self.assert_each_game_frame_once(kept,60)
 def test_a_20_fps_game_loses_both_copies(self):
  kept,stats,_=filtered(stream(60,copies_each=2),game_fps=20);self.assert_each_game_frame_once(kept,60);self.assertGreaterEqual(stats['repeats_skipped'],100)
 def test_a_frame_lost_on_the_way_does_not_shift_the_copies(self):
  # Stream frames 41 (a copy) and 60 (a game frame) never arrive: the time stamps keep the count.
  kept,_,_=filtered(stream(60,lose=(41,60)));games=self.settled(kept)
  self.assertEqual(games,[game for game in range(games[0],60) if game!=30])
 def test_a_game_at_the_stream_rate_keeps_every_frame(self):
  frames=[(round(i*STEP),BIG if i%2 else TINY*20,False,i) for i in range(120)]
  for fps in (59.9,60,50,None):
   kept,stats,_=filtered(frames,game_fps=fps);self.assertEqual(len(kept),120,fps);self.assertEqual(stats['repeats_skipped'],0)
 def test_copies_as_large_as_the_frames_leave_nothing_out(self):
  # An encoder that fills every frame to the same size: no place in the run stands out, so nothing can be told apart.
  kept,stats,repeats=filtered(stream(60,copy=lambda size:size));self.assertEqual(len(kept),120);self.assertEqual(stats['repeats_skipped'],0)
  self.assertEqual(repeats.state(),'looking for the copies: the game draws 30 a second')
 def test_nothing_is_left_out_while_in_between_pictures_cannot_be_made(self):
  kept,stats,_=filtered(stream(60),wanted=False);self.assertEqual(len(kept),120);self.assertEqual(stats['repeats_skipped'],0)
 def test_keyframes_always_stay(self):
  frames=[(pts,size,True,game) if n%30==1 else (pts,size,key,game) for n,(pts,size,key,game) in enumerate(stream(120))]
  kept,_,_=filtered(frames)
  for i,frame in enumerate(frames):
   if frame[2]:self.assertIn((i,frame),kept)
 def test_a_game_that_shows_a_frame_three_times_is_followed_again(self):
  # A 30 fps game that misses once: one of its frames fills three stream frames, and from then on its frames sit one place later.
  frames=stream(30)+[(round((60+n)*STEP),size,key,game) for n,(_,size,key,game) in enumerate(stream(1,copies_each=2))]
  frames+=[(round((63+n)*STEP),size,False,game+31) for n,(_,size,_,game) in enumerate(stream(40))]
  kept,_,_=filtered(frames);games=[frame[3] for i,frame in kept if i>=63+r.RECENT]
  self.assertEqual(games,list(range(games[0],71)))
 def test_the_stats_say_what_it_does(self):
  stats=collections.Counter();repeats=r.RepeatFrames(stats)
  self.assertEqual(repeats.state(),'off')
  repeats.wanted=True;repeats.skip(0,BIG,False,None);self.assertEqual(repeats.state(),"waiting for the game's frame count")
  repeats.skip(1502,BIG,False,59.9);self.assertEqual(repeats.state(),'not needed: the game draws 60 a second')

class SmoothTests(unittest.TestCase):
 def test_a_30_fps_game_gets_a_picture_between_each_two_of_its_frames_on_a_60_hz_screen(self):
  kept,_,_=filtered(stream(80))
  stats=collections.Counter();p=FramePacer(stats);screen=[];start=10.0;period=F
  out=SimpleNamespace(smooth=True,smooth_failed=None,frame=SimpleNamespace(format=SimpleNamespace(name='d3d11')))
  motion=s.SmoothMotion(stats,SimpleNamespace(add=lambda *a:None))
  pending=list(kept);t=start;count=0
  while pending or p.items:
   while pending and start+pending[0][0]*F<=t:i,frame=pending.pop(0);p.add(i*F,frame[3],t)
   ahead=motion.ahead(out,period,p.spacing)
   shown=p.advance(period,t,ahead)
   if shown is not None:screen.append(('frame',shown))
   else:
    pick=p.between(period) if ahead else None
    screen.append(('between',pick[1],pick[2],round(pick[0],2)) if pick else None)
   count+=1;t=start+count*period
   if count>400:break
  self.assertTrue(motion.can_run(out))
  # Once settled, the screen alternates a game frame and the picture half way to the next one, at every refresh.
  tail=screen[60:-4]
  for a,b in zip(tail,tail[1:]):
   if a and a[0]=='frame':self.assertEqual(b,('between',a[1],a[1]+1,.5))
   else:self.assertEqual(b[0],'frame')
 def test_it_can_run_only_with_frames_from_the_graphics_card_and_a_working_output(self):
  motion=s.SmoothMotion(collections.Counter(),None)
  out=SimpleNamespace(smooth=True,smooth_failed=None,frame=SimpleNamespace(format=SimpleNamespace(name='d3d11')))
  self.assertTrue(motion.can_run(out))
  out.frame=SimpleNamespace(format=SimpleNamespace(name='nv12'));self.assertFalse(motion.can_run(out))
  out.frame=SimpleNamespace(format=SimpleNamespace(name='d3d11'));out.smooth_failed='shader';self.assertFalse(motion.can_run(out))
  out.smooth_failed=None;motion.turn(None,False);self.assertFalse(motion.can_run(out))

if __name__=='__main__':unittest.main()
