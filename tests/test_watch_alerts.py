"""Alert me when: the picture moves again, the game slows down, the CPU reaches a temperature; each from real readings, used once."""
import ctypes,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import watch_alerts as w
import desktop_notice as n

RATE=80_000_000//8
STILL=60_000;LOGO=420_000;GAME=6_000_000

def run(alerts,seconds,rate=RATE,linked=True,view=None,frames=60):
 fired=[]
 for sent in seconds:fired+=alerts.second((sent,frames),rate,linked,view or {})
 return fired

class MovesTests(unittest.TestCase):
 def armed(self):
  alerts=w.Alerts();alerts.arm('moves',True);return alerts
 def test_a_still_screen_that_starts_moving_sets_it_off_once(self):
  alerts=self.armed();self.assertEqual(run(alerts,[STILL+i*500 for i in range(12)]),[])
  self.assertEqual(alerts.state['moves'],'Watching: the picture is still')
  fired=run(alerts,[GAME,GAME*1.1]);self.assertEqual([kind for kind,_,_ in fired],['moves']);self.assertFalse(alerts.wanted['moves'])
  self.assertEqual(run(alerts,[STILL]*10+[GAME]*3),[])
 def test_a_loading_screen_with_a_turning_logo_counts_as_still(self):
  alerts=self.armed();self.assertEqual(run(alerts,[LOGO*(1+.2*(i%3)) for i in range(10)]),[])
  self.assertEqual(alerts.state['moves'],'Watching: the picture is still')
  self.assertEqual(len(run(alerts,[GAME,GAME])),1)
 def test_one_busy_second_is_not_enough(self):
  alerts=self.armed();self.assertEqual(run(alerts,[STILL]*10+[GAME]+[STILL]*10),[])
 def test_a_game_already_moving_waits_for_the_picture_to_be_still_first(self):
  alerts=self.armed();self.assertEqual(run(alerts,[GAME*(1+.5*(i%2)) for i in range(20)]),[])
  self.assertEqual(alerts.state['moves'],'Waiting for the picture to be still')
 def test_a_small_change_on_a_still_screen_is_not_movement(self):
  # Several times the still seconds, but far under the stream's rate: a cursor or a clock, not the game starting.
  alerts=self.armed();self.assertEqual(run(alerts,[20_000]*10+[150_000]*3),[])
 def test_no_picture_means_nothing_is_judged(self):
  alerts=self.armed();run(alerts,[STILL]*9);run(alerts,[0],frames=0)
  self.assertEqual(alerts.state['moves'],'Waiting for the picture');self.assertEqual(run(alerts,[GAME]*2),[])
  run(alerts,[0]*3,linked=False);self.assertEqual(alerts.state['moves'],'Waiting for the picture')
 def test_it_works_without_knowing_the_streams_rate(self):
  alerts=self.armed();self.assertEqual(run(alerts,[STILL]*10,rate=None),[]);self.assertEqual(len(run(alerts,[GAME]*2,rate=None)),1)
 def test_nothing_is_watched_unless_asked(self):
  self.assertEqual(run(w.Alerts(),[STILL]*10+[GAME]*3),[])

class MeterTests(unittest.TestCase):
 def test_keyframes_carry_the_whole_picture_so_they_are_left_out(self):
  meter=w.MotionMeter();meter.add(500_000,True);meter.add(2000,False);meter.add(3000,False)
  self.assertEqual(meter.take(),(5000,3));self.assertEqual(meter.take(),(0,0))

def view(points,fps,name='Some Game',cpu=60):
 return dict(points=points,game_fps=fps,name=name,status={'cpu_c':cpu})

