"""Direct3D 11 video output. A frame decoded on the GPU reaches the screen without visiting the CPU, and the GPU also converts its colour and scales it."""
import ctypes,struct,uuid
from ctypes import POINTER,WINFUNCTYPE,Structure,byref,c_char_p,c_float,c_size_t,c_uint,c_ulong,c_void_p,sizeof
from ctypes import wintypes
import av

HRESULT=ctypes.HRESULT
def com(index,restype,*arguments):
 """A method from a COM object's table. The object's address is the first argument."""
 prototype=WINFUNCTYPE(restype,c_void_p,*arguments)
 def call(this,*values):
  table=c_void_p.from_address(this).value
  return prototype(c_void_p.from_address(table+index*sizeof(c_void_p)).value)(this,*values)
 return call
def iid(text):return uuid.UUID(text).bytes_le
OUT=POINTER(c_void_p);ANY=c_void_p;UINT=c_uint
IID_DXGI_DEVICE=iid('54ec77fa-1377-44e6-8c32-88fd5f44c84c');IID_FACTORY2=iid('50c83a1c-e072-4c48-87b0-3630fa36a6d0');IID_SWAP2=iid('a8be2ac4-199f-4946-b331-79599fb98de7');IID_TEXTURE=iid('6f15aaf2-d208-4e89-9ab4-489535d34f9c')
QueryInterface=com(0,HRESULT,c_char_p,OUT);Release=com(2,c_ulong)
GetDeviceOfChild=com(3,None,OUT);GetTextureDesc=com(10,None,ANY)
CreateBuffer=com(3,HRESULT,ANY,ANY,OUT);CreateTexture2D=com(5,HRESULT,ANY,ANY,OUT);CreateShaderResourceView=com(7,HRESULT,ANY,ANY,OUT);CreateRenderTargetView=com(9,HRESULT,ANY,ANY,OUT);CreateVertexShader=com(12,HRESULT,ANY,c_size_t,ANY,OUT);CreatePixelShader=com(15,HRESULT,ANY,c_size_t,ANY,OUT);CreateSamplerState=com(23,HRESULT,ANY,OUT);GetImmediateContext=com(40,None,OUT)
PSSetShaderResources=com(8,None,UINT,UINT,ANY);PSSetShader=com(9,None,ANY,ANY,UINT);PSSetSamplers=com(10,None,UINT,UINT,ANY);VSSetShader=com(11,None,ANY,ANY,UINT);Draw=com(13,None,UINT,UINT);Map=com(14,HRESULT,ANY,UINT,UINT,UINT,ANY);Unmap=com(15,None,ANY,UINT);PSSetConstantBuffers=com(16,None,UINT,UINT,ANY);IASetPrimitiveTopology=com(24,None,UINT);OMSetRenderTargets=com(33,None,UINT,ANY,ANY);RSSetViewports=com(44,None,UINT,ANY);CopySubresourceRegion=com(46,None,ANY,UINT,UINT,UINT,UINT,ANY,UINT,ANY);ClearRenderTargetView=com(50,None,ANY,ANY);ClearState=com(110,None);Flush=com(111,None)
GetParent=com(6,HRESULT,c_char_p,OUT);GetAdapter=com(7,HRESULT,OUT);MakeWindowAssociation=com(8,HRESULT,wintypes.HWND,UINT);CreateSwapChainForHwnd=com(15,HRESULT,ANY,wintypes.HWND,ANY,ANY,ANY,OUT)
Present=com(8,HRESULT,UINT,UINT);GetBuffer=com(9,HRESULT,UINT,c_char_p,OUT);ResizeBuffers=com(13,HRESULT,UINT,UINT,UINT,UINT,UINT);SetMaximumFrameLatency=com(31,HRESULT,UINT);GetFrameLatencyWaitableObject=com(33,wintypes.HANDLE)
GetBlobPointer=com(3,c_void_p);GetBlobSize=com(4,c_size_t)

