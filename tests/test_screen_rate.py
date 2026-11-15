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

def at(*rates,size=(2560,1440,32)):return [size+(hz,) for hz in rates]
class FasterTests(unittest.TestCase):
 """With smooth motion a screen that can run faster than the stream does, so there is a refresh for a picture between two frames."""
 def test_two_refreshes_a_frame_come_first(self):
  self.assertEqual(s.fastest(LAPTOP,(2560,1440,32,60)),120);self.assertEqual(s.fastest(LAPTOP,(2560,1440,32,165)),120)
  self.assertEqual(s.fastest(at(60,119),(2560,1440,32,60)),119);self.assertEqual(s.fastest(at(60,120,240),(2560,1440,32,60)),120)
 def test_then_a_steady_rate_with_more_then_the_fastest_quick_one(self):
  self.assertEqual(s.fastest(at(60,240),(2560,1440,32,60)),240);self.assertEqual(s.fastest(at(60,100,144),(2560,1440,32,60)),144)
 def test_a_screen_already_fast_enough_or_too_slow_is_left_alone(self):
  for rates,current in (((60,120),120),((60,144),144),((60,75),60),((60,),60),((60,240),240)):
   self.assertIsNone(s.fastest(at(*rates),(2560,1440,32,current)),(rates,current))
  self.assertIsNone(s.fastest(LAPTOP,None))
  # A fast rate offered only at another size is not used.
  self.assertIsNone(s.fastest(at(60)+at(120,size=(1920,1080,32)),(2560,1440,32,60)))
 def test_room_for_in_between_pictures_starts_at_half_again_the_stream(self):
  for hz in (89,90,100,119,144,165,240):self.assertTrue(s.fast(hz),hz)
  for hz in (0,None,59,60,75,85):self.assertFalse(s.fast(hz),hz)
 def test_a_60_hz_screen_that_offers_120_is_switched_and_put_back(self):
  screen=Screen(current=(2560,1440,32,60));rate=s.ScreenRate(screen)
  self.assertEqual(rate.want(True,1,faster=True),(60,120));self.assertEqual(rate.label(),'60 -> 120 Hz')
  for _ in range(4):self.assertIsNone(rate.want(True,1,faster=True))
  rate.want(False,1);self.assertEqual(screen.calls,[('switch',120),('restore',)])
 def test_a_screen_left_at_60_before_the_pictures_start_is_asked_again_once_they_do(self):
  screen=Screen(current=(2560,1440,32,60));rate=s.ScreenRate(screen)
  for _ in range(3):self.assertIsNone(rate.want(True,1))
  self.assertEqual(rate.note,'60 Hz already fits 60 fps');self.assertEqual(rate.want(True,1,faster=True),(60,120))
 def test_without_matching_a_fast_screen_keeps_its_rate(self):
  screen=Screen(modes=at(60,144),current=(2560,1440,32,144));rate=s.ScreenRate(screen)
  self.assertIsNone(rate.want(True,1,faster=True,match=False));self.assertEqual(screen.calls,[])
  self.assertEqual(rate.note,'144 Hz already has room for in-between pictures')
  slow=Screen(modes=at(60,75),current=(2560,1440,32,60));rate=s.ScreenRate(slow)
  self.assertIsNone(rate.want(True,1,faster=True,match=False));self.assertEqual(rate.note,'60 Hz, and no rate fast enough for in-between pictures at 2560x1440')
 def test_a_screen_with_no_fast_rate_is_still_matched(self):
  # A 75 Hz screen has no room for in-between pictures, but 60 Hz still shows every frame for the same time.
  screen=Screen(modes=at(60,75),current=(2560,1440,32,75));rate=s.ScreenRate(screen)
  self.assertEqual(rate.want(True,1,faster=True,match=True),(75,60))
 def test_120_hz_stays_when_the_pictures_stop_and_the_screen_still_fits(self):
  screen=Screen(current=(2560,1440,32,60));rate=s.ScreenRate(screen);rate.want(True,1,faster=True)
  self.assertIsNone(rate.want(True,1,faster=False));self.assertEqual(screen.calls,[('switch',120)]);self.assertEqual(rate.label(),'60 -> 120 Hz')
 def test_144_hz_for_the_pictures_goes_back_when_they_stop(self):
  screen=Screen(modes=at(60,144),current=(2560,1440,32,60));screen.restore=lambda device:(screen.calls.append(('restore',)),setattr(screen,'now',(2560,1440,32,60)))
  rate=s.ScreenRate(screen);self.assertEqual(rate.want(True,1,faster=True),(60,144))
  self.assertIsNone(rate.want(True,1,faster=False));self.assertEqual(screen.calls,[('switch',144),('restore',)]);self.assertIsNone(rate.label())
 def test_a_matched_screen_that_fits_the_pictures_too_is_kept(self):
  screen=Screen();rate=s.ScreenRate(screen);self.assertEqual(rate.want(True,1),(165,120))
  self.assertIsNone(rate.want(True,1,faster=True));self.assertEqual(screen.calls,[('switch',120)])

@unittest.skipUnless(sys.platform=='win32','Windows only')
class WindowsTests(unittest.TestCase):
 def test_the_structures_have_windows_sizes(self):
  self.assertEqual((ctypes.sizeof(s.DEVMODE),ctypes.sizeof(s.MONITORINFOEX)),(220,104))
 def test_this_screen_lists_the_mode_it_runs_in(self):
  # Reads only: switching this PC's screen in a test would flash it.
  system=s.Windows();device=system.screen(ctypes.windll.user32.GetDesktopWindow())
  self.assertTrue(device);current=system.current(device);self.assertIn(current,system.modes(device))
 def test_types_another_module_gives_the_same_call_do_not_break_the_lookup(self):
  # The variable refresh check gives GetMonitorInfoW a structure of its own. In 1.6.0 that made every later lookup here fail.
  class Other(ctypes.Structure):_fields_=[('cbSize',ctypes.c_uint32)]
  shared=ctypes.windll.user32.GetMonitorInfoW;kept=shared.argtypes
  try:
   system=s.Windows();shared.argtypes=[ctypes.c_void_p,ctypes.POINTER(Other)]
   self.assertTrue(system.screen(ctypes.windll.user32.GetDesktopWindow()))
  finally:shared.argtypes=kept

if __name__=='__main__':unittest.main()
