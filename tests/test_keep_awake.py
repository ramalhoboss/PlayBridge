"""The display stays on while a session runs."""
import os,sys,unittest
from pathlib import Path
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import keep_awake

class KeepAwakeTests(unittest.TestCase):
 def test_windows_is_asked_only_when_the_wish_changes(self):
  calls=[];awake=keep_awake.KeepAwake(calls.append)
  for on in (False,True,True,True,False,False,True):awake.want(on)
  self.assertEqual(calls,[keep_awake.AWAKE,keep_awake.RELEASED,keep_awake.AWAKE])
 def test_the_request_keeps_both_the_display_and_the_pc_on_and_the_release_keeps_neither(self):
  self.assertEqual(keep_awake.AWAKE,0x80000003);self.assertEqual(keep_awake.RELEASED,0x80000000)
 def test_a_failing_call_does_not_stop_the_window(self):
  def broken(flags):raise OSError('no')
  awake=keep_awake.KeepAwake(broken);awake.want(True);awake.want(False)
  self.assertFalse(awake.on)
 def hint(self,battery=True):
  return keep_awake.BatteryHint(lambda:battery,seconds=5)
 def test_frames_lost_on_battery_bring_the_hint_once(self):
  hint=self.hint();said=[hint.second(True,40,60) for _ in range(12)]
  self.assertEqual(said,[None]*4+[keep_awake.HINT]+[None]*7);self.assertTrue(hint.on)
 def test_a_smooth_picture_on_battery_says_nothing(self):
  hint=self.hint();self.assertEqual([hint.second(True,59.9,60) for _ in range(20)],[None]*20)
 def test_lost_frames_on_mains_power_are_not_blamed_on_the_battery(self):
  hint=self.hint(False);self.assertEqual([hint.second(True,30,60) for _ in range(20)],[None]*20);self.assertFalse(hint.on)
 def test_one_good_second_starts_the_count_again_and_a_new_session_may_say_it_again(self):
  hint=self.hint();said=[hint.second(True,fps,60) for fps in (40,40,40,40,60,40,40,40,40)];self.assertEqual(said,[None]*9)
  for _ in range(5):hint.second(True,40,60)
  self.assertTrue(hint.told);hint.second(False,0,60)
  self.assertEqual([hint.second(True,40,60) for _ in range(5)][-1],keep_awake.HINT)
 def test_a_30_fps_profile_is_judged_against_30(self):
  hint=self.hint();self.assertEqual([hint.second(True,29.9,30) for _ in range(10)],[None]*10)
 @unittest.skipUnless(sys.platform=='win32','Windows only')
 def test_windows_says_whether_this_pc_runs_on_battery(self):
  self.assertIn(keep_awake.on_battery(),(True,False))
 @unittest.skipUnless(sys.platform=='win32','Windows only')
 def test_windows_accepts_the_request_and_the_release(self):
  call=keep_awake.windows_call()
  self.assertNotEqual(call(keep_awake.AWAKE),0);self.assertNotEqual(call(keep_awake.RELEASED),0)

if __name__=='__main__':unittest.main()
