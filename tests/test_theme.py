import os,re,sys,types,unittest
from pathlib import Path
APP=Path(__file__).resolve().parents[1]/'app'
sys.path.insert(0,str(APP))
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
import customtkinter as ctk
import numpy as np
from PIL import Image
from luxury_theme import BG,CARD,GOLD,PANEL,LuxButton,apply_theme,bezel_image,button_image,dot,gold_text,rounded_mask,tint

def rgb(text):return tuple(int(text[i:i+2],16) for i in (1,3,5))

class ThemeTests(unittest.TestCase):
 def test_tint_keeps_the_shape_and_uses_the_colour_at_full_strength(self):
  image=Image.new('RGBA',(2,1),(0,0,0,0));image.putpixel((0,0),(255,255,255,255))
  result=tint(image,'#D4AF37');self.assertEqual(result.getpixel((0,0)),(0xD4,0xAF,0x37,255));self.assertEqual(result.getpixel((1,0))[3],0)
 def test_tint_keeps_shading_and_ignores_transparent_pixels(self):
  image=Image.new('RGBA',(3,1),(255,255,255,0));image.putpixel((0,0),(100,100,100,255));image.putpixel((1,0),(50,50,50,255))
  result=tint(image,'#D4AF37');self.assertEqual(result.getpixel((0,0))[:3],(0xD4,0xAF,0x37));self.assertLess(result.getpixel((1,0))[0],0xD4*.6)
 def test_widgets_that_name_no_colour_do_not_fall_back_to_blue(self):
  apply_theme()
  for widget in ('CTkButton','CTkSwitch','CTkSlider','CTkOptionMenu','DropdownMenu'):
   for name,value in ctk.ThemeManager.theme[widget].items():
    if 'color' in name:self.assertNotIn(value,(['#3B8ED0','#1F6AA5'],['#36719F','#144870']),widget+' '+name)
  self.assertEqual(ctk.ThemeManager.theme['CTkSwitch']['progress_color'],GOLD)
 def test_a_mask_can_stop_at_a_fraction_of_a_pixel(self):
  mask=rounded_mask((100,60),.25,10)
  self.assertAlmostEqual(mask.getpixel((0,30)),191,delta=3);self.assertEqual(mask.getpixel((1,30)),255);self.assertAlmostEqual(mask.getpixel((50,0)),191,delta=3)
 def test_curves_blend_smoothly_into_the_background(self):
  mask=np.asarray(rounded_mask((100,60),0,10))
  self.assertEqual(mask[0,0],0);self.assertEqual(mask[30,50],255)
  self.assertGreater(len(set(mask[:10,:10].flatten().tolist())),5)
 def test_all_four_corners_match_and_small_shapes_work(self):
  for size,radius in (((100,60),10),((34,34),17),((40,12),6)):
   mask=np.asarray(rounded_mask(size,0,radius))
   self.assertTrue((mask==mask[::-1]).all());self.assertTrue((mask==mask[:,::-1]).all());self.assertEqual(mask.shape,(size[1],size[0]))
 def test_a_bezel_rim_is_one_pixel_of_gold_between_the_panel_and_the_black_behind_it(self):
  image=bezel_image((200,120))
  self.assertEqual(image.size,(200,120));self.assertEqual(image.getpixel((0,0)),rgb(BG));self.assertEqual(image.getpixel((100,60)),rgb(PANEL))
  red,green,blue=image.getpixel((0,60));self.assertGreater(red,blue+40);self.assertGreater(green,blue);self.assertEqual(image.getpixel((1,60)),rgb(PANEL))
 def test_a_glow_sits_outside_the_rim(self):
  image=bezel_image((200,120),glow=3)
  self.assertGreater(image.getpixel((2,60))[0],rgb(BG)[0]);self.assertGreater(image.getpixel((3,60))[0],image.getpixel((2,60))[0]);self.assertEqual(image.getpixel((4,60)),rgb(PANEL))
 def test_gold_lettering_is_warm_on_a_transparent_ground(self):
  art=gold_text('Gold',24)
  if art is None:self.skipTest('The font is not installed')
  pixels=np.asarray(art);self.assertEqual(pixels[...,3].min(),0);opaque=pixels[pixels[...,3]==255];self.assertGreater(len(opaque),0);self.assertTrue((opaque[...,0]>opaque[...,2]).all())
 def test_a_gold_button_differs_when_hovered_and_has_dark_lettering(self):
  rest=button_image((130,38),'Connect',tone='gold');hover=button_image((130,38),'Connect',tone='gold',hovering=True)
  self.assertEqual(rest.size,(130,38));self.assertNotEqual(rest.tobytes(),hover.tobytes());self.assertLess(np.asarray(rest.convert('L'))[10:28,30:100].min(),60)
 def test_a_plain_button_has_a_thin_rim_around_its_face(self):
  image=button_image((40,40))
  self.assertEqual(image.getpixel((0,0)),rgb(PANEL));self.assertEqual(image.getpixel((20,20)),rgb(CARD));self.assertEqual(image.getpixel((1,20)),rgb(CARD));self.assertGreater(image.getpixel((0,20))[0],60)
 def test_a_ghost_button_shows_a_rim_only_when_selected(self):
  self.assertEqual(button_image((58,66),tone='ghost').getextrema(),tuple((value,value) for value in rgb(PANEL)))
  self.assertGreater(button_image((58,66),tone='ghost',selected=True).getpixel((0,33))[0],60)
 def test_a_disabled_button_loses_its_bright_rim(self):
  self.assertNotEqual(button_image((85,32),'Next',enabled=False).tobytes(),button_image((85,32),'Next').tobytes())
 def test_an_icon_and_label_both_appear_in_either_layout(self):
  for compound in ('left','top'):
   bare=button_image((58,66),'LIVE',compound=compound);marked=button_image((58,66),'LIVE',icon=dot(GOLD),compound=compound);self.assertNotEqual(bare.tobytes(),marked.tobytes())
 def test_restyling_with_what_it_already_shows_draws_nothing(self):
  calls=[];icon=dot(GOLD);button=types.SimpleNamespace(text='LIVE',icon=icon,selected=False,clickable=True,draw=lambda:calls.append(1))
  LuxButton.restyle(button,text='LIVE',icon=icon,selected=False);self.assertEqual(calls,[])
  LuxButton.restyle(button,text='Offline');self.assertEqual(calls,[1]);self.assertEqual(button.text,'Offline')
 def test_the_interface_has_no_cool_colours_left(self):
  for name in ('playbridge_ui.py','gaming_hub.py','luxury_theme.py'):
   for colour in re.findall(r"#[0-9A-Fa-f]{6}\b",(APP/name).read_text(encoding='utf8')):
    self.assertGreaterEqual(int(colour[1:3],16),int(colour[5:7],16),name+' '+colour)
if __name__=='__main__':unittest.main()
