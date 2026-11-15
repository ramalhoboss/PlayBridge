"""In-between pictures. On a screen faster than the stream, as 60 fps on a 120 or 144 Hz screen, the graphics card makes the pictures the
stream lacks from the motion between the two frames around them, so the motion looks as smooth as the screen can show it.

Two frames give a field of motion vectors, found on smaller copies of their brightness first and then on finer ones, each cell starting
from the vectors of the cells around it, of the cell before it in the last pair and of no motion at all. The vectors are found from the
middle in time, so each cell of the picture to be made has one, with no holes to fill. Each pixel then takes the vectors of the cells
around it, weighs them by how well the two frames agree along them, and mixes the two frames there. Where they agree nowhere, as in a
fade, at something that comes into view or at a cut, it mixes the two frames where they are: a vector that fits nothing would show
pieces of the wrong place.

Every vector a cell tries gets a pixel of its own and a later pass picks the best, so the card works on all of them at once.

The picture comes out as brightness and colour planes at the frame's own size, like a decoded frame, so the presenter scales,
sharpens and enlarges it exactly as it does a real one."""
import ctypes,struct
from ctypes import byref,c_char_p,c_size_t,c_void_p
import d3d11_presenter as d3d

R16F=54;R16=56;R16G16=35;R32F=41;RGBA32F=2;RGBA16F=10
# Search radius on the smallest copy, in its pixels: 4 there is about 6 % of the picture's width per frame.
RADIUS=4
# How much a vector straying from its neighbours' costs, per pixel of the level it is found on, against the mean brightness difference.
LAMBDA=.002
# Brightness disagreement (0 to 1) from which a pixel starts to mix the frames where they are instead of along its vectors, and from
# which it only does that.
AGREE=.06;DISAGREE=.15
# How sharply each pixel prefers the vectors that agree best over the others.
PREFER=.015
# How much better than no motion a vector must agree before a pixel follows it, so still text and noise do not wander.
STILL=.004
# The smallest copy is no taller than this: with the radius, vectors reach about 12 % of the picture's height a frame.
SMALLEST=40
# Vectors each cell tries from the level below: five from there, the last pair's and none.
STARTS=7

