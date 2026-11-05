import math,os,sys,unittest
from pathlib import Path
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import numpy as np
from PIL import Image
import scene

def icon():
 image=Image.new('RGB',(64,64),(200,40,40));image.paste((40,40,200),(32,0,64,64));return image
SIZES=((900,620),(1000,660),(1540,920),(1920,1080),(3840,2160),(1208,1080))
class CoverTests(unittest.TestCase):
 def setUp(self):self.faces=scene.cover_faces(icon(),120,'Game')
 def test_a_cover_facing_the_camera_keeps_its_art_and_size(self):
  sprite,left,top=scene.render_cover(self.faces)
  self.assertAlmostEqual(left,-60,delta=4);self.assertAlmostEqual(top,-60,delta=4)
  self.assertGreater(sprite.getpixel((-left-30,-top+50))[0],150);self.assertGreater(sprite.getpixel((-left+30,-top+50))[2],150)
 def test_a_turned_cover_is_narrower_and_its_near_edge_is_taller(self):
  sprite,left,top=scene.render_cover(self.faces,yaw=math.radians(50));alpha=np.asarray(sprite.getchannel('A'))>128
  self.assertLess(sprite.width,110);columns=np.nonzero(alpha.any(axis=0))[0];heights=alpha.sum(axis=0)
  self.assertGreater(heights[columns[-1]-8],heights[columns[0]+8])
 def test_the_edge_that_shows_follows_the_turn(self):
  right=scene.render_cover(self.faces,yaw=math.radians(30))[0];left=scene.render_cover(self.faces,yaw=math.radians(-30))[0]
  # Turned one way or the other, the box shows one side: never both, and never a gap between it and the front.
  for sprite in (right,left):
   alpha=np.asarray(sprite.getchannel('A'))>128;middle=alpha[alpha.shape[0]//2];columns=np.nonzero(middle)[0];self.assertTrue(middle[columns[0]:columns[-1]+1].all())
 def test_the_white_rim_marks_the_focus_and_can_fade(self):
  def rim_pixel(rim):
   sprite,left,top=scene.render_cover(self.faces,rim=rim);return sprite.getpixel((-left-60,-top+10))[1]
  self.assertGreater(rim_pixel(1),rim_pixel(0)+100);self.assertGreater(rim_pixel(.5),rim_pixel(0));self.assertLess(rim_pixel(.5),rim_pixel(1))
 def test_a_game_without_art_still_gets_a_cover_and_a_tile(self):
  self.assertEqual(scene.cover_faces(None,48,'')['side'],48);self.assertGreater(scene.render_cover(scene.cover_faces(None,48,'Name'))[0].width,10);self.assertEqual(scene.flat_tile(None,48,'Name').size,(48,48))
 def test_a_dimmed_cover_keeps_its_shape(self):
  sprite=scene.render_cover(self.faces)[0];darker=scene.dimmed(sprite,.5);self.assertEqual(darker.getchannel('A').tobytes(),sprite.getchannel('A').tobytes());self.assertLess(darker.getpixel((sprite.width//2,sprite.height//2+40))[0],sprite.getpixel((sprite.width//2,sprite.height//2+40))[0])

class RowTests(unittest.TestCase):
 def setUp(self):self.layout=scene.page_layout(1540,920)
 def test_a_tile_travels_without_a_jump(self):
  for offset in (-1,1):
   for part in (0,2):self.assertAlmostEqual(scene.tile_pose(offset*.999,self.layout)[part],scene.tile_pose(offset,self.layout)[part],delta=.5)
  for offset in (-2,1,2,3):self.assertLess(scene.tile_pose(offset,self.layout)[0],scene.tile_pose(offset+1,self.layout)[0])
 def test_the_focused_tile_is_the_big_one_and_the_rest_are_the_same_size(self):
  self.assertEqual(scene.tile_pose(0,self.layout)[2],self.layout.focus);self.assertEqual(scene.tile_pose(1,self.layout)[2],self.layout.small);self.assertEqual(scene.tile_pose(-3,self.layout)[2],self.layout.small);self.assertEqual(scene.tile_pose(0,self.layout)[3],0);self.assertEqual(scene.tile_pose(2,self.layout)[3],1)
 def test_the_tile_before_the_focus_peeks_in_at_the_edge(self):
  cx,_,side,_=scene.tile_pose(-1,self.layout);self.assertLess(cx-side/2,0);self.assertGreater(cx+side/2,0);self.assertLess(cx+side/2,scene.tile_pose(0,self.layout)[0]-self.layout.focus/2)
 def test_tiles_keep_clear_of_each_other_at_rest(self):
  for offset in (0,1,2):
   a,_,side_a,_=scene.tile_pose(offset,self.layout);b,_,side_b,_=scene.tile_pose(offset+1,self.layout);self.assertEqual(round(b-side_b/2-(a+side_a/2)),self.layout.gap)
 def test_a_tile_swings_only_on_its_way(self):
  self.assertEqual(scene.turn_of(0),0);self.assertAlmostEqual(scene.turn_of(1),0);self.assertGreater(scene.turn_of(.5),0);self.assertLess(scene.turn_of(-.5),0);self.assertAlmostEqual(scene.turn_of(.5),scene.TURN_YAW)
 def test_the_page_fits_any_window_from_small_to_4k(self):
  for size in SIZES:
   layout=scene.page_layout(*size);self.assertLess(layout.hints_y+layout.hints,size[1]+1,size);self.assertLessEqual(layout.cards_y+layout.card_height,layout.hints_y,size);self.assertLess(layout.pill_y+layout.pill,layout.cards_y,size);self.assertLess(layout.meta_y,layout.pill_y,size)
   self.assertLessEqual(layout.band_y+layout.band_height,layout.title_top+1,size);self.assertLessEqual(layout.cards[-1][2],size[0],size);self.assertLessEqual(layout.margin+layout.title_width,size[0],size)

class PictureTests(unittest.TestCase):
 def test_the_art_fills_the_page_whatever_its_shape(self):
  for art in (Image.new('RGB',(1920,1080),(200,180,160)),Image.new('RGB',(512,512),(200,180,160)),Image.new('RGB',(3000,400),(200,180,160))):
   self.assertEqual(scene.hero_picture(art,None,(640,360)).size,(640,360))
 def test_the_art_stays_bright_where_nothing_stands_and_dark_under_the_words(self):
  hero=scene.hero_picture(Image.new('RGB',(160,90),(200,200,200)),None,(800,450));self.assertGreater(hero.getpixel((640,140))[0],hero.getpixel((20,420))[0]+80);self.assertGreater(hero.getpixel((640,140))[0],130)
 def test_a_game_without_art_shows_its_cover_on_the_right(self):
  hero=scene.hero_picture(None,Image.new('RGB',(64,64),(250,30,30)),(800,450));self.assertGreater(hero.getpixel((700,180))[0],hero.getpixel((60,180))[0]);self.assertGreater(hero.getpixel((700,180))[0],hero.getpixel((700,180))[1])
 def test_with_nothing_at_all_the_page_is_dark_and_cool(self):
  red,green,blue=scene.hero_picture(None,None,(400,225)).getpixel((300,60));self.assertLess(max(red,green,blue),150);self.assertGreater(blue,red);self.assertGreater(blue,green)
 def test_glass_darkens_and_blurs_what_is_behind_it(self):
  image=Image.new('RGB',(100,100),(220,220,220));image.paste((0,0,0),(50,0,100,100));scene.glass(image,(10,10,90,90),8);self.assertLess(image.getpixel((30,50))[0],160);self.assertGreater(image.getpixel((48,50))[0],image.getpixel((70,50))[0]);self.assertLess(image.getpixel((48,50))[0]-image.getpixel((52,50))[0],40)
 def test_a_long_title_takes_two_lines_and_stays_inside_the_width(self):
  for name in ('Y','UNCHARTED™: Drake\'s Fortune Remastered','W'*90,''):
   font,lines=scene.title_lines(name,300,40);self.assertLessEqual(len(lines),2);self.assertTrue(all(font.getlength(line)<=300 for line in lines) or font.size<=14);self.assertNotIn('™',' '.join(lines))
 def test_the_page_draws_at_any_size_with_any_name(self):
  for size in ((900,620),(1540,920)):
   layout=scene.page_layout(*size);page=scene.library_page(Image.new('RGB',(64,36),(90,90,90)),None,layout,'A very long name indeed for a game that goes on and on and on and on and on','Played today',(('Your time','3½ h','Across'),('On your PS5','10.4 GB','PS4 game')));self.assertEqual(page.size,size)
   self.assertGreater(page.getpixel((layout.margin+8,layout.title_bottom-layout.title_size//2))[0],-1)
 def test_the_live_cards_fit_the_last_two_cards_and_cope_with_no_reading(self):
  layout=scene.page_layout(1540,920);picture=scene.live_cards(layout,(0,'—','No picture yet','—'),('Console','Not connected','No game open'));self.assertEqual(picture.width,layout.cards[3][2]-layout.cards[2][0]);self.assertEqual(picture.height,layout.card_height)
  self.assertEqual(scene.live_cards(layout,(1,'60','3840×2160','72 Mbps'),('Console','CPU 52°','SoC 61°')).size,picture.size)
 def test_the_name_beside_the_tile_stays_inside_the_window(self):
  layout=scene.page_layout(900,620);sprite,x,y=scene.name_line(layout,'W'*200);self.assertLessEqual(x+sprite.width,900+layout.name_size*2);self.assertGreater(sprite.getbbox()[2],0)
 def test_the_big_button_copes_with_every_state(self):
  for text,hovering,enabled,busy in (('Play',False,True,None),('Resume',True,True,None),('Connecting',False,False,None),('Starting',False,True,60)):self.assertEqual(scene.play_pill(290,58,text,hovering,enabled,busy).size,(290,58))
 def test_the_top_bar_says_where_to_click(self):
  layout=scene.page_layout(1540,920);picture,hits=scene.top_bar(layout,dict(status='PS5  ·  Online',online=True,clock='17:42',shelf='All games',hover='power'));self.assertEqual(picture.width,1540)
  for key in ('games','live','media','shelf','search','settings','fullscreen','power'):self.assertIn(key,hits)
  self.assertLess(hits['games'][2],hits['live'][0]);self.assertLess(hits['settings'][2],hits['fullscreen'][0]);self.assertLessEqual(hits['power'][2],1540-layout.margin+1)
 def test_searching_takes_the_shelfs_place(self):
  layout=scene.page_layout(1540,920);_,hits=scene.top_bar(layout,dict(status='',clock='17:42',shelf='All games',search='dem',searching=True));self.assertNotIn('shelf',hits)
 def test_a_narrow_top_bar_drops_the_shelf_and_keeps_the_buttons(self):
  layout=scene.page_layout(420,620);_,hits=scene.top_bar(layout,dict(status='A console with a long name  ·  Online',clock='17:42',shelf='Most played',pad=True));self.assertIn('power',hits);self.assertIn('games',hits)
 def test_the_hint_bar_draws_keys_and_shapes(self):
  layout=scene.page_layout(1540,920)
  for hints in ((('Enter','Play'),('F6','Live view')),(('cross','Play'),('circle','Back'),('square','Refresh'),('L1','Previous tab'))):self.assertEqual(scene.hint_bar(layout,hints,'Line','').size,(1540,layout.hints))
  self.assertEqual(scene.hint_bar(layout,(),'x'*900,True).size,(1540,layout.hints))
 def test_a_menu_lists_its_rows(self):
  picture,rows=scene.drop_menu((('rest','Rest mode'),('off','Turn off PS5')),1,1);self.assertEqual(len(rows),2);self.assertEqual(rows[0][1],rows[1][0]);self.assertLessEqual(rows[1][1],picture.height)
 def test_the_top_bar_marks_the_page_that_is_showing(self):
  layout=scene.page_layout(1540,920);values=dict(status='Not connected',clock='10:00')
  games,hits=scene.top_bar(layout,values);self.assertEqual(games.tobytes(),scene.top_bar(layout,dict(values,tab='games'))[0].tobytes());self.assertNotEqual(games.tobytes(),scene.top_bar(layout,dict(values,tab='live'))[0].tobytes())
  self.assertTrue({'games','live','media','search','settings','fullscreen','power'}<=set(hits));self.assertNotEqual(games.tobytes(),scene.top_bar(layout,dict(values,selected='settings'))[0].tobytes())
 def test_the_gauge_copes_with_any_reading(self):
  for fraction in (-1,0,.5,1,9):
   self.assertEqual(scene.ring_gauge(100,fraction,'60','FPS').size,(100,100));self.assertEqual(scene.glass_gauge(90,fraction,'60').size,(90,90))
if __name__=='__main__':unittest.main()
