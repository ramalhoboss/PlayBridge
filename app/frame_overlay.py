"""Drawing the overlay into a decoded frame before a live stream makes it again. The frame stays in the console's own colours (BT.709,
limited range) and only the overlay's corner of it is touched, so a 4K frame costs about as little as a 1080p one. The overlay's
colours are worked out once each time it changes; each frame then only mixes them in, weighted by the overlay's transparency."""
import ctypes
import av
import numpy as np

KR,KB=.2126,.0722;KG=1-KR-KB
# The overlay's distance from the frame's corner at 1080p, as on screen.
MARGIN=16

def plane_array(plane):
 """A plane of the frame as a writable array, rows by bytes."""
 raw=(ctypes.c_uint8*(plane.line_size*plane.height)).from_address(plane.buffer_ptr)
 return np.ctypeslib.as_array(raw).reshape(plane.height,plane.line_size)

def copy(frame):
 """The frame in a picture of its own, for a frame that other frames are still built on."""
 out=av.VideoFrame(frame.width,frame.height,frame.format.name);out.pts=frame.pts
 for source,target in zip(frame.planes,out.planes):
  rows=min(source.height,target.height);size=min(source.line_size,target.line_size)
  plane_array(target)[:rows,:size]=plane_array(source)[:rows,:size]
 return out

class FrameOverlay:
 def __init__(self):self.image=None;self.parts=None
 def prepare(self,image):
  """(BGRA bytes, width, height) or None, as hud.render gives it, in the frame's colours: luma and chroma already weighted by the
  overlay's transparency, and how much of the frame stays under each of them. Kept until the overlay changes."""
  if image is self.image:return self.parts
  self.image=image
  if image is None:self.parts=None;return None
  data,width,height=image;w,h=width//2*2,height//2*2
  if not w or not h:self.parts=None;return None
  pixels=np.frombuffer(data,np.uint8).reshape(height,width,4)[:h,:w].astype(np.float32)
  b,g,r,a=pixels[...,0],pixels[...,1],pixels[...,2],pixels[...,3]/255
  luma=KR*r+KG*g+KB*b
  y=16+luma*219/255;u=128+(b-luma)/(2*(1-KB))*224/255;v=128+(r-luma)/(2*(1-KR))*224/255
  # Chroma is kept once for every 2 by 2 pixels: their mean, weighted by how much of each the overlay covers.
  def quarter(values):return values.reshape(h//2,2,w//2,2).mean(axis=(1,3))
  self.parts=(y*a,1-a,quarter(u*a),quarter(v*a),1-quarter(a),w,h);return self.parts
 def apply(self,frame,image):
  """Mixes the overlay into the frame's top left corner. frame: an NV12 or YUV420P frame this code may write to. False when it was
  not drawn: no overlay, another pixel format, or a frame too small for it."""
  parts=self.prepare(image)
  if parts is None or frame.format.name not in ('nv12','yuv420p'):return False
  y_part,y_keep,u_part,v_part,c_keep,w,h=parts
  margin=round(MARGIN*max(1,frame.height/1080))//2*2;x0=y0=margin
  if x0+w>frame.width or y0+h>frame.height:return False
  luma=plane_array(frame.planes[0]);region=luma[y0:y0+h,x0:x0+w];region[:]=np.clip(region*y_keep+y_part+.5,0,255).astype(np.uint8)
  cx,cy,cw,ch=x0//2,y0//2,w//2,h//2
  if frame.format.name=='nv12':
   both=plane_array(frame.planes[1])[cy:cy+ch,cx*2:(cx+cw)*2].reshape(ch,cw,2)
   both[...,0]=np.clip(both[...,0]*c_keep+u_part+.5,0,255).astype(np.uint8);both[...,1]=np.clip(both[...,1]*c_keep+v_part+.5,0,255).astype(np.uint8)
  else:
   for index,part in ((1,u_part),(2,v_part)):
    region=plane_array(frame.planes[index])[cy:cy+ch,cx:cx+cw];region[:]=np.clip(region*c_keep+part+.5,0,255).astype(np.uint8)
  return True
 def draw(self,frame,image,own):
  """The frame to encode, with the overlay in it when there is one. own: whether this code may write to the frame; when not, the
  overlay goes on a copy and the frame is left as it was."""
  if self.prepare(image) is None or frame.format.name not in ('nv12','yuv420p'):return frame
  if not own:frame=copy(frame)
  self.apply(frame,image);return frame
