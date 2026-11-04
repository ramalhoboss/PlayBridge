import argparse,collections,ctypes,os,queue,sys,threading,time,unittest
import tkinter as tk
from ctypes import byref,c_void_p
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import av,numpy as np
import d3d11_presenter as d
import playbridge as core
from frame_pacing import FramePacer

def player(renderer='auto',headless=False,**settings):
 with patch.object(core,'config',return_value=settings):
  return core.Player(argparse.Namespace(renderer=renderer,profile='balanced',auto_reconnect=False,device=None,connect_only=True,host='127.0.0.1',record=False,preview=False,headless=headless,seconds=0))
def changing_packets(count):
 encoder=av.CodecContext.create('libx264','w');encoder.width=640;encoder.height=360;encoder.pix_fmt='yuv420p';encoder.time_base=Fraction(1,30);encoder.framerate=Fraction(30,1);encoder.options={'preset':'ultrafast','tune':'zerolatency'};encoder.open();result=[]
 for n in range(count):
  frame=av.VideoFrame(640,360,'yuv420p');frame.pts=n;frame.time_base=Fraction(1,30)
  for plane in frame.planes:plane.update(bytes([n%200+20])*plane.buffer_size)
  result+=[bytes(p) for p in encoder.encode(frame)]
 return result
def result_of(rows,y,u,v):
 """The picture a limited range colour should give, from 0 to 255."""
 return [round(255*(row[0]*y/255+row[1]*u/255+row[2]*v/255+row[3])) for row in rows]

class SumsTests(unittest.TestCase):
 def test_limited_range_reaches_black_and_white(self):
  rows=d.colour_rows(1,False)
  self.assertEqual(result_of(rows,16,128,128),[0,0,0]);self.assertEqual(result_of(rows,235,128,128),[255,255,255])
 def test_full_range_is_left_alone(self):
  rows=d.colour_rows(1,True)
  self.assertEqual(result_of(rows,0,128,128),[0,0,0]);self.assertEqual(result_of(rows,255,128,128),[255,255,255])
 def test_each_standard_has_its_own_colours(self):
  self.assertNotEqual(d.colour_rows(1,False),d.colour_rows(5,False));self.assertNotEqual(d.colour_rows(1,False),d.colour_rows(9,False));self.assertEqual(d.colour_rows(1,False),d.colour_rows(2,False))
 def test_a_picture_keeps_its_shape_in_the_window(self):
  self.assertEqual(d.fitted(3840,2160,1920,1080),(0,0,1920,1080));self.assertEqual(d.fitted(3840,2160,1468,826),(0,0,1468,825))
  self.assertEqual(d.fitted(3840,2160,1000,1000),(0,219,1000,562));self.assertEqual(d.fitted(3840,2160,3000,1000),(611,0,1777,1000))
 def test_the_area_filter_starts_at_half_size(self):
  self.assertEqual(d.luma_filter(2),d.BOX);self.assertEqual(d.luma_filter(3.5),d.BOX);self.assertEqual(d.luma_filter(1.5),d.CUBIC);self.assertEqual(d.luma_filter(1),d.CUBIC)
 def test_fsr_only_enlarges(self):
  self.assertTrue(d.enlarged(.5));self.assertTrue(d.enlarged(.75));self.assertFalse(d.enlarged(1));self.assertFalse(d.enlarged(2))
 def test_the_easu_constants_follow_amds(self):
  # 1080p on a 4K screen: a screen pixel is half a texel, and the gathers sit one, two and four texels from the first.
  c=d.easu_constants(1920,1080,3840,2160);self.assertEqual(c[:4],(.5,.5,-.25,-.25))
  self.assertEqual([round(value*size,6) for value,size in zip(c[4:14],(1920,1080)*5)],[1,1,1,-1,-1,2,1,2,0,4]);self.assertEqual(c[14:],(0,0))
 def test_slice_zero_leaves_a_single_plane(self):
  self.assertEqual(d.surface_of(SimpleNamespace(planes=[SimpleNamespace(buffer_ptr=77)])),(77,0))
  self.assertEqual(d.surface_of(SimpleNamespace(planes=[SimpleNamespace(buffer_ptr=77),SimpleNamespace(buffer_ptr=5)])),(77,5))