class Texture2DDesc(Structure):_fields_=[('Width',UINT),('Height',UINT),('MipLevels',UINT),('ArraySize',UINT),('Format',UINT),('SampleCount',UINT),('SampleQuality',UINT),('Usage',UINT),('BindFlags',UINT),('CPUAccessFlags',UINT),('MiscFlags',UINT)]
class SwapChainDesc1(Structure):_fields_=[('Width',UINT),('Height',UINT),('Format',UINT),('Stereo',wintypes.BOOL),('SampleCount',UINT),('SampleQuality',UINT),('BufferUsage',UINT),('BufferCount',UINT),('Scaling',UINT),('SwapEffect',UINT),('AlphaMode',UINT),('Flags',UINT)]
class ViewDesc(Structure):_fields_=[('Format',UINT),('ViewDimension',UINT),('MostDetailedMip',UINT),('MipLevels',UINT),('Unused',UINT*2)]
class BufferDesc(Structure):_fields_=[('ByteWidth',UINT),('Usage',UINT),('BindFlags',UINT),('CPUAccessFlags',UINT),('MiscFlags',UINT),('StructureByteStride',UINT)]
class SamplerDesc(Structure):_fields_=[('Filter',UINT),('AddressU',UINT),('AddressV',UINT),('AddressW',UINT),('MipLODBias',c_float),('MaxAnisotropy',UINT),('ComparisonFunc',UINT),('BorderColor',c_float*4),('MinLOD',c_float),('MaxLOD',c_float)]
class Mapped(Structure):_fields_=[('Data',c_void_p),('RowPitch',UINT),('DepthPitch',UINT)]
class Viewport(Structure):_fields_=[('X',c_float),('Y',c_float),('Width',c_float),('Height',c_float),('MinDepth',c_float),('MaxDepth',c_float)]

BGRA8=87;R8=61;R8G8=49;NV12=103;P010=104;R16=56;R16G16=35
USAGE_DEFAULT=0;USAGE_DYNAMIC=2;USAGE_STAGING=3
BIND_CONSTANT=4;BIND_SHADER=8;BIND_TARGET=0x20
CPU_WRITE=0x10000;CPU_READ=0x20000;MAP_READ=1;MAP_DISCARD=4
TEXTURE2D_VIEW=4;TRIANGLES=4;FILTER_LINEAR=0x15;ADDRESS_CLAMP=3;LEVEL_SDK=7;DRIVER_HARDWARE=1;DEVICE_VIDEO=0x800
FLIP_DISCARD=4;SCALING_STRETCH=0;ALPHA_IGNORE=3;TARGET_OUTPUT=0x20;FRAME_LATENCY_WAITABLE=64;NO_WINDOW_CHANGES=1
# The most a frame may wait for the screen. Longer would hold up the clock this runs on.
WAIT_MS=15
VIEWS={NV12:(R8,R8G8),P010:(R16,R16G16)}
# Each plane's texture format and how much smaller than the picture it is.
PLANES={'yuv420p':((R8,1),(R8,2),(R8,2)),'yuvj420p':((R8,1),(R8,2),(R8,2)),'nv12':((R8,1),(R8G8,2))}
CUBIC,BOX=0,1
BLACK=(c_float*4)(0,0,0,1)

