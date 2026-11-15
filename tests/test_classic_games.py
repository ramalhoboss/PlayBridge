"""The 1.5.x Games page inside the Qt window: it draws the whole page at the screen's pixels, and a click lands on what the page shows there."""
import json,sys,tempfile,time,unittest
from pathlib import Path
APP=Path(__file__).resolve().parents[1]/'app'
sys.path.insert(0,str(APP))
try:
 import PySide6  # noqa: F401
 from PySide6.QtCore import QCoreApplication
 from PySide6.QtGui import QGuiApplication
 import classic_games,scene
 from console_control import ConsoleLink
 from qt_models import Shelf
except ImportError:classic_games=None

GAMES=[dict(title=f'PPSA0000{index}',name=name,played=0,seconds=3600*index,installed=0,size=10**9) for index,name in enumerate(('First game','Second game','Third game'),1)]

@unittest.skipIf(classic_games is None,'PySide6 is not installed')
class ClassicGamesTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.gui=QGuiApplication.instance() or QGuiApplication(['test'])
 def setUp(self):
  self.folder=tempfile.TemporaryDirectory();Path(self.folder.name,'games.json').write_text(json.dumps(GAMES),encoding='utf8')
  self.link=ConsoleLink(self.folder.name);self.state=Shelf(self.link,{});self.state.sync('',None,'Waiting for your PS5…')
  self.view=classic_games.ClassicShelf(self.state,self.link,animations=lambda:False)
  self.view.show(True);self.view.resize(770,460,2.0);self.view.arrange();self.settle()
 def tearDown(self):
  self.view.show(False);self.folder.cleanup()
 def settle(self,seconds=8):
  """Lets the drawing thread finish and the page take what it drew."""
  end=time.monotonic()+seconds
  while time.monotonic()<end:
   QCoreApplication.processEvents();self.view.painted=True;self.view.step()
   with self.view.lock:done=all(job[0] in self.view.ready for job in self.view.wanted)
   if done and self.view.under is not None and not self.view.stale:return
   time.sleep(.01)
 def test_page_is_drawn_at_the_screens_pixels(self):
  self.assertEqual((self.view.surface.width(),self.view.surface.height()),(1540,920))
  self.assertEqual(self.view.under.size,(1540,920))
  self.assertEqual((self.view.layout.width,self.view.layout.height),(1540,920))
 def test_clicks_find_what_the_page_shows(self):
  layout=self.view.layout;r=2.0
  # The big button says Connect while there is no console, and a click on it is the action.
  self.assertEqual(self.view.released((layout.margin+10)/r,(layout.pill_y+layout.pill/2)/r),('action',0))
  self.assertEqual(self.view.released((layout.option_x+layout.pill/2)/r,(layout.pill_y+layout.pill/2)/r),('more',0))
  cx,cy,side,_=scene.tile_pose(1,layout);self.assertEqual(self.view.released(cx/r,cy/r),('tile',1))
  x0,y0,x1,y1=self.view.top_hits['search'];self.assertEqual(self.view.released((x0+x1)/2/r,(y0+y1)/2/r),('top','search'))
 def test_menu_takes_the_clicks_while_open(self):
  self.state.open_menu('more');self.view.refresh();self.settle()
  x0,y0,x1,y1=self.view.menu_box;top,bottom=self.view.menu_rows[1]
  self.assertEqual(self.view.released((x0+x1)/2/2,(y0+(top+bottom)/2)/2),('menu',1))
  self.assertEqual(self.view.released(5,5),('away',0))
  # The pointer chooses the row under it, as in 1.5.x.
  self.view.pointer_at((x0+x1)/2/2,(y0+(top+bottom)/2)/2);self.assertEqual(self.state.menu['selected'],1)
 def test_a_new_focus_moves_the_row(self):
  self.state.move(1);self.view.refresh();self.settle()
  self.assertEqual(self.view.position,1.0)
  self.assertEqual(self.view.words_key[3],'Second game')
 def test_hidden_page_stops_and_closes_its_menu(self):
  self.state.open_menu('more');self.view.refresh();self.view.show(False)
  self.assertIsNone(self.state.menu);self.assertFalse(self.view.timer.isActive())
 def test_the_link_reads_what_is_missing_only_while_the_page_shows(self):
  self.assertTrue(self.link.browsing);self.view.show(False);self.assertFalse(self.link.browsing)
 def trophies(self):
  book=self.link.trophy_book;book['user']='1a2b3c4d';book['games']['PPSA00001']='NPWR12345_00'
  book['sets']['NPWR12345_00']=dict(key='k',name='First Game Trophies',trophies=[dict(id=n,grade=grade,hidden=n==2,name=f'Trophy {n}',detail='Do it') for n,grade in enumerate(('gold','silver','bronze'))])
  book['earned']['1a2b3c4d']={'NPWR12345_00':{1:1700000000}};self.link.revision+=1;self.state.sync('',None,'Waiting for your PS5…');self.view.refresh();self.settle()
 def test_the_trophies_card_follows_the_four(self):
  self.trophies();key=self.view.page_key
  self.assertIn(('Trophies','1 / 3','22% complete'),key);self.assertLessEqual(self.view.layout.extra[2],self.view.layout.width)
  # The card changes only its own place on the page.
  from PIL import ImageChops
  layout=self.view.layout;words=(layout,'Game','Line',(('Your time','1 h','x'),('On your PS5','1 GB','y')))
  changed=ImageChops.difference(scene.library_page(None,None,*words),scene.library_page(None,None,*words,('Trophies','1 / 3','22% complete'))).getbbox()
  x0,y0,x1,y1=layout.extra;self.assertTrue(changed and x0-2<=changed[0] and changed[2]<=x1+2 and y0-2<=changed[1] and changed[3]<=y1+2,changed)
 def test_the_page_is_clear_where_the_art_shows(self):
  from PySide6.QtGui import QImage
  self.assertEqual(self.view.surface.format(),QImage.Format.Format_ARGB32_Premultiplied);self.assertEqual(self.view.under.mode,'RGBA')
  # The middle of the right half has only the scrim over the art: much of the art shows.
  self.assertLess(self.view.under.getpixel((1200,420))[3],200)
 def test_the_art_comes_with_its_page_and_a_new_game_brings_its_own(self):
  # A little larger than the page, in whole units of the window (the screen's ratio here is 2).
  layout=self.view.layout;size=self.view.scenery_job(self.view.focused())[0][1]
  self.assertTrue(layout.width*scene.SCENERY_ROOM<=size[0]<=layout.width*scene.SCENERY_ROOM+16 and size[0]%2==0 and size[1]%2==0,size)
  self.assertEqual(self.view.front,0);entry=self.view.scenery[0];self.assertEqual((entry[1].width(),entry[1].height()),size)
  self.assertEqual((entry[2].width(),entry[2].height()),(-(-size[0]//4),-(-size[1]//4)))
  # The second game has art of its own; the first has none.
  from PIL import Image
  self.link.arts.mkdir(parents=True,exist_ok=True);Image.new('RGB',(320,180),(90,120,200)).save(self.link.arts/'PPSA00002.jpg');self.link.revision+=1
  self.state.move(1);self.view.refresh();self.view.moved_at=0;self.settle()
  self.assertEqual(self.view.front,1);self.assertEqual(self.view.page_key[2],'Second game');self.assertEqual(self.view.scenery_key,self.view.scenery_job(self.view.focused())[0])
 def test_the_art_items_take_their_slot(self):
  classic_games.ClassicArt.view=self.view
  try:
   art=classic_games.ClassicArt();art.setProperty('slot',0);frost=classic_games.ClassicArt();frost.setProperty('role','frost');other=classic_games.ClassicArt();other.setProperty('slot',1)
   picture=self.view.scenery[0][1]
   # Drawn pixel for pixel at the screen's ratio of 2, the frost four times larger.
   self.assertEqual((art.implicitWidth(),art.implicitHeight()),(picture.width()/2,picture.height()/2));self.assertGreaterEqual(frost.implicitWidth(),art.implicitWidth())
   self.assertTrue(art.property('shown'));self.assertTrue(frost.property('shown'));self.assertFalse(other.property('shown'))
  finally:classic_games.ClassicArt.view=None
 def test_textures_come_out_at_the_pictures_pixels(self):
  # Qt makes a texture round(textureSize × the screen's scale) pixels wide.
  for ratio in (1.0,1.25,1.5,1.75,2.0,2.25):
   for width in range(400,1800,13):
    pixels=classic_games.qt_round(width*ratio);self.assertEqual(classic_games.qt_round(classic_games.texture_units(pixels,ratio)*ratio),pixels,(ratio,width))
  self.assertEqual(classic_games.whole_units(1233,1.25),1236);self.assertEqual(classic_games.whole_units(1233,1.0),1233)
 def test_the_window_learns_where_the_glass_is(self):
  frame=classic_games.ClassicFrame();self.view.frame=frame;self.view.stale=True;self.settle()
  glass=frame.property('glass');self.assertEqual(len(glass),4)
  x0,y0,x1,y1=self.view.layout.cards[0];self.assertEqual((glass[0]['x'],glass[0]['w']),(x0/2,(x1-x0)/2))
  self.trophies();self.state.open_menu('more');self.state.menu_choose([key for key,_ in self.state.menu['items']].index('trophies'));self.view.refresh();self.settle()
  self.assertEqual(len(frame.property('glass')),6)
 def test_the_trophy_list_lies_over_the_page_and_takes_clicks(self):
  self.trophies();self.state.open_menu('more');self.state.menu_choose([key for key,_ in self.state.menu['items']].index('trophies'));self.view.refresh();self.settle()
  self.assertIsNotNone(self.view.panel_box);fit,top,row=scene.trophy_fit(self.view.layout);x0,y0,x1,y1=self.view.panel_box
  self.assertEqual(self.view.released((x0+x1)/2/2,(top+row*1.5)/2),('panel',1));self.assertEqual(self.view.released(5,5),('away',0))
  self.state.navigate('down');self.view.refresh();self.settle();self.assertEqual(self.state.panel['selected'],1)
  self.state.dismiss();self.view.refresh();self.settle();self.assertIsNone(self.view.panel_box)

if __name__=='__main__':unittest.main()
