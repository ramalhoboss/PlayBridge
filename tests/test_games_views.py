"""The Games page in its grid and its list, inside the Qt window's drawing: the page lays itself out again for a new view, a click lands on the
game under it, the View menu opens under its button and changes the view, and the shelf moves by the grid's columns."""
import json,sys,tempfile,time,unittest
from pathlib import Path
APP=Path(__file__).resolve().parents[1]/'app'
sys.path.insert(0,str(APP))
try:
 import PySide6  # noqa: F401
 from PySide6.QtCore import QCoreApplication
 from PySide6.QtGui import QGuiApplication
 import classic_games,library_view
 from console_control import ConsoleLink
 from qt_models import Shelf
except ImportError:classic_games=None

GAMES=[dict(title=f'PPSA{index:05d}',name=f'Game number {index}',played=0,seconds=3600*index,installed=0,size=10**9) for index in range(1,31)]

@unittest.skipIf(classic_games is None,'PySide6 is not installed')
class GamesViewsTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.gui=QGuiApplication.instance() or QGuiApplication(['test'])
 def setUp(self):
  self.folder=tempfile.TemporaryDirectory();Path(self.folder.name,'games.json').write_text(json.dumps(GAMES),encoding='utf8')
  self.link=ConsoleLink(self.folder.name);self.changed=[]
  self.state=Shelf(self.link,{'view_changed':lambda:(self.changed.append(self.state.options.key()),self.view.relayout())});self.state.sync('',None,'Waiting for your PS5…')
  self.view=classic_games.ClassicShelf(self.state,self.link,animations=lambda:False)
  self.view.show(True);self.view.resize(800,450,2.0);self.view.arrange();self.settle()
 def tearDown(self):
  self.view.show(False);self.folder.cleanup()
 def settle(self,seconds=10):
  end=time.monotonic()+seconds
  while time.monotonic()<end:
   QCoreApplication.processEvents();self.view.painted=True;self.view.step()
   with self.view.lock:done=all(job[0] in self.view.ready for job in self.view.wanted)
   if done and self.view.under is not None and not self.view.stale:return
   time.sleep(.01)
 def use(self,view):
  self.state.options.view=view;self.view.relayout();self.view.refresh();self.settle()
 def test_grid_lays_out_again_and_the_shelf_moves_by_its_columns(self):
  self.use('grid');layout=self.view.layout
  self.assertEqual(layout.view,'grid');self.assertEqual(self.state.columns,layout.columns);self.assertGreater(layout.columns,3)
  self.state.navigate('down');self.assertEqual(self.state.target,layout.columns)
  self.state.navigate('right');self.assertEqual(self.state.target,layout.columns+1)
  self.state.wheel(-1);self.assertEqual(self.state.target,1)
 def test_a_click_lands_on_the_game_under_it(self):
  for view in ('grid','list'):
   self.use(view);layout=self.view.layout;x,y=library_view.cell(layout,2,self.view.scroll)
   self.assertEqual(self.view.released(x/2,y/2),('tile',2))
   self.assertEqual(self.view.released((layout.pill_x+10)/2,(layout.pill_y+layout.pill/2)/2),('action',0))
 def test_focus_far_down_scrolls_the_sheet_into_sight(self):
  self.use('list');self.state.go_to(29);self.view.refresh();self.settle()
  layout=self.view.layout;self.assertEqual(self.view.scroll,29-layout.rows_shown+1);self.assertEqual(self.view.spot[1],29.0)
  x,y=library_view.cell(layout,29,self.view.scroll);self.assertEqual(self.view.released(x/2,y/2),('tile',29))
 def test_view_menu_opens_under_its_button_and_changes_the_view(self):
  x0,y0,x1,y1=self.view.top_hits['view'];self.assertEqual(self.view.released((x0+x1)/4,(y0+y1)/4),('top','view'))
  self.state.open_menu('view');self.view.refresh();self.settle()
  box=self.view.menu_box;self.assertLessEqual(abs(box[2]-x1),1);self.assertGreater(box[1],y1)
  self.state.menu_choose(2);self.settle()
  self.assertEqual(self.state.options.view,'list');self.assertIsNone(self.state.menu);self.assertEqual(self.view.layout.view,'list');self.assertEqual(self.changed[-1][0],'list')
  self.state.open_menu('view');size=[item[0] for item in self.state.menu['items']].index('size');self.state.menu_choose(size)
  self.assertEqual(self.state.options.size,'large');self.assertEqual(self.state.menu['kind'],'view');self.assertEqual(self.state.menu['selected'],size)
 def test_trophy_list_and_menus_cover_the_sheet(self):
  self.use('grid');self.state.open_menu('more');self.view.refresh();self.settle()
  layout=self.view.layout;box=self.view.menu_box;self.assertGreater(box[1],layout.pill_y);self.assertLessEqual(abs(box[2]-(layout.option_x+layout.pill)),1)
  self.assertIn('view_menu',[item[0] for item in self.state.menu['items']])

if __name__=='__main__':unittest.main()
