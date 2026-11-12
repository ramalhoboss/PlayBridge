import os,sys,tkinter as tk,types,unittest
from pathlib import Path
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from game_mode import GameShelf,PopMenu,SHELVES,TopStrip,ago_text,empty_line,game_cards,game_line,load_icon,load_picture,power_items,shelf_games,size_text,status_text,time_text,total_cards

GAMES=[{'title':'PPSA00001','name':'Zeta','played':300,'seconds':60},{'title':'CUSA00002','name':'alpha','played':200,'seconds':7200},{'title':'CUSA00003','name':'Beta Zone','played':100,'seconds':None}]
def names(*args):return [game['name'] for game in shelf_games(GAMES,*args)]
class Link:
 def __init__(self,games=(),online=False,refreshing=False):self.games=games;self.online=online;self.refreshing=refreshing;self.browsing=False;self.focus=''

class ShelfTests(unittest.TestCase):
 def test_the_first_shelf_keeps_the_console_order(self):self.assertEqual(names(),['Zeta','alpha','Beta Zone'])
 def test_most_played_and_by_name_ignore_case_and_missing_time(self):
  self.assertEqual(names('played'),['alpha','Zeta','Beta Zone']);self.assertEqual(names('name'),['alpha','Beta Zone','Zeta'])
 def test_a_shelf_for_each_console(self):
  self.assertEqual(names('ps5'),['Zeta']);self.assertEqual(names('ps4'),['alpha','Beta Zone'])
 def test_search_works_inside_a_shelf_and_ignores_case(self):
  self.assertEqual(names('all','ZE'),['Zeta']);self.assertEqual(names('ps4','z'),['Beta Zone']);self.assertEqual(names('ps5','nothing'),[])
 def test_every_shelf_has_a_name_and_works(self):
  for key,label in SHELVES:self.assertTrue(label);self.assertIsInstance(shelf_games(GAMES,key),list)
 def test_the_line_under_a_name_says_what_is_happening(self):
  self.assertEqual(game_line(GAMES[0],waiting='PPSA00001'),'Starting on your PS5');self.assertEqual(game_line(GAMES[0],running='PPSA00001'),'Open on your PS5')
  self.assertEqual(game_line(GAMES[1],now=200+3*86400),'Played 3 days ago  ·  2 h played');self.assertEqual(game_line(GAMES[2]),'Not played on this console yet');self.assertEqual(game_line({'title':'PPSA00004','seconds':1800,'played':0}),'30 min played')
 def test_an_empty_shelf_says_why(self):
  self.assertIn('Connect',empty_line(Link(),''));self.assertIn('Reading',empty_line(Link(online=True,refreshing=True),''));self.assertIn('No games were found',empty_line(Link(online=True),''));self.assertIn('matches',empty_line(Link(GAMES),'x'));self.assertIn('shelf',empty_line(Link(GAMES),''))
 def test_how_long_ago_in_words(self):
  day=86400;self.assertEqual(ago_text(0,3600),'today');self.assertEqual(ago_text(0,day),'yesterday');self.assertEqual(ago_text(0,7*day),'7 days ago');self.assertEqual(ago_text(0,90*day),'3 months ago');self.assertEqual(ago_text(0,800*day),'2 years ago')
 def test_play_time_as_it_is_said(self):
  self.assertEqual(time_text(30),'1 min');self.assertEqual(time_text(1500),'25 min');self.assertEqual(time_text(3600),'1 h');self.assertEqual(time_text(3*3600+1800),'3½ h');self.assertEqual(time_text(21*3600),'21 h');self.assertEqual(time_text(1234*3600+1800),'1,234 h')
 def test_sizes_only_when_the_console_gave_one(self):
  self.assertEqual(size_text(11179851776),'11.2 GB');self.assertEqual(size_text(150*10**9),'150 GB');self.assertEqual(size_text(0),'—');self.assertEqual(size_text(None),'—');self.assertEqual(size_text('big'),'—')
 def test_the_cards_say_only_what_the_console_keeps(self):
  time_card,place=game_cards({'title':'CUSA00002','name':'alpha','played':200,'seconds':7200,'size':5*10**9,'installed':0});self.assertEqual(time_card[:2],('Your time','2 h'));self.assertIn('Last played',time_card[2]);self.assertEqual(place,('On your PS5','5.0 GB','PS4 game'))
  time_card,place=game_cards({'title':'PPSA00001','name':'x','played':0,'seconds':None});self.assertEqual(time_card[1],'Not played');self.assertEqual(place[1:],('—','PS5 game'))
  time_card,place=total_cards(GAMES);self.assertEqual(time_card[1:],('2 h','Across 3 games'));self.assertEqual(place[1],'3 games')
 def test_a_missing_or_broken_icon_is_no_icon(self):
  self.assertIsNone(load_icon(None,64));self.assertIsNone(load_icon(Path(__file__),64));self.assertIsNone(load_icon(Path('nowhere.png'),64))
  self.assertIsNone(load_picture(None,(64,64)));self.assertIsNone(load_picture(Path(__file__),(64,64)))
 def test_tk_has_nothing_to_paint_over_the_page(self):
  try:root=tk.Tk()
  except tk.TclError:self.skipTest('no display')
  try:
   shelf=GameShelf(root,Link(),{});self.assertEqual(shelf.cget('background'),'');shelf.configure(cursor='hand2')
   # The grid never places a widget that asks for no room.
   self.assertGreater(shelf.winfo_reqwidth(),1);self.assertGreater(shelf.winfo_reqheight(),1)
  finally:root.destroy()
 def test_every_tile_in_view_is_drawn_before_any_page(self):
  try:root=tk.Tk()
  except tk.TclError:self.skipTest('no display')
  try:
   import scene
   many=[{'title':f'PPSA{n:05d}','name':f'Game {n}','played':n,'seconds':60} for n in range(1,61)]
   link=Link(many);link.icon=lambda title:None;link.art=lambda title:None;link.game_name=lambda title:title;link.revision=0
   layout=scene.page_layout(1920,1080);across=(layout.width-layout.margin)//(layout.small+layout.gap)+3
   shelf=GameShelf(root,link,{});shelf.games=list(many);shelf.layout=layout;shelf.shown=True;shelf.target=20;shelf.position=20.0;shelf.plan()
   kinds=[job[0][0] for job in shelf.wanted];first={job[0][2] for job in shelf.wanted[:shelf.near] if job[0][0]=='tile'}
   self.assertNotIn('page',kinds[:shelf.near])
   self.assertLessEqual({many[index]['title'] for index in shelf.visible() if index!=shelf.target},first)
   # Once still, the next screen of tiles is drawn too, after the pages.
   self.assertLessEqual({many[index]['title'] for index in range(21,min(60,21+2*across))},{job[0][2] for job in shelf.wanted if job[0][0]=='tile'})
  finally:root.destroy()
 def test_an_icon_replaced_under_the_same_name_is_drawn_again(self):
  try:root=tk.Tk()
  except tk.TclError:self.skipTest('no display')
  try:
   import tempfile,scene
   from PIL import Image
   with tempfile.TemporaryDirectory() as tmp:
    icon=Path(tmp)/'PPSA00001.png';art=Path(tmp)/'PPSA00001.jpg';Image.new('RGB',(64,64),(200,0,0)).save(icon);Image.new('RGB',(64,36),(0,0,200)).save(art)
    link=Link(GAMES);link.icon=lambda title:icon if title=='PPSA00001' else None;link.art=lambda title:art if title=='PPSA00001' else None;link.game_name=lambda title:title;link.revision=0
    shelf=GameShelf(root,link,{});shelf.games=list(GAMES);shelf.layout=scene.page_layout(1920,1080);shelf.revision=0
    tile,faces,page=shelf.tile_job(GAMES[0])[0],shelf.faces_job(GAMES[0],shelf.layout.focus)[0],shelf.page_job(GAMES[0])[0]
    # The console sends a new icon and new art. The link counts a change, and the page asks the files again.
    later=icon.stat().st_mtime_ns+10**9;os.utime(icon,ns=(later,later));os.utime(art,ns=(later,later));link.revision=1;shelf.sync('',None,'')
    self.assertNotEqual(shelf.tile_job(GAMES[0])[0],tile);self.assertNotEqual(shelf.faces_job(GAMES[0],shelf.layout.focus)[0],faces);self.assertNotEqual(shelf.page_job(GAMES[0])[0],page)
    # Until then, nothing is asked of the disk again.
    self.assertEqual(shelf.tile_job(GAMES[0])[0],shelf.tile_job(GAMES[0])[0])
  finally:root.destroy()
 def test_the_big_button_says_what_it_will_do(self):
  try:root=tk.Tk()
  except tk.TclError:self.skipTest('no display')
  try:
   link=Link(GAMES);shelf=GameShelf(root,link,{});shelf.games=list(GAMES);self.assertEqual(shelf.action_text(),'Connect')
   shelf.info={'state':'connecting'};self.assertEqual(shelf.action_text(),'Connecting')
   link.online=True;self.assertEqual(shelf.action_text(),'Play');shelf.running='PPSA00001';self.assertEqual(shelf.action_text(),'Resume');shelf.running='';shelf.waiting='PPSA00001';self.assertEqual(shelf.action_text(),'Starting')
   shelf.games=[];shelf.waiting=None;self.assertEqual(shelf.action_text(),'')
  finally:root.destroy()
 def test_a_menu_answers_the_keys_and_runs_what_is_chosen(self):
  try:root=tk.Tk()
  except tk.TclError:self.skipTest('no display')
  try:
   ran=[];link=Link(GAMES,online=True);shelf=GameShelf(root,link,dict(rest=lambda:ran.append('rest'),off=lambda:ran.append('off')))
   shelf.open_menu('power');self.assertEqual([key for key,_ in shelf.menu['items']],['rest','reboot','off','recovery']);self.assertTrue(shelf.navigate('down'));self.assertTrue(shelf.navigate('down'));self.assertTrue(shelf.navigate('left'));self.assertEqual(shelf.menu['selected'],2);self.assertTrue(shelf.navigate('accept'));self.assertEqual(ran,['off']);self.assertIsNone(shelf.menu)
   shelf.open_menu('more');self.assertTrue(shelf.dismiss());self.assertFalse(shelf.dismiss())
   # Nothing to turn off without a console.
   link.online=False;shelf.open_menu('power');self.assertIsNone(shelf.menu);self.assertIn('Connect',shelf.notice)
  finally:root.destroy()
 def test_the_power_list_offers_a_soft_reset_only_with_a_game_open(self):
  self.assertEqual([key for key,_ in power_items(True,'')],['rest','reboot','off','recovery'])
  self.assertEqual(power_items(True,'PPSA00001')[0][0],'soft_reset')
 def test_without_a_console_the_power_list_holds_only_the_way_out_of_gaming_mode(self):
  self.assertEqual(power_items(False,''),[]);self.assertEqual(power_items(False,'','Exit Gaming Mode'),[('exit','Exit Gaming Mode')])
 def test_the_top_bar_says_how_the_console_is(self):
  self.assertEqual(status_text({}),'Not connected');self.assertEqual(status_text({'name':'Box','state':'connecting'}),'Connecting to Box');self.assertEqual(status_text({'state':'online'}),'PS5  ·  Online')
 def test_the_small_menu_moves_runs_what_is_chosen_and_goes_away(self):
  try:root=tk.Tk()
  except tk.TclError:self.skipTest('no display')
  try:
   ran=[];menu=PopMenu(root,(('rest','Rest mode'),('off','Turn off PS5')),400,200,1,ran.append);self.assertIs(PopMenu.current,menu)
   menu.answer('down');self.assertEqual(menu.selected,1);menu.answer('down');self.assertEqual(menu.selected,0);menu.answer('up');menu.answer('accept');self.assertEqual(ran,['off']);self.assertIsNone(PopMenu.current)
   PopMenu(root,(('rest','Rest mode'),),400,200,1,ran.append).answer('back');self.assertEqual(ran,['off']);self.assertIsNone(PopMenu.current)
  finally:root.destroy()
 def test_the_top_strip_draws_only_when_something_in_it_changed_and_reports_clicks(self):
  try:root=tk.Tk()
  except tk.TclError:self.skipTest('no display')
  try:
   root.geometry('1200x800');pressed=[];strip=TopStrip(root,pressed.append);strip.pack(fill='x');root.update()
   strip.show(tab='live',status='Not connected',clock='10:00');first=strip.picture;self.assertIsNotNone(first);strip.show(tab='live',status='Not connected',clock='10:00');self.assertIs(strip.picture,first)
   strip.show(tab='media',status='Not connected',clock='10:00');self.assertIsNot(strip.picture,first)
   x0,y0,x1,y1=strip.hits['power'];strip.released(types.SimpleNamespace(x=(x0+x1)//2,y=(y0+y1)//2));self.assertEqual(pressed,['power']);strip.released(types.SimpleNamespace(x=2,y=2));self.assertEqual(pressed,['power'])
  finally:root.destroy()
if __name__=='__main__':unittest.main()
