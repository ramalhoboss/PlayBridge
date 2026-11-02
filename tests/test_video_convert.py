import os,sys,unittest
from pathlib import Path
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import av,numpy as np
from video_convert import reformat_for_display

def frame_of(luma,u,v,width=3840,height=2160):
 """A limited range BT.709 frame, as the console sends, from one value or an array per plane."""
 frame=av.VideoFrame(width,height,'yuv420p');frame.colorspace=1;frame.color_range=1
 for index,(plane,value) in enumerate(zip(frame.planes,(luma,u,v))):
  rows,columns=(height,width) if index==0 else (height//2,width//2)
  data=np.zeros((plane.buffer_size//plane.line_size,plane.line_size),dtype=np.uint8);data[:rows,:columns]=value;plane.update(data.tobytes())
 return frame

def rgb(frame):
 plane=frame.planes[0]
 return np.frombuffer(plane,np.uint8).reshape(frame.height,plane.line_size//4,4)[:,:frame.width,:3][...,::-1].astype(np.float64)

class DisplayConversion(unittest.TestCase):
 def test_levels_reach_the_full_range(self):
  for luma,expected in ((16,0),(48,37.3),(64,55.9),(128,130.4),(235,255)):
   for width,height in ((1920,1080),(3000,1688)):
    picture=rgb(reformat_for_display(frame_of(luma,128,128),width,height,'bgr0'))
    self.assertAlmostEqual(picture.mean(),expected,delta=1,msg=f'{luma} at {width}x{height}')
 def test_a_4k_frame_keeps_one_colour_per_pixel_at_1080p(self):
  v=np.full((1080,1920),128,np.uint8);v[:,::2]=200;v[:,1::2]=56
  picture=rgb(reformat_for_display(frame_of(128,128,v),1920,1080,'bgr0'))
  self.assertGreater(np.abs(np.diff(picture[500:520,100:1800,0],axis=1)).mean(),200)
 def test_colours_follow_the_stream_matrix(self):
  # Skin tone: BT.601 would give about 182, 152, 118.
  picture=rgb(reformat_for_display(frame_of(150,110,150),1920,1080,'bgr0')).mean(axis=(0,1))
  for value,expected in zip(picture,(195.5,148.1,118.0)):self.assertAlmostEqual(value,expected,delta=1.5)
 def test_rgb24_for_screenshots_uses_the_same_levels(self):
  frame=reformat_for_display(frame_of(235,128,128),3840,2160,'rgb24')
  self.assertEqual(frame.to_ndarray().min(),255)
 def test_scaling_up_and_at_full_size_keep_the_picture_size(self):
  for width,height in ((3840,2160),(1920,1080),(2560,1440)):
   done=reformat_for_display(frame_of(128,128,128,1920,1080),width,height,'bgr0')
   self.assertEqual((done.width,done.height),(width,height))

if __name__=='__main__':unittest.main()
