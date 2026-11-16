"""Trophies from PSN: Sony's answers become the same games and trophies the console's files give, the list is read once and kept,
an open game reads its trophies and the player's side, a friend's side stands beside them or the page says they are private, the
Games page gets a PS4 game's trophies from PSN while the console's own stay first, trophies wait while the budget is short, and
signing out forgets them."""
import json,shutil,sys,tempfile,unittest,urllib.parse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import psn_link,psn_trophies as pt
import console_control as control
from test_psn_link import CODE,PNG,Clock,FakeSony

def title(key,name,platform,earned,defined,progress,updated,icon=''):
 return dict(npServiceName='trophy2' if platform=='PS5' else 'trophy',npCommunicationId=key,trophySetVersion='01.00',trophyTitleName=name,trophyTitleIconUrl=icon,
  trophyTitlePlatform=platform,definedTrophies=defined,earnedTrophies=earned,progress=progress,lastUpdatedDateTime=updated,hiddenFlag=False)
ALL=dict(bronze=2,silver=1,gold=0,platinum=1)
MINE=[title('NPWR11111_00','Astro Bot','PS5',dict(bronze=2,silver=1,gold=0,platinum=1),ALL,100,'2026-11-10T20:00:00Z','https://image.example/astro.png'),
 title('NPWR22222_00','Old Racer','PS4',dict(bronze=1,silver=0,gold=0,platinum=0),ALL,12,'2025-02-01T10:00:00Z'),
 title('NPWR33333_00','Puzzle Days','PS5',dict(bronze=0,silver=0,gold=0,platinum=0),ALL,0,'2026-01-05T10:00:00Z')]
DEFINED=[dict(trophyId=0,trophyHidden=False,trophyType='platinum',trophyName='All of it',trophyDetail='Every trophy.',trophyIconUrl='https://image.example/t0.png'),
 dict(trophyId=1,trophyHidden=False,trophyType='bronze',trophyName='First steps',trophyDetail='Finish the first level.'),
 dict(trophyId=2,trophyHidden=True,trophyType='bronze',trophyName='The twist',trophyDetail='A secret.'),
 dict(trophyId=3,trophyHidden=False,trophyType='silver',trophyName='Fast',trophyDetail='Win a race.')]
def earned(ids,dates=None):
 return [dict(trophyId=i,trophyHidden=False,earned=i in ids,earnedDateTime=(dates or {}).get(i,'2026-11-09T12:00:00Z') if i in ids else None,trophyEarnedRate=str(5.5+i)) for i in range(4)]

class TrophySony(FakeSony):
 """FakeSony with the trophy service too."""
 def __init__(self):
  super().__init__();self.titles={'me':list(MINE),'111':[MINE[0],MINE[2]]};self.sets={'NPWR11111_00':DEFINED,'NPWR22222_00':DEFINED[:2]}
  self.earned={('me','NPWR11111_00'):earned({0,1,2,3}),('me','NPWR22222_00'):earned({1})[:2],('111','NPWR11111_00'):earned({1})}
  self.private=set();self.by_title={'CUSA01234':MINE[1]}
 def __call__(self,method,url,headers,body):
  parts=urllib.parse.urlsplit(url);path=parts.path;query=urllib.parse.parse_qs(parts.query)
  if '/trophy/v1/' not in path:return super().__call__(method,url,headers,body)
  self.requests.append((method,url,headers,body))
  def answer(data,status=200):return status,{},json.dumps(data).encode()
  bits=path.split('/trophy/v1/')[1].split('/')
  if bits[0]=='users' and bits[1] in self.private:return answer({'error':dict(code=2240526,message='Not permitted by access control')},403)
  if bits[0]=='users' and bits[2]=='trophySummary':return answer(dict(accountId='1',trophyLevel='312',progress=40,tier=4,earnedTrophies=dict(bronze=3,silver=1,gold=0,platinum=1)))
  if bits[0]=='users' and bits[2]=='trophyTitles':
   items=self.titles.get(bits[1],[]);offset=int(query.get('offset',['0'])[0]);limit=int(query['limit'][0])
   return answer(dict(trophyTitles=items[offset:offset+limit],totalItemCount=len(items)))
  if bits[0]=='users' and bits[2]=='titles':
   ids=query['npTitleIds'][0].split(',');found=[dict(npTitleId=i,trophyTitles=[self.by_title[i[:9]]]) for i in ids if i[:9] in self.by_title]
   return answer(dict(titles=found,totalItemCount=len(found))) if found else answer({'error':dict(message='Resource not found')},404)
  if bits[0]=='npCommunicationIds':return answer(dict(trophySetVersion='01.00',hasTrophyGroups=False,trophies=self.sets.get(bits[1],[]),totalItemCount=4))
  if bits[0]=='users' and bits[2]=='npCommunicationIds':
   found=self.earned.get((bits[1],bits[3]))
   return answer(dict(trophySetVersion='01.00',trophies=found)) if found is not None else answer({'error':dict(message='Resource not found')},404)
  return answer({'error':'not here'},404)
 def trophy_calls(self):return [urllib.parse.urlsplit(url).path for _,url,_,_ in self.requests if '/trophy/v1/' in url]

