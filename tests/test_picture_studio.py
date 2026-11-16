"""Picture Studio: the values the picture uses for every game and for one game, what the graphics card's video engine is said to do, and
on this PC's graphics card the debanding pass and the video engine drawing an in-between picture letterboxed into the window."""
import ctypes,os,sys,unittest
from ctypes import Structure,byref,c_void_p
from pathlib import Path
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import picture_studio as studio

class Core:
 def __init__(self,saved=None):self.saved=dict(saved or {})
 def config(self):return dict(self.saved)
 def save_config(self,**values):self.saved.update(values)

class Presenter:
 def __init__(self):self.super_resolution=True;self.video_hdr=False;self.fsr=False;self.sharpen=False;self.deband=False;self.turned=[]
 def turn_engine(self,super_resolution=None,video_hdr=None):
  self.turned.append((super_resolution,video_hdr))
  if super_resolution is not None:self.super_resolution=super_resolution
  if video_hdr is not None:self.video_hdr=video_hdr

class StudioTests(unittest.TestCase):
 def test_the_usual_values_default_to_super_resolution_only(self):
  self.assertEqual(studio.PictureStudio(Core()).current(),{'super_resolution':True,'video_hdr':False,'fsr':False,'sharpen':False,'deband':False})
 def test_a_switch_without_a_game_of_its_own_changes_the_usual_values(self):
  core=Core();picture=studio.PictureStudio(core);presenter=Presenter()
  picture.change('deband',True,presenter);self.assertTrue(core.saved['deband']);self.assertTrue(presenter.deband)
 def test_a_game_kept_with_its_own_values_gets_them_back_each_time_it_runs(self):
  core=Core();picture=studio.PictureStudio(core);presenter=Presenter()
  picture.see('CUSA00001','Uncharted',presenter);picture.change('sharpen',True,presenter);self.assertTrue(picture.keep_for_game(presenter))
  # Its own values change while it runs; the usual ones stay as they were.
  picture.change('deband',True,presenter);self.assertTrue(core.saved['picture_presets']['CUSA00001']['deband']);self.assertNotIn('deband',core.saved)
  self.assertTrue(picture.see('','',presenter));self.assertFalse(presenter.deband);self.assertTrue(presenter.sharpen)
  self.assertTrue(picture.see('CUSA00001','Uncharted',presenter));self.assertTrue(presenter.deband)
  self.assertEqual(picture.view()['studioGames'],['Uncharted']);self.assertTrue(picture.view()['studioOwn'])
 def test_forgetting_a_game_goes_back_to_the_usual_values(self):
  core=Core({'picture_presets':{'PPSA1':{'video_hdr':True,'name':'Game'}}});picture=studio.PictureStudio(core);presenter=Presenter()
  picture.see('PPSA1','Game',presenter);self.assertTrue(presenter.video_hdr);self.assertEqual(presenter.turned,[(None,True)])
  picture.forget_game(presenter);self.assertFalse(presenter.video_hdr);self.assertEqual(core.saved['picture_presets'],{})
 def test_nothing_is_kept_without_a_game(self):
  core=Core();self.assertFalse(studio.PictureStudio(core).keep_for_game(Presenter()));self.assertNotIn('picture_presets',core.saved)
 def test_a_broken_presets_entry_is_left_out(self):
  self.assertEqual(studio.PictureStudio(Core({'picture_presets':'nonsense'})).presets(),{})

try:
 import numpy as np
 import d3d11_presenter as d3d
 import gpu_scaler as gs
except Exception:np=None

@unittest.skipIf(np is None,'needs numpy and the presenter')
class EngineChoiceTests(unittest.TestCase):
 def presenter(self,**values):
  p=object.__new__(d3d.D3D11Presenter)
  p.__dict__.update(dict(super_resolution=True,video_hdr=False,fsr=False,engine=None,engine_failed=None,scaling_refused=False,hdr_refused=None,vendor=0,engine_active=False,screen_hdr=False,hdr=False))
  p.__dict__.update(values);return p
 def test_only_nvidia_and_intel_cards_enlarge_in_their_video_engine(self):
  self.assertTrue(gs.can_enlarge(gs.NVIDIA));self.assertTrue(gs.can_enlarge(gs.INTEL));self.assertFalse(gs.can_enlarge(gs.AMD))
 def test_the_streams_colours_are_named_as_dxgi_names_them(self):
  self.assertEqual(gs.stream_space(1,False),8);self.assertEqual(gs.stream_space(2,True),9);self.assertEqual(gs.stream_space(6,False),6);self.assertEqual(gs.stream_space(9,False),10)
  self.assertEqual(gs.legacy_space(1,False),1<<2|1<<4);self.assertEqual(gs.legacy_space(5,True),2<<4)
 def test_an_amd_card_is_told_to_use_fsr(self):
  state=self.presenter(vendor=gs.AMD,fsr=True).engine_state()
  self.assertEqual(state['scaling'],'not on this graphics card, so FSR 1 enlarges');self.assertEqual(state['hdr'],'off')
 def test_hdr_on_another_maker_says_what_it_needs(self):
  self.assertEqual(self.presenter(vendor=gs.INTEL,video_hdr=True).engine_state()['hdr'],'needs an NVIDIA RTX graphics card')
  self.assertEqual(self.presenter(vendor=gs.NVIDIA,video_hdr=True).engine_state()['hdr'],'waiting for Windows HDR on this screen')
 def test_a_fault_is_named_by_its_kind_only(self):
  state=self.presenter(vendor=gs.NVIDIA,video_hdr=True,engine_failed='OSError: [WinError -2147024809] details').engine_state()
  self.assertEqual(state,{'scaling':'stopped: OSError','hdr':'stopped: OSError'})
 def test_misses_while_the_engine_draws_stop_it_before_another_frame_in_flight(self):
  p=self.presenter(engine_active=True,timeouts=0,misses=d3d.collections.deque(),cross=False,extra=0)
  for n in range(d3d.MISS_LIMIT):p.missed(now=n*.1)
  self.assertEqual(p.engine_failed,'the screen kept waiting for pictures');self.assertEqual(p.extra,0)
  for n in range(d3d.MISS_LIMIT):p.missed(now=1+n*.1)
  self.assertEqual(p.extra,1)

