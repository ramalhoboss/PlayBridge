"""In-between pictures: the search plan, and on this PC's graphics card the picture half way along a known move."""
import ctypes,os,sys,unittest
from ctypes import byref,c_void_p,Structure
from pathlib import Path
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import in_between as ib

class PlanTests(unittest.TestCase):
 def test_1080p_works_on_8_pixel_cells_down_to_a_level_under_40_rows(self):
  cell,final,sizes=ib.plan(1920,1080)
  self.assertEqual((cell,final),(8,1));self.assertEqual(sizes[0],(1920,1080));self.assertLessEqual(sizes[-1][1],ib.SMALLEST);self.assertGreater(sizes[-2][1],ib.SMALLEST)
  for bigger,smaller in zip(sizes,sizes[1:]):self.assertEqual(smaller,((bigger[0]+1)//2,(bigger[1]+1)//2))
 def test_4k_gets_cells_twice_as_large_so_the_work_stays_about_the_same(self):
  cell,final,sizes=ib.plan(3840,2160);self.assertEqual((cell,final),(16,2));self.assertEqual(ib.cells(sizes[final]),ib.cells(ib.plan(1920,1080)[2][1]))
 def test_each_cell_covers_four_pixels_of_its_level(self):
  self.assertEqual(ib.cells((960,540)),(240,135));self.assertEqual(ib.cells((61,34)),(16,9))
 def test_the_smallest_level_tries_every_vector_in_reach(self):
  self.assertEqual(ib.tries(True,False),(2*ib.RADIUS+1)**2);self.assertEqual(ib.tries(True,True),(2*ib.RADIUS+1)**2+9);self.assertEqual(ib.tries(False,True),ib.STARTS)

try:
 import numpy as np
 import d3d11_presenter as d3d
except Exception:np=None

class SubresourceData(Structure):_fields_=[('Data',c_void_p),('Pitch',ctypes.c_uint),('Slice',ctypes.c_uint)]

@unittest.skipIf(np is None or sys.platform!='win32','needs numpy and Direct3D 11')
class PictureTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  try:
   cls.device=d3d.new_device();context=c_void_p();d3d.GetImmediateContext(cls.device,byref(context));cls.context=context.value
   blobs=d3d.compiled();vs=c_void_p();d3d.CreateVertexShader(cls.device,blobs[b'vs'],len(blobs[b'vs']),None,byref(vs));cls.vs=vs.value
   sampler=c_void_p();d3d.CreateSamplerState(cls.device,byref(d3d.SamplerDesc(Filter=d3d.FILTER_LINEAR,AddressU=d3d.ADDRESS_CLAMP,AddressV=d3d.ADDRESS_CLAMP,AddressW=d3d.ADDRESS_CLAMP,MaxLOD=1000)),byref(sampler));cls.sampler=sampler.value
   d3d.VSSetShader(cls.context,cls.vs,None,0);d3d.PSSetSamplers(cls.context,0,1,byref(sampler));d3d.IASetPrimitiveTopology(cls.context,d3d.TRIANGLES)
   cls.work=ib.InBetween(cls.device,cls.context)
  except Exception as error:raise unittest.SkipTest(f'no Direct3D 11 here: {error}')
  cls.views=[]
 @classmethod
 def tearDownClass(cls):
  cls.work.release()
  for view in cls.views:d3d.Release(view)
  for pointer in (cls.sampler,cls.vs,cls.context):d3d.Release(pointer)
 def texture(self,array,form):
  array=np.ascontiguousarray(array);height,width=array.shape[:2];data=SubresourceData(array.ctypes.data,array.strides[0],0);texture=c_void_p();view=c_void_p()
  d3d.CreateTexture2D(self.device,byref(d3d.Texture2DDesc(Width=width,Height=height,MipLevels=1,ArraySize=1,Format=form,SampleCount=1,BindFlags=d3d.BIND_SHADER)),byref(data),byref(texture))
  d3d.CreateShaderResourceView(self.device,texture.value,None,byref(view));d3d.Release(texture.value);self.views.append(view.value);return view.value
 def frame(self,serial,luma):
  height,width=luma.shape;chroma=np.full((height//2,width//2,2),128,np.uint8)
  return ib.Frame(serial,self.texture(luma,d3d.R8),self.texture(chroma,d3d.R8G8),(width,height),(width,height),(width//2,height//2))
 def read(self,texture,width,height):
  staging=c_void_p();desc=d3d.Texture2DDesc();d3d.GetTextureDesc(texture,byref(desc));desc.Usage=d3d.USAGE_STAGING;desc.BindFlags=0;desc.CPUAccessFlags=d3d.CPU_READ
  d3d.CreateTexture2D(self.device,byref(desc),None,byref(staging));d3d.CopySubresourceRegion(self.context,staging.value,0,0,0,0,texture,0,None);mapped=d3d.Mapped();d3d.Map(self.context,staging.value,0,d3d.MAP_READ,0,byref(mapped))
  try:rows=np.ctypeslib.as_array(ctypes.cast(mapped.Data,ctypes.POINTER(ctypes.c_uint8)),shape=(height*mapped.RowPitch,)).reshape(height,mapped.RowPitch)[:,:width*2].copy().view(np.uint16)
  finally:d3d.Unmap(self.context,staging.value,0);d3d.Release(staging.value)
  return rows.astype(np.float64)*255/65535
 def test_a_picture_moved_by_12_and_6_pixels_shows_half_way_at_6_and_3(self):
  # Soft detail at several scales, as in a game, which moves to the right and down between the two frames.
  rng=np.random.default_rng(3);noise=rng.random((360+64,640+64))
  def blur(a,r):
   c=np.cumsum(np.cumsum(np.pad(a,((r+1,r),(r+1,r)),mode='edge'),0),1);n=2*r+1
   return (c[n:,n:]-c[:-n,n:]-c[n:,:-n]+c[:-n,:-n])/n/n
  scene=sum(blur(noise,r)*w for r,w in ((2,1),(6,2),(14,3)));scene=(scene-scene.min())/(scene.max()-scene.min())*200+28
  def at(dx,dy):return scene[32-dy:32-dy+360,32-dx:32-dx+640]
  a=at(0,0).astype(np.uint8);b=at(12,6).astype(np.uint8);truth=at(6,3)
  luma,_=self.work.render(self.frame(1,a),self.frame(2,b),.5)
  made=self.read(self.work.luma_out[2],640,360);mixed=(a.astype(np.float64)+b)/2
  inner=(slice(24,-24),slice(24,-24))
  def psnr(x):return 10*np.log10(255**2/((x[inner]-truth[inner])**2).mean())
  self.assertGreater(psnr(made),psnr(mixed)+6,(psnr(made),psnr(mixed)));self.assertGreater(psnr(made),30)
 def test_a_still_picture_stays_as_it_is(self):
  rng=np.random.default_rng(4);still=(rng.random((180,320))*200+28).astype(np.uint8)
  self.work.render(self.frame(3,still),self.frame(4,still),.5);made=self.read(self.work.luma_out[2],320,180)
  self.assertLess(np.abs(made-still).max(),2)

if __name__=='__main__':unittest.main()