class SlowTests(unittest.TestCase):
 def test_a_game_under_its_usual_rate_for_three_seconds_sets_it_off(self):
  alerts=w.Alerts();alerts.arm('slow',True);usual=[60.0]*200
  self.assertEqual(run(alerts,[STILL]*3,view=view(usual,59.9)),[]);self.assertEqual(alerts.state['slow'],'Watching: usually 60 fps, now 60')
  self.assertEqual(run(alerts,[STILL]*2,view=view(usual,41.0)),[])
  fired=run(alerts,[STILL],view=view(usual,41.0));self.assertEqual(fired[0][:2],('slow','Some Game slowed down'));self.assertIn('41',fired[0][2])
  self.assertFalse(alerts.wanted['slow'])
 def test_a_30_fps_game_at_30_is_at_its_usual_rate(self):
  alerts=w.Alerts();alerts.arm('slow',True);self.assertEqual(run(alerts,[STILL]*10,view=view([30.0]*200,29.9)),[])
 def test_a_short_dip_is_not_slowing_down(self):
  alerts=w.Alerts();alerts.arm('slow',True);usual=[60.0]*200
  for fps in (40,40,59,40,40,59):self.assertEqual(run(alerts,[STILL],view=view(usual,fps)),[])
 def test_without_the_consoles_count_it_waits(self):
  alerts=w.Alerts();alerts.arm('slow',True)
  self.assertEqual(run(alerts,[STILL]*5,view=view([60.0]*(w.USUAL_POINTS-1),20.0)),[]);self.assertEqual(alerts.state['slow'],"Waiting for the game's frame count")
  self.assertEqual(run(alerts,[STILL]*5,view=view([None]*200,None)),[])

class HotTests(unittest.TestCase):
 def test_it_fires_at_the_temperature_set(self):
  alerts=w.Alerts(70);alerts.arm('hot',True)
  self.assertEqual(run(alerts,[STILL],view=view([],None,cpu=69)),[]);self.assertEqual(alerts.state['hot'],'Watching: the CPU is at 69 °C')
  fired=run(alerts,[STILL],view=view([],None,cpu=71));self.assertEqual(fired[0][:2],('hot','Your PS5 reached 71 °C'))
 def test_a_missing_reading_is_never_a_temperature(self):
  alerts=w.Alerts();alerts.arm('hot',True)
  for cpu in (-1,0,None,True):self.assertEqual(run(alerts,[STILL],view=view([],None,cpu=cpu)),[])
  self.assertEqual(alerts.state['hot'],"Waiting for the PS5's temperature")
 def test_only_its_choices_are_kept(self):
  self.assertEqual(w.Alerts(85).hot_at,w.HOT_DEFAULT);self.assertEqual(w.Alerts(None).hot_at,w.HOT_DEFAULT);self.assertEqual(w.Alerts(90).hot_at,90)

class TrophyTests(unittest.TestCase):
 def test_a_trophy_alert_is_used_once_and_names_the_trophy(self):
  alerts=w.Alerts();earned=[dict(id=3,name='Done It',grade='gold',at=1)]
  self.assertEqual(alerts.trophies('Some Game',earned),[])
  alerts.arm('trophy',True);run(alerts,[STILL]);self.assertEqual(alerts.state['trophy'],'Watching for the next trophy you earn')
  self.assertEqual(alerts.trophies('Some Game',earned),[('trophy','Trophy earned: Done It','In Some Game.')]);self.assertFalse(alerts.wanted['trophy'])
  alerts.arm('trophy',True);self.assertEqual(alerts.trophies('G',earned*2)[0][1],'2 trophies earned')
  alerts.arm('trophy',True);self.assertEqual(alerts.trophies('G',[dict(id=1,name='',grade='',at=1)])[0][1],'Trophy earned')

class NoticeTests(unittest.TestCase):
 def test_the_notification_block_is_the_one_windows_expects(self):
  # NOTIFYICONDATAW with the balloon icon, as Windows Vista and later take it: 976 bytes on 64-bit Windows, 956 on 32-bit.
  self.assertEqual(ctypes.sizeof(n.NotifyIconData),976 if ctypes.sizeof(ctypes.c_void_p)==8 else 956)
  self.assertEqual(ctypes.sizeof(n.FlashInfo),32 if ctypes.sizeof(ctypes.c_void_p)==8 else 20)
 def test_the_icon_goes_once_its_notification_has_been_read(self):
  clock=[0.0];notice=n.DesktopNotice(0,'none.ico',lambda:clock[0]);notice.calls=None;notice.shown_until=5.0
  removed=[];notice.remove=lambda:removed.append(clock[0])
  notice.tick();clock[0]=5.0;notice.tick();self.assertEqual(removed,[5.0])

if __name__=='__main__':unittest.main()
