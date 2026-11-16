"""The graphics card's own video engine for the picture. NVIDIA RTX Video Super Resolution and Intel's video super resolution enlarge it, and
NVIDIA RTX Video HDR turns it into HDR on a screen with Windows HDR on. Both go through Direct3D 11's video processor, which every card
has, but only NVIDIA's and Intel's drivers take these extensions; on other cards the presenter keeps FSR 1 and its own shaders.
The method tables follow Microsoft's d3d11.h as Wine declares it, and the extension values are the ones Chromium sends."""
import ctypes
from ctypes import POINTER,Structure,byref,c_char_p,c_float,c_long,c_void_p,c_wchar
from ctypes import wintypes
from d3d11_presenter import ANY,BGRA8,HRESULT,IID_DXGI_DEVICE,OUT,UINT,GetAdapter,GetOutputDesc,EnumOutputs,OutputDesc,QueryInterface,Release,adapters,com,iid,window_monitor

BOOL=wintypes.BOOL
IID_VIDEO_DEVICE=iid('10ec4d5b-975a-4689-b9e4-d0aac30fe333');IID_VIDEO_CONTEXT=iid('61f21c45-3c0e-4a74-9cea-67100d9ad5e4');IID_VIDEO_CONTEXT1=iid('a7f026da-a5f8-4487-a564-15e34357651e')
IID_OUTPUT6=iid('068346e8-aaec-4b84-add7-137f513f77a1')
# ID3D11VideoDevice and ID3D11VideoProcessorEnumerator.
CreateVideoProcessor=com(4,HRESULT,ANY,UINT,OUT);CreateInputView=com(8,HRESULT,ANY,ANY,ANY,OUT);CreateOutputView=com(9,HRESULT,ANY,ANY,ANY,OUT);CreateEnumerator=com(10,HRESULT,ANY,OUT)
CheckProcessorFormat=com(8,HRESULT,UINT,POINTER(UINT))
# ID3D11VideoContext. The extension calls return their HRESULT, as a driver that says no is an answer here, not an error.
SetOutputTargetRect=com(13,None,ANY,BOOL,ANY);SetOutputBackgroundColor=com(14,None,ANY,BOOL,ANY);SetOutputColorSpace=com(15,None,ANY,ANY);SetOutputExtension=com(19,c_long,ANY,c_char_p,UINT,ANY)
SetStreamFrameFormat=com(27,None,ANY,UINT,UINT);SetStreamColorSpace=com(28,None,ANY,UINT,ANY);SetStreamSourceRect=com(30,None,ANY,UINT,BOOL,ANY);SetStreamDestRect=com(31,None,ANY,UINT,BOOL,ANY)
SetStreamAutoProcessing=com(37,None,ANY,UINT,BOOL);SetStreamExtension=com(39,c_long,ANY,UINT,c_char_p,UINT,ANY);GetStreamExtension=com(52,c_long,ANY,UINT,c_char_p,UINT,ANY)
Blt=com(53,HRESULT,ANY,ANY,UINT,UINT,ANY)
# ID3D11VideoContext1: colour spaces by their DXGI names, which also cover BT.2020 and HDR10.
SetOutputColorSpace1=com(70,None,ANY,UINT);SetStreamColorSpace1=com(74,None,ANY,UINT,UINT);GetStreamColorSpace1=com(76,None,ANY,UINT,POINTER(UINT))
GetAdapterDesc=com(8,HRESULT,ANY);GetOutputDesc1=com(27,HRESULT,ANY)

