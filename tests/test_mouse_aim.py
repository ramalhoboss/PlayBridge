"""Mouse aim: how fast the mouse moves becomes where the right stick points, with each game's own curve and dead zone, the buttons, the
settings kept per game, and Windows' Raw Input reports. Nothing here moves or holds this PC's own pointer."""
import ctypes,json,struct,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import mouse_aim as m
import pad_input as pads

class Clock:
 def __init__(self):self.now=100.0
 def __call__(self):return self.now

def profile(**changes):return m.clean(dict(m.DEFAULTS,**changes))

class CurveTests(unittest.TestCase):
 def test_a_still_mouse_leaves_the_stick_at_rest(self):
  self.assertEqual(m.stick(0,0,profile()),(128,128))
 def test_any_movement_jumps_past_the_games_dead_zone(self):
  rx,ry=m.stick(1,0,profile(deadzone=.2));self.assertEqual(ry,128);self.assertGreaterEqual(rx,m.axis(.2))
  self.assertEqual(m.stick(1,0,profile(deadzone=0))[0],128)
 def test_a_fast_sweep_pushes_it_all_the_way_and_no_further(self):
  self.assertEqual(m.stick(m.FULL_SPEED,0,profile()),(255,128));self.assertEqual(m.stick(-10*m.FULL_SPEED,0,profile()),(0,128))
  # Half the speed at twice the sensitivity is the same push.
  self.assertEqual(m.stick(m.FULL_SPEED/4,0,profile(sensitivity=2)),m.stick(m.FULL_SPEED/2,0,profile()))
 def test_down_is_down_unless_inverted(self):
  self.assertGreater(m.stick(0,2000,profile())[1],128);self.assertLess(m.stick(0,2000,profile(invert=True))[1],128)
 def test_the_games_curve_is_undone_so_small_movements_count_for_more(self):
  even=m.stick(m.FULL_SPEED/4,0,profile(deadzone=0))[0];bent=m.stick(m.FULL_SPEED/4,0,profile(deadzone=0,curve=2))[0]
  self.assertEqual(even,m.axis(.25));self.assertEqual(bent,m.axis(.5))
 def test_a_diagonal_keeps_its_direction(self):
  rx,ry=m.stick(1000,1000,profile(deadzone=0));self.assertEqual(rx,ry)
 def test_settings_stay_within_their_limits(self):
  self.assertEqual(m.clean(dict(sensitivity=99,curve=0,deadzone=-1,invert='yes')),dict(sensitivity=5.0,curve=1.0,deadzone=0.0,invert=False))
  self.assertEqual(m.clean(None),m.DEFAULTS);self.assertEqual(m.clean(dict(sensitivity=float('nan'),curve=True))['curve'],1.0)

class AimTests(unittest.TestCase):
 def setUp(self):self.clock=Clock();self.aim=m.MouseAim(self.clock)
 def test_nothing_counts_until_you_aim(self):
  self.aim.move(500,0);self.aim.buttons(0x1);self.assertEqual(self.aim.state(),pads.NEUTRAL);self.assertFalse(self.aim.in_use(self.clock.now))
 def test_the_stick_follows_the_last_few_milliseconds_and_comes_back(self):
  self.aim.start(profile(deadzone=0))
  # 40 counts in the last 20 ms: 2000 counts a second, half way at sensitivity 1.
  self.aim.move(20,0);self.clock.now+=.008;self.aim.move(20,0)
  state=self.aim.state();self.assertEqual((state.rx,state.ry,state.lx,state.ly),(m.axis(.5),128,128,128))
  self.clock.now+=m.WINDOW+.001;self.assertEqual(self.aim.state().rx,128)
 def test_the_buttons_press_the_triggers_the_stick_and_the_shoulders(self):
  self.aim.start(profile());self.aim.buttons(0x1|0x4|0x10|0x40|0x100);state=self.aim.state()
  self.assertEqual(state.buttons,pads.R2|pads.L2|pads.R3|pads.L1|pads.R1);self.assertEqual((state.l2,state.r2),(255,255))
  self.aim.buttons(0x2|0x8);state=self.aim.state();self.assertEqual((state.buttons,state.l2,state.r2),(pads.R3|pads.L1|pads.R1,0,0))
 def test_letting_go_lets_go_of_everything(self):
  self.aim.start(profile());self.aim.buttons(0x1);self.aim.move(50,50);self.assertTrue(self.aim.in_use(self.clock.now))
  self.aim.stop();self.assertEqual(self.aim.state(),pads.NEUTRAL);self.assertFalse(self.aim.in_use(self.clock.now))
 def test_it_plays_with_the_keyboard_and_a_controller(self):
  self.aim.start(profile(deadzone=0));self.aim.move(40,0)
  keys=pads.PadState(buttons=pads.CROSS,lx=0);both=pads.merge(pads.merge(pads.NEUTRAL,keys),self.aim.state())
  self.assertEqual((both.buttons,both.lx,both.rx),(pads.CROSS,0,m.axis(.5)))

class ProfileTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'aim.json'
 def test_each_game_keeps_its_own_and_the_rest_share_one(self):
  kept=m.AimProfiles(self.path);kept.set('',sensitivity=2.0);kept.set('PPSA01234',curve=2.5,deadzone=.2);kept.save()
  again=m.AimProfiles(self.path)
  self.assertEqual((again.get('PPSA01234')['curve'],again.get('PPSA01234')['sensitivity']),(2.5,2.0))
  self.assertEqual(again.get('PPSA09999'),profile(sensitivity=2.0));self.assertTrue(again.own('PPSA01234'));self.assertFalse(again.own('PPSA09999'))
 def test_a_broken_file_starts_from_the_defaults(self):
  self.path.write_text('{"x":',encoding='utf-8');self.assertEqual(m.AimProfiles(self.path).get(''),m.DEFAULTS)
  self.path.write_text(json.dumps({'PPSA01234':{'sensitivity':'fast'}}),encoding='utf-8');self.assertEqual(m.AimProfiles(self.path).get('PPSA01234'),m.DEFAULTS)

class RawTests(unittest.TestCase):
 def report(self,flags,buttons,dx,dy,kind=m.RIM_TYPEMOUSE):
  header=struct.pack('<II',kind,m.HEADER+24)+bytes(m.HEADER-8)
  return header+struct.pack('<H2xHhIiiI',flags,buttons,0,0,dx,dy,0)
 def test_a_mouse_report_gives_its_buttons_and_movement(self):
  self.assertEqual(m.read_raw(self.report(0,0x1,-7,12)),(0x1,-7,12))
 def test_a_pen_or_remote_desktop_moves_nothing(self):
  self.assertEqual(m.read_raw(self.report(m.MOUSE_MOVE_ABSOLUTE,0x4,30000,20000)),(0x4,0,0))
 def test_other_devices_and_short_reports_are_left_out(self):
  self.assertIsNone(m.read_raw(self.report(0,0,1,1,kind=1)));self.assertIsNone(m.read_raw(b'\0'*10))

@unittest.skipUnless(sys.platform=='win32','Raw Input is Windows only')
class WindowsTests(unittest.TestCase):
 def test_the_mouse_is_heard_only_between_start_and_stop(self):
  # Registering only asks Windows for the mouse's reports; with no window of this test in front, none of them counts.
  aim=m.MouseAim();raw=m.RawMouse(aim,lambda:0);self.addCleanup(raw.close)
  self.assertTrue(raw.begin());self.assertTrue(raw.start())
  for _ in range(100):
   if raw.registered:break
   import time;time.sleep(.01)
  self.assertTrue(raw.registered,raw.error);raw.stop()
  for _ in range(100):
   if not raw.registered:break
   import time;time.sleep(.01)
  self.assertFalse(raw.registered)
  raw.close();raw.thread.join(2);self.assertFalse(raw.thread.is_alive())

if __name__=='__main__':unittest.main()