SHADERS=b"""
cbuffer Picture:register(b0){float2 size;float2 ratio;float4 rows[3];int luma_filter;int chroma_filter;int interleaved;int unused;};
Texture2D luma:register(t0);Texture2D blue:register(t1);Texture2D red:register(t2);SamplerState smooth:register(s0);
struct Pixel{float4 at:SV_Position;float2 uv:TEXCOORD0;};
Pixel vs(uint id:SV_VertexID){Pixel p;p.uv=float2(id<<1&2,id&2);p.at=float4(p.uv*float2(2,-2)+float2(-1,1),0,1);return p;}
// Every texel under the screen pixel, each by how much of it lies there. The same as the area scaler on the CPU.
float4 box(Texture2D t,float2 c,float2 r,int2 last){
 float2 lo=c-r/2,hi=c+r/2;float4 sum=0;
 [loop]for(int y=floor(lo.y);y<ceil(hi.y);y++){
  float wy=min(y+1,hi.y)-max(y,lo.y);
  [loop]for(int x=floor(lo.x);x<ceil(hi.x);x++)sum+=t.Load(int3(clamp(int2(x,y),0,last),0))*(min(x+1,hi.x)-max(x,lo.x))*wy;
 }
 return sum/(r.x*r.y);
}
float kernel(float x){x=abs(x);return x<1?x*x*(1.4*x-2.4)+1:x<2?.6*(x*(x*(5-x)-8)+4):0;}
// The CPU's bicubic, for enlarging and for small reductions, where it widens with the ratio so no texel is skipped. At one texel per pixel it returns the texels unchanged.
float4 cubic(Texture2D t,float2 c,float2 r,int2 last){
 float2 s=max(r,1),lo=ceil(c-2*s-.5),hi=floor(c+2*s-.5);float4 sum=0;float total=0;
 [loop]for(int y=lo.y;y<=hi.y;y++){
  float wy=kernel((y+.5-c.y)/s.y);
  [loop]for(int x=lo.x;x<=hi.x;x++){float w=kernel((x+.5-c.x)/s.x)*wy;sum+=t.Load(int3(clamp(int2(x,y),0,last),0))*w;total+=w;}
 }
 return sum/total;
}
float4 ps(Pixel p):SV_Target{
 float2 c=p.uv*size,cc=c/2,cr=ratio/2;int2 last=int2(size)-1,chroma_last=(int2(size)+1)/2-1;float4 y;
 if(luma_filter)y=box(luma,c,ratio,last);else y=cubic(luma,c,ratio,last);
 float u,v;float2 d;blue.GetDimensions(d.x,d.y);
 if(interleaved){float4 uv=chroma_filter?box(blue,cc,cr,chroma_last):blue.SampleLevel(smooth,cc/d,0);u=uv.r;v=uv.g;}
 else if(chroma_filter){u=box(blue,cc,cr,chroma_last).r;v=box(red,cc,cr,chroma_last).r;}
 else{u=blue.SampleLevel(smooth,cc/d,0).r;v=red.SampleLevel(smooth,cc/d,0).r;}
 float4 pixel=float4(y.r,u,v,1);return float4(dot(rows[0],pixel),dot(rows[1],pixel),dot(rows[2],pixel),1);
}
// After AMD's contrast adaptive sharpening: least where neighbours already reach the limits, so edges do not ring.
float4 sharpen(Pixel p):SV_Target{
 int3 at=int3(p.at.xy,0);float3 c=luma.Load(at).rgb,n=luma.Load(at,int2(0,-1)).rgb,s=luma.Load(at,int2(0,1)).rgb,w=luma.Load(at,int2(-1,0)).rgb,e=luma.Load(at,int2(1,0)).rgb;
 float3 low=min(c,min(n,min(s,min(w,e)))),high=max(c,max(n,max(s,max(w,e))));float3 amount=sqrt(saturate(min(low,1-high)/max(high,.0001)))*-.16;
 return float4(saturate((c+(n+s+w+e)*amount)/(1+4*amount)),1);
}
"""

def colour_rows(colorspace,full_range):
 """What turns (Y,U,V,1) into each of R, G and B, with values from 0 to 1. The console always sends BT.709 limited range."""
 kr,kb={5:(.299,.114),6:(.299,.114),9:(.2627,.0593),10:(.2627,.0593)}.get(colorspace,(.2126,.0722));kg=1-kr-kb
 ys,cs,yo=(1,1,0) if full_range else (255/219,255/224,16/255);co=128/255
 ru=0;rv=cs*2*(1-kr);gu=-cs*2*(1-kb)*kb/kg;gv=-cs*2*(1-kr)*kr/kg;bu=cs*2*(1-kb);bv=0
 return tuple((ys,u,v,-ys*yo-(u+v)*co) for u,v in ((ru,rv),(gu,gv),(bu,bv)))
def fitted(width,height,window_width,window_height):
 """Where a picture goes in the window, keeping its shape: x, y, width, height."""
 scale=min(window_width/width,window_height/height);shown_width=max(1,int(width*scale));shown_height=max(1,int(height*scale))
 return (window_width-shown_width)//2,(window_height-shown_height)//2,shown_width,shown_height
