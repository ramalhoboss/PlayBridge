"""The speedrun timer: runs, splits against the best ones, and each game's best run kept on the PC."""
import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import run_timer as r

class Clock:
 def __init__(self):self.now=1000.0
 def __call__(self):return self.now

class TimerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'runs.json'
 def timer(self):
  clock=Clock();return r.RunTimer(self.path,clock),clock
 def test_the_time_reads_as_a_speedrun_timer_shows_it(self):
  self.assertEqual([r.text(s) for s in (0,42.36,725.81,3723.45)],['0:00.0','0:42.3','12:05.8','1:02:03.4'])
  self.assertEqual((r.delta(3.25),r.delta(-1.5)),('+0:03.2','−0:01.5'))
 def test_a_run_with_splits_becomes_the_games_best(self):
  timer,clock=self.timer();timer.start('PPSA01234','Some Game');clock.now+=61.2
  name,at,behind=timer.split('First boss');self.assertEqual((name,round(at,6),behind),('First boss',61.2,None));clock.now+=30
  self.assertEqual(timer.split()[0],'Split 2');clock.now+=8.8
  self.assertAlmostEqual(timer.stop(),100.0);self.assertEqual(timer.state,'finished')
  kept=json.loads(self.path.read_text(encoding='utf-8'))['PPSA01234']
  self.assertEqual((kept['total'],kept['name'],kept['splits']),(100.0,'Some Game',{'First boss':61.2,'Split 2':91.2}))
  # The time stays where it stopped.
  clock.now+=50;self.assertEqual(timer.view()['time'],'1:40.0')
 def test_the_next_run_shows_how_far_ahead_or_behind_each_split_is(self):
  timer,clock=self.timer();timer.start('PPSA01234','Some Game');clock.now+=60;timer.split('First boss');clock.now+=40;timer.stop()
  again=r.RunTimer(self.path,clock);again.start('PPSA01234','Some Game');clock.now+=58.5
  name,at,behind=again.split('First boss');self.assertAlmostEqual(behind,-1.5)
  view=again.view();self.assertEqual((view['split'],view['delta'],view['ahead'],view['best']),('First boss  0:58.5','−0:01.5',True,'Best 1:40.0'))
  clock.now+=45;again.stop()
  # Slower overall: the best run stays, but the quicker split is kept as that split's best.
  kept=json.loads(self.path.read_text(encoding='utf-8'))['PPSA01234'];self.assertEqual((kept['total'],kept['splits']['First boss']),(100.0,58.5))
 def test_splits_only_while_running_and_a_reset_clears_it(self):
  timer,clock=self.timer();self.assertIsNone(timer.split());self.assertIsNone(timer.stop())
  timer.start();clock.now+=5;timer.reset();self.assertEqual((timer.state,timer.view()['time'],timer.splits),('idle','0:00.0',[]))
 def test_a_run_without_a_game_is_not_kept(self):
  timer,clock=self.timer();timer.start();clock.now+=10;timer.stop();self.assertFalse(self.path.exists())
 def test_a_broken_file_starts_empty(self):
  self.path.write_text('[1,2',encoding='utf-8');self.assertEqual(r.RunTimer(self.path).best,{})
  self.path.write_text('[1,2]',encoding='utf-8');self.assertEqual(r.RunTimer(self.path).best,{})

if __name__=='__main__':unittest.main()
