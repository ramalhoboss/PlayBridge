"""The PS5's performance: the game's frame rate, temperatures and power while it runs, a summary once it ends, and the overlay."""
import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import performance as p

GAME='PPSA01234'
def status(cpu=61,soc=55,gpu=90000,cpu_mw=30000,mem=12000):
 return dict(cpu_c=cpu,soc_c=soc,gpu_mw=gpu,cpu_mw=cpu_mw,mem_mw=mem,title=GAME,app=5)

class Clock:
 def __init__(self):self.now=100.0
 def __call__(self):return self.now

def log(folder,said=None):
 clock=Clock();book=p.PerformanceLog(Path(folder)/'sessions.json',{GAME:'Some Game'}.get,(said.append if said is not None else None),clock,lambda:1_700_000_000)
 return book,clock

def play(book,clock,seconds,fps=60.0,title=GAME,**reading):
 for _ in range(int(seconds*4)):book.add(status(**reading),fps,title);clock.now+=.25

class ReadingTests(unittest.TestCase):
 def test_power_is_read_in_watts_only_when_the_console_measured_it(self):
  self.assertEqual(p.watts(status()),(90.0,30.0,12.0))
  for missing in (dict(gpu_mw=-1,cpu_mw=-1,mem_mw=-1),dict(gpu_mw=0,cpu_mw=0,mem_mw=0),{},dict(gpu_mw=True,cpu_mw=1,mem_mw=1),dict(gpu_mw='9',cpu_mw=1,mem_mw=1)):
   self.assertIsNone(p.watts(missing),missing)
  self.assertIsNone(p.watts(None))
 def test_a_temperature_the_console_did_not_read_is_not_shown(self):
  self.assertEqual(p.reading(status(),'cpu_c'),61)
  for value in (-1,0,None,True,'61'):self.assertIsNone(p.reading({'cpu_c':value},'cpu_c'),value)

class SessionTests(unittest.TestCase):
 def setUp(self):
  self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
 def test_a_game_that_ran_long_enough_leaves_its_summary(self):
  said=[];book,clock=log(self.folder.name,said)
  play(book,clock,50,fps=60.0,cpu=60);play(book,clock,20,fps=30.0,cpu=72,gpu=120000)
  book.add({},None,'');clock.now+=.25
  history=book.history();self.assertEqual(len(history),1);s=history[0]
  self.assertEqual((s['title'],s['name'],s['started']),(GAME,'Some Game',1_700_000_000))
  self.assertEqual(s['fps_usual'],60);self.assertEqual(s['fps_lowest'],30.0);self.assertAlmostEqual(s['fps_average'],(50*60+20*30)/70,delta=.1)
  self.assertEqual(s['at_usual'],round(100*50/70));self.assertEqual((s['cpu_max'],s['soc_max']),(72,55))
  self.assertEqual(s['watts_max'],162.0);self.assertAlmostEqual(s['gpu_watts'],(50*90+20*120)/70,delta=.1);self.assertEqual(s['memory_watts'],12.0)
  self.assertEqual(book.last_report,s)
  self.assertEqual(said,[p.report_line(s)]);self.assertIn('Some Game: ',said[0]);self.assertIn('CPU up to 72 °C',said[0])
 def test_a_launch_and_a_close_leave_nothing(self):
  said=[];book,clock=log(self.folder.name,said);play(book,clock,p.SHORTEST-5);book.end()
  self.assertEqual(book.history(),[]);self.assertEqual(said,[]);self.assertIsNone(book.last_report)
 def test_switching_games_ends_the_first_one(self):
  book,clock=log(self.folder.name);play(book,clock,70);play(book,clock,70,title='PPSA09999');book.end()
  self.assertEqual([s['title'] for s in book.history()],[GAME,'PPSA09999'])
 def test_what_the_console_never_gave_stays_unknown(self):
  book,clock=log(self.folder.name)
  play(book,clock,70,fps=None,cpu=-1,soc=-1,gpu=-1,cpu_mw=-1,mem=-1);book.end();s=book.history()[0]
  for key in ('fps_average','fps_lowest','fps_usual','at_usual','cpu_max','soc_max'):self.assertIsNone(s[key],key)
  self.assertNotIn('watts_average',s);self.assertEqual(p.report_line(s),'')
  self.assertEqual(p.report_details(s),['Some Game  ·  1 min'])
 def test_the_history_keeps_the_newest_and_survives_a_broken_file(self):
  path=Path(self.folder.name)/'sessions.json';path.write_text('not json',encoding='utf-8')
  book,clock=log(self.folder.name);play(book,clock,70);book.end();self.assertEqual(len(book.history()),1)
  path.write_text(json.dumps([{'title':str(i)} for i in range(p.KEEP)]),encoding='utf-8')
  play(book,clock,70);book.end();history=book.history();self.assertEqual(len(history),p.KEEP);self.assertEqual(history[-1]['title'],GAME);self.assertEqual(history[0]['title'],'1')
 def test_the_overlay_view_follows_the_running_game(self):
  book,clock=log(self.folder.name);self.assertEqual(book.view()['name'],'')
  play(book,clock,2,fps=58.0);play(book,clock,1,fps=40.0);view=book.view()
  self.assertEqual((view['name'],view['game_fps'],view['lowest']),('Some Game',40.0,40));self.assertEqual(len(view['points']),12)
  play(book,clock,p.POINTS);self.assertEqual(len(book.view()['points']),p.POINTS)
  book.add({},None,'');self.assertIsNone(book.view()['points'][-1]);self.assertEqual(book.view()['name'],'')
  book.end();view=book.view();self.assertEqual((view['points'],view['status'],view['game_fps']),([],{},None))

class OverlayTests(unittest.TestCase):
 def view(self,**changes):
  base=dict(status=status(),game_fps=59.9,points=[60.0]*100+[None]*3+[30.0]*50,name='Some Game',lowest=30);base.update(changes);return base
 def test_its_lines_show_only_what_was_measured(self):
  name,big,note,lines=p.overlay_lines(self.view(),dict(picture='2160p',mbps=78.4,pc_ms=9.6,smooth=None))
  self.assertEqual((name,big,note),('Some Game','60','FPS  ·  lowest 30'))
  self.assertEqual(lines,['CPU 61°   SoC 55°','132 W   GPU 90  CPU 30  RAM 12','2160p   78 Mbps   PC 10 ms'])
  name,big,note,lines=p.overlay_lines(self.view(status={},game_fps=None,lowest=None,name=''),{})
  self.assertEqual((name,big,note,lines),('PS5','—','FPS',[]))
 def test_smooth_motion_shows_the_rate_on_screen(self):
  _,big,note,_=p.overlay_lines(self.view(game_fps=30.0),dict(smooth=60));self.assertEqual((big,note),('30','FPS  →  60 smooth'))
 def test_it_is_drawn_with_transparency_at_the_screens_size(self):
  for scale in (.5,1,2,4):
   data,width,height=p.render_overlay(self.view(),dict(picture='1080p',mbps=40,pc_ms=8,smooth=60),scale)
   self.assertEqual(len(data),width*height*4)
   s=max(.75,min(2.5,scale));self.assertEqual(width,round(250*s))
   # BGRA: the corner outside the rounded panel is clear, the panel itself half see-through.
   self.assertEqual(data[3],0);inside=(height//2*width+3)*4;self.assertTrue(0<data[inside+3]<255,scale)
  small=p.render_overlay(self.view(status={}),{})
  self.assertLess(small[2],p.render_overlay(self.view(),dict(picture='1080p'))[2])

if __name__=='__main__':unittest.main()