class Rational(Structure):_fields_=[('Numerator',UINT),('Denominator',UINT)]
class ContentDesc(Structure):_fields_=[('InputFrameFormat',UINT),('InputFrameRate',Rational),('InputWidth',UINT),('InputHeight',UINT),('OutputFrameRate',Rational),('OutputWidth',UINT),('OutputHeight',UINT),('Usage',UINT)]
class InputViewDesc(Structure):_fields_=[('FourCC',UINT),('ViewDimension',UINT),('MipSlice',UINT),('ArraySlice',UINT)]
class OutputViewDesc(Structure):_fields_=[('ViewDimension',UINT),('MipSlice',UINT),('FirstArraySlice',UINT),('ArraySize',UINT)]
class Stream(Structure):_fields_=[('Enable',BOOL),('OutputIndex',UINT),('InputFrameOrField',UINT),('PastFrames',UINT),('FutureFrames',UINT),('ppPastSurfaces',c_void_p),('pInputSurface',c_void_p),('ppFutureSurfaces',c_void_p),('ppPastSurfacesRight',c_void_p),('pInputSurfaceRight',c_void_p),('ppFutureSurfacesRight',c_void_p)]
class VideoColor(Structure):_fields_=[('R',c_float),('G',c_float),('B',c_float),('A',c_float)]
class AdapterDesc(Structure):_fields_=[('Description',c_wchar*128),('VendorId',UINT),('DeviceId',UINT),('SubSysId',UINT),('Revision',UINT),('DedicatedVideoMemory',ctypes.c_size_t),('DedicatedSystemMemory',ctypes.c_size_t),('SharedSystemMemory',ctypes.c_size_t),('AdapterLuid',UINT*2)]
class OutputDesc1(Structure):_fields_=[('DeviceName',c_wchar*32),('DesktopCoordinates',wintypes.RECT),('AttachedToDesktop',BOOL),('Rotation',UINT),('Monitor',c_void_p),('BitsPerColor',UINT),('ColorSpace',UINT),('RedPrimary',c_float*2),('GreenPrimary',c_float*2),('BluePrimary',c_float*2),('WhitePoint',c_float*2),('MinLuminance',c_float),('MaxLuminance',c_float),('MaxFullFrameLuminance',c_float)]

NVIDIA=0x10de;INTEL=0x8086;AMD=0x1002
# NVIDIA's post-processing interface: version 1, method 2 is super resolution. RTX Video HDR has an interface of its own: version 4, method 3.
NVIDIA_PPE=iid('d43ce1b3-1f4b-48ac-baee-c3c25375e6f7');NVIDIA_TRUE_HDR=iid('fdd62bb4-620b-4fd7-9ab3-1e59d0d544b3')
# Intel's video processing extension: the interface version, the pre-processing mode, then scaling by super resolution.
INTEL_VPE=iid('edd1d4b9-8659-4cbc-a4d6-9831a2163ac3');INTEL_VERSION,INTEL_MODE,INTEL_SCALING=0x01,0x20,0x37;INTEL_VERSION3=3;INTEL_PREPROC=1;INTEL_SUPER_RESOLUTION=2
class IntelExtension(Structure):_fields_=[('Function',UINT),('Param',c_void_p)]

PROGRESSIVE=0;USAGE_NORMAL=0;VIEW_TEXTURE2D=1;FORMAT_INPUT=1;FORMAT_OUTPUT=2;NV12=103;P010=104;RGB10=24
# DXGI colour spaces: the stream's YCbCr, and RGB for an SDR screen or for HDR10.
SDR_OUT=0;HDR10_OUT=12
# Views of decoder surfaces kept at once. A decoder's pool has about twenty, so this only drops ones a new decoder left behind.
MOST_INPUTS=64
NAMES={NVIDIA:'NVIDIA RTX Video Super Resolution',INTEL:'Intel video super resolution'}

def stream_space(colorspace,full_range):
 """The DXGI colour space of the stream, from FFmpeg's colour space number. The console sends BT.709 in limited range."""
 if colorspace in (9,10):return 11 if full_range else 10
 if colorspace in (5,6):return 7 if full_range else 6
 return 9 if full_range else 8
def legacy_space(colorspace,full_range):
 """The same as D3D11_VIDEO_PROCESSOR_COLOR_SPACE, for drivers without the newer call: BT.709 or BT.601, studio or full range."""
 return (0 if colorspace in (5,6) else 1)<<2|(2 if full_range else 1)<<4
def vendor_of(device):
 """The PCI vendor of the card a device is on, or 0 when Windows does not say."""
 dxgi=c_void_p();adapter=c_void_p()
 try:
  QueryInterface(device,IID_DXGI_DEVICE,byref(dxgi));GetAdapter(dxgi.value,byref(adapter));desc=AdapterDesc();GetAdapterDesc(adapter.value,byref(desc));return desc.VendorId
 except OSError:return 0
 finally:
  if adapter.value:Release(adapter.value)
  if dxgi.value:Release(dxgi.value)
def can_enlarge(vendor):
 """Whether a card from this maker has super resolution in its video engine. Others are left to FSR 1."""
 return vendor in NAMES