class ParseTests(unittest.TestCase):
 def test_sonys_answers_become_games_and_trophies(self):
  found=pt.title_from(MINE[1]);self.assertEqual((found['set'],found['service'],found['platforms'],found['progress']),('NPWR22222_00','trophy',['PS4'],12))
  self.assertIsNone(pt.title_from(dict(MINE[0],npCommunicationId='../../x')),'a set name that is not a set never reaches a path')
  self.assertEqual(pt.title_from(dict(MINE[0],npServiceName=None))['service'],'trophy2')
  self.assertEqual(pt.summary_from(dict(trophyLevel='312',tier=4,progress=40,earnedTrophies=dict(gold='2')))['level'],312)
  rows=pt.merged(pt.definitions_from(dict(trophies=DEFINED)),pt.states_from(dict(trophies=earned({1}))),pt.states_from(dict(trophies=earned({1,3}))))
  self.assertEqual([(row['id'],row['grade'],bool(row['earned']),bool(row['theirs'])) for row in rows],[(0,'platinum',False,False),(1,'bronze',True,True),(2,'bronze',False,False),(3,'silver',False,True)])
  self.assertAlmostEqual(rows[1]['rate'],6.5)

class BookTests(unittest.TestCase):
 def setUp(self):
  self.folder=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,self.folder,True)
  self.sony=TrophySony();self.clock=Clock();self.psn=self.make_psn();self.book=self.make_book(self.psn)
  self.assertEqual(self.psn.sign_in(CODE),'');self.psn.do(self.psn.jobs.get_nowait())
 def make_psn(self):return psn_link.Psn(self.folder/'psn',opener=self.sony,clock=self.clock)
 def make_book(self,psn):
  book=pt.TrophyBook(psn,self.folder/'psn'/'trophies');psn.helpers.append(book);return book
 def poll(self,times=1):
  for _ in range(times):self.clock.now+=2;self.psn.poll()
 def page(self,chosen='All'):return pt.page('on',self.book.view(),[('111','NightOwl'),('222','ModSquad')],chosen,icon=lambda url:url and 'file:'+url.rsplit('/',1)[-1])
 def test_the_list_is_read_once_kept_and_filtered(self):
  self.poll();shown=self.page()
  self.assertEqual(shown['level']['level'],312);self.assertEqual([row['name'] for row in shown['titles']],['Astro Bot','Puzzle Days','Old Racer'])
  self.assertTrue(shown['titles'][0]['platinum']);self.assertEqual(shown['titles'][2]['line'],'1 of 4 trophies')
  self.assertEqual([row['name'] for row in self.page('PS4')['titles']],['Old Racer']);self.assertEqual([row['name'] for row in self.page('Platinum')['titles']],['Astro Bot'])
  calls=len(self.sony.trophy_calls());self.poll(5);self.assertEqual(len(self.sony.trophy_calls()),calls,'not read again while the page does not show')
  again=self.make_book(self.make_psn());self.assertEqual(len(again.view()['titles']),3,'kept for the next start')
 def test_an_open_game_shows_its_trophies_and_a_friends(self):
  self.poll();self.book.watch(True);self.book.show_set('NPWR11111_00');self.poll()
  opened=self.page()['open'];self.assertEqual(opened['line'],'4 of 4 earned  ·  100%  ·  Platinum earned')
  self.assertEqual([row['name'] for row in opened['rows']],['All of it','First steps','The twist','Fast']);self.assertEqual(opened['rows'][1]['rare'],'6.5% of players')
  self.assertEqual(opened['rows'][0]['icon'],'file:t0.png')
  self.book.compare_with('111');self.poll(2);shown=self.page()
  self.assertEqual(shown['friendLine'],'2 games in common with NightOwl.');self.assertEqual([row['name'] for row in shown['titles']],['Astro Bot','Puzzle Days'])
  self.assertEqual([row['theirs'] for row in shown['open']['rows']],['Not yet','9 Nov 2026','Not yet','Not yet']);self.assertEqual(shown['open']['theirsLine'],'NightOwl: 1 of 4 earned')
  calls=len(self.sony.trophy_calls());self.poll(3);self.assertEqual(len(self.sony.trophy_calls()),calls,'nothing read again while nothing changed')
 def test_a_private_friend_and_a_hidden_trophy(self):
  self.sony.private.add('222');self.sony.earned[('me','NPWR33333_00')]=earned(set());self.sony.sets['NPWR33333_00']=DEFINED
  self.poll();self.book.watch(True);self.book.compare_with('222');self.book.show_set('NPWR33333_00');self.poll(2);shown=self.page()
  self.assertEqual(shown['friendLine'],'ModSquad keeps their trophies private.');self.assertFalse(shown['comparing']);self.assertEqual(len(shown['titles']),3)
  self.assertEqual(shown['open']['theirsLine'],'ModSquad keeps their trophies private.')
  secret=shown['open']['rows'][2];self.assertEqual((secret['name'],secret['icon']),('Hidden trophy',''));self.assertEqual(self.psn.problem,'','a private friend is not a problem with PSN')
 def test_the_games_page_gets_a_ps4_game_from_psn_and_the_consoles_own_first(self):
  link=control.ConsoleLink(self.folder/'link');link.more_trophies=self.book;before=link.revision
  self.assertIsNone(link.trophy_set('CUSA01234'))
  self.book.want_titles(['CUSA01234','PPSA00001','bad']);self.poll(3)
  found=link.trophy_set('CUSA01234');self.assertEqual((found['set'],found['source'],found['known']),('NPWR22222_00','psn',True))
  self.assertEqual([(row['name'],bool(row['earned'])) for row in found['trophies']],[('All of it',False),('First steps',True)]);self.assertEqual(found['tally']['earned'],1)
  self.assertGreater(link.revision,before,'the page redraws');self.assertIsNone(link.trophy_set('PPSA00001'),'no trophies on PSN for it')
  link.revision+=1;self.assertEqual(link.revision,before+1+self.book.shelf_changes)
  book=link.trophy_book;book['games']['CUSA01234']='NPWR99999_00';book['sets']['NPWR99999_00']=dict(key='k',name='From the console',trophies=[dict(id=0,grade='gold',hidden=False,name='Own',detail='')])
  book['user']='1a2b3c4d';book['earned']['1a2b3c4d']={'NPWR99999_00':{0:1700000000}}
  self.assertEqual(link.trophy_set('CUSA01234')['name'],'From the console','what the console read stays first')
  asked=len(self.sony.trophy_calls());self.book.want_titles(['PPSA00001']);self.poll(2);self.assertEqual(len(self.sony.trophy_calls()),asked,'a game with no trophies on PSN is not asked about again')
 def test_next_up_lists_the_trophies_most_players_have_from_games_in_progress(self):
  self.sony.sets['NPWR22222_00']=[dict(row) for row in DEFINED];self.sony.sets['NPWR22222_00'][3]['trophyDetail']='Win a race in chapter 3.'
  self.sony.earned[('me','NPWR22222_00')]=earned({1})
  self.poll();self.book.watch(True);calls=len(self.sony.trophy_calls());self.poll(2)
  self.assertEqual(len(self.sony.trophy_calls()),calls,'nothing is read for Next up until it shows')
  self.book.hunt(True);shown=self.page('Next up')
  self.assertTrue(shown['hunting']);self.assertEqual(shown['titles'],[]);self.assertEqual(shown['huntLine'],'Reading your game in progress…')
  self.poll(3);shown=self.page('Next up')
  # Only Old Racer is started and unfinished; its platinum and the trophy already earned are left out, the most common first.
  self.assertEqual([(row['name'],row['rare'],row['watch'],row['game']) for row in shown['hunt']],
   [('Fast','8.5% of players have it','it belongs to Chapter 3','Old Racer'),('Hidden trophy','7.5% of players have it','','Old Racer')])
  self.assertIn('Watch out marks',shown['huntLine']);self.assertEqual(shown['hunt'][1]['detail'],'Keep playing to find out what it is.')
  self.assertEqual([row['name'] for row in self.page('All')['titles']],['Astro Bot','Puzzle Days','Old Racer'],'the other filters are as before')
  calls=len(self.sony.trophy_calls());self.poll(3);self.assertEqual(len(self.sony.trophy_calls()),calls,'read once, then kept')
  self.book.hunt(False);self.assertIsNone(self.book.view()['hunt'])
 def test_watch_out_reads_the_trophys_own_words(self):
  cases={('Lost Relic','Find the relic in Chapter 4 before the bridge falls.'):'it belongs to Chapter 4',('Ghost','Finish a mission without being seen.'):'it has to be done without being seen',
   ('Iron Will','Complete the game on Hard.'):'it needs Hard difficulty',('Speedy','Finish the game in a single playthrough.'):'it has to be done in one playthrough',
   ('Veteran','Reach level 50.'):'',('Gone','This one is missable.'):'its description says it can be missed',('Curtain','Finish Act ii.'):'it belongs to Act II',
   ('Early bird','Open the gate before the guards arrive.'):'it has to happen before something else in the game',('Collector','Find every coin.'):''}
  for (name,detail),why in cases.items():self.assertEqual(pt.watch_out(name,detail),why,name)
  self.assertEqual(pt.hunt_view([]),([],'Start a game with trophies, and the trophies you have left that most players earned show here.'))
  self.assertEqual(pt.hunt_view(None),([],''))
 def test_an_answer_in_an_odd_shape_is_a_problem_not_the_end_of_the_thread(self):
  original=TrophySony.__call__
  def odd(sony,method,url,headers,body):
   if url.split('?')[0].endswith('/trophyTitles'):return 200,{},b'[1,2,3]'
   return original(sony,method,url,headers,body)
  self.sony.__class__=type('OddSony',(TrophySony,),{'__call__':odd})
  with self.assertRaises(psn_link.Problem) as caught:self.psn.poll()
  self.assertIn('could not read',str(caught.exception),'run() turns a Problem into words on the page and carries on')
 def test_trophies_wait_while_the_budget_is_short_and_sign_out_forgets(self):
  for _ in range(psn_link.MOST-pt.ROOM+1):self.psn.budget.spend()
  try:self.psn.poll()
  except psn_link.Busy:pass
  self.assertEqual(self.sony.trophy_calls(),[]);self.assertIsNone(self.book.view()['summary'])
  self.clock.now+=psn_link.WINDOW+1;self.poll();self.assertIsNotNone(self.book.view()['summary'])
  self.psn.forget();self.assertEqual(self.book.view()['titles'],[]);self.assertFalse((self.folder/'psn'/'trophies').exists())

if __name__=='__main__':unittest.main()
