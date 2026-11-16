import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import performance_lab,share_cards
from performance import CURVE,GameSession,curve,mode_of,percentile

def summary(rates,title='T1',name='Game',start=1000,status=None):
 session=GameSession(title,name,0,start)
 for i,rate in enumerate(rates):session.add(status or {'cpu_c':70,'soc_c':60,'gpu_mw':150000,'cpu_mw':40000,'mem_mw':15000},rate,i/4)
 return session.summary()

class SummaryTests(unittest.TestCase):
 def test_percentile_by_nearest_rank(self):
  values=list(range(1,101))
  self.assertEqual(percentile(values,1),1);self.assertEqual(percentile(values,50),50);self.assertEqual(percentile(values,95),95);self.assertEqual(percentile(values,100),100)
  self.assertEqual(percentile([7],.1),7);self.assertIsNone(percentile([],1))
 def test_mode_is_the_cap_its_fastest_seconds_sit_on(self):
  self.assertEqual(mode_of([59.5]*90+[45]*10),'60 fps');self.assertEqual(mode_of([30]*100),'30 fps');self.assertEqual(mode_of([39.6]*50),'40 fps')
  self.assertEqual(mode_of([80,95,72,88]*20),'Unlocked');self.assertEqual(mode_of([0,0]),'')
 def test_pauses_are_left_out_of_the_numbers(self):
  s=summary([60]*400+[0]*200+[30]*2)
  self.assertEqual(s['fps_lowest'],30);self.assertGreater(s['fps_average'],59);self.assertEqual(s['mode'],'60 fps')
  self.assertEqual(s['fps_low01'],30);self.assertEqual(s['fps_low1'],60)
 def test_only_pauses_give_no_rate(self):
  s=summary([0]*50)
  for key in ('fps_average','fps_lowest','fps_usual','at_usual'):self.assertIsNone(s[key],key)
  self.assertNotIn('curve',s);self.assertNotIn('mode',s)
 def test_curve_keeps_at_most_its_points_and_marks_pauses(self):
  rates=[60]*1000+[0]*200+[50]*1000
  points=curve(rates)
  self.assertLessEqual(len(points),CURVE);self.assertIn([0,0],points);self.assertEqual(points[0],[60,60]);self.assertEqual(points[-1],[50,50])
  self.assertEqual(curve([]),[]);self.assertEqual(curve([60,30]),[[60,60],[30,30]])
 def test_a_stretch_with_a_dip_keeps_its_lowest(self):
  points=curve([60]*9+[20],points=1)
  self.assertEqual(points,[[56.0,20]])

class ReportTests(unittest.TestCase):
 def test_one_report_for_each_game_and_mode_newest_first(self):
  history=[summary([60]*400,'A','Alpha',100),summary([30]*400,'A','Alpha',300),summary([60]*800,'A','Alpha',200),summary([45,90,70]*100,'B','Beta',50)]
  found=performance_lab.reports(history)
  self.assertEqual([r['key'] for r in found],['A|30 fps','A|60 fps','B|Unlocked'])
  sixty=found[1];self.assertEqual(sixty['sessions'],2);self.assertEqual(sixty['last'],200);self.assertAlmostEqual(sixty['minutes'],(399+799)/4/60,delta=.2)
 def test_averages_are_weighted_by_minutes(self):
  short=dict(summary([60]*240,'A','Alpha',1),minutes=1);long=dict(summary([50]*240,'A','Alpha',2),minutes=3)
  long['mode']=short['mode']='60 fps'
  report=performance_lab.reports([short,long])[0]
  self.assertEqual(report['fps_average'],52.5)
 def test_old_summaries_without_the_new_numbers(self):
  old=dict(title='C',name='Old',started=10,minutes=12,fps_average=58.0,fps_lowest=31.0,fps_usual=60,at_usual=90,cpu_max=None,cpu_average=None,soc_max=None,soc_average=None)
  report=performance_lab.reports([old])[0]
  self.assertEqual(report['mode'],'60 fps');self.assertIsNone(report['fps_low1']);self.assertEqual(report['curve'],[]);self.assertEqual(report['fps_lowest'],31.0)
  old['fps_usual']=48;self.assertEqual(performance_lab.reports([old])[0]['mode'],'Unlocked')
 def test_bad_entries_are_skipped(self):
  self.assertEqual(performance_lab.reports([None,'x',{},{'title':'A'},{'title':'A','fps_average':None}]),[])
  self.assertEqual(performance_lab.reports('not a list'),[])
 def test_view_picks_the_newest_when_the_choice_is_gone(self):
  history=[summary([60]*400,'A','Alpha',100),summary([30]*400,'B','Beta',300)]
  self.assertEqual(performance_lab.view(history,'')['labPicked'],'B|30 fps')
  self.assertEqual(performance_lab.view(history,'A|60 fps')['labPicked'],'A|60 fps')
  self.assertEqual(performance_lab.view(history,'gone|60 fps')['labPicked'],'B|30 fps')
  self.assertEqual(performance_lab.view([],'A|60 fps'),dict(labRows=[],labPicked=''))
  row=performance_lab.view(history)['labRows'][0]
  self.assertIn('1% low',row['numbers']);self.assertTrue(row['steady'].endswith('at 30 fps'));self.assertIn('1 session',row['line'])
 def test_words(self):
  self.assertEqual(performance_lab.duration(42),'42 min');self.assertEqual(performance_lab.duration(120),'2 h');self.assertEqual(performance_lab.duration(135),'2 h 15 min')
  self.assertEqual(performance_lab.stability(dict(mode='Unlocked',at_usual=80)),'');self.assertEqual(performance_lab.stability(dict(mode='60 fps',at_usual=97.4)),'97% of the time at 60 fps')

