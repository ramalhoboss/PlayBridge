"""Which graphics card decodes the stream, and the stream sizes it can decode, asked of the card the decoder and the video output also use."""
import ctypes,functools
from ctypes import Structure,byref,c_long,c_size_t,c_ubyte,c_void_p,c_wchar
from d3d11_presenter import ANY,NV12,UINT,GetAdapter,QueryInterface,Release,adapters,com,iid,new_device,IID_DXGI_DEVICE

IID_VIDEO_DEVICE=iid('10ec4d5b-975a-4689-b9e4-d0aac30fe333')
H264=iid('1b81be68-a0c7-11d3-b984-00c04f2e73c5')
# The HRESULT is read rather than raised: a card that says no is an answer here, not an error.
GetAdapterDesc=com(8,c_long,ANY);CheckVideoDecoderFormat=com(13,c_long,ANY,UINT,ANY);GetVideoDecoderConfigCount=com(14,c_long,ANY,ANY)
# Each stream size as the decoder is asked for it: 1080 lines are coded as 1088, in whole 16-line blocks.
SIZES={4:(1920,1088),5:(2560,1440),6:(3840,2160)}
NAMES={4:'1080p',5:'1440p',6:'4K'}
VENDORS={0x1002:'AMD',0x10de:'NVIDIA',0x8086:'Intel',0x1414:'Microsoft'}
# Windows' own software renderer, listed as an adapter on every PC.
SOFTWARE=0x1414
AUTOMATIC='auto'

class AdapterDesc(Structure):_fields_=[('Description',c_wchar*128),('VendorId',UINT),('DeviceId',UINT),('SubSysId',UINT),('Revision',UINT),('DedicatedVideoMemory',c_size_t),('DedicatedSystemMemory',c_size_t),('SharedSystemMemory',c_size_t),('AdapterLuid',UINT*2)]
class DecoderDesc(Structure):_fields_=[('Guid',c_ubyte*16),('SampleWidth',UINT),('SampleHeight',UINT),('OutputFormat',UINT)]

def decodes(video,width,height):
 """True when the card offers an H.264 decoder at this size. Drivers answer with no configurations above their largest."""
 desc=DecoderDesc(Guid=(c_ubyte*16)(*H264),SampleWidth=width,SampleHeight=height,OutputFormat=NV12);count=UINT()
 return GetVideoDecoderConfigCount(video,byref(desc),byref(count))>=0 and count.value>0
@functools.lru_cache(maxsize=1)
def cards():
 """The graphics cards Windows lists, in its order, each with its name, maker and memory of its own in MB. Windows' software renderer is left out."""
 found=[]
 try:listed=adapters()
 except (AttributeError,OSError):return ()
 for index,adapter in enumerate(listed):
  try:
   desc=AdapterDesc();GetAdapterDesc(adapter,byref(desc))
   if desc.VendorId!=SOFTWARE:found.append({'index':index,'name':desc.Description.strip() or 'Unknown graphics card','vendor':VENDORS.get(desc.VendorId,f'{desc.VendorId:#06x}'),'memory':desc.DedicatedVideoMemory//2**20})
  except OSError:pass
  finally:Release(adapter)
 return tuple(found)
def automatic(found):
 """The card with the most memory of its own. A laptop with two lists the processor's graphics first, because it drives the screen,
 and Direct3D's default card would be that one rather than the NVIDIA or AMD card."""
 return max(found,key=lambda card:(card['memory'],-card['index']))['index'] if found else None
def choose(wanted,found=None):
 """The place in Windows' list of the card chosen in Settings, by name, or of the automatic one. None on a PC with no card to choose."""
 found=cards() if found is None else found
 return next((card['index'] for card in found if card['name']==wanted),automatic(found))
def label(index,found=None):
 """The name Settings shows for the card at this place, or the automatic choice when it is that."""
 found=cards() if found is None else found
 return next((card['name'] for card in found if card['index']==index),'')
@functools.lru_cache(maxsize=4)
def probe(adapter=None):
 """The card's name and maker, and for each stream resolution whether it decodes it. None where Direct3D 11 cannot start."""
 try:device=new_device(adapter)
 except OSError:return None
 if not device:return None
 dxgi=c_void_p();adapter=c_void_p();video=c_void_p()
 try:
  QueryInterface(device,IID_DXGI_DEVICE,byref(dxgi));GetAdapter(dxgi.value,byref(adapter))
  desc=AdapterDesc();GetAdapterDesc(adapter.value,byref(desc))
  card={'name':desc.Description.strip() or 'Unknown graphics card','vendor':VENDORS.get(desc.VendorId,f'{desc.VendorId:#06x}'),'decodes':{r:False for r in SIZES}}
  # A card with no video decoder, such as Windows' own basic driver, has no video device to ask.
  try:QueryInterface(device,IID_VIDEO_DEVICE,byref(video))
  except OSError:return card
  supported=ctypes.c_int()
  if CheckVideoDecoderFormat(video.value,H264,NV12,byref(supported))<0 or not supported.value:return card
  card['decodes']={r:decodes(video.value,*size) for r,size in SIZES.items()}
  return card
 except OSError:return None
 finally:
  for pointer in (video,adapter,dxgi):
   if pointer.value:Release(pointer.value)
  Release(device)

def largest(card):
 """The largest stream resolution the card decodes, with each smaller one too, or 0."""
 best=0
 for resolution in sorted(SIZES):
  if not (card and card['decodes'].get(resolution)):break
  best=resolution
 return best
def summary(card):
 """One line for Settings: the card, and what it leaves to the processor."""
 if card is None:return 'No graphics card answered, so the processor decodes the video. A 1080p profile is the safe choice.'
 best=largest(card)
 if best==6:return f"Graphics card: {card['name']}. It decodes every profile, up to 4K."
 if best:return f"Graphics card: {card['name']}. It decodes up to {NAMES[best]}. Higher profiles are decoded by the processor, which can stutter."
 return f"Graphics card: {card['name']}. It cannot decode this video, so the processor does. A 1080p profile is the safe choice."
def processor_notice(resolution,card):
 """Said when a 1440p or 4K stream ends up decoded by the processor. Empty where that is expected or harmless."""
 if resolution<5:return ''
 size=NAMES.get(resolution,'this resolution')
 if card is not None and card['decodes'].get(resolution):return f'The graphics card stopped decoding {size}, so the processor took over. If the picture stutters, reconnect or choose a lower profile.'
 return f"This graphics card cannot decode {size}, so the processor is decoding it. If the picture stutters, choose a {NAMES.get(largest(card),'1080p')} profile in Settings."
def report(card):
 """For the stats file and exported diagnostics: the card's model and maker, which say nothing about its owner."""
 if card is None:return {'graphics_card':None,'graphics_vendor':None,'gpu_decodes_up_to':None}
 return {'graphics_card':card['name'],'graphics_vendor':card['vendor'],'gpu_decodes_up_to':NAMES.get(largest(card))}
