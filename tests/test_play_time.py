import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import play_time

class Clock:
 def __init__(self):self.now=1000.0;self.day='2026-11-17'
 def time(self):return self.now
 def today(self):return self.day

class PlayTimeTests(unittest.TestCase):
 def make(self,saved=None):
  self.clock=Clock();self.kept=[]
  return play_time.PlayTime(saved,self.kept.append,clock=self.clock.time,today=self.clock.today)
 def test_a_limit_needs_a_pin_and_the_pin_unlocks_for_a_while(self):
  t=self.make()
  self.assertIn('PIN first',t.set_limit('1 hour'))
  self.assertIn('four to eight',t.set_pin('12a4'))
  self.assertEqual(t.set_pin('2468'),'');self.assertEqual(t.set_limit('1 hour'),'');self.assertEqual(t.limit,3600)
  self.assertNotIn('2468',str(self.kept[-1]))
  self.clock.now+=play_time.UNLOCKED_FOR+1;self.assertFalse(t.unlocked());self.assertIn('Unlock',t.set_limit('Off'))
  self.assertEqual(t.unlock('1111'),'That PIN is not right.');self.assertEqual(t.unlock('2468'),'');self.assertTrue(t.unlocked())
 def test_five_wrong_pins_wait_a_minute(self):
  t=self.make();t.set_pin('2468');t.lock()
  for _ in range(4):self.assertEqual(t.unlock('0000'),'That PIN is not right.')
  self.assertIn('Too many',t.unlock('0000'));self.assertIn('Too many',t.unlock('2468'))
  self.clock.now+=play_time.WAIT+1;self.assertEqual(t.unlock('2468'),'')
 def test_warnings_then_the_end_then_more_time(self):
  t=self.make();t.set_pin('2468');t.set_limit('30 minutes');t.lock()
  said=[t.count(60) for _ in range(30)]
  spoken=[s for s in said if s]
  self.assertEqual(len(spoken),3);self.assertIn('10 min of play time left',spoken[0]);self.assertIn('One minute',spoken[1]);self.assertIn('used up',spoken[2])
  self.assertTrue(t.blocked());self.assertEqual(t.count(60),'')
  self.assertIn('Unlock',t.add(1800));t.unlock('2468');self.assertEqual(t.add(1800),'');self.assertEqual(t.blocked(),'')
 def test_a_new_day_starts_from_nothing_and_the_saved_state_comes_back(self):
  t=self.make();t.set_pin('2468');t.set_limit('1 hour');t.count(3600);self.assertTrue(t.blocked())
  saved=t.data();again=play_time.PlayTime(saved,lambda d:None,clock=self.clock.time,today=self.clock.today)
  self.assertTrue(again.blocked());self.assertTrue(again.has_pin());self.assertFalse(again.unlocked())
  self.clock.day='2026-11-18';self.assertEqual(again.blocked(),'');self.assertEqual(again.left(),3600)
 def test_no_limit_counts_but_never_blocks(self):
  t=self.make();self.assertEqual(t.count(7200),'');self.assertEqual(t.blocked(),'');self.assertIn('today: 2 h 00 min',t.view()['line'])
 def test_forgetting_the_pin_turns_the_limit_off(self):
  t=self.make();t.set_pin('2468');t.set_limit('2 hours');self.assertEqual(t.forget_pin(),'');self.assertFalse(t.has_pin());self.assertIsNone(t.left())

if __name__=='__main__':unittest.main()
