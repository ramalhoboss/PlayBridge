"""The overlay: drawn as panels, and mixed into a live stream's frames in the console's own colours, only in its corner."""
import sys,unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import av
import numpy as np
import frame_overlay as f
import hud
import live_broadcast as live
import pad_input as pads
import video_encoders as v

def solid(width,height,bgra):return (bytes(bgra)*width*height,width,height)
def frame(width=640,height=360,fmt='nv12',y=60,u=110,v_=150):
 out=av.VideoFrame(width,height,fmt)
 if fmt=='nv12':out.planes[0].update(bytes([y])*out.planes[0].buffer_size);out.planes[1].update(bytes([u,v_])*(out.planes[1].buffer_size//2))
 else:
  for plane,value in zip(out.planes,(y,u,v_)):plane.update(bytes([value])*plane.buffer_size)
 return out
def planes(picture):
 """Y, U and V as full arrays of the picture's own size."""
 if picture.format.name=='nv12':
  luma=f.plane_array(picture.planes[0])[:,:picture.width].copy();both=f.plane_array(picture.planes[1])[:,:picture.width].reshape(picture.height//2,picture.width//2,2)
  return luma,both[...,0].copy(),both[...,1].copy()
 return tuple(f.plane_array(p)[:,:w].copy() for p,w in zip(picture.planes,(picture.width,picture.width//2,picture.width//2)))

class BlendTests(unittest.TestCase):
 def test_an_opaque_overlay_takes_its_own_colours_in_bt709_limited_range(self):
  for fmt in ('nv12','yuv420p'):
   picture=frame(fmt=fmt);self.assertTrue(f.FrameOverlay().apply(picture,solid(40,20,(0,0,255,255))))
   y,u,v_=planes(picture);m=f.MARGIN
   # Red in BT.709 limited range: Y 63, U 102, V 240.
   self.assertEqual((int(y[m+5,m+5]),int(u[m//2+2,m//2+2]),int(v_[m//2+2,m//2+2])),(63,102,240),fmt)
   # Outside its corner the frame is as it was.
   self.assertEqual((int(y[m+25,m+5]),int(y[m+5,m+45]),int(y[200,300])),(60,60,60));self.assertEqual((int(u[100,100]),int(v_[100,100])),(110,150))
 def test_a_half_transparent_overlay_mixes_with_the_frame(self):
  picture=frame();f.FrameOverlay().apply(picture,solid(40,20,(255,255,255,128)));y,u,v_=planes(picture);m=f.MARGIN;a=128/255
  self.assertAlmostEqual(int(y[m+5,m+5]),round(235*a+60*(1-a)),delta=1);self.assertAlmostEqual(int(u[m//2+2,m//2+2]),round(128*a+110*(1-a)),delta=1)
 def test_a_clear_overlay_leaves_the_frame_alone(self):
  picture=frame();before=planes(picture);f.FrameOverlay().apply(picture,solid(40,20,(9,9,9,0)))
  for a,b in zip(before,planes(picture)):self.assertTrue(np.array_equal(a,b))
 def test_it_is_placed_further_in_on_a_larger_frame(self):
  picture=frame(1920*2,1080*2);f.FrameOverlay().apply(picture,solid(40,20,(0,0,255,255)));y,_,_=planes(picture)
  self.assertEqual((int(y[32+5,32+5]),int(y[20,20])),(63,60))
 def test_what_it_cannot_draw_it_says(self):
  overlay=f.FrameOverlay();self.assertFalse(overlay.apply(frame(),None));self.assertFalse(overlay.apply(frame(64,36),solid(80,40,(0,0,0,255))))
  self.assertFalse(overlay.apply(av.VideoFrame(64,64,'rgb24'),solid(8,8,(0,0,0,255))))
 def test_the_colours_are_worked_out_once_per_overlay(self):
  overlay=f.FrameOverlay();image=solid(40,20,(0,0,255,255));first=overlay.prepare(image);self.assertIs(overlay.prepare(image),first)

class RemakerTests(unittest.TestCase):
 def test_it_says_which_frames_are_its_own_to_draw_on(self):
  drawn=[];stream=type('S',(),{'pix_fmt':'nv12','encode':lambda self,frame:[frame]})()
  remaker=live.Remaker.__new__(live.Remaker);remaker.stream=stream;remaker.overlay=lambda picture,own:(drawn.append((picture.format.name,own)),picture)[1]
  for fmt in ('yuv420p','nv12'):
   picture=frame(fmt=fmt);picture.pts=1;picture.time_base=Fraction(1,90000);remaker._encode(picture)
  self.assertEqual(drawn,[('nv12',True),('nv12',True)])
  # A frame in the encoder's own format that a processor's decoder made is its reference too.
  stream.pix_fmt='yuv420p';drawn.clear();picture=frame(fmt='yuv420p');picture.pts=1;remaker._encode(picture);self.assertEqual(drawn,[('yuv420p',False)])
 def test_a_frame_other_frames_are_built_on_is_copied_and_left_alone(self):
  picture=frame(fmt='yuv420p');picture.pts=77;before=planes(picture);image=solid(40,20,(0,0,255,255))
  out=f.FrameOverlay().draw(picture,image,False);self.assertIsNot(out,picture);self.assertEqual(out.pts,77)
  for a,b in zip(before,planes(picture)):self.assertTrue(np.array_equal(a,b))
  y,_,_=planes(out);m=f.MARGIN;self.assertEqual((int(y[m+5,m+5]),int(y[200,300])),(63,60))
  # Its own frame is drawn on as it is, and with no overlay nothing is copied.
  mine=frame();self.assertIs(f.FrameOverlay().draw(mine,image,True),mine);self.assertIs(f.FrameOverlay().draw(picture,None,False),picture)

class PanelTests(unittest.TestCase):
 def timer(self,**changes):
  base=dict(state='running',time='12:05.8',name='Some Game',split='First boss  0:58.5',delta='−0:01.5',ahead=True,best='Best 1:40.0');base.update(changes);return base
 def test_the_panels_stack_into_one_image(self):
  view=dict(status={'cpu_c':60},game_fps=60.0,points=[60.0]*20,name='Some Game',lowest=58)
  alone=hud.render(timer=self.timer());both=hud.render(view,{},self.timer(),dict(name='Done It',grade='gold'),pads.PadState(buttons=pads.CROSS|pads.L1,l2=200,lx=255))
  self.assertEqual(len(alone[0]),alone[1]*alone[2]*4);self.assertGreater(both[2],alone[2]*3);self.assertEqual(both[1],250)
  self.assertIsNone(hud.render())
 def test_it_grows_with_the_picture(self):
  self.assertEqual(hud.render(timer=self.timer(),scale=2)[1],500);self.assertEqual(hud.render(timer=self.timer(),scale=.2)[1],round(250*.75))
 def test_a_trophy_shows_its_own_picture_or_its_grade(self):
  import io
  from PIL import Image
  out=io.BytesIO();Image.new('RGBA',(64,64),(20,200,60,255)).save(out,'PNG')
  def at(trophy,x,y):data,width,height=hud.render(trophy=trophy);return tuple(int(v) for v in np.frombuffer(data,np.uint8).reshape(height,width,4)[y,x])
  # BGRA: the picture's green in the panel's left square; without one, a bronze circle; a broken one falls back to the circle.
  self.assertEqual(at(dict(name='Done It',grade='bronze',icon=out.getvalue()),12+17,12+17)[:3],(60,200,20))
  self.assertEqual(at(dict(name='Done It',grade='bronze'),12+11,29)[:3],(70,130,205))
  self.assertEqual(at(dict(name='Done It',grade='bronze',icon=b'\x89PNG broken'),12+11,29)[:3],(70,130,205))
 def test_a_pressed_button_lights_up(self):
  def lit(state):
   data,width,height=hud.render(pad=state);pixels=np.frombuffer(data,np.uint8).reshape(height,width,4);return int((pixels[...,3]==255).sum())
  self.assertGreater(lit(pads.PadState(buttons=pads.CROSS|pads.TRIANGLE|pads.UP)),lit(pads.PadState()))

class EncoderTests(unittest.TestCase):
 def test_h264_is_only_used_to_draw_the_overlay(self):
  with patch.object(v,'_found',['h264_amf','hevc_amf','libsvtav1']):
   self.assertEqual((v.for_live(),v.for_files(),v.for_live_h264()),('hevc_amf','hevc_amf','h264_amf'))
  with patch.object(v,'_found',['h264_nvenc']):self.assertEqual((v.for_live(),v.for_files(),v.for_live_h264()),(None,None,'h264_nvenc'))
  self.assertEqual((v.kind('h264_amf'),v.pixel_format('h264_amf',live=True)),('h264','nv12'))
  self.assertEqual(v.bitrate('h264_nvenc',1080,live=True),12_000_000)

if __name__=='__main__':unittest.main()