class FailureTests(unittest.TestCase):
 def presenter(self,show):
  output=d.D3D11Presenter.__new__(d.D3D11Presenter);output.frame=None;output.failed=None;output.failures=0;output.pending=False;output.wanted=(10,10);output.size=(10,10);output.show=show;output.detach=lambda:None
  return output
 def test_a_fault_has_to_keep_coming_to_end_the_output(self):
  def broken(frame):raise OSError('device lost')
  output=self.presenter(broken)
  self.assertFalse(output.draw(1));self.assertFalse(output.draw(1));self.assertIsNone(output.failed);self.assertFalse(output.draw(1));self.assertIsInstance(output.failed,OSError)
 def test_a_good_frame_forgives_earlier_faults(self):
  answers=[OSError(),OSError(),True,OSError(),OSError(),True]
  def show(frame):
   answer=answers.pop(0)
   if answer is True:return True
   raise answer
  output=self.presenter(show)
  for _ in range(6):output.draw(1)
  self.assertIsNone(output.failed);self.assertEqual(output.failures,0)
 def test_a_fault_while_tidying_up_is_not_a_second_failure(self):
  def broken(frame):raise OSError('device lost')
  def worse():raise OSError('gone too')
  output=self.presenter(broken);output.detach=worse;forgotten=[];output.forget=lambda:forgotten.append(1)
  self.assertFalse(output.draw(1));self.assertEqual(forgotten,[1]);self.assertEqual(output.failures,1)
 def test_it_draws_again_only_when_there_is_a_reason(self):
  shown=[];output=self.presenter(lambda frame:shown.append(frame) or True)
  output.refresh();self.assertEqual(shown,[])
  output.frame='old';output.refresh();self.assertEqual(shown,[])
  output.wanted=(20,20);output.refresh();self.assertEqual(shown,['old'])
  output.wanted=(10,10);output.pending=True;output.refresh();self.assertEqual(shown,['old','old'])

class ChoiceTests(unittest.TestCase):
 def test_windows_uses_the_gpu_output_unless_it_is_turned_off(self):
  with patch.object(core.sys,'platform','win32'):
   self.assertEqual(player().renderer,'d3d11');self.assertEqual(player(direct_video=False).renderer,'gdi');self.assertEqual(player(headless=True).renderer,'gdi')
 def test_asking_for_an_output_wins(self):
  self.assertEqual(player('gdi').renderer,'gdi');self.assertEqual(player('d3d11',direct_video=False).renderer,'d3d11')
 def test_only_the_gpu_output_keeps_pictures_on_the_gpu(self):
  asked=[]
  def decoder(codec,on_gpu):asked.append(on_gpu);return 'gpu'
  with patch.object(core,'gpu_decoder',decoder):
   gpu=player('d3d11');gpu.capture_info={'resolution':4};self.assertEqual(gpu.video_decoder(),'gpu');self.assertTrue(gpu.decoder_on_gpu)
   memory=player('gdi');memory.capture_info={'resolution':6};self.assertEqual(memory.video_decoder(),'gpu');self.assertFalse(memory.decoder_on_gpu)
  self.assertEqual(asked,[True,False])
 def test_software_decoding_never_counts_as_on_the_gpu(self):
  with patch.object(core,'gpu_decoder',return_value=None):
   p=player('d3d11');p.capture_info={'resolution':6};p.video_decoder();self.assertEqual(p.decoder_name,'software');self.assertFalse(p.decoder_on_gpu)
 def test_leaving_the_gpu_output_lets_go_of_its_frames(self):
  p=player('d3d11');p.frames.append('surface');p.last_native_frame='surface';p.use_gdi()
  self.assertEqual(p.renderer,'gdi');self.assertEqual(len(p.frames),0);self.assertIsNone(p.last_native_frame)

