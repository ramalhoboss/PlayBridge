"""Play counted: sessions start, end and survive a restart, short ones are left out, and the week, each game, the streak and a year are
worked out from them, with the console's own totals beside PlayBridge's."""
import shutil,sys,tempfile,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import game_stats

def at(day,hour,minute=0):return time.mktime((2026,11,day,hour,minute,0,0,0,-1))

class PlayLogTests(unittest.TestCase):
 def setUp(self):
  self.folder=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,self.folder,True);self.path=self.folder/'play.json'
 def play(self,log,title,name,start,minutes):
  for second in range(0,minutes*60+1,30):log.see(title,name,start+second)
 def test_sessions_start_end_and_survive_a_restart(self):
  log=game_stats.PlayLog(self.path)
  self.play(log,'PPSA01','Astro Bot',at(14,20),45);log.see('',now=at(14,20,46))
  self.play(log,'PPSA02','Hades II',at(14,21),20)
  log.see('PPSA02','Hades II',at(14,21,40))  # back after a long silence: a new session
  log.see('PPSA03','Quick Look',at(14,21,41));log.see('PPSA03','Quick Look',at(14,21,41,)+30);log.see('',now=at(14,21,42))
  self.assertEqual([(s[1],round((s[3]-s[2])/60)) for s in log.sessions],[('Astro Bot',45),('Hades II',20)],'the 30-second look is left out')
  self.play(log,'PPSA01','Astro Bot',at(15,10),5);log.save(at(15,10,5))
  again=game_stats.PlayLog(self.path);self.assertEqual(len(again.sessions),3,'the open session was kept as it stood')
  log.trophy('PPSA01','Astro Bot',2,at(15,10,3));log.close();self.assertEqual(game_stats.PlayLog(self.path).trophies,[['PPSA01','Astro Bot',at(15,10,3),2]])
  self.path.write_text('{"sessions":[["x","y","bad",3]],"trophies":"no"}',encoding='utf8');self.assertEqual(game_stats.PlayLog(self.path).sessions,[])
 def test_the_week_the_games_the_streak_and_the_year(self):
  log=game_stats.PlayLog(self.path)
  log.sessions=[['PPSA01','Astro Bot',at(9,20),at(9,22)],['PPSA01','Astro Bot',at(13,23),at(14,1)],['PPSA02','Hades II',at(14,18),at(14,18,30)],['PPSA01','Astro Bot',at(15,9),at(15,10)]]
  log.trophies=[['PPSA01','Astro Bot',at(14,0,30),3],['PPSA02','Hades II',at(1,12),1]]
  now=at(15,12);bars=game_stats.week(log.sessions,now)
  self.assertEqual([bar['label'] for bar in bars][-1],'Today');self.assertEqual([round(bar['seconds']/3600,1) for bar in bars],[2.0,0,0,0,1.0,1.5,1.0])
  rows=game_stats.games(log.sessions,log.trophies,[dict(title='PPSA01',name='ASTRO BOT',seconds=360000)],now)
  self.assertEqual([(row['name'],row['text'],row['sessions'],row['console'],row['trophies']) for row in rows],[('ASTRO BOT','5.0 h',3,'100 h',3),('Hades II','30 min',1,'',1)])
  self.assertEqual(rows[0]['weekText'],'5.0 h');self.assertEqual(rows[0]['trophiesWeek'],3)
  self.assertEqual(game_stats.streak(log.sessions,now),3);self.assertEqual(game_stats.streak(log.sessions,at(16,8)),3,'today without play yet still counts yesterday');self.assertEqual(game_stats.streak(log.sessions,at(18,8)),0)
  year=game_stats.year(log.sessions,log.trophies,2026,now)
  self.assertEqual((year['hours'],year['days'],year['sessions'],year['games'],year['trophies'],year['month']),('5.5 h',4,4,2,4,'November'));self.assertEqual(year['top'][0]['name'],'Astro Bot')
  self.assertEqual(year['longest']['text'],'2.0 h');self.assertEqual(game_stats.years(log.sessions),[2026])
  # 13, 14 and 15 November in a row; Monday the 9th has the most hours.
  self.assertEqual((year['streak'],year['weekday']),(3,'Mondays'))
  self.assertEqual((game_stats.year([],[],2025,now)['streak'],game_stats.year([],[],2025,now)['weekday']),(0,''))
  page=game_stats.page(log,[],None,now);self.assertEqual((page['weekText'],page['weekSessions'],page['weekTrophies'],page['streak'],page['year']['year']),('5.5 h',4,3,3,2026))
  self.assertTrue(game_stats.page(game_stats.PlayLog(self.folder/'none.json'),[],None,now)['empty'])
 def test_hours_in_words(self):
  self.assertEqual([game_stats.hours(s) for s in (300,3600*2.25,3600*42.4)],['5 min','2.2 h','42 h'])

if __name__=='__main__':unittest.main()