class SubresourceData(Structure):_fields_=[('Data',c_void_p),('Pitch',ctypes.c_uint),('Slice',ctypes.c_uint)]

@unittest.skipIf(np is None or sys.platform!='win32','needs numpy and Direct3D 11')
class GraphicsCardTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  try:
   cls.device=d3d.new_device();context=c_void_p();d3d.GetImmediateContext(cls.device,byref(context));cls.context=context.value
   blobs=d3d.compiled();cls.owned=[];cls.shaders={}
   vs=c_void_p();d3d.CreateVertexShader(cls.device,blobs[b'vs'],len(blobs[b'vs']),None,byref(vs));cls.owned.append(vs.value)
   for name in (b'deband',b'copy_plane'):shader=c_void_p();d3d.CreatePixelShader(cls.device,blobs[name],len(blobs[name]),None,byref(shader));cls.shaders[name]=shader.value;cls.owned.append(shader.value)
   sampler=c_void_p();d3d.CreateSamplerState(cls.device,byref(d3d.SamplerDesc(Filter=d3d.FILTER_LINEAR,AddressU=d3d.ADDRESS_CLAMP,AddressV=d3d.ADDRESS_CLAMP,AddressW=d3d.ADDRESS_CLAMP,MaxLOD=1000)),byref(sampler));cls.owned.append(sampler.value)
   buffer=c_void_p();d3d.CreateBuffer(cls.device,byref(d3d.BufferDesc(ByteWidth=96,Usage=d3d.USAGE_DYNAMIC,BindFlags=d3d.BIND_CONSTANT,CPUAccessFlags=d3d.CPU_WRITE)),None,byref(buffer));cls.constants=buffer.value;cls.owned.append(buffer.value)
   d3d.VSSetShader(cls.context,vs.value,None,0);d3d.PSSetSamplers(cls.context,0,1,byref(sampler));d3d.PSSetConstantBuffers(cls.context,0,1,byref(buffer));d3d.IASetPrimitiveTopology(cls.context,d3d.TRIANGLES)
  except Exception as error:raise unittest.SkipTest(f'no Direct3D 11 here: {error}')
 @classmethod
 def tearDownClass(cls):
  for pointer in reversed(cls.owned):d3d.Release(pointer)
  d3d.Release(cls.context);d3d.Release(cls.device)
 def setUp(self):self.made=[]
 def tearDown(self):
  for pointer in reversed(self.made):d3d.Release(pointer)
 def texture(self,array,form,bind=None):
  array=np.ascontiguousarray(array);height,width=array.shape[:2];data=SubresourceData(array.ctypes.data,array.strides[0],0);texture=c_void_p()
  d3d.CreateTexture2D(self.device,byref(d3d.Texture2DDesc(Width=width,Height=height,MipLevels=1,ArraySize=1,Format=form,SampleCount=1,BindFlags=bind or d3d.BIND_SHADER)),byref(data),byref(texture));self.made.append(texture.value)
  return texture.value
 def view(self,texture):view=c_void_p();d3d.CreateShaderResourceView(self.device,texture,None,byref(view));self.made.append(view.value);return view.value
 def target(self,width,height,form=None):
  texture=c_void_p();view=c_void_p()
  d3d.CreateTexture2D(self.device,byref(d3d.Texture2DDesc(Width=width,Height=height,MipLevels=1,ArraySize=1,Format=form or d3d.BGRA8,SampleCount=1,BindFlags=d3d.BIND_SHADER|d3d.BIND_TARGET)),None,byref(texture));self.made.append(texture.value)
  d3d.CreateRenderTargetView(self.device,texture.value,None,byref(view));self.made.append(view.value);return texture.value,view.value
 def read(self,texture,width,height):
  staging=c_void_p();desc=d3d.Texture2DDesc();d3d.GetTextureDesc(texture,byref(desc));desc.Usage=d3d.USAGE_STAGING;desc.BindFlags=0;desc.CPUAccessFlags=d3d.CPU_READ
  d3d.CreateTexture2D(self.device,byref(desc),None,byref(staging));d3d.CopySubresourceRegion(self.context,staging.value,0,0,0,0,texture,0,None);mapped=d3d.Mapped();d3d.Map(self.context,staging.value,0,d3d.MAP_READ,0,byref(mapped))
  try:return np.ctypeslib.as_array(ctypes.cast(mapped.Data,ctypes.POINTER(ctypes.c_uint8)),shape=(height*mapped.RowPitch,)).reshape(height,mapped.RowPitch)[:,:width*4].reshape(height,width,4).astype(np.float64)
  finally:d3d.Unmap(self.context,staging.value,0);d3d.Release(staging.value)
 def test_debanding_smooths_steps_of_one_colour_level_and_keeps_an_edge(self):
  width,height=512,64;row=np.zeros(width)
  # Steps of 2 levels every 24 pixels, as an 8-bit sky after compression, then a hard edge from 40 to 200.
  row[:384]=60+2*(np.arange(384)//24);row[384:448]=40;row[448:]=200
  picture=np.zeros((height,width,4),np.uint8);picture[...,:3]=row[None,:,None];picture[...,3]=255
  source=self.view(self.texture(picture,d3d.BGRA8));texture,into=self.target(width,height)
  mapped=d3d.Mapped();d3d.Map(self.context,self.constants,0,d3d.MAP_DISCARD,0,byref(mapped))
  ctypes.memmove(mapped.Data,bytes(80)+ctypes.string_at(ctypes.addressof((ctypes.c_float*4)(d3d.DEBAND_RADIUS,d3d.DEBAND_STEPS/255,0,0)),16),96);d3d.Unmap(self.context,self.constants,0)
  target=c_void_p(into);d3d.OMSetRenderTargets(self.context,1,byref(target),None);d3d.RSSetViewports(self.context,1,byref(d3d.Viewport(0,0,width,height,0,1)))
  d3d.PSSetShader(self.context,self.shaders[b'deband'],None,0);d3d.PSSetShaderResources(self.context,0,1,byref(c_void_p(source)));d3d.Draw(self.context,3,0)
  d3d.PSSetShaderResources(self.context,0,1,byref(c_void_p()));d3d.OMSetRenderTargets(self.context,0,None,None)
  out=self.read(texture,width,height)[...,0].mean(axis=0)
  self.assertLessEqual(np.abs(np.diff(row[24:360])).max(),2)
  # The steps become a slope: no jump between neighbours as large as a step, and the average level stays where it was.
  self.assertLess(np.abs(np.diff(out[24:360])).max(),1.2);self.assertAlmostEqual(out[24:360].mean(),row[24:360].mean(),delta=.6)
  # The edge stays sharp, with the dark side and the bright side as they were.
  self.assertLess(abs(out[440]-40),1);self.assertLess(abs(out[456]-200),1);self.assertGreater(out[449]-out[446],150)
 def test_the_video_engine_draws_an_in_between_picture_letterboxed_into_the_window(self):
  width,height=64,48
  try:engine=gs.VideoEngine(self.device,self.context,gs.vendor_of(self.device));engine.prepare(width,height,128,128,d3d.NV12,False)
  except OSError as error:self.skipTest(f'no video processor here: {error}')
  try:
   # An in-between picture: luma 126 (mid grey in studio range) and neutral chroma, as the in-between shaders leave them.
   luma=self.view(self.texture(np.full((height,width),126,np.uint8),d3d.R8));chroma=self.view(self.texture(np.full((height//2,width//2,2),128,np.uint8),d3d.R8G8))
   output=object.__new__(d3d.D3D11Presenter);output.__dict__.update(device=self.device,context=self.context,shaders=self.shaders,engine=engine,nv12=None,nv12_failed=False)
   source=output.between_source(luma,chroma,(width,height,d3d.NV12))
   if source is None:self.skipTest('this card cannot draw into NV12')
   window,_=self.target(128,128)
   engine.draw(*source,window,(32,40,64,48),(128,128),1,False,False)
   out=self.read(window,128,128)
   # (126-16)*255/219 for each of red, green and blue in the picture, black around it.
   self.assertTrue(np.all(np.abs(out[50:78,40:88,:3]-128.1)<3),out[64,64]);self.assertTrue(np.all(out[:30,:,:3]<2));self.assertTrue(np.all(out[:,:28,:3]<2))
   output.release_nv12()
  finally:engine.release()

if __name__=='__main__':unittest.main()