def luma_filter(ratio):
 # From half size down the area filter keeps the most detail, as it does on the CPU in video_convert.
 return BOX if ratio>=1.999 else CUBIC
def surface_of(frame):
 """A GPU frame's texture and its slice. The list of planes stops at a zero, and slice zero is one."""
 planes=frame.planes;return planes[0].buffer_ptr,planes[1].buffer_ptr if len(planes)>1 else 0
def to_system(frame):
 """A copy in ordinary memory of a frame held on the GPU, for a screenshot. FFmpeg's device takes calls from any thread."""
 texture,index=surface_of(frame);device=c_void_p();context=c_void_p();staging=c_void_p();desc=Texture2DDesc();GetDeviceOfChild(texture,byref(device));GetImmediateContext(device.value,byref(context));GetTextureDesc(texture,byref(desc))
 desc.Usage=USAGE_STAGING;desc.BindFlags=0;desc.CPUAccessFlags=CPU_READ;desc.ArraySize=1;desc.MiscFlags=0
 try:
  CreateTexture2D(device.value,byref(desc),None,byref(staging));CopySubresourceRegion(context.value,staging.value,0,0,0,0,texture,index,None)
  mapped=Mapped();Map(context.value,staging.value,0,MAP_READ,0,byref(mapped))
  try:
   copy=av.VideoFrame(frame.width,frame.height,'nv12');copy.colorspace=frame.colorspace;copy.color_range=frame.color_range;copy.pts=frame.pts
   for plane,start,rows in ((copy.planes[0],0,frame.height),(copy.planes[1],mapped.RowPitch*desc.Height,(frame.height+1)//2)):
    for row in range(rows):ctypes.memmove(plane.buffer_ptr+row*plane.line_size,mapped.Data+start+row*mapped.RowPitch,min(plane.line_size,mapped.RowPitch))
  finally:Unmap(context.value,staging.value,0)
 finally:
  if staging.value:Release(staging.value)
  Release(context.value);Release(device.value)
 return copy

def compiled():
 compiler=ctypes.WinDLL('d3dcompiler_47');compile_source=compiler.D3DCompile;compile_source.restype=ctypes.HRESULT
 compile_source.argtypes=[c_char_p,c_size_t,c_char_p,c_void_p,c_void_p,c_char_p,c_char_p,UINT,UINT,OUT,OUT]
 blobs={}
 for name,target in ((b'vs',b'vs_5_0'),(b'ps',b'ps_5_0'),(b'sharpen',b'ps_5_0')):
  code=c_void_p();errors=c_void_p()
  try:compile_source(SHADERS,len(SHADERS),None,None,None,name,target,1<<15,0,byref(code),byref(errors))
  except OSError as error:raise RuntimeError(ctypes.string_at(GetBlobPointer(errors.value),GetBlobSize(errors.value)).decode(errors='replace') if errors.value else str(error)) from error
  blobs[name]=ctypes.string_at(GetBlobPointer(code.value),GetBlobSize(code.value));Release(code.value)
 return blobs
def new_device():
 library=ctypes.WinDLL('d3d11');create=library.D3D11CreateDevice;create.restype=ctypes.HRESULT;create.argtypes=[c_void_p,UINT,c_void_p,UINT,c_void_p,UINT,UINT,OUT,c_void_p,c_void_p]
 device=c_void_p();create(None,DRIVER_HARDWARE,None,DEVICE_VIDEO,None,0,LEVEL_SDK,byref(device),None,None);return device.value

class D3D11Presenter:
 """Draws on the thread of the refresh clock. Only resizing and hiding involve the window's own thread, which never waits for this one."""
 def __init__(self,window,sharpen=False):
  self.hwnd=window.winfo_id();self.frame=None;self.failed=None;self.failures=0;self.sharpen=sharpen;self.wanted=(max(1,window.winfo_width()),max(1,window.winfo_height()));self.pending=False
  self.kernel=ctypes.WinDLL('kernel32');self.kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];self.kernel.WaitForSingleObject.restype=wintypes.DWORD
  # Both fail here, in the window's thread, where the app can still choose the other output.
  self.blobs=compiled();self.own=new_device();self.forget()
 def forget(self):
  self.device=None;self.context=None;self.swap=None;self.target=None;self.back=None;self.scaled=None;self.scaled_view=None;self.size=None;self.waitable=None;self.owned=[];self.surface=None;self.surface_shape=None;self.planes=None;self.plane_shape=None;self.views=None;self.arranged=None;self.viewport=None
 def keep(self,pointer):
  self.owned.append(pointer.value);return pointer.value
 def attach(self,device):
  """Takes over a reference to the device. A new decoder brings a new device, and the swap chain has to live on the decoder's."""
  self.detach();self.device=device;context=c_void_p();GetImmediateContext(device,byref(context));self.context=context.value
  shader=c_void_p();CreateVertexShader(device,self.blobs[b'vs'],len(self.blobs[b'vs']),None,byref(shader));self.vertex_shader=self.keep(shader)
  shader=c_void_p();CreatePixelShader(device,self.blobs[b'ps'],len(self.blobs[b'ps']),None,byref(shader));self.pixel_shader=self.keep(shader)
  shader=c_void_p();CreatePixelShader(device,self.blobs[b'sharpen'],len(self.blobs[b'sharpen']),None,byref(shader));self.sharpen_shader=self.keep(shader)
  sampler=c_void_p();CreateSamplerState(device,byref(SamplerDesc(Filter=FILTER_LINEAR,AddressU=ADDRESS_CLAMP,AddressV=ADDRESS_CLAMP,AddressW=ADDRESS_CLAMP,MaxLOD=1000)),byref(sampler));self.keep(sampler)
  buffer=c_void_p();CreateBuffer(device,byref(BufferDesc(ByteWidth=96,Usage=USAGE_DYNAMIC,BindFlags=BIND_CONSTANT,CPUAccessFlags=CPU_WRITE)),None,byref(buffer));self.constants=self.keep(buffer)
  VSSetShader(self.context,self.vertex_shader,None,0);PSSetSamplers(self.context,0,1,byref(sampler));PSSetConstantBuffers(self.context,0,1,byref(buffer));IASetPrimitiveTopology(self.context,TRIANGLES)
 def detach(self):
  """A window takes one flip swap chain at a time, and the old one goes only once its device has been cleared and flushed."""
  if self.context:
   ClearState(self.context);self.release_target()
   for pointer in reversed(self.owned):Release(pointer)
   if self.swap:Release(self.swap)
   if self.surface:self.release_surface()
   if self.planes:self.release_planes()
   Flush(self.context);Release(self.context)
  if self.device and self.device!=self.own:Release(self.device)
  self.forget()
 def open_swap_chain(self):
  width,height=self.wanted;desc=SwapChainDesc1(Width=width,Height=height,Format=BGRA8,SampleCount=1,BufferUsage=TARGET_OUTPUT,BufferCount=2,Scaling=SCALING_STRETCH,SwapEffect=FLIP_DISCARD,AlphaMode=ALPHA_IGNORE,Flags=FRAME_LATENCY_WAITABLE)
  dxgi=c_void_p();adapter=c_void_p();factory=c_void_p();first=c_void_p();swap=c_void_p()
  QueryInterface(self.device,IID_DXGI_DEVICE,byref(dxgi));GetAdapter(dxgi.value,byref(adapter));GetParent(adapter.value,IID_FACTORY2,byref(factory))
  try:
   CreateSwapChainForHwnd(factory.value,self.device,self.hwnd,byref(desc),None,None,byref(first))
   MakeWindowAssociation(factory.value,self.hwnd,NO_WINDOW_CHANGES);QueryInterface(first.value,IID_SWAP2,byref(swap));Release(first.value)
  finally:Release(factory.value);Release(adapter.value);Release(dxgi.value)
  self.swap=swap.value;SetMaximumFrameLatency(self.swap,1);self.waitable=GetFrameLatencyWaitableObject(self.swap);self.size=self.wanted;self.open_target()
 def open_target(self):
  back=c_void_p();view=c_void_p();GetBuffer(self.swap,0,IID_TEXTURE,byref(back));CreateRenderTargetView(self.device,back.value,None,byref(view));self.back=back.value;self.target=view.value;self.arranged=None
  width,height=self.size;texture=c_void_p();shown=c_void_p();drawn=c_void_p()
  CreateTexture2D(self.device,byref(Texture2DDesc(Width=width,Height=height,MipLevels=1,ArraySize=1,Format=BGRA8,SampleCount=1,BindFlags=BIND_SHADER|BIND_TARGET)),None,byref(texture))
  CreateRenderTargetView(self.device,texture.value,None,byref(drawn));CreateShaderResourceView(self.device,texture.value,None,byref(shown));Release(texture.value);self.scaled=drawn.value;self.scaled_view=shown.value
 def release_target(self):
  for pointer in (self.scaled_view,self.scaled,self.target,self.back):
   if pointer:Release(pointer)
  self.scaled_view=self.scaled=self.target=self.back=None
 def fit(self):
  """The swap chain, at the size the window has now. Until a new frame comes the system stretches the old one, so a resize never shows black."""
  if self.swap is None:self.open_swap_chain()
  elif self.size!=self.wanted:
   OMSetRenderTargets(self.context,0,None,None);self.release_target();Flush(self.context);ResizeBuffers(self.swap,0,*self.wanted,0,FRAME_LATENCY_WAITABLE);self.size=self.wanted;self.open_target()
 def release_surface(self):
  for pointer in self.surface:Release(pointer)
  self.surface=None;self.surface_shape=None
 def release_planes(self):
  for pointer in self.planes:Release(pointer)
  self.planes=None;self.plane_shape=None
 def copy_surface(self,texture,index):
  # Decoder surfaces cannot be read by shaders, but this copy stays on the GPU.
  desc=Texture2DDesc();GetTextureDesc(texture,byref(desc));shape=(desc.Width,desc.Height,desc.Format)
  if shape!=self.surface_shape:
   if desc.Format not in VIEWS:raise RuntimeError('Unsupported surface format')
   if self.surface:self.release_surface()
   copy=c_void_p();luma=c_void_p();chroma=c_void_p()
   CreateTexture2D(self.device,byref(Texture2DDesc(Width=desc.Width,Height=desc.Height,MipLevels=1,ArraySize=1,Format=desc.Format,SampleCount=1,BindFlags=BIND_SHADER)),None,byref(copy))
   first,second=VIEWS[desc.Format]
   CreateShaderResourceView(self.device,copy.value,byref(ViewDesc(Format=first,ViewDimension=TEXTURE2D_VIEW,MipLevels=1)),byref(luma));CreateShaderResourceView(self.device,copy.value,byref(ViewDesc(Format=second,ViewDimension=TEXTURE2D_VIEW,MipLevels=1)),byref(chroma))
   self.surface=(chroma.value,luma.value,copy.value);self.surface_shape=shape;self.views=(c_void_p*3)(luma.value,chroma.value,chroma.value);self.arranged=None
  CopySubresourceRegion(self.context,self.surface[2],0,0,0,0,texture,index,None)
 def upload(self,frame):
  # Software decoding: the planes go up as they are, and the rest of the work is still the GPU's.
  name=frame.format.name
  if name not in PLANES:frame=frame.reformat(format='yuv420p');name='yuv420p'
  shape=(frame.width,frame.height,name)
  if shape!=self.plane_shape:
   if self.planes:self.release_planes()
   made=[];views=[]
   for layout,shrink in PLANES[name]:
    texture=c_void_p();view=c_void_p();CreateTexture2D(self.device,byref(Texture2DDesc(Width=(frame.width+shrink-1)//shrink,Height=(frame.height+shrink-1)//shrink,MipLevels=1,ArraySize=1,Format=layout,SampleCount=1,Usage=USAGE_DYNAMIC,BindFlags=BIND_SHADER,CPUAccessFlags=CPU_WRITE)),None,byref(texture));CreateShaderResourceView(self.device,texture.value,None,byref(view));made+=[texture.value,view.value];views.append(view.value)
   self.planes=made;self.plane_shape=shape;self.views=(c_void_p*3)(views[0],views[1],views[-1]);self.arranged=None
  for number,(layout,shrink) in enumerate(PLANES[name]):
   source=frame.planes[number];texture=self.planes[number*2];mapped=Mapped();rows=(frame.height+shrink-1)//shrink;Map(self.context,texture,0,MAP_DISCARD,0,byref(mapped))
   if mapped.RowPitch==source.line_size:ctypes.memmove(mapped.Data,source.buffer_ptr,rows*source.line_size)
   else:
    for row in range(rows):ctypes.memmove(mapped.Data+row*mapped.RowPitch,source.buffer_ptr+row*source.line_size,min(source.line_size,mapped.RowPitch))
   Unmap(self.context,texture,0)
 def arrange(self,frame,interleaved):
  """Sets where the picture goes and how it is filtered, when any of that has changed."""
  key=(frame.width,frame.height,frame.colorspace,frame.color_range,interleaved,self.size)
  if key==self.arranged:return
  x,y,width,height=fitted(frame.width,frame.height,*self.size);across=frame.width/width;down=frame.height/height;ratio=max(across,down);rows=colour_rows(frame.colorspace,frame.color_range==2)
  data=struct.pack('<16f4i',frame.width,frame.height,across,down,*rows[0],*rows[1],*rows[2],luma_filter(ratio),int(ratio>2.001),int(interleaved),0)
  mapped=Mapped();Map(self.context,self.constants,0,MAP_DISCARD,0,byref(mapped));ctypes.memmove(mapped.Data,data,len(data));Unmap(self.context,self.constants,0)
  self.viewport=Viewport(x,y,width,height,0,1);self.whole=Viewport(0,0,self.size[0],self.size[1],0,1);self.arranged=key
 def show(self,frame):
  on_gpu=frame.format.name=='d3d11'
  if on_gpu:
   texture,index=surface_of(frame);device=c_void_p();GetDeviceOfChild(texture,byref(device))
   if device.value==self.device:Release(device.value)
   else:self.attach(device.value)
  elif self.device!=self.own:self.attach(self.own)
  self.fit()
  if self.kernel.WaitForSingleObject(self.waitable,WAIT_MS):self.pending=True;return False
  self.pending=False
  if on_gpu:self.copy_surface(texture,index)
  else:self.upload(frame)
  self.arrange(frame,on_gpu or frame.format.name=='nv12')
  context=self.context;first=c_void_p(self.scaled if self.sharpen else self.target)
  OMSetRenderTargets(context,1,byref(first),None);ClearRenderTargetView(context,first,BLACK);RSSetViewports(context,1,byref(self.viewport));PSSetShader(context,self.pixel_shader,None,0);PSSetShaderResources(context,0,3,self.views);Draw(context,3,0)
  if self.sharpen:
   last=c_void_p(self.target);view=c_void_p(self.scaled_view);empty=c_void_p()
   OMSetRenderTargets(context,1,byref(last),None);RSSetViewports(context,1,byref(self.whole));PSSetShader(context,self.sharpen_shader,None,0);PSSetShaderResources(context,0,1,byref(view));Draw(context,3,0);PSSetShaderResources(context,0,1,byref(empty))
  self.present();return True
 def present(self):Present(self.swap,1,0)
 def attempt(self,frame):
  try:
   shown=self.show(frame);self.failures=0;return shown
  except Exception as error:
   # A lost device takes everything with it, including ours, and the next frame starts over. Only a fault that keeps coming ends this output.
   self.failures+=1
   if self.failures>=3:self.failed=error
   try:self.detach()
   except Exception:self.forget()
   return False
 def draw(self,frame):
  """True once the frame is on its way to the screen."""
  self.frame=frame;return self.attempt(frame)
 def refresh(self):
  frame=self.frame
  if frame is not None and (self.pending or self.wanted!=self.size):self.attempt(frame)