class PacingTests(unittest.TestCase):
 def test_both_outputs_keep_the_standard_pacer(self):
  # More room rode out made-up bursts, but on the real console it mostly added delay.
  standard=FramePacer(collections.Counter())
  for renderer in ('d3d11','gdi'):
   p=player(renderer);self.assertEqual((p.pacer.max_lead,p.pacer.capacity),(standard.max_lead,standard.capacity))
 def test_falling_back_lets_go_of_the_frames_in_the_pacer(self):
  p=player('d3d11');p.pacer.add(1.,'surface',1.);p.use_gdi()
  self.assertEqual(len(p.pacer.items),0);self.assertIs(p.pacer.stats,p.stats)
 def test_the_decoder_has_surfaces_for_every_frame_the_app_can_hold(self):
  video=core.gpu_decoder(0,True)
  if video is None:self.skipTest('no hardware decoder here')
  # The decoded queue, the pacer, the last frame kept for screenshots and the one on screen.
  most=core.GPU_DECODED_FRAMES+FramePacer(collections.Counter()).capacity+2;held=collections.deque(maxlen=most);seen=0
  for data in changing_packets(most*3):
   for frame in video.decode(av.Packet(data)):held.append(frame);seen+=1
  self.assertEqual(len(held),most);self.assertGreater(seen,most*2);self.assertEqual(held[-1].format.name,'d3d11')
 def test_a_burst_of_gpu_frames_is_kept_until_it_can_be_handed_on(self):
  if core.gpu_decoder(0,True) is None:self.skipTest('no hardware decoder here')
  p=player('d3d11');p.capture_info={'resolution':6};sent=queue.Queue();done=threading.Event();burst=changing_packets(30)
  for n,data in enumerate(burst[:core.GPU_DECODED_FRAMES+4]):sent.put((data,n*1500,n*1500,time.perf_counter()))
  thread=threading.Thread(target=p.decode_video,args=(sent,done),daemon=True);thread.start();until=time.perf_counter()+10
  while not sent.empty() and time.perf_counter()<until:time.sleep(.01)
  time.sleep(.2);done.set();thread.join(5)
  self.assertTrue(p.decoder_on_gpu);self.assertEqual(len(p.frames),core.GPU_DECODED_FRAMES);self.assertEqual(p.stats['video_replaced'],p.stats['video_decoded']-core.GPU_DECODED_FRAMES)
 def test_frames_in_memory_keep_the_short_queue(self):
  self.assertLess(core.DECODED_FRAMES,core.GPU_DECODED_FRAMES)
  with patch.object(core,'gpu_decoder',return_value=None):
   p=player('d3d11');p.capture_info={'resolution':6};sent=queue.Queue();done=threading.Event()
   for n,data in enumerate(changing_packets(30)[:core.DECODED_FRAMES+4]):sent.put((data,n*1500,n*1500,time.perf_counter()))
   thread=threading.Thread(target=p.decode_video,args=(sent,done),daemon=True);thread.start();until=time.perf_counter()+10
   while p.stats['video_decoded']<core.DECODED_FRAMES+1 and time.perf_counter()<until:time.sleep(.01)
   time.sleep(.2);done.set();thread.join(5)
  self.assertFalse(p.decoder_on_gpu);self.assertEqual(len(p.frames),core.DECODED_FRAMES)

