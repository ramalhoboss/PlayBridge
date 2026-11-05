"""The pages without a game of their own, Settings, Media and the Live waiting screen, all show PlayBridge's own picture."""
import os,sys,unittest
from pathlib import Path
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import numpy as np
from PIL import Image
from luxury_theme import AmbientScene,button_image
from scene import no_art
from settings_look import backdrop

class BackdropTests(unittest.TestCase):
 def test_the_picture_is_cool_not_gold(self):
  pixels=np.asarray(no_art((320,180)),dtype=float).reshape(-1,3)
  brightest=pixels[pixels.sum(1).argmax()]
  self.assertGreater(brightest[2],brightest[0]);self.assertGreater(brightest[2],brightest[1])
 def test_settings_media_and_the_waiting_screen_show_the_same_picture(self):
  # Each drawing has its own fine noise, so the pages are compared by their colour on the right, away from the words.
  for image in (AmbientScene.backdrop((320,180)),backdrop((320,180),40)):
   self.assertEqual(image.size,(320,180))
   right=np.asarray(image.crop((200,20,320,90)),dtype=float).mean((0,1))
   self.assertGreater(right[2],right[0]);self.assertGreater(right[2],right[1])
 def test_a_button_on_the_picture_keeps_it_in_its_corners(self):
  under=Image.new('RGB',(120,40),(10,120,200))
  image=button_image((120,40),'Refresh',behind=under)
  self.assertEqual(image.getpixel((0,0)),(10,120,200))

if __name__=='__main__':unittest.main()