SHADERS=b"""
struct Pixel{float4 at:SV_Position;float2 uv:TEXCOORD0;};
SamplerState smooth:register(s0);
cbuffer Motion:register(b2){float2 lsize;float2 tsize;float2 grid;float2 cgrid;float2 pgrid;float cell;float ccell;float pcell;float cscale;float tscale;float radius;float lambda;float stride;int first;int use_past;int subpixel;int count;int spare1;int spare2;};
Texture2D<float> fa:register(t0);Texture2D<float> fb:register(t1);Texture2D<float4> coarse:register(t2);Texture2D<float4> past:register(t3);
Texture2D<float> costs:register(t4);Texture2D<float4> chosen:register(t5);
// Half the size: each pixel the mean of four.
float half_size(Pixel p):SV_Target{
 int2 o=int2(p.at.xy)*2,last=int2(lsize)-1;
 return .25*(fa.Load(int3(min(o,last),0))+fa.Load(int3(min(o+int2(1,0),last),0))+fa.Load(int3(min(o+int2(0,1),last),0))+fa.Load(int3(min(o+1,last),0)));
}
float level(Texture2D<float> t,float2 q){return t.SampleLevel(smooth,clamp(q,.5,lsize-.5)/tsize,0);}
// How much the two frames disagree over 8x8 points around c, each moved half the vector the other way: the middle in time.
float cost(float2 c,float2 v){
 float2 h=v*.5;float s=0;
 [loop]for(int y=0;y<8;y++)[loop]for(int x=0;x<8;x++){float2 q=c+(float2(x,y)-3.5)*stride;s+=abs(level(fa,q-h)-level(fb,q+h));}
 return s/64;
}
float2 centre(int2 g){return (g+.5)*cell;}
float2 past_vector(float2 c){return use_past?past.Load(int3(clamp(int2(c/pcell),0,int2(pgrid)-1),0)).xy*tscale:0;}
float2 coarse_vector(int2 at){return coarse.Load(int3(clamp(at,0,int2(cgrid)-1),0)).xy*cscale;}
// The vector a cell should stay near: its cell's on the level below.
float2 reference(int2 g){return first?0:coarse_vector(int2(centre(g)/ccell));}
// The k-th vector a cell starts from. On the smallest copy: every vector within the radius, then around the last pair's.
float2 start(int2 g,int k){
 float2 c=centre(g);
 if(first){
  int side=int(2*radius+1);
  if(k<side*side)return float2(k%side,k/side)-radius;
  k-=side*side;return round(past_vector(c))+float2(k%3-1,k/3-1);
 }
 int2 at=int2(c/ccell);
 if(k==0)return coarse_vector(at);if(k==1)return coarse_vector(at+int2(1,0));if(k==2)return coarse_vector(at-int2(1,0));
 if(k==3)return coarse_vector(at+int2(0,1));if(k==4)return coarse_vector(at-int2(0,1));if(k==5)return past_vector(c);return 0;
}
float try_start(Pixel p):SV_Target{int2 at=int2(p.at.xy);int2 g=int2(at.x/count,at.y);return cost(centre(g),start(g,at.x%count));}
float4 pick_start(Pixel p):SV_Target{
 int2 g=int2(p.at.xy);float2 ref=reference(g),best=0;float low=1e9,raw=0;
 [loop]for(int k=0;k<count;k++){float2 v=start(g,k);float r=costs.Load(int3(g.x*count+k,g.y,0));float d=r+lambda*(abs(v.x-ref.x)+abs(v.y-ref.y));if(d<low){low=d;raw=r;best=v;}}
 return float4(best,raw,0);
}
// Then the eight vectors one pixel around the best, and from the four beside it where the best lies between pixels.
float try_near(Pixel p):SV_Target{int2 at=int2(p.at.xy);int2 g=int2(at.x/9,at.y);int k=at.x%9;return cost(centre(g),chosen.Load(int3(g,0)).xy+float2(k%3-1,k/3-1));}
float4 pick_near(Pixel p):SV_Target{
 int2 g=int2(p.at.xy);float2 middle=chosen.Load(int3(g,0)).xy,ref=reference(g),best=middle;float r[9];float low=1e9,raw=0;
 [unroll]for(int k=0;k<9;k++){r[k]=costs.Load(int3(g.x*9+k,g.y,0));float2 v=middle+float2(k%3-1,k/3-1);float d=r[k]+lambda*(abs(v.x-ref.x)+abs(v.y-ref.y));if(d<low){low=d;raw=r[k];best=v;}}
 if(subpixel&&all(best==middle)){
  float ax=r[3]-2*r[4]+r[5],ay=r[1]-2*r[4]+r[7];
  if(ax>0)best.x+=clamp((r[3]-r[5])/(2*ax),-.5,.5);
  if(ay>0)best.y+=clamp((r[1]-r[7])/(2*ay),-.5,.5);
 }
 return float4(best,raw,0);
}
cbuffer Between:register(b3){float2 fsize;float2 ftsize;float2 fgrid;float fcell;float t;float2 csize;float2 ctsize;float agree;float disagree;float prefer;float still;};
Texture2D<float> ya:register(t0);Texture2D<float> yb:register(t1);Texture2D<float4> field:register(t2);Texture2D<float2> ca:register(t3);Texture2D<float2> cb:register(t4);
Texture2D<float4> wa:register(t5);Texture2D<float4> wb:register(t6);
float fy(Texture2D<float> s,float2 q){return s.SampleLevel(smooth,clamp(q,.5,fsize-.5)/ftsize,0);}
float2 fc(Texture2D<float2> s,float2 q){return s.SampleLevel(smooth,clamp(q,.5,csize-.5)/ctsize,0);}
// The vectors of the four cells around q, their mix and no motion. Cell middles fall between blocks of 2x2 pixels, so a block's four
// pixels share the cells.
void candidates(float2 q,out float2 cand[6]){
 float2 gc=q/fcell-.5,f=frac(gc);int2 g=int2(floor(gc)),last=int2(fgrid)-1;
 cand[0]=field.Load(int3(clamp(g,0,last),0)).xy;cand[1]=field.Load(int3(clamp(g+int2(1,0),0,last),0)).xy;
 cand[2]=field.Load(int3(clamp(g+int2(0,1),0,last),0)).xy;cand[3]=field.Load(int3(clamp(g+1,0,last),0)).xy;
 cand[4]=lerp(lerp(cand[0],cand[1],f.x),lerp(cand[2],cand[3],f.x),f.y);cand[5]=0;
}
struct Weights{float4 first:SV_Target0;float4 second:SV_Target1;};
// Once for each block of 2x2 pixels, at its middle: how well the frames agree along each vector, as weights, and how much the block
// takes the nearer frame because none agrees.
Weights weigh(Pixel p){
 float2 q=p.at.xy*2,cand[6];candidates(q,cand);float e[6];float low=1e9;
 [unroll]for(int i=0;i<6;i++){
  float2 a=q-t*cand[i],b=q+(1-t)*cand[i];
  float s=abs(fy(ya,a)-fy(yb,b))+abs(fy(ya,a+float2(1,0))-fy(yb,b+float2(1,0)))+abs(fy(ya,a-float2(1,0))-fy(yb,b-float2(1,0)))
         +abs(fy(ya,a+float2(0,1))-fy(yb,b+float2(0,1)))+abs(fy(ya,a-float2(0,1))-fy(yb,b-float2(0,1)));
  e[i]=s/5-(i==5?still:0);low=min(low,e[i]);
 }
 float w[6];float total=0;
 [unroll]for(int k=0;k<6;k++){w[k]=exp(-(e[k]-low)/prefer);total+=w[k];}
 Weights o;o.first=float4(w[0],w[1],w[2],w[3])/total;o.second=float4(w[4]/total,w[5]/total,smoothstep(agree,disagree,low),0);return o;
}
float between_y(Pixel p):SV_Target{
 float2 q=p.at.xy,cand[6];candidates(q,cand);int3 b=int3(int2(q)/2,0);float4 one=wa.Load(b),two=wb.Load(b);float w[6]={one.x,one.y,one.z,one.w,two.x,two.y};
 float sum=0;
 [unroll]for(int i=0;i<6;i++)sum+=w[i]*((1-t)*fy(ya,q-t*cand[i])+t*fy(yb,q+(1-t)*cand[i]));
 return lerp(sum,(1-t)*fy(ya,q)+t*fy(yb,q),two.z);
}
// Colour at half the size, one pixel for each block.
float2 between_c(Pixel p):SV_Target{
 float2 q=p.at.xy,cand[6];candidates(q*2,cand);int3 b=int3(int2(q),0);float4 one=wa.Load(b),two=wb.Load(b);float w[6]={one.x,one.y,one.z,one.w,two.x,two.y};
 float2 sum=0;
 [unroll]for(int i=0;i<6;i++){float2 v=cand[i]*.5;sum+=w[i]*((1-t)*fc(ca,q-t*v)+t*fc(cb,q+(1-t)*v));}
 return lerp(sum,(1-t)*fc(ca,q)+t*fc(cb,q),two.z);
}
"""
NAMES=(b'half_size',b'try_start',b'pick_start',b'try_near',b'pick_near',b'weigh',b'between_y',b'between_c')