class CardTests(unittest.TestCase):
 def test_frame_times(self):
  self.assertEqual(share_cards.frame_times([[50,25],[0,0],['x',1],[40,0]]),[(20.0,40.0),None,None,(25.0,None)])
 def test_card_for_a_full_report(self):
  report=performance_lab.reports([summary([60]*900+[40]*20+[0]*80,'A','A game whose name is far too long to fit on one line of the card at all, really')])[0]
  image=share_cards.performance_card(report)
  self.assertEqual((image.mode,image.size),('RGB',(1200,675)))
  # The graph's gold line is drawn inside its panel.
  data=image.crop((540,300,1130,540)).tobytes();self.assertTrue(any(data[i]>200 and data[i+1]>180 and data[i+2]<170 for i in range(0,len(data),3)))
 def test_card_for_a_report_with_little_in_it(self):
  image=share_cards.performance_card(dict(key='x|Unlocked',title='X',name='',mode='Unlocked',sessions=1,minutes=0,fps_average=None,curve=[[0,0]],last=0))
  self.assertEqual(image.size,(1200,675))
 def test_cards_do_not_share_their_ground(self):
  first=share_cards.background();first.putpixel((600,300),(255,0,0))
  self.assertNotEqual(share_cards.background().getpixel((600,300)),(255,0,0))
 def test_long_text_is_cut_to_fit(self):
  from PIL import Image,ImageDraw
  draw=ImageDraw.Draw(Image.new('RGB',(10,10)));text,font=share_cards.fit(draw,'W'*200,50,'semibold',600)
  self.assertTrue(text.endswith('…'));self.assertLessEqual(draw.textlength(text,font=font),600)
 def test_wrapped_card_of_a_year(self):
  import game_stats,time
  year=game_stats.year([['PPSA01','Astro Bot',1_790_000_000,1_790_007_200],['PPSA02','Hades II',1_790_090_000,1_790_093_600]],[['PPSA01','Astro Bot',1_790_001_000,2]],
   time.localtime(1_790_000_000).tm_year,1_790_100_000)
  image=share_cards.wrapped_card(year,dict(level=312,counts=[dict(grade='platinum',count=8)]))
  self.assertEqual((image.mode,image.size),('RGB',(1200,675)))
  # The first game's bar is full: gold across the panel.
  data=image.crop((680,250,1100,262)).tobytes();self.assertTrue(sum(1 for i in range(0,len(data),3) if data[i]>190 and data[i+2]<120)>200)
  self.assertEqual(share_cards.wrapped_card(dict(year=2025,hours='0 h',top=[])).size,(1200,675),'an empty year and no PSN still draw')

if __name__=='__main__':unittest.main()