class Reading(d.D3D11Presenter):
 """Keeps what is about to reach the screen."""
 picture=None
 def present(self):
  desc=d.Texture2DDesc();d.GetTextureDesc(self.back,byref(desc));desc.Usage=d.USAGE_STAGING;desc.BindFlags=0;desc.CPUAccessFlags=d.CPU_READ;desc.MiscFlags=0;staging=c_void_p();d.CreateTexture2D(self.device,byref(desc),None,byref(staging))
  d.CopySubresourceRegion(self.context,staging.value,0,0,0,0,self.back,0,None);mapped=d.Mapped();d.Map(self.context,staging.value,0,d.MAP_READ,0,byref(mapped))
  raw=np.frombuffer(ctypes.string_at(mapped.Data,mapped.RowPitch*desc.Height),np.uint8).reshape(desc.Height,mapped.RowPitch//4,4);self.picture=raw[:,:desc.Width,:3][...,::-1].copy();d.Unmap(self.context,staging.value,0);d.Release(staging.value)
  super().present()

Y,U,V=120,90,190
def flat_packets():
 """A picture of one colour, in the limited range the console sends."""
 encoder=av.CodecContext.create('libx264','w');encoder.width=640;encoder.height=360;encoder.pix_fmt='yuv420p';encoder.time_base=Fraction(1,30);encoder.framerate=Fraction(30,1);encoder.options={'preset':'ultrafast','tune':'zerolatency','qp':'4'};encoder.open();result=[]
 for i in range(6):
  frame=av.VideoFrame(640,360,'yuv420p');frame.pts=i;frame.time_base=Fraction(1,30)
  for plane,value in zip(frame.planes,(Y,U,V)):plane.update(bytes([value])*plane.buffer_size)
  result+=[bytes(p) for p in encoder.encode(frame)]
 return result+[bytes(p) for p in encoder.encode(None)]

class DrawingTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.root=tk.Tk();cls.root.geometry('320x200+40+40');surface=tk.Frame(cls.root,bg='',width=320,height=200);surface.pack(fill='both',expand=True);cls.root.update()
  try:cls.output=Reading(surface)
  except Exception as error:
   cls.root.destroy();raise unittest.SkipTest(f'no Direct3D 11 here: {error}')
 @classmethod
 def tearDownClass(cls):
  cls.output.detach();cls.root.destroy()
 def setUp(self):self.output.sharpen=False;self.output.fsr=False
 def drawn(self,frame,width=640,height=360):
  self.output.wanted=(width,height)
  for _ in range(5):
   if self.output.draw(frame):return self.output.picture
   time.sleep(.02)
  self.fail(f'never drawn: {self.output.failed!r}')
 def gpu_frames(self):
  video=core.gpu_decoder(0,True)
  if video is None:self.skipTest('no hardware decoder here')
  frames=[]
  for data in flat_packets():frames+=video.decode(av.Packet(data))
  if not frames:self.skipTest('the hardware decoder gave no frames')
  return frames
 def assert_the_colour(self,picture):
  self.assertEqual(picture.shape,(360,640,3));expected=result_of(d.colour_rows(1,False),Y,U,V)
  for got,want in zip(picture[180,320],expected):self.assertAlmostEqual(int(got),want,delta=2)
 def test_a_frame_held_on_the_gpu_shows_its_colour(self):
  frames=self.gpu_frames();self.assertEqual(frames[-1].format.name,'d3d11');self.assert_the_colour(self.drawn(frames[-1]));self.assertIsNone(self.output.failed)
 def test_a_frame_in_memory_shows_the_same_colour(self):
  for name in ('yuv420p','nv12'):
   frame=av.VideoFrame(640,360,'yuv420p')
   for plane,value in zip(frame.planes,(Y,U,V)):plane.update(bytes([value])*plane.buffer_size)
   self.assert_the_colour(self.drawn(frame.reformat(format=name)))
 def test_sharpening_leaves_a_flat_colour_alone(self):
  frames=self.gpu_frames();self.output.sharpen=True;self.assert_the_colour(self.drawn(frames[-1]))
 def test_fsr_enlarges_a_flat_colour_unchanged(self):
  frames=self.gpu_frames();self.output.fsr=True;self.output.sharpen=True;picture=self.drawn(frames[-1],1280,720);self.assertTrue(self.output.enlarging);self.assertEqual(picture.shape,(720,1280,3))
  for got,want in zip(picture[360,640],result_of(d.colour_rows(1,False),Y,U,V)):self.assertAlmostEqual(int(got),want,delta=2)
 def test_fsr_waits_for_a_picture_to_enlarge(self):
  self.output.fsr=True;self.drawn(self.gpu_frames()[-1]);self.assertFalse(self.output.enlarging)
 def test_fsr_enlarges_an_edge_without_ringing(self):
  # Dark grey on the left and light grey on the right, which bicubic rings around.
  rows=np.full((540,640),128,np.uint8);rows[:360]=40;rows[:360,320:]=200;edge=av.VideoFrame.from_ndarray(rows,format='yuv420p')
  self.output.fsr=True;row=self.drawn(edge,1280,720)[360].astype(int);self.assertTrue(self.output.enlarging)
  dark,light=result_of(d.colour_rows(1,False),40,128,128)[0],result_of(d.colour_rows(1,False),200,128,128)[0]
  self.assertGreaterEqual(row.min(),dark-2);self.assertLessEqual(row.max(),light+2);self.assertLessEqual(int(((row[:,0]>dark+20)&(row[:,0]<light-20)).sum()),3)
 def test_nothing_old_stays_around_a_smaller_picture(self):
  frames=self.gpu_frames();self.drawn(frames[-1]);picture=self.drawn(frames[-1],640,480)
  self.assertEqual(picture.shape,(480,640,3));self.assertEqual(int(picture[:60].max()),0);self.assertEqual(int(picture[-60:].max()),0);self.assertGreater(int(picture[240,320].max()),0)
 def test_a_new_decoder_brings_a_new_device(self):
  first=self.gpu_frames();self.drawn(first[-1]);device=self.output.device;del first
  second=self.gpu_frames();self.assert_the_colour(self.drawn(second[-1]));self.assertNotEqual(self.output.device,device)
 def test_a_screenshot_reads_the_same_picture_back(self):
  frame=self.gpu_frames()[-1];picture=d.to_system(frame);self.assertEqual((picture.format.name,picture.width,picture.height),('nv12',640,360))
  rows=np.frombuffer(picture.planes[0],np.uint8).reshape(-1,picture.planes[0].line_size);self.assertAlmostEqual(int(rows[180,320]),Y,delta=2)
if __name__=='__main__':unittest.main()