def compiled():
 """The pixel shaders, from the same compiler the presenter uses."""
 compiler=ctypes.WinDLL('d3dcompiler_47');compile_source=compiler.D3DCompile;compile_source.restype=ctypes.HRESULT
 compile_source.argtypes=[c_char_p,c_size_t,c_char_p,c_void_p,c_void_p,c_char_p,c_char_p,d3d.UINT,d3d.UINT,d3d.OUT,d3d.OUT]
 blobs={}
 for name in NAMES:
  code=c_void_p();errors=c_void_p()
  try:compile_source(SHADERS,len(SHADERS),None,None,None,name,b'ps_5_0',1<<15,0,byref(code),byref(errors))
  except OSError as error:raise RuntimeError(ctypes.string_at(d3d.GetBlobPointer(errors.value),d3d.GetBlobSize(errors.value)).decode(errors='replace') if errors.value else str(error)) from error
  blobs[name]=ctypes.string_at(d3d.GetBlobPointer(code.value),d3d.GetBlobSize(code.value));d3d.Release(code.value)
 return blobs

def plan(width,height):
 """For a picture of this size: the cell of the final vectors in its pixels, the level they are first found on, and every level's size
 from the picture itself down to the smallest. 4K pictures get cells twice as large, so the work stays about that of 1080p."""
 cell=16 if height>1600 else 8;final=cell.bit_length()-3;sizes=[(width,height)]
 while len(sizes)<=final or sizes[-1][1]>SMALLEST:sizes.append(((sizes[-1][0]+1)//2,(sizes[-1][1]+1)//2))
 return cell,final,sizes
def cells(size):return ((size[0]+3)//4,(size[1]+3)//4)
def tries(first,use_past):
 """How many vectors each cell tries first."""
 return (2*RADIUS+1)**2+(9 if use_past else 0) if first else STARTS

class Frame:
 """A frame the presenter keeps on the GPU: its brightness and colour as shader views, the textures' sizes and a number that changes
 whenever the slot holds another frame."""
 def __init__(self,serial,luma,chroma,size,luma_size,chroma_size):
  self.serial=serial;self.luma=luma;self.chroma=chroma;self.size=size;self.luma_size=luma_size;self.chroma_size=chroma_size

class InBetween:
 """Owns every texture of the work and draws on the presenter's device and context. Nothing here waits for the GPU."""
 # Frames whose smaller copies are kept: the two of the pair and the one that comes next.
 KEPT=3
 def __init__(self,device,context,blobs=None):
  self.device=device;self.context=context;self.owned=[];self.shaders={}
  for name,blob in (blobs or compiled()).items():shader=c_void_p();d3d.CreatePixelShader(device,blob,len(blob),None,byref(shader));self.shaders[name]=self.keep(shader.value)
  self.motion=[];self.between=self.buffer(64);self.shape=None;self.sized=[]
  # Called after each pass with its shader and size, to time them.
  self.after=None
 def keep(self,pointer):self.owned.append(pointer);return pointer
 def fill(self,buffer,data):
  mapped=d3d.Mapped();d3d.Map(self.context,buffer,0,d3d.MAP_DISCARD,0,byref(mapped));ctypes.memmove(mapped.Data,data,len(data));d3d.Unmap(self.context,buffer,0)
 def buffer(self,size):
  buffer=c_void_p();d3d.CreateBuffer(self.device,byref(d3d.BufferDesc(ByteWidth=size,Usage=d3d.USAGE_DYNAMIC,BindFlags=d3d.BIND_CONSTANT,CPUAccessFlags=d3d.CPU_WRITE)),None,byref(buffer));return self.keep(buffer.value)
 def texture(self,width,height,form):
  texture=c_void_p();view=c_void_p();target=c_void_p()
  d3d.CreateTexture2D(self.device,byref(d3d.Texture2DDesc(Width=width,Height=height,MipLevels=1,ArraySize=1,Format=form,SampleCount=1,BindFlags=d3d.BIND_SHADER|d3d.BIND_TARGET)),None,byref(texture))
  d3d.CreateRenderTargetView(self.device,texture.value,None,byref(target));d3d.CreateShaderResourceView(self.device,texture.value,None,byref(view))
  self.sized+=[view.value,target.value,texture.value];return view.value,target.value,texture.value
 def release(self):
  self.free_sized()
  for pointer in reversed(self.owned):d3d.Release(pointer)
  self.owned=[];self.motion=[]
 def free_sized(self):
  for pointer in reversed(self.sized):d3d.Release(pointer)
  self.sized=[];self.shape=None
 def prepare(self,frame):
  """Textures for frames of this size, made again only when the size changes."""
  shape=(frame.size,frame.luma_size,frame.chroma_size)
  if shape==self.shape:return
  self.free_sized();self.cell,self.final,self.sizes=plan(*frame.size)
  width,height=frame.size;self.chroma_picture=((width+1)//2,(height+1)//2)
  # The smaller copies of each kept frame, from level 1 on: level 0 is the frame itself.
  self.pyramids=[[self.texture(*size,R16F) for size in self.sizes[1:]] for _ in range(self.KEPT)];self.holds=[None]*self.KEPT;self.used=[0]*self.KEPT;self.uses=0
  # The vectors of each level the search runs on, and the final ones twice, so the last pair's can start this pair's.
  self.fields={number:self.texture(*cells(self.sizes[number]),RGBA32F) for number in range(self.final,len(self.sizes))}
  self.finals=[self.texture(*cells(self.sizes[self.final]),RGBA32F) for _ in range(2)];self.pair=None;self.last=None
  # Each vector a cell tries gets a pixel here, and each cell's first pick waits in the second texture; both serve every level in turn.
  widest=max(cells(self.sizes[number])[0]*max(9,tries(number==len(self.sizes)-1,True)) for number in range(self.final,len(self.sizes)))
  tallest=cells(self.sizes[self.final])[1];self.costs=self.texture(widest,tallest,R32F);self.chosen=self.texture(*cells(self.sizes[self.final]),RGBA32F)
  self.luma_out=self.texture(width,height,R16);self.chroma_out=self.texture(*self.chroma_picture,R16G16)
  self.weights=(self.texture(*self.chroma_picture,RGBA16F),self.texture(*self.chroma_picture,RGBA16F))
  while len(self.motion)<len(self.sizes)*2+1:self.motion.append(self.buffer(96))
  self.shape=shape
 def run(self,shader,buffer,slot,sources,target,size):
  # target: one render target, or several for a shader that writes more than one.
  context=self.context;nothing=(c_void_p*8)();targets=target if isinstance(target,tuple) else (target,)
  d3d.PSSetShaderResources(context,0,8,nothing);d3d.OMSetRenderTargets(context,len(targets),(c_void_p*len(targets))(*targets),None)
  d3d.RSSetViewports(context,1,byref(d3d.Viewport(0,0,size[0],size[1],0,1)));d3d.PSSetShader(context,self.shaders[shader],None,0)
  d3d.PSSetConstantBuffers(context,slot,1,byref(c_void_p(buffer)));d3d.PSSetShaderResources(context,0,len(sources),(c_void_p*len(sources))(*sources));d3d.Draw(context,3,0)
  if self.after:self.after(shader,size)
 def motion_constants(self,buffer,lsize,tsize,grid=(0,0),cgrid=(0,0),pgrid=(0,0),cell=0,ccell=0,pcell=0,cscale=0,tscale=0,radius=0,lambda_=0,stride=1,first=0,use_past=0,subpixel=0,count=0):
  self.fill(buffer,struct.pack('<18f6i',*lsize,*tsize,*grid,*cgrid,*pgrid,cell,ccell,pcell,cscale,tscale,radius,lambda_,stride,first,use_past,subpixel,count,0,0))
 def copies(self,frame,keep):
  """The smaller copies of a frame, made now unless they are already kept. keep: the frames of the pair being worked on, whose
  copies stay, so the second never takes the first one's place."""
  self.uses+=1
  if frame.serial in self.holds:
   index=self.holds.index(frame.serial);self.used[index]=self.uses;return self.pyramids[index]
  index=min((i for i in range(self.KEPT) if self.holds[i] not in keep),key=lambda i:self.used[i])
  self.holds[index]=frame.serial;self.used[index]=self.uses;levels=self.pyramids[index]
  source=frame.luma
  for number,(view,target,_) in enumerate(levels,1):
   buffer=self.motion[number-1];self.motion_constants(buffer,self.sizes[number-1],self.sizes[number-1])
   self.run(b'half_size',buffer,2,(source,),target,self.sizes[number]);source=view
  return levels
 def search(self,buffer,sources,grid,count,out):
  """One level: every starting vector of every cell, the best of them, the eight around it, and the best of those."""
  fa,fb,coarse,past=sources;costs,chosen=self.costs,self.chosen
  self.run(b'try_start',buffer,2,(fa,fb,coarse,past),costs[1],(grid[0]*count,grid[1]))
  self.run(b'pick_start',buffer,2,(fa,fb,coarse,past,costs[0]),chosen[1],grid)
  self.run(b'try_near',buffer,2,(fa,fb,coarse,past,None,chosen[0]),costs[1],(grid[0]*9,grid[1]))
  self.run(b'pick_near',buffer,2,(fa,fb,coarse,past,costs[0],chosen[0]),out,grid)
 def vectors(self,a,b):
  """The field of motion from a to b, found once for each pair."""
  if self.pair==(a.serial,b.serial):return self.finals[self.last]
  keep={a.serial,b.serial};first=self.copies(a,keep);second=self.copies(b,keep)
  # The last pair's vectors start this one's only when it ended where this one begins.
  use_past=int(self.pair is not None and self.pair[1]==a.serial);past=self.finals[self.last][0] if use_past else None
  out=1-self.last if self.last is not None else 0
  top=len(self.sizes)-1;pgrid=cells(self.sizes[self.final]);base=len(self.sizes)
  for number in range(top,self.final-1,-1):
   buffer=self.motion[base+number-self.final];size=self.sizes[number];grid=cells(size);scale=2**number;count=tries(number==top,use_past)
   coarse=self.fields[number+1][0] if number<top else None
   self.motion_constants(buffer,size,size,grid,cells(self.sizes[number+1]) if number<top else (0,0),pgrid,4,8,self.cell/scale,2,1/scale,RADIUS,LAMBDA,1,int(number==top),use_past,0,count)
   self.search(buffer,(first[number-1][0],second[number-1][0],coarse,past),grid,count,self.fields[number][1])
  # Then on the frames themselves, on the same cells, to a quarter of a pixel or so, over points 1.5 pixels apart at 1080p.
  buffer=self.motion[-1];grid=cells(self.sizes[self.final]);scale=2**self.final
  self.motion_constants(buffer,a.size,a.luma_size,grid,grid,pgrid,self.cell,self.cell,self.cell,scale,1,0,LAMBDA/scale,self.cell*1.5/8,0,use_past,1,STARTS)
  self.search(buffer,(a.luma,b.luma,self.fields[self.final][0],past),grid,STARTS,self.finals[out][1])
  self.pair=(a.serial,b.serial);self.last=out;return self.finals[out]
 def render(self,a,b,t):
  """The picture at t (0 at a, 1 at b) as views of brightness and colour, ready for the presenter's usual drawing."""
  self.prepare(a);field=self.vectors(a,b)
  grid=cells(self.sizes[self.final])
  self.fill(self.between,struct.pack('<16f',*a.size,*a.luma_size,*grid,self.cell,t,*self.chroma_picture,*a.chroma_size,AGREE,DISAGREE,PREFER,STILL))
  first,second=self.weights
  self.run(b'weigh',self.between,3,(a.luma,b.luma,field[0]),(first[1],second[1]),self.chroma_picture)
  self.run(b'between_y',self.between,3,(a.luma,b.luma,field[0],None,None,first[0],second[0]),self.luma_out[1],a.size)
  self.run(b'between_c',self.between,3,(a.luma,b.luma,field[0],a.chroma,b.chroma,first[0],second[0]),self.chroma_out[1],self.chroma_picture)
  d3d.PSSetShaderResources(self.context,0,8,(c_void_p*8)());d3d.OMSetRenderTargets(self.context,0,None,None)
  return self.luma_out[0],self.chroma_out[0]
 def forget(self):
  """A new stream or a jump: no frame and no vectors carry over."""
  if self.shape:self.holds=[None]*self.KEPT;self.pair=None;self.last=None
