import os,sys,tempfile,time,types,unittest
from pathlib import Path
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from qt_models import Shelf,capture_card,controller_text,file_url,game_kind,library_info

GAMES=[{'title':'PPSA00001','name':'Zeta','played':300,'seconds':60},{'title':'CUSA00002','name':'alpha','played':200,'seconds':7200},{'title':'CUSA00003','name':'Beta Zone','played':100,'seconds':None}]
class Link:
 def __init__(self,games=GAMES,online=True):self.games=list(games);self.online=online;self.revision=1;self.focus='';self.refreshed=0;self.refreshing=False;self.browsing=False
 def refresh(self):self.refreshed+=1
 def icon(self,title):return None
 def art(self,title):return None
class Clock:
 def __init__(self):self.now=100.0
 def __call__(self):return self.now

def shelf(**link):
 sounds=[];ran=[];clock=Clock()
 actions={name:(lambda *values,name=name:ran.append((name,)+values)) for name in ('connect','open','close','live')}
 page=Shelf(Link(**link),actions,sounds.append,clock);page.sync('',None,'')
 return page,sounds,ran,clock

class FileTests(unittest.TestCase):
 def test_no_file_is_no_picture(self):
  self.assertEqual(file_url(None),'');self.assertEqual(file_url(''),'');self.assertEqual(file_url(Path('nowhere','missing.png')),'')
 def test_a_replaced_file_gets_a_new_address(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'icon0.png';path.write_bytes(b'one');os.utime(path,ns=(1_000_000_000,1_000_000_000))
   first=file_url(path);self.assertTrue(first.startswith('file:///'));self.assertIn('?v=',first)
   path.write_bytes(b'two');os.utime(path,ns=(2_000_000_000,2_000_000_000))
   self.assertNotEqual(file_url(path),first);self.assertEqual(file_url(path).split('?')[0],first.split('?')[0])
 def test_what_kind_of_title(self):
  self.assertEqual(game_kind('PPSA01234'),'PS5 game');self.assertEqual(game_kind('CUSA01234'),'PS4 game');self.assertEqual(game_kind('BREW00001'),'App')

class ShelfTests(unittest.TestCase):
 def test_the_shelf_reads_the_games_only_when_the_console_changed_them(self):
  page,_,_,_=shelf();self.assertEqual(len(page.games),3);self.assertFalse(page.sync('',None,''))
  page.link.revision=2;page.link.games=GAMES[:2];self.assertTrue(page.sync('',None,''));self.assertEqual(len(page.tiles()),2)
 def test_the_focused_game_stays_in_focus_when_the_list_changes(self):
  page,_,_,_=shelf();page.go_to(2);page.link.revision=2;page.link.games=[GAMES[2],GAMES[0]];page.sync('',None,'')
  self.assertEqual(page.focused()['title'],'CUSA00003');self.assertEqual(page.link.focus,'CUSA00003')
 def test_moving_past_the_end_only_bumps(self):
  page,sounds,_,_=shelf();page.move(-1);self.assertEqual(page.target,0);self.assertEqual(sounds[-1],'edge')
  page.move(1);self.assertEqual(page.target,1);self.assertEqual(sounds[-1],'move');page.move(5);self.assertEqual(page.target,2)
 def test_music_waits_until_the_row_is_still(self):
  page,_,_,clock=shelf();page.move(1);self.assertIsNone(page.settled())
  clock.now+=0.5;page.move(1);clock.now+=0.5;self.assertIsNone(page.settled())
  clock.now+=0.5;self.assertEqual(page.settled(),'CUSA00003');self.assertIsNone(page.settled())
 def test_the_big_button_says_what_happens(self):
  page,_,_,_=shelf();self.assertEqual(page.action_text(),'Play')
  page.sync('PPSA00001',None,'');self.assertEqual(page.action_text(),'Resume')
  page.sync('',  'PPSA00001','');self.assertEqual(page.action_text(),'Starting')
  page.link.online=False;page.sync('',None,'');self.assertEqual(page.action_text(),'Connect')
  page.info={'state':'connecting'};self.assertEqual(page.action_text(),'Connecting')
 def test_choosing_opens_the_game_or_connects(self):
  page,sounds,ran,_=shelf();page.move(1);page.choose();self.assertEqual(ran[-1],('open','CUSA00002'));self.assertEqual(sounds[-1],'accept')
  page.link.online=False;page.choose();self.assertEqual(ran[-1],('connect',))
  page.info={'state':'connecting'};page.choose();self.assertEqual(len(ran),2);self.assertEqual(sounds[-1],'edge')
 def test_up_and_down_change_the_shelf(self):
  page,_,_,_=shelf();page.navigate('down');self.assertNotEqual(page.shelf,'all');page.navigate('up');self.assertEqual(page.shelf,'all')
  self.assertFalse(page.navigate('nothing'))
 def test_the_menu_takes_the_arrows_while_it_is_open(self):
  page,_,ran,_=shelf();page.sync('PPSA00001',None,'');page.open_menu('more')
  self.assertEqual([key for key,_ in page.menu['items']],['close','refresh','live'])
  page.navigate('up');self.assertEqual(page.menu['selected'],2);page.navigate('down');page.navigate('down')
  page.navigate('accept');self.assertIsNone(page.menu);self.assertEqual(page.link.refreshed,1)
  page.open_menu('more');page.menu_choose(0);self.assertEqual(ran[-1],('close',))
 def test_no_close_in_the_menu_without_an_open_game(self):
  page,_,_,_=shelf();page.open_menu('more');self.assertNotIn('close',[key for key,_ in page.menu['items']])
 def test_typing_searches_and_back_clears_the_menu_first(self):
  page,_,_,_=shelf();page.type_text('ze');self.assertEqual([game['name'] for game in page.games],['Zeta']);self.assertTrue(page.searching)
  page.erase();page.erase();self.assertEqual(len(page.games),3)
  page.type_text('\x07');self.assertEqual(page.text,'');page.type_text('a'*60);self.assertEqual(len(page.text),40)
  page.open_menu('more');self.assertTrue(page.dismiss());self.assertIsNone(page.menu);self.assertEqual(len(page.text),40)
  self.assertTrue(page.dismiss());self.assertEqual(page.text,'');self.assertFalse(page.dismiss())
 def test_the_view_has_what_the_page_draws(self):
  page,_,_,_=shelf();view=page.view()
  for key in ('shelf','shelfName','shelves','text','searching','focus','count','title','name','line','kind','cards','action','status','notice','menu','more'):self.assertIn(key,view)
  self.assertEqual(view['name'],'Zeta');self.assertEqual(view['kind'],'PS5 game');self.assertEqual(view['count'],3);self.assertTrue(all(set(card)=={'title','value','note'} for card in view['cards']))
  page.type_text('nothing here');view=page.view();self.assertEqual(view['name'],'Your games');self.assertFalse(view['more']);self.assertEqual(view['title'],'')

class LineTests(unittest.TestCase):
 def test_the_top_bar_state(self):
  health={'decoded_width':1920,'decoded_height':1080,'received_mbps':41.6}
  info=library_info('PS5',True,True,True,health,59.7,'Wireless Controller',{'cpu_c':61,'soc_c':0})
  self.assertEqual((info['state'],info['fps'],info['picture'],info['bitrate'],info['cpu'],info['soc'],info['pad']),('online',60,'1920×1080','42 Mbps',61,None,True))
  info=library_info('',False,True,False,health,None,'',{});self.assertEqual((info['name'],info['state'],info['fps'],info['picture'],info['bitrate']),('PS5','connecting',None,'',''))
  self.assertEqual(library_info('PS5',False,False,False,{},None,'',{})['state'],'offline')
 def test_the_controller_line_only_speaks_when_something_is_wrong(self):
  pad=types.SimpleNamespace(name='',answer=(0,0),link=lambda now:'ready');self.assertIn('No controller',controller_text(pad,0))
  pad.name='Pad';self.assertEqual(controller_text(pad,0),'')
  pad.link=lambda now:'failed';pad.answer=(0,0x8063000a-2**32);self.assertEqual(controller_text(pad,0),'  ·  Controller could not start (8063000a)')
  pad.link=lambda now:'starting';self.assertIn('starting',controller_text(pad,0))
 def test_a_capture_card(self):
  item=types.SimpleNamespace(kind='Photos',path=Path('shot.jpeg'),modified=time.mktime((2026,11,10,23,49,0,0,0,-1)),size=2_200_000)
  card=capture_card(item);self.assertEqual((card['kind'],card['action'],card['when']),('photo','Open photo','10 Nov 2026 · 23:49'));self.assertTrue(card['detail'].startswith('JPG'))
  item.kind='Videos';item.path=Path('clip.mp4');card=capture_card(item);self.assertEqual((card['kind'],card['action']),('video','Play recording'));self.assertTrue(card['detail'].startswith('MP4'))

if __name__=='__main__':unittest.main()
