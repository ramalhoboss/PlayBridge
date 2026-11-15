"""The Games page's views: the choice as the settings keep it, the View menu, where the grid and the list put everything, and how the arrows,
the wheel and the controller move in each."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import library_view as lv
import scene

class ChoiceTests(unittest.TestCase):
 def test_saved_choice_comes_back_and_odd_values_fall_back(self):
  choice=lv.ViewChoice('grid','large',False,False);self.assertEqual(lv.ViewChoice.from_saved(choice.saved()).key(),('grid','large',False,False))
  self.assertEqual(lv.ViewChoice.from_saved({'games_view':'cards','tile_size':'huge'}).key(),('row','medium',True,True))
  choice.next_size();self.assertEqual(choice.size,'small')
 def test_view_menu_marks_the_view_and_offers_what_goes_with_it(self):
  grid=lv.menu_items(lv.ViewChoice('grid'),'All games')
  self.assertEqual([item[0] for item in grid],['view:row','view:grid','view:list','shelf','size','names','badges'])
  self.assertEqual([item[2] for item in grid[:3]],[False,True,False]);self.assertEqual(grid[3][2],'All games');self.assertEqual(grid[4][1:],('Tile size','Medium'))
  self.assertEqual([item[0] for item in lv.menu_items(lv.ViewChoice('list','small'),'A to Z')][3:],['shelf','size'])
  self.assertEqual(lv.menu_items(lv.ViewChoice('list','small'),'A to Z')[4][1:],('Row size','Small'))
  self.assertNotIn('names',[item[0] for item in lv.menu_items(lv.ViewChoice('row'),'All games')])
 def test_menu_draws_ticks_and_values(self):
  picture,rows=scene.drop_menu(lv.menu_items(lv.ViewChoice('grid'),'Most played'),2,1.0)
  self.assertEqual(len(rows),7);plain,_=scene.drop_menu([('a','Row'),('b','Grid')],0,1.0);self.assertGreater(picture.width,plain.width)

class LayoutTests(unittest.TestCase):
 def setUp(self):self.base=scene.page_layout(1600,900)
 def test_the_row_keeps_the_consoles_layout(self):
  page=lv.arranged(self.base,lv.ViewChoice('row'));self.assertEqual(page.view,'row');self.assertEqual((page.row_y,page.pill_x,page.band_y),(self.base.row_y,self.base.margin,self.base.band_y))
  self.assertGreater(scene.page_layout(1600,900,lv.ROW_SCALE['large']).small,self.base.small)
 def test_grid_fills_the_sheet_and_every_cell_stays_on_it(self):
  for size in ('small','medium','large'):
   page=lv.arranged(self.base,lv.ViewChoice('grid',size));x0,y0,x1,y1=page.inner
   self.assertGreaterEqual(page.columns,4);self.assertGreaterEqual(page.rows_shown,2)
   first=lv.cell(page,0,0);last=lv.cell(page,page.columns-1,0)
   self.assertGreaterEqual(first[0]-page.side/2,x0-1);self.assertLessEqual(last[0]+page.side/2,x1+1)
   bottom=lv.cell(page,(page.rows_shown-1)*page.columns,0)[1]+page.side/2+page.name_room;self.assertLessEqual(bottom,y1+1)
   self.assertGreater(page.pill_x,page.margin);self.assertEqual(page.band_y,page.sheet[1])
  self.assertGreater(lv.arranged(self.base,lv.ViewChoice('grid','small')).columns,lv.arranged(self.base,lv.ViewChoice('grid','large')).columns)
 def test_list_drops_columns_on_a_narrow_page_and_keeps_the_name_room(self):
  wide=lv.arranged(self.base,lv.ViewChoice('list'));self.assertEqual([column[0] for column in wide.list_columns],['kind','played','time','trophies','size'])
  # Everything scales with the window, so only a name that needs more room than a page has makes the columns give way, play time last.
  original=lv.NAME_ROOM;lv.NAME_ROOM=1000
  try:narrow=lv.arranged(self.base,lv.ViewChoice('list'))
  finally:lv.NAME_ROOM=original
  self.assertEqual([column[0] for column in narrow.list_columns],['time','trophies','size']);self.assertGreaterEqual(narrow.name_end-narrow.name_x,round(900*narrow.unit))
  self.assertEqual([column[0] for column in lv.arranged(scene.page_layout(700,700),lv.ViewChoice('list')).list_columns],['kind','played','time','trophies','size'])
 def test_scroll_moves_as_little_as_it_can(self):
  page=lv.arranged(self.base,lv.ViewChoice('list'));shown=page.rows_shown
  self.assertEqual(lv.first_row(page,0,0,40),0);self.assertEqual(lv.first_row(page,shown,0,40),1);self.assertEqual(lv.first_row(page,3,2,40),2)
  self.assertEqual(lv.first_row(page,1,5,40),1);self.assertEqual(lv.first_row(page,39,0,40),40-shown);self.assertEqual(lv.first_row(page,2,0,3),0)
 def test_hits_find_the_game_under_the_point(self):
  grid=lv.arranged(self.base,lv.ViewChoice('grid'))
  for index in (0,3,grid.columns+1):
   x,y=lv.cell(grid,index,0);self.assertEqual(lv.hit(grid,x,y,30,0),index)
  x,y=lv.cell(grid,1,0);self.assertIsNone(lv.hit(grid,x+grid.side*.6,y,30,0));self.assertIsNone(lv.hit(grid,x,y,1,0))
  rows=lv.arranged(self.base,lv.ViewChoice('list'));x,y=lv.cell(rows,4,2);self.assertEqual(lv.hit(rows,x,y,30,2),4);self.assertIsNone(lv.hit(rows,x,rows.rows_top-2,30,0))
  self.assertEqual(list(lv.in_sight(rows,30,0))[0],0);self.assertLessEqual(len(lv.in_sight(rows,30,3)),rows.rows_shown+3)

class MoveTests(unittest.TestCase):
 def test_row_moves_along_and_changes_shelf_up_and_down(self):
  self.assertEqual(lv.move_for('row','right',0,10),('to',1));self.assertEqual(lv.move_for('row','left',0,10),('edge',))
  self.assertEqual(lv.move_for('row','down',3,10),('shelf',1));self.assertEqual(lv.move_for('row','next',8,10),('to',9));self.assertIsNone(lv.move_for('row','accept',0,10))
  self.assertEqual(lv.move_for('row','up',0,0),('shelf',-1));self.assertEqual(lv.move_for('row','right',0,0),('edge',))
 def test_grid_moves_both_ways_and_lands_on_a_short_last_row(self):
  self.assertEqual(lv.move_for('grid','down',1,10,4),('to',5));self.assertEqual(lv.move_for('grid','up',5,10,4),('to',1))
  self.assertEqual(lv.move_for('grid','up',2,10,4),('edge',));self.assertEqual(lv.move_for('grid','down',7,10,4),('to',9))
  self.assertEqual(lv.move_for('grid','down',9,10,4),('edge',));self.assertEqual(lv.move_for('grid','right',3,10,4),('to',4))
  self.assertEqual(lv.move_for('grid','next',0,40,4,3),('to',12));self.assertEqual(lv.move_for('grid','previous',5,40,4,3),('to',0))
 def test_list_moves_up_and_down_and_changes_shelf_sideways(self):
  self.assertEqual(lv.move_for('list','down',0,5),('to',1));self.assertEqual(lv.move_for('list','right',0,5),('shelf',1))
  self.assertEqual(lv.move_for('list','next',0,50,1,8),('to',8));self.assertEqual(lv.move_for('list','up',0,5),('edge',))
 def test_wheel_turns_a_grid_row_at_a_time(self):
  self.assertEqual(lv.wheel_for('grid',1,2,20,5),('to',7));self.assertEqual(lv.wheel_for('grid',1,17,20,5),('edge',));self.assertEqual(lv.wheel_for('grid',1,12,20,5),('to',17))
  self.assertEqual(lv.wheel_for('grid',1,13,17,5),('to',16));self.assertEqual(lv.wheel_for('list',-1,0,5),('edge',));self.assertEqual(lv.wheel_for('row',1,0,5),('to',1))
 def test_hints_show_the_arrows_each_view_uses(self):
  keys=(('←  →','Move'),('Enter','Play'))
  self.assertEqual(lv.hints('grid',keys)[0],('←↑↓→','Move'));self.assertEqual(lv.hints('list',keys)[0],('↑  ↓','Move'));self.assertEqual(lv.hints('row',keys),keys)

class PictureTests(unittest.TestCase):
 def test_badges_list_rows_and_names_draw(self):
  plain=scene.tile_badges(160,False,False,None,False);self.assertEqual(plain.size,(160,160));self.assertEqual(plain.getchannel('A').getbbox(),None)
  marks=scene.tile_badges(160,True,True,40,False);self.assertIsNotNone(marks.getchannel('A').getbbox())
  self.assertEqual(scene.grid_name('A long name',150,16,True).mode,'RGBA')
  page=lv.arranged(scene.page_layout(1600,900),lv.ViewChoice('list'))
  row=scene.list_row(page,None,'Game',"",{'kind':'PS5 game','played':'Today','time':'2 h','size':'5 GB'},(0.5,'10 / 20  ·  50%',False),True)
  self.assertEqual(row.size,(page.inner[2]-page.inner[0],page.row));self.assertEqual(scene.list_focus(400,page.row,1.0).size,(400,page.row))

if __name__=='__main__':unittest.main()
