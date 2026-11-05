"""A screen whose rate does not fit the stream's 59.94 fps gets one that does while the game fills it."""
import ctypes,os,sys,unittest
from pathlib import Path
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import screen_rate as s

LAPTOP=[(2560,1440,32,hz) for hz in (165,144,120,60,59)]+[(1920,1080,32,hz) for hz in (165,60)]
class Screen:
 """A 165 Hz laptop screen as Windows describes it."""
 def __init__(self,modes=LAPTOP,current=(2560,1440,32,165),accepts=True):
  self.listed=modes;self.now=current;self.accepts=accepts;self.calls=[]
 def screen(self,hwnd):return '\\\\.\\DISPLAY1'
 def current(self,device):return self.now
 def modes(self,device):return self.listed
 def switch(self,device,hz):
  self.calls.append(('switch',hz))
  if self.accepts:self.now=self.now[:3]+(hz,)
  return self.accepts
 def restore(self,device):self.calls.append(('restore',));self.now=self.now[:3]+(165,)

class RuleTests(unittest.TestCase):
 def test_rates_that_hold_every_frame_equally_long_are_steady(self):
  # Windows names 59.94 Hz 59 and 119.88 Hz 119.
  for hz in (59,60,119,120,239,240,59.9):self.assertTrue(s.steady(hz),hz)
  for hz in (50,75,90,100,144,165,175):self.assertFalse(s.steady(hz),hz)
  self.assertTrue(s.steady(0));self.assertTrue(s.steady(None))
 def test_the_fastest_steady_rate_at_the_same_size_is_chosen(self):
  self.assertEqual(s.best(LAPTOP,(2560,1440,32,165)),120)
  self.assertEqual(s.best([m for m in LAPTOP if m[3]!=120],(2560,1440,32,144)),60)
 def test_a_steady_screen_or_one_without_a_steady_rate_is_left_alone(self):
  self.assertIsNone(s.best(LAPTOP,(2560,1440,32,60)));self.assertIsNone(s.best([(2560,1440,32,165),(2560,1440,32,144)],(2560,1440,32,165)))
  self.assertIsNone(s.best(LAPTOP,None))
 def test_a_rate_offered_only_at_another_size_is_not_used(self):
  self.assertIsNone(s.best([(1920,1080,32,120),(2560,1440,32,165)],(2560,1440,32,165)))

class SwitchTests(unittest.TestCase):
 def test_the_screen_switches_while_the_game_fills_it_and_comes_back_after(self):
  screen=Screen();rate=s.ScreenRate(screen)
  self.assertEqual(rate.want(True,1),(165,120));self.assertEqual(rate.label(),'165 -> 120 Hz')
  for _ in range(5):self.assertIsNone(rate.want(True,1))
  self.assertIsNone(rate.want(False,1));self.assertEqual(screen.calls,[('switch',120),('restore',)]);self.assertIsNone(rate.label())
  self.assertEqual(rate.want(True,1),(165,120))
 def test_nothing_happens_on_a_steady_screen_and_it_is_not_asked_again(self):
  screen=Screen(current=(2560,1440,32,60));rate=s.ScreenRate(screen);asked=[]
  screen.modes=lambda device:asked.append(device) or LAPTOP
  for _ in range(8):self.assertIsNone(rate.want(True,1))
  self.assertEqual((screen.calls,len(asked)),([],1))
 def test_a_screen_that_refuses_is_not_asked_every_quarter_second(self):
  screen=Screen(accepts=False);rate=s.ScreenRate(screen)
  for _ in range(8):self.assertIsNone(rate.want(True,1))
  self.assertEqual(screen.calls,[('switch',120)]);rate.want(False,1);self.assertEqual(screen.calls,[('switch',120)])
 def test_a_failing_display_call_never_stops_the_window(self):
  screen=Screen();screen.current=lambda device:(_ for _ in ()).throw(OSError('driver'));rate=s.ScreenRate(screen)
  self.assertIsNone(rate.want(True,1));self.assertIsNone(rate.want(False,1))
 def test_the_stats_say_why_a_screen_was_or_was_not_switched(self):
  cases=((Screen(),'165 -> 120 Hz'),(Screen(current=(2560,1440,32,60)),'60 Hz already fits 60 fps'),
         (Screen(modes=[(2560,1440,32,144)],current=(2560,1440,32,144)),'144 Hz, and no rate that fits 60 fps at 2560x1440'),
         (Screen(accepts=False),'Windows refused 120 Hz'))
  for screen,note in cases:
   rate=s.ScreenRate(screen);rate.want(True,1);self.assertEqual(rate.note,note)
  broken=Screen();broken.modes=lambda device:(_ for _ in ()).throw(OSError('driver'));rate=s.ScreenRate(broken);rate.want(True,1)
  self.assertEqual(rate.note,'Could not read the screen: driver')
 def test_the_note_stays_after_the_screen_is_put_back(self):
  rate=s.ScreenRate(Screen());rate.want(True,1);rate.want(False,1);self.assertEqual((rate.note,rate.label()),('165 -> 120 Hz',None))
 def test_away_from_windows_nothing_is_done(self):
  rate=s.ScreenRate();rate.system=None;self.assertIsNone(rate.want(True,1))

@unittest.skipUnless(sys.platform=='win32','Windows only')
class WindowsTests(unittest.TestCase):
 def test_the_structures_have_windows_sizes(self):
  self.assertEqual((ctypes.sizeof(s.DEVMODE),ctypes.sizeof(s.MONITORINFOEX)),(220,104))
 def test_this_screen_lists_the_mode_it_runs_in(self):
  # Reads only: switching this PC's screen in a test would flash it.
  system=s.Windows();device=system.screen(ctypes.windll.user32.GetDesktopWindow())
  self.assertTrue(device);current=system.current(device);self.assertIn(current,system.modes(device))

if __name__=='__main__':unittest.main()