def screen_hdr(hwnd):
 """True when Windows HDR is on for the screen the window is on: its output then takes HDR10. False when off or when it cannot be asked."""
 monitor=window_monitor(hwnd)
 try:listed=adapters()
 except (AttributeError,OSError):return False
 try:
  for adapter in listed:
   index=0
   while True:
    output=c_void_p()
    try:EnumOutputs(adapter,index,byref(output))
    except OSError:break
    try:
     desc=OutputDesc();GetOutputDesc(output.value,byref(desc))
     if desc.Monitor==monitor:
      newer=c_void_p()
      try:QueryInterface(output.value,IID_OUTPUT6,byref(newer))
      except OSError:return False
      try:full=OutputDesc1();GetOutputDesc1(newer.value,byref(full));return full.ColorSpace==HDR10_OUT
      finally:Release(newer.value)
    finally:Release(output.value)
    index+=1
 finally:
  for adapter in listed:Release(adapter)
 return False

class VideoEngine:
 """The video processor of one device, set up for one picture size and one window size at a time. Every call is on the drawing thread."""
 def __init__(self,device,context,vendor):
  video=c_void_p();QueryInterface(device,IID_VIDEO_DEVICE,byref(video));self.video=video.value
  try:
   plain=c_void_p();QueryInterface(context,IID_VIDEO_CONTEXT,byref(plain));self.context=plain.value
  except OSError:Release(self.video);raise
  newer=c_void_p()
  try:QueryInterface(context,IID_VIDEO_CONTEXT1,byref(newer));self.context1=newer.value
  except OSError:self.context1=None
  self.vendor=vendor;self.enumerator=None;self.processor=None;self.shape=None;self.inputs={};self.outputs={};self.placed=None
  # What the driver took for the processor now: the super resolution's name, and whether RTX Video HDR is on and on offer.
  self.scaling=None;self.hdr_on=False;self.hdr_offered=False
 def release_inputs(self):
  for view in self.inputs.values():Release(view)
  self.inputs={}
 def release_outputs(self):
  """The views of the window's textures, which go each time the swap chain is resized."""
  for view in self.outputs.values():Release(view)
  self.outputs={};self.placed=None
 def release_processor(self):
  self.release_inputs();self.release_outputs()
  for pointer in (self.processor,self.enumerator):
   if pointer:Release(pointer)
  self.processor=self.enumerator=None;self.shape=None;self.scaling=None;self.hdr_on=False;self.hdr_offered=False
 def release(self):
  self.release_processor()
  for pointer in (self.context1,self.context,self.video):
   if pointer:Release(pointer)
  self.context1=self.context=self.video=None
 def takes(self,format,need):
  flags=UINT(0);CheckProcessorFormat(self.enumerator,format,byref(flags));return bool(flags.value&need)
 def prepare(self,width,height,out_width,out_height,source_format,enlarge):
  """A processor for pictures of this size into a window of that size, with the maker's super resolution asked for when enlarge is set.
  Raises when the card's video engine cannot read the decoder's format or draw the window's usual one."""
  shape=(width,height,out_width,out_height,source_format,bool(enlarge))
  if shape==self.shape:return
  self.release_processor()
  desc=ContentDesc(InputFrameFormat=PROGRESSIVE,InputFrameRate=Rational(60,1),InputWidth=width,InputHeight=height,OutputFrameRate=Rational(60,1),OutputWidth=out_width,OutputHeight=out_height,Usage=USAGE_NORMAL)
  enumerator=c_void_p();CreateEnumerator(self.video,byref(desc),byref(enumerator));self.enumerator=enumerator.value
  for format,need in ((source_format,FORMAT_INPUT),(BGRA8,FORMAT_OUTPUT)):
   if not self.takes(format,need):raise RuntimeError(f'The video engine does not take format {format}')
  processor=c_void_p();CreateVideoProcessor(self.video,self.enumerator,0,byref(processor));self.processor=processor.value
  # The driver's own clean-ups stay off: the picture is the console's, as it was made.
  SetStreamAutoProcessing(self.context,self.processor,0,0);SetStreamFrameFormat(self.context,self.processor,0,PROGRESSIVE)
  SetOutputBackgroundColor(self.context,self.processor,0,byref(VideoColor(0,0,0,1)))
  self.shape=shape
  if enlarge:self.scaling=self.ask_scaling()
  # RTX Video HDR draws into 10-bit buffers, which the engine must be able to draw.
  self.hdr_offered=self.vendor==NVIDIA and self.takes(RGB10,FORMAT_OUTPUT) and self.true_hdr_offered()
 def ask_scaling(self):
  """Turns on the maker's super resolution for this processor. Its name when the driver took it, None when it said no."""
  if self.vendor==NVIDIA:
   info=(UINT*3)(1,2,1)
   return NAMES[NVIDIA] if SetStreamExtension(self.context,self.processor,0,NVIDIA_PPE,ctypes.sizeof(info),info)>=0 else None
  if self.vendor==INTEL:
   value=UINT(0);ext=IntelExtension(INTEL_VERSION,ctypes.cast(byref(value),c_void_p))
   for function,param,stream in ((INTEL_VERSION,INTEL_VERSION3,False),(INTEL_MODE,INTEL_PREPROC,False),(INTEL_SCALING,INTEL_SUPER_RESOLUTION,True)):
    ext.Function=function;value.value=param
    result=SetStreamExtension(self.context,self.processor,0,INTEL_VPE,ctypes.sizeof(ext),byref(ext)) if stream else SetOutputExtension(self.context,self.processor,INTEL_VPE,ctypes.sizeof(ext),byref(ext))
    if result<0:return None
   return NAMES[INTEL]
  return None
 def true_hdr_offered(self):
  """Whether NVIDIA's driver offers RTX Video HDR, as it answers for its own interface."""
  offered=UINT(0)
  return GetStreamExtension(self.context,self.processor,0,NVIDIA_TRUE_HDR,ctypes.sizeof(offered),byref(offered))>=0 and offered.value==1
 def set_hdr(self,on):
  """RTX Video HDR on or off for this processor. True when the driver did as asked."""
  if bool(on)==self.hdr_on:return True
  info=(UINT*3)(4,3,1 if on else 0)
  if SetStreamExtension(self.context,self.processor,0,NVIDIA_TRUE_HDR,ctypes.sizeof(info),info)<0:return False
  self.hdr_on=bool(on);return True
 def input_view(self,texture,index):
  key=(texture,index);view=self.inputs.get(key)
  if view is None:
   if len(self.inputs)>=MOST_INPUTS:self.release_inputs()
   made=c_void_p();CreateInputView(self.video,texture,self.enumerator,byref(InputViewDesc(0,VIEW_TEXTURE2D,0,index)),byref(made));view=self.inputs[key]=made.value
  return view
 def output_view(self,texture):
  view=self.outputs.get(texture)
  if view is None:made=c_void_p();CreateOutputView(self.video,texture,self.enumerator,byref(OutputViewDesc(VIEW_TEXTURE2D,0,0,0)),byref(made));view=self.outputs[texture]=made.value
  return view
 def draw(self,texture,index,target,picture,window,colorspace,full_range,hdr):
  """Enlarges slice index of texture into the rectangle picture=(x, y, width, height) of target, a window-sized texture of window=(width, height),
  black around it. hdr: the target is HDR10 and the picture is converted to it."""
  frame_rect=wintypes.RECT(0,0,self.shape[0],self.shape[1]);x,y,width,height=picture
  placed=(picture,window,colorspace,full_range,hdr)
  if placed!=self.placed:
   SetOutputTargetRect(self.context,self.processor,1,byref(wintypes.RECT(0,0,*window)))
   SetStreamSourceRect(self.context,self.processor,0,1,byref(frame_rect));SetStreamDestRect(self.context,self.processor,0,1,byref(wintypes.RECT(x,y,x+width,y+height)))
   if self.context1:SetStreamColorSpace1(self.context1,self.processor,0,stream_space(colorspace,full_range));SetOutputColorSpace1(self.context1,self.processor,HDR10_OUT if hdr else SDR_OUT)
   else:SetStreamColorSpace(self.context,self.processor,0,byref(UINT(legacy_space(colorspace,full_range))));SetOutputColorSpace(self.context,self.processor,byref(UINT(0)))
   self.placed=placed
  stream=Stream(Enable=1,pInputSurface=self.input_view(texture,index))
  Blt(self.context,self.processor,self.output_view(target),0,1,byref(stream))
