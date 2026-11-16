"""Direct3D 11 video output. A frame decoded on the GPU reaches the screen without visiting the CPU, and the GPU also converts its colour and scales it."""
import collections,ctypes,struct,threading,time,uuid
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
IID_FACTORY5=iid('7632e1f5-ee65-4dca-87fd-84cd75f8838d');IID_DXGI_DEVICE=iid('54ec77fa-1377-44e6-8c32-88fd5f44c84c');IID_FACTORY1=iid('770aae78-f26f-4dba-a829-253c83d1b387');IID_FACTORY2=iid('50c83a1c-e072-4c48-87b0-3630fa36a6d0');IID_SWAP2=iid('a8be2ac4-199f-4946-b331-79599fb98de7');IID_TEXTURE=iid('6f15aaf2-d208-4e89-9ab4-489535d34f9c')
QueryInterface=com(0,HRESULT,c_char_p,OUT);Release=com(2,c_ulong)
GetDeviceOfChild=com(3,None,OUT);GetTextureDesc=com(10,None,ANY)
CreateBuffer=com(3,HRESULT,ANY,ANY,OUT);CreateTexture2D=com(5,HRESULT,ANY,ANY,OUT);CreateShaderResourceView=com(7,HRESULT,ANY,ANY,OUT);CreateRenderTargetView=com(9,HRESULT,ANY,ANY,OUT);CreateVertexShader=com(12,HRESULT,ANY,c_size_t,ANY,OUT);CreatePixelShader=com(15,HRESULT,ANY,c_size_t,ANY,OUT);CreateSamplerState=com(23,HRESULT,ANY,OUT);GetImmediateContext=com(40,None,OUT)
PSSetShaderResources=com(8,None,UINT,UINT,ANY);PSSetShader=com(9,None,ANY,ANY,UINT);PSSetSamplers=com(10,None,UINT,UINT,ANY);VSSetShader=com(11,None,ANY,ANY,UINT);Draw=com(13,None,UINT,UINT);Map=com(14,HRESULT,ANY,UINT,UINT,UINT,ANY);Unmap=com(15,None,ANY,UINT);PSSetConstantBuffers=com(16,None,UINT,UINT,ANY);IASetPrimitiveTopology=com(24,None,UINT);OMSetRenderTargets=com(33,None,UINT,ANY,ANY);RSSetViewports=com(44,None,UINT,ANY);CopySubresourceRegion=com(46,None,ANY,UINT,UINT,UINT,UINT,ANY,UINT,ANY);ClearRenderTargetView=com(50,None,ANY,ANY);ClearState=com(110,None);Flush=com(111,None)
GetParent=com(6,HRESULT,c_char_p,OUT);GetAdapter=com(7,HRESULT,OUT);EnumAdapters=com(7,HRESULT,UINT,OUT);EnumOutputs=com(7,HRESULT,UINT,OUT);GetOutputDesc=com(7,HRESULT,ANY);MakeWindowAssociation=com(8,HRESULT,wintypes.HWND,UINT);CreateSwapChainForHwnd=com(15,HRESULT,ANY,wintypes.HWND,ANY,ANY,ANY,OUT)
Present=com(8,HRESULT,UINT,UINT);GetBuffer=com(9,HRESULT,UINT,c_char_p,OUT);ResizeBuffers=com(13,HRESULT,UINT,UINT,UINT,UINT,UINT);SetMaximumFrameLatency=com(31,HRESULT,UINT);GetMaximumFrameLatency=com(32,HRESULT,POINTER(UINT));GetFrameLatencyWaitableObject=com(33,wintypes.HANDLE)
GetBlobPointer=com(3,c_void_p);GetBlobSize=com(4,c_size_t)
CheckFeatureSupport=com(28,HRESULT,UINT,ANY,UINT)
CheckColorSpaceSupport=com(37,HRESULT,UINT,POINTER(UINT));SetColorSpace1=com(38,HRESULT,UINT)
CreateBlendState=com(20,HRESULT,ANY,OUT);OMSetBlendState=com(35,None,ANY,ANY,UINT)

class Texture2DDesc(Structure):_fields_=[('Width',UINT),('Height',UINT),('MipLevels',UINT),('ArraySize',UINT),('Format',UINT),('SampleCount',UINT),('SampleQuality',UINT),('Usage',UINT),('BindFlags',UINT),('CPUAccessFlags',UINT),('MiscFlags',UINT)]
class SwapChainDesc1(Structure):_fields_=[('Width',UINT),('Height',UINT),('Format',UINT),('Stereo',wintypes.BOOL),('SampleCount',UINT),('SampleQuality',UINT),('BufferUsage',UINT),('BufferCount',UINT),('Scaling',UINT),('SwapEffect',UINT),('AlphaMode',UINT),('Flags',UINT)]
class ViewDesc(Structure):_fields_=[('Format',UINT),('ViewDimension',UINT),('MostDetailedMip',UINT),('MipLevels',UINT),('Unused',UINT*2)]
class BufferDesc(Structure):_fields_=[('ByteWidth',UINT),('Usage',UINT),('BindFlags',UINT),('CPUAccessFlags',UINT),('MiscFlags',UINT),('StructureByteStride',UINT)]
class SamplerDesc(Structure):_fields_=[('Filter',UINT),('AddressU',UINT),('AddressV',UINT),('AddressW',UINT),('MipLODBias',c_float),('MaxAnisotropy',UINT),('ComparisonFunc',UINT),('BorderColor',c_float*4),('MinLOD',c_float),('MaxLOD',c_float)]
class OutputDesc(Structure):_fields_=[('DeviceName',ctypes.c_wchar*32),('DesktopCoordinates',wintypes.RECT),('AttachedToDesktop',wintypes.BOOL),('Rotation',UINT),('Monitor',c_void_p)]
class Mapped(Structure):_fields_=[('Data',c_void_p),('RowPitch',UINT),('DepthPitch',UINT)]
class BlendTarget(Structure):_fields_=[('BlendEnable',wintypes.BOOL),('SrcBlend',UINT),('DestBlend',UINT),('BlendOp',UINT),('SrcBlendAlpha',UINT),('DestBlendAlpha',UINT),('BlendOpAlpha',UINT),('RenderTargetWriteMask',UINT)]
class BlendDesc(Structure):_fields_=[('AlphaToCoverageEnable',wintypes.BOOL),('IndependentBlendEnable',wintypes.BOOL),('RenderTarget',BlendTarget*8)]
class Viewport(Structure):_fields_=[('X',c_float),('Y',c_float),('Width',c_float),('Height',c_float),('MinDepth',c_float),('MaxDepth',c_float)]

BGRA8=87;R8=61;R8G8=49;NV12=103;P010=104;R16=56;R16G16=35;RGB10=24
USAGE_DEFAULT=0;USAGE_DYNAMIC=2;USAGE_STAGING=3
BIND_CONSTANT=4;BIND_SHADER=8;BIND_TARGET=0x20
CPU_WRITE=0x10000;CPU_READ=0x20000;MAP_READ=1;MAP_DISCARD=4
# The overlay is mixed over the picture by its own transparency: ONE and INV_SRC_ALPHA, added, every colour written.
BLEND_ONE=2;BLEND_INV_SRC_ALPHA=6;BLEND_ADD=1;WRITE_ALL=15
# The overlay's distance from the picture's corner, in pixels at 1080p.
HUD_MARGIN=16
TEXTURE2D_VIEW=4;TRIANGLES=4;FILTER_LINEAR=0x15;ADDRESS_CLAMP=3;LEVEL_SDK=7;DRIVER_UNKNOWN=0;DRIVER_HARDWARE=1;DEVICE_VIDEO=0x800
FLIP_DISCARD=4;SCALING_STRETCH=0;ALPHA_IGNORE=3;TARGET_OUTPUT=0x20;FRAME_LATENCY_WAITABLE=64;NO_WINDOW_CHANGES=1
# Variable refresh: a swap chain made with ALLOW_TEARING may present at once, and a screen with G-Sync, FreeSync or Adaptive-Sync then
# starts its refresh when the frame arrives instead of on its own fixed beat.
ALLOW_TEARING=0x800;PRESENT_ALLOW_TEARING=0x200;FEATURE_PRESENT_ALLOW_TEARING=0
# The most a frame may wait for the screen. Longer would hold up the clock this runs on.
WAIT_MS=15
# Swap chains not ready in time, within this many seconds, that show this PC needs a second frame in flight.
MISS_LIMIT=5;MISS_WINDOW=5
# Frames in flight are never more than this: each one can add a refresh of delay.
MOST_IN_FLIGHT=3
VIEWS={NV12:(R8,R8G8),P010:(R16,R16G16)}
# HDR10 for the window, from the graphics card's video engine: 10-bit buffers shown as BT.2020 with PQ. The usual buffers are sRGB.
SRGB_SPACE=0;HDR10_SPACE=12;IID_SWAP3=iid('94d99bdb-f1f8-4ab0-b236-7da0170edab1');NVIDIA_VENDOR=0x10de
# Debanding: how far off the neighbours are, in pixels of a 1080p picture, and how close in steps of 8-bit colour they must all be.
DEBAND_RADIUS=14;DEBAND_STEPS=2.5
# Each plane's texture format and how much smaller than the picture it is.
PLANES={'yuv420p':((R8,1),(R8,2),(R8,2)),'yuvj420p':((R8,1),(R8,2),(R8,2)),'nv12':((R8,1),(R8G8,2))}
CUBIC,BOX=0,1
PIXEL_SHADERS=(b'ps',b'sharpen',b'rgb',b'easu',b'rcas',b'hud',b'plain',b'divider',b'copy_plane',b'deband',b'hud_pq')
BLACK=(c_float*4)(0,0,0,1)
# RCAS in stops below its strongest. 0.2 gives it about the strength of the sharpening after bicubic.
RCAS_STOPS=.2

SHADERS=b"""
cbuffer Picture:register(b0){float2 size;float2 ratio;float4 rows[3];int luma_filter;int chroma_filter;int interleaved;int unused;float4 post;};
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
// The performance overlay, with its colours weighted by its transparency for the blend state.
float4 hud(Pixel p):SV_Target{float4 c=luma.SampleLevel(smooth,p.uv,0);return float4(c.rgb*c.a,c.a);}
// After AMD's contrast adaptive sharpening: least where neighbours already reach the limits, so edges do not ring.
float4 sharpen(Pixel p):SV_Target{
 int3 at=int3(p.at.xy,0);float3 c=luma.Load(at).rgb,n=luma.Load(at,int2(0,-1)).rgb,s=luma.Load(at,int2(0,1)).rgb,w=luma.Load(at,int2(-1,0)).rgb,e=luma.Load(at,int2(1,0)).rgb;
 float3 low=min(c,min(n,min(s,min(w,e)))),high=max(c,max(n,max(s,max(w,e))));float3 amount=sqrt(saturate(min(low,1-high)/max(high,.0001)))*-.16;
 return float4(saturate((c+(n+s+w+e)*amount)/(1+4*amount)),1);
}
// The colours at the picture's own size, for FSR to enlarge.
float4 rgb(Pixel p):SV_Target{
 float2 c=p.at.xy,cc=c/2;float2 d;blue.GetDimensions(d.x,d.y);float y=luma.Load(int3(c,0)).r,u,v;
 if(interleaved){float2 uv=blue.SampleLevel(smooth,cc/d,0).rg;u=uv.r;v=uv.g;}
 else{u=blue.SampleLevel(smooth,cc/d,0).r;v=red.SampleLevel(smooth,cc/d,0).r;}
 float4 pixel=float4(y,u,v,1);return float4(saturate(float3(dot(rows[0],pixel),dot(rows[1],pixel),dot(rows[2],pixel))),1);
}
// AMD FidelityFX Super Resolution 1, the 32-bit EASU and RCAS of ffx_fsr1.h v1.20210629.
// Copyright (c) 2021 Advanced Micro Devices, Inc. MIT licence, in THIRD-PARTY-NOTICES.md.
cbuffer Scaler:register(b1){float4 con0;float4 con1;float4 con2;float4 con3;float2 origin;float sharpness;float spare;};
float rcp_low(float a){return asfloat(0x7ef07ebbu-asuint(a));}
float rcp_medium(float a){float b=asfloat(0x7ef19fffu-asuint(a));return b*(-b*a+2);}
float rsq_low(float a){return asfloat(0x5f347d74u-(asuint(a)>>1));}
void easu_tap(inout float3 sum,inout float total,float2 off,float2 dir,float2 len,float lob,float clp,float3 c){
 float2 v=float2(off.x*dir.x+off.y*dir.y,off.x*-dir.y+off.y*dir.x)*len;float d2=min(v.x*v.x+v.y*v.y,clp);
 float wb=2./5*d2-1,wa=lob*d2-1;wb*=wb;wa*=wa;wb=25./16*wb-(25./16-1);float w=wb*wa;sum+=c*w;total+=w;
}
void easu_set(inout float2 dir,inout float len,float w,float a,float b,float c,float d,float e){
 float across=rcp_low(max(abs(d-c),abs(c-b))),dx=d-b;dir.x+=dx*w;across=saturate(abs(dx)*across);len+=across*across*w;
 float down=rcp_low(max(abs(e-c),abs(c-a))),dy=e-a;dir.y+=dy*w;down=saturate(abs(dy)*down);len+=down*down*w;
}
// Edge adaptive enlarging, from the picture in luma to the pixel at the same place in the viewport.
float4 easu(Pixel p):SV_Target{
 float2 pp=float2(uint2(p.at.xy-origin))*con0.xy+con0.zw,fp=floor(pp);pp-=fp;
 float2 p0=fp*con1.xy+con1.zw,p1=p0+con2.xy,p2=p0+con2.zw,p3=p0+con3.xy;
 float4 bczzR=luma.GatherRed(smooth,p0),bczzG=luma.GatherGreen(smooth,p0),bczzB=luma.GatherBlue(smooth,p0);
 float4 ijfeR=luma.GatherRed(smooth,p1),ijfeG=luma.GatherGreen(smooth,p1),ijfeB=luma.GatherBlue(smooth,p1);
 float4 klhgR=luma.GatherRed(smooth,p2),klhgG=luma.GatherGreen(smooth,p2),klhgB=luma.GatherBlue(smooth,p2);
 float4 zzonR=luma.GatherRed(smooth,p3),zzonG=luma.GatherGreen(smooth,p3),zzonB=luma.GatherBlue(smooth,p3);
 float4 bczzL=bczzB*.5+(bczzR*.5+bczzG),ijfeL=ijfeB*.5+(ijfeR*.5+ijfeG),klhgL=klhgB*.5+(klhgR*.5+klhgG),zzonL=zzonB*.5+(zzonR*.5+zzonG);
 float bL=bczzL.x,cL=bczzL.y,iL=ijfeL.x,jL=ijfeL.y,fL=ijfeL.z,eL=ijfeL.w,kL=klhgL.x,lL=klhgL.y,hL=klhgL.z,gL=klhgL.w,oL=zzonL.z,nL=zzonL.w;
 float2 dir=0;float len=0;
 easu_set(dir,len,(1-pp.x)*(1-pp.y),bL,eL,fL,gL,jL);easu_set(dir,len,pp.x*(1-pp.y),cL,fL,gL,hL,kL);
 easu_set(dir,len,(1-pp.x)*pp.y,fL,iL,jL,kL,nL);easu_set(dir,len,pp.x*pp.y,gL,jL,kL,lL,oL);
 float2 dir2=dir*dir;float dirR=dir2.x+dir2.y;bool zro=dirR<1./32768;dirR=rsq_low(dirR);dirR=zro?1:dirR;dir.x=zro?1:dir.x;dir*=dirR;
 len=len*.5;len*=len;float stretch=(dir.x*dir.x+dir.y*dir.y)*rcp_low(max(abs(dir.x),abs(dir.y)));
 float2 len2=float2(1+(stretch-1)*len,1-.5*len);float lob=.5+((1./4-.04)-.5)*len,clp=rcp_low(lob);
 float3 f=float3(ijfeR.z,ijfeG.z,ijfeB.z),g=float3(klhgR.w,klhgG.w,klhgB.w),j=float3(ijfeR.y,ijfeG.y,ijfeB.y),k=float3(klhgR.x,klhgG.x,klhgB.x);
 float3 low=min(min(f,g),min(j,k)),high=max(max(f,g),max(j,k)),sum=0;float total=0;
 easu_tap(sum,total,float2(0,-1)-pp,dir,len2,lob,clp,float3(bczzR.x,bczzG.x,bczzB.x));easu_tap(sum,total,float2(1,-1)-pp,dir,len2,lob,clp,float3(bczzR.y,bczzG.y,bczzB.y));
 easu_tap(sum,total,float2(-1,1)-pp,dir,len2,lob,clp,float3(ijfeR.x,ijfeG.x,ijfeB.x));easu_tap(sum,total,float2(0,1)-pp,dir,len2,lob,clp,j);
 easu_tap(sum,total,float2(0,0)-pp,dir,len2,lob,clp,f);easu_tap(sum,total,float2(-1,0)-pp,dir,len2,lob,clp,float3(ijfeR.w,ijfeG.w,ijfeB.w));
 easu_tap(sum,total,float2(1,1)-pp,dir,len2,lob,clp,k);easu_tap(sum,total,float2(2,1)-pp,dir,len2,lob,clp,float3(klhgR.y,klhgG.y,klhgB.y));
 easu_tap(sum,total,float2(2,0)-pp,dir,len2,lob,clp,float3(klhgR.z,klhgG.z,klhgB.z));easu_tap(sum,total,float2(1,0)-pp,dir,len2,lob,clp,g);
 easu_tap(sum,total,float2(1,2)-pp,dir,len2,lob,clp,float3(zzonR.z,zzonG.z,zzonB.z));easu_tap(sum,total,float2(0,2)-pp,dir,len2,lob,clp,float3(zzonR.w,zzonG.w,zzonB.w));
 return float4(min(high,max(low,sum/total)),1);
}
// The picture as the console sends it, only left of the comparison line, which is post.z pixels from the window's left.
float4 plain(Pixel p):SV_Target{if(p.at.x>=post.z)discard;return ps(p);}
// The comparison line itself.
float4 divider(Pixel p):SV_Target{return float4(1,1,1,1);}
// One plane of an in-between picture into the same plane of a surface the graphics card's video engine can take.
float4 copy_plane(Pixel p):SV_Target{return luma.Load(int3(p.at.xy,0));}
// Debanding, after the scaler. Where four neighbours post.x pixels off, in a direction that changes from pixel to pixel, all lie within
// post.y of the pixel, it takes their average, so the steps compression leaves in skies and shadows smooth out. A little noise there
// keeps the screen's 8 bits from stepping again. An edge or any texture has a neighbour further off, and stays as it was.
float noise(float2 q){float3 r=frac(q.xyx*.1031);r+=dot(r,r.yzx+33.33);return frac((r.x+r.y)*r.z);}
float4 deband(Pixel p):SV_Target{
 uint2 d;luma.GetDimensions(d.x,d.y);int2 at=int2(p.at.xy),last=int2(d)-1;float3 c=luma.Load(int3(at,0)).rgb;
 float a=noise(p.at.xy)*6.2831853,r=post.x*(.5+.5*noise(p.at.yx+17.3));int2 o=int2(round(float2(cos(a),sin(a))*r)),q=int2(-o.y,o.x);
 float3 s1=luma.Load(int3(clamp(at+o,0,last),0)).rgb,s2=luma.Load(int3(clamp(at-o,0,last),0)).rgb,s3=luma.Load(int3(clamp(at+q,0,last),0)).rgb,s4=luma.Load(int3(clamp(at-q,0,last),0)).rgb;
 float3 far=max(max(abs(s1-c),abs(s2-c)),max(abs(s3-c),abs(s4-c)));
 if(all(far<post.y))c=(s1+s2+s3+s4)*.25+(noise(p.at.xy+.5)-.5)/255;
 return float4(saturate(c),1);
}
// The overlay on an HDR10 screen: its colours as Windows shows SDR there, with white at about 200 nits, in BT.2020 and PQ.
float3 pq(float3 nits){float3 y=pow(saturate(nits/10000),.1593017578125);return pow((.8359375+18.8515625*y)/(1+18.6875*y),78.84375);}
float4 hud_pq(Pixel p):SV_Target{float4 c=luma.SampleLevel(smooth,p.uv,0);float3 l=mul(float3x3(.6274,.3293,.0433,.0691,.9195,.0114,.0164,.0880,.8956),pow(c.rgb,2.2));return float4(pq(l*200)*c.a,c.a);}
// Sharpening as strong as it can be before the cross of neighbours would clip.
float4 rcas(Pixel p):SV_Target{
 int3 at=int3(p.at.xy,0);float3 b=luma.Load(at,int2(0,-1)).rgb,d=luma.Load(at,int2(-1,0)).rgb,e=luma.Load(at).rgb,f=luma.Load(at,int2(1,0)).rgb,h=luma.Load(at,int2(0,1)).rgb;
 float3 low=min(min(b,d),min(f,h)),high=max(max(b,d),max(f,h)),lobes=max(-(min(low,e)/(4*high)),(1-max(high,e))/(4*low-4));
 float lobe=max(-(.25-1./16),min(max(lobes.r,max(lobes.g,lobes.b)),0))*sharpness;
 return float4((lobe*(b+d+h+f)+e)*rcp_medium(4*lobe+1),1);
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
def enlarged(ratio):
 # FSR only enlarges. At one texel per pixel or smaller the usual filters stay.
 return ratio<.999
def easu_constants(width,height,shown_width,shown_height):
 """AMD's FsrEasuCon for a picture that fills its texture: from a screen pixel to the picture, then the four gathers around it."""
 across,down=width/shown_width,height/shown_height;x,y=1/width,1/height
 return (across,down,.5*across-.5,.5*down-.5,x,y,x,-y,-x,2*y,x,2*y,0,4*y,0,0)
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

user32=ctypes.WinDLL('user32');IsWindowVisible=user32.IsWindowVisible;IsWindowVisible.argtypes=[wintypes.HWND];IsWindowVisible.restype=wintypes.BOOL
GetClientRect=user32.GetClientRect;GetClientRect.argtypes=[wintypes.HWND,POINTER(wintypes.RECT)];GetClientRect.restype=wintypes.BOOL
def showing(hwnd):
 """True when the window is on screen with a real size. Both calls are safe from any thread."""
 rect=wintypes.RECT();return bool(IsWindowVisible(hwnd)) and bool(GetClientRect(hwnd,byref(rect))) and rect.right>1 and rect.bottom>1

def compiled():
 compiler=ctypes.WinDLL('d3dcompiler_47');compile_source=compiler.D3DCompile;compile_source.restype=ctypes.HRESULT
 compile_source.argtypes=[c_char_p,c_size_t,c_char_p,c_void_p,c_void_p,c_char_p,c_char_p,UINT,UINT,OUT,OUT]
 blobs={}
 for name,target in ((b'vs',b'vs_5_0'),*((name,b'ps_5_0') for name in PIXEL_SHADERS)):
  code=c_void_p();errors=c_void_p()
  try:compile_source(SHADERS,len(SHADERS),None,None,None,name,target,1<<15,0,byref(code),byref(errors))
  except OSError as error:raise RuntimeError(ctypes.string_at(GetBlobPointer(errors.value),GetBlobSize(errors.value)).decode(errors='replace') if errors.value else str(error)) from error
  blobs[name]=ctypes.string_at(GetBlobPointer(code.value),GetBlobSize(code.value));Release(code.value)
 return blobs
def window_monitor(hwnd):
 user32=ctypes.windll.user32;user32.MonitorFromWindow.argtypes=[wintypes.HWND,wintypes.DWORD];user32.MonitorFromWindow.restype=c_void_p
 return user32.MonitorFromWindow(hwnd,2)  # MONITOR_DEFAULTTONEAREST
def drives(adapter,monitor):
 """True when this adapter sends the picture to that monitor itself."""
 index=0
 while True:
  output=c_void_p()
  try:EnumOutputs(adapter,index,byref(output))
  except OSError:return False
  try:
   desc=OutputDesc();GetOutputDesc(output.value,byref(desc))
   if desc.Monitor==monitor:return True
  finally:Release(output.value)
  index+=1
def adapters():
 """Every graphics adapter in Windows' order, which is the order FFmpeg numbers them in too. The caller releases each one."""
 library=ctypes.WinDLL('dxgi');create=library.CreateDXGIFactory1;create.restype=ctypes.HRESULT;create.argtypes=[c_char_p,OUT]
 factory=c_void_p();create(IID_FACTORY1,byref(factory));found=[]
 try:
  while True:
   adapter=c_void_p()
   # Windows answers DXGI_ERROR_NOT_FOUND after the last one.
   try:EnumAdapters(factory.value,len(found),byref(adapter))
   except OSError:return found
   found.append(adapter.value)
 finally:Release(factory.value)
def new_device(adapter=None):
 """A device on the adapter at this place in Windows' list, or on Windows' default one. On a laptop with two graphics cards the default
 is the processor's, which drives the screen, so the app names the card it wants."""
 library=ctypes.WinDLL('d3d11');create=library.D3D11CreateDevice;create.restype=ctypes.HRESULT;create.argtypes=[c_void_p,UINT,c_void_p,UINT,c_void_p,UINT,UINT,OUT,c_void_p,c_void_p]
 listed=adapters() if adapter is not None else []
 chosen=listed[adapter] if adapter is not None and 0<=adapter<len(listed) else None
 try:
  if chosen:
   # An adapter named here needs the unknown driver type: Direct3D refuses the hardware type with one.
   try:device=c_void_p();create(chosen,DRIVER_UNKNOWN,None,DEVICE_VIDEO,None,0,LEVEL_SDK,byref(device),None,None);return device.value
   except OSError:pass  # A card that will not start leaves Windows' default one, as before there was a choice.
  device=c_void_p();create(None,DRIVER_HARDWARE,None,DEVICE_VIDEO,None,0,LEVEL_SDK,byref(device),None,None);return device.value
 finally:
  for pointer in listed:Release(pointer)

def tearing_supported():
 """Whether Windows and the graphics driver let a window present at once, which variable refresh needs. False where it cannot be asked."""
 try:
  library=ctypes.WinDLL('dxgi');create=library.CreateDXGIFactory1;create.restype=ctypes.HRESULT;create.argtypes=[c_char_p,OUT]
  factory=c_void_p();create(IID_FACTORY1,byref(factory));newer=c_void_p()
  try:
   QueryInterface(factory.value,IID_FACTORY5,byref(newer))
   try:allowed=wintypes.BOOL(0);CheckFeatureSupport(newer.value,FEATURE_PRESENT_ALLOW_TEARING,byref(allowed),sizeof(allowed));return bool(allowed.value)
   finally:Release(newer.value)
  finally:Release(factory.value)
 except (AttributeError,OSError):return False

# What a screen's EDID shows when it can vary its refresh: AMD's FreeSync block, the HDMI Forum block with a VRR range, a DisplayID
# Adaptive-Sync or dynamic range block, or range limits given as bare limits over more than 10 Hz, as DisplayPort Adaptive-Sync
# screens give them. A screen with none of these keeps a fixed beat, and presenting at once there tears the picture as it moves.
OUI_AMD=0x00001A;OUI_HDMI_FORUM=0xC45DD8
DISPLAYID_VARIABLE=(0x25,0x2B)
def edid_varies(edid):
 """True when the EDID shows variable refresh, False when it is a readable EDID without any sign of it, None when it is no EDID."""
 if not edid or len(edid)<128 or edid[:8]!=b'\x00\xff\xff\xff\xff\xff\xff\x00':return None
 for at in (54,72,90,108):
  d=edid[at:at+18]
  if d[0]==0 and d[1]==0 and d[3]==0xFD:
   # Rate offsets (EDID 1.4): bit 1 adds 255 to the highest vertical rate, bits 0 and 1 together to the lowest too.
   lowest=d[5]+(255 if d[4]&3==3 else 0);highest=d[6]+(255 if d[4]&2 else 0)
   if d[10]==1 and highest-lowest>10:return True
 for start in range(128,len(edid)-127,128):
  block=edid[start:start+128]
  if block[0]==0x02:
   # CTA-861: data blocks from byte 4 up to where the detailed timings start.
   at,end=4,min(block[2],127)
   while at<end:
    tag,length=block[at]>>5,block[at]&31;body=block[at+1:at+1+length]
    if tag==3 and length>=3:
     oui=body[0]|body[1]<<8|body[2]<<16
     if oui==OUI_AMD:return True
     # HDMI 2.1: the block's bytes 9 and 10 hold VRRmin (6 bits) and VRRmax (10 bits); both 0 means no VRR.
     if oui==OUI_HDMI_FORUM and length>=10 and (body[8]&0x3f or (body[8]>>6)<<8|body[9]):return True
    at+=1+length
  elif block[0]==0x70:
   # DisplayID: blocks of tag, revision and length from byte 5, within the section's own length.
   at,end=5,min(5+block[2],127)
   while at+3<=end:
    if block[at] in DISPLAYID_VARIABLE:return True
    at+=3+block[at+2]
 return False

class MONITORINFOEXW(Structure):
 _fields_=[('cbSize',wintypes.DWORD),('rcMonitor',wintypes.RECT),('rcWork',wintypes.RECT),('dwFlags',wintypes.DWORD),('szDevice',wintypes.WCHAR*32)]
class DISPLAY_DEVICEW(Structure):
 _fields_=[('cb',wintypes.DWORD),('DeviceName',wintypes.WCHAR*32),('DeviceString',wintypes.WCHAR*128),('StateFlags',wintypes.DWORD),('DeviceID',wintypes.WCHAR*128),('DeviceKey',wintypes.WCHAR*128)]
def screen_edid(hwnd):
 """The EDID Windows keeps for the screen the window is on, or None. Read only, from the screen's own registry entry."""
 import winreg
 try:
  # Its own handle: the types set here must not change those other modules gave the same functions, as screen_rate does.
  user32=ctypes.WinDLL('user32');user32.GetMonitorInfoW.argtypes=[c_void_p,POINTER(MONITORINFOEXW)];user32.GetMonitorInfoW.restype=wintypes.BOOL
  user32.EnumDisplayDevicesW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,POINTER(DISPLAY_DEVICEW),wintypes.DWORD];user32.EnumDisplayDevicesW.restype=wintypes.BOOL
  info=MONITORINFOEXW();info.cbSize=sizeof(info)
  if not user32.GetMonitorInfoW(window_monitor(hwnd),byref(info)):return None
  found=[]
  for index in range(8):
   device=DISPLAY_DEVICEW();device.cb=sizeof(device)
   # EDD_GET_DEVICE_INTERFACE_NAME: DeviceID becomes \\?\DISPLAY#<model>#<instance>#{class}, the screen's place in the registry.
   if not user32.EnumDisplayDevicesW(info.szDevice,index,byref(device),1):break
   found.append(device)
  # DISPLAY_DEVICE_ACTIVE: the screen the picture goes to now, before any the adapter showed once.
  for device in sorted(found,key=lambda device:not device.StateFlags&1):
   parts=device.DeviceID.removeprefix('\\\\?\\').split('#')
   if len(parts)<3:continue
   try:
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,rf'SYSTEM\CurrentControlSet\Enum\{parts[0]}\{parts[1]}\{parts[2]}\Device Parameters') as key:
     return bytes(winreg.QueryValueEx(key,'EDID')[0])
   except OSError:continue
 except (AttributeError,OSError,ValueError):pass
 return None
def screen_varies(hwnd):
 """Whether the window's screen can vary its refresh: True, False, or None when Windows has no EDID to read for it."""
 return edid_varies(screen_edid(hwnd))

def in_flight(cross,extra=0):
 """Frames queued for the screen: one keeps the delay lowest, a second covers the copy between two cards, and each extra one was earned
 by a run of misses on this PC."""
 return min(MOST_IN_FLIGHT,(2 if cross else 1)+extra)

class D3D11Presenter:
 """Draws on the thread of the refresh clock. Only resizing and hiding involve the window's own thread, which never waits for this one."""
 def __init__(self,window,sharpen=False,fsr=False,adapter=None,vrr=False,smooth=False,super_resolution=True,video_hdr=False,deband=False):
  self.hwnd=window.winfo_id();self.frame=None;self.failed=None;self.failures=0;self.sharpen=sharpen;self.fsr=fsr;self.wanted=(max(1,window.winfo_width()),max(1,window.winfo_height()));self.pending=False
  # In-between pictures: wanted, and why they stopped for this session if they did. Their shaders are compiled the first time.
  self.smooth=smooth;self.smooth_failed=None;self.motion_blobs=None;self.serials=0;self.compiling=None
  if smooth:self.start_compiling()
  self.kernel=ctypes.WinDLL('kernel32');self.kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];self.kernel.WaitForSingleObject.restype=wintypes.DWORD
  # Both fail here, in the window's thread, where the app can still choose the other output.
  # Waits for the swap chain that ran out, and whether the last one drew on a card other than the screen's, for the stats.
  self.timeouts=0;self.cross=False;self.extra=0;self.misses=collections.deque()
  # Variable refresh only where it was asked for, the driver offers it and the screen can follow it. Otherwise the swap chain and
  # every present are as before. A screen whose EDID shows a fixed rate would tear, so the switch does nothing there.
  self.fixed_screen=bool(vrr) and screen_varies(self.hwnd) is False
  self.tearing=bool(vrr) and not self.fixed_screen and tearing_supported()
  # The overlay the window wants shown, (BGRA bytes, width, height) or None, and the one on the graphics card now.
  self.hud_wanted=None
  # The graphics card's video engine (gpu_scaler.py): super resolution and RTX Video HDR as wanted; why the engine, its super resolution or
  # HDR10 stopped for this session if they did; the maker of the card that draws; whether the last frame went through the engine; and
  # whether Windows HDR is on for the window's screen, which the window's thread finds out.
  self.super_resolution=bool(super_resolution);self.video_hdr=bool(video_hdr);self.engine_failed=None;self.scaling_refused=False;self.hdr_refused=None
  self.vendor=0;self.engine_active=False;self.screen_hdr=False
  # Debanding after the scaler, and the comparison: the console's picture left of the middle, this one's right of it.
  self.deband=bool(deband);self.split=False
  self.blobs=compiled();self.own=new_device(adapter);self.forget()
 def forget(self):
  self.slots=[];self.motion=None;self.hud_texture=None;self.hud_view=None;self.hud_shown=None;self.hud_size=None;self.blend=None
  self.device=None;self.context=None;self.swap=None;self.flight=None;self.target=None;self.back=None;self.scaled=None;self.scaled_view=None;self.size=None;self.waitable=None;self.owned=[];self.surface=None;self.surface_shape=None;self.planes=None;self.plane_shape=None;self.views=None;self.arranged=None;self.viewport=None;self.converted=None;self.converted_shape=None;self.enlarging=False
  self.engine=None;self.hdr=False;self.hdr_wanted=False;self.placement=None;self.colour=None;self.scaled_texture=None;self.second=None;self.nv12=None;self.nv12_failed=False
 def keep(self,pointer):
  self.owned.append(pointer.value);return pointer.value
 def attach(self,device):
  """Takes over a reference to the device. A new decoder brings a new device, and the swap chain has to live on the decoder's."""
  self.detach();self.device=device;context=c_void_p();GetImmediateContext(device,byref(context));self.context=context.value
  shader=c_void_p();CreateVertexShader(device,self.blobs[b'vs'],len(self.blobs[b'vs']),None,byref(shader));self.vertex_shader=self.keep(shader)
  self.shaders={}
  for name in PIXEL_SHADERS:shader=c_void_p();CreatePixelShader(device,self.blobs[name],len(self.blobs[name]),None,byref(shader));self.shaders[name]=self.keep(shader)
  sampler=c_void_p();CreateSamplerState(device,byref(SamplerDesc(Filter=FILTER_LINEAR,AddressU=ADDRESS_CLAMP,AddressV=ADDRESS_CLAMP,AddressW=ADDRESS_CLAMP,MaxLOD=1000)),byref(sampler));self.keep(sampler)
  buffers=[]
  for size in (96,80):buffer=c_void_p();CreateBuffer(device,byref(BufferDesc(ByteWidth=size,Usage=USAGE_DYNAMIC,BindFlags=BIND_CONSTANT,CPUAccessFlags=CPU_WRITE)),None,byref(buffer));buffers.append(self.keep(buffer))
  self.constants,self.scaler=buffers
  target=BlendTarget(BlendEnable=1,SrcBlend=BLEND_ONE,DestBlend=BLEND_INV_SRC_ALPHA,BlendOp=BLEND_ADD,SrcBlendAlpha=BLEND_ONE,DestBlendAlpha=BLEND_INV_SRC_ALPHA,BlendOpAlpha=BLEND_ADD,RenderTargetWriteMask=WRITE_ALL)
  blend=c_void_p();CreateBlendState(device,byref(BlendDesc(0,0,(BlendTarget*8)(target))),byref(blend));self.blend=self.keep(blend)
  VSSetShader(self.context,self.vertex_shader,None,0);PSSetSamplers(self.context,0,1,byref(sampler));PSSetConstantBuffers(self.context,0,2,(c_void_p*2)(*buffers));IASetPrimitiveTopology(self.context,TRIANGLES)
  from gpu_scaler import vendor_of
  self.vendor=vendor_of(device)
 def detach(self):
  """A window takes one flip swap chain at a time, and the old one goes only once its device has been cleared and flushed."""
  if self.context:
   ClearState(self.context);self.release_target();self.release_hud()
   for pointer in reversed(self.owned):Release(pointer)
   if self.swap:Release(self.swap)
   if self.surface:self.release_surface()
   if self.planes:self.release_planes()
   if self.converted:self.release_converted()
   self.release_slots()
   if self.motion:self.motion.release();self.motion=None
   self.release_nv12()
   if self.engine:self.engine.release()
   Flush(self.context);Release(self.context)
  if self.device and self.device!=self.own:Release(self.device)
  self.forget()
 def open_swap_chain(self):
  dxgi=c_void_p();adapter=c_void_p();factory=c_void_p();first=c_void_p();swap=c_void_p()
  QueryInterface(self.device,IID_DXGI_DEVICE,byref(dxgi));GetAdapter(dxgi.value,byref(adapter));GetParent(adapter.value,IID_FACTORY2,byref(factory))
  # On a laptop the NVIDIA card draws and the processor's graphics shows the screen, so every frame is copied across before it can show.
  # With one frame in flight, about 7 frames a second never reached the 3060 laptop's screen, and handing one over took up to 14 ms against under 3 here.
  try:self.cross=not drives(adapter.value,window_monitor(self.hwnd))
  except OSError:self.cross=False
  width,height=self.wanted;desc=SwapChainDesc1(Width=width,Height=height,Format=RGB10 if self.hdr_wanted else BGRA8,SampleCount=1,BufferUsage=TARGET_OUTPUT,BufferCount=in_flight(self.cross,self.extra)+1,Scaling=SCALING_STRETCH,SwapEffect=FLIP_DISCARD,AlphaMode=ALPHA_IGNORE,Flags=self.swap_flags())
  try:
   CreateSwapChainForHwnd(factory.value,self.device,self.hwnd,byref(desc),None,None,byref(first))
   MakeWindowAssociation(factory.value,self.hwnd,NO_WINDOW_CHANGES);QueryInterface(first.value,IID_SWAP2,byref(swap));Release(first.value)
  finally:Release(factory.value);Release(adapter.value);Release(dxgi.value)
  self.flight=in_flight(self.cross,self.extra);self.swap=swap.value;SetMaximumFrameLatency(self.swap,self.flight);self.waitable=GetFrameLatencyWaitableObject(self.swap);self.size=self.wanted
  self.hdr=self.hdr_wanted;shown=self.set_colour_space();self.open_target();return shown
 def set_colour_space(self):
  """HDR10 for 10-bit buffers; the usual ones stay sRGB. False when Windows would not show HDR10 here, which ends HDR10 for the session."""
  if not self.hdr:return True
  newer=c_void_p();support=UINT(0)
  try:QueryInterface(self.swap,IID_SWAP3,byref(newer))
  except OSError:self.hdr_refused='Windows would not show HDR10 here';return False
  try:
   CheckColorSpaceSupport(newer.value,HDR10_SPACE,byref(support))
   if support.value&1:SetColorSpace1(newer.value,HDR10_SPACE);return True
  except OSError:pass
  finally:Release(newer.value)
  self.hdr_refused='Windows would not show HDR10 here';return False
 def open_target(self):
  back=c_void_p();view=c_void_p();GetBuffer(self.swap,0,IID_TEXTURE,byref(back));CreateRenderTargetView(self.device,back.value,None,byref(view));self.back=back.value;self.target=view.value;self.arranged=None
  width,height=self.size;texture=c_void_p();shown=c_void_p();drawn=c_void_p()
  CreateTexture2D(self.device,byref(Texture2DDesc(Width=width,Height=height,MipLevels=1,ArraySize=1,Format=BGRA8,SampleCount=1,BindFlags=BIND_SHADER|BIND_TARGET)),None,byref(texture))
  CreateRenderTargetView(self.device,texture.value,None,byref(drawn));CreateShaderResourceView(self.device,texture.value,None,byref(shown));self.scaled_texture=texture.value;self.scaled=drawn.value;self.scaled_view=shown.value
 def second_target(self):
  """Another texture the size of the window, for a second pass after the scaler: (view, target, texture). Made when first wanted."""
  if self.second is None:
   width,height=self.size;texture=c_void_p();shown=c_void_p();drawn=c_void_p()
   CreateTexture2D(self.device,byref(Texture2DDesc(Width=width,Height=height,MipLevels=1,ArraySize=1,Format=BGRA8,SampleCount=1,BindFlags=BIND_SHADER|BIND_TARGET)),None,byref(texture))
   try:CreateRenderTargetView(self.device,texture.value,None,byref(drawn));CreateShaderResourceView(self.device,texture.value,None,byref(shown))
   except OSError:
    for pointer in (drawn.value,texture.value):
     if pointer:Release(pointer)
    raise
   self.second=(shown.value,drawn.value,texture.value)
  return self.second
 def release_target(self):
  # The video engine's views of these textures hold them too, and resizing the swap chain needs every hold on its buffers gone.
  if self.engine:self.engine.release_outputs()
  for pointer in (self.scaled_view,self.scaled,self.scaled_texture,self.target,self.back,*(self.second or ())):
   if pointer:Release(pointer)
  self.scaled_view=self.scaled=self.scaled_texture=self.target=self.back=self.second=None
 def fit(self):
  """The swap chain, at the size the window has now. Until a new frame comes the system stretches the old one, so a resize never shows black."""
  if self.swap is None:
   # A swap chain made on a hidden window of one pixel sometimes showed the picture black, or enlarged from the middle of the window,
   # for the whole session. It waits until the window shows, and False tells the caller to keep the frame for later.
   if not showing(self.hwnd):return False
   return self.open_swap_chain()
  elif self.size!=self.wanted or self.flight!=in_flight(self.cross,self.extra) or self.hdr!=self.hdr_wanted:
   flight=in_flight(self.cross,self.extra)
   OMSetRenderTargets(self.context,0,None,None);self.release_target();Flush(self.context);ResizeBuffers(self.swap,flight+1,*self.wanted,RGB10 if self.hdr_wanted else BGRA8,self.swap_flags())
   SetMaximumFrameLatency(self.swap,flight);self.flight=flight;self.size=self.wanted;self.hdr=self.hdr_wanted;shown=self.set_colour_space();self.open_target()
   # Buffers Windows will not show as HDR10 wait for the next frame, which goes back to sRGB.
   return shown
  return True
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
   self.surface=(chroma.value,luma.value,copy.value);self.surface_shape=shape;self.surface_views=(c_void_p*3)(luma.value,chroma.value,chroma.value);self.arranged=None
  CopySubresourceRegion(self.context,self.surface[2],0,0,0,0,texture,index,None)
  # Every time, as an in-between picture or a slot may have been shown since.
  self.views=self.surface_views
 def release_slots(self):
  for slot in self.slots:
   for pointer in slot['owned']:Release(pointer)
  self.slots=[]
 def slot_for(self,frame):
  """The GPU copy of a decoded frame among the three that in-between pictures work from: the one made earlier for this frame, or a new
  copy in the slot used longest ago. The slot keeps the frame, so its decoder surface cannot be reused while it is wanted."""
  self.serials+=1
  for slot in self.slots:
   if slot['frame'] is frame:slot['used']=self.serials;return slot
  texture,index=surface_of(frame);desc=Texture2DDesc();GetTextureDesc(texture,byref(desc));shape=(desc.Width,desc.Height,desc.Format)
  if desc.Format not in VIEWS:raise RuntimeError('Unsupported surface format')
  slot=min(self.slots,key=lambda slot:slot['used']) if len(self.slots)>=3 else None
  if slot is None or slot['shape']!=shape:
   if slot is not None:
    for pointer in slot['owned']:Release(pointer)
    self.slots.remove(slot)
   copy=c_void_p();luma=c_void_p();chroma=c_void_p()
   CreateTexture2D(self.device,byref(Texture2DDesc(Width=desc.Width,Height=desc.Height,MipLevels=1,ArraySize=1,Format=desc.Format,SampleCount=1,BindFlags=BIND_SHADER)),None,byref(copy))
   first,second=VIEWS[desc.Format]
   CreateShaderResourceView(self.device,copy.value,byref(ViewDesc(Format=first,ViewDimension=TEXTURE2D_VIEW,MipLevels=1)),byref(luma));CreateShaderResourceView(self.device,copy.value,byref(ViewDesc(Format=second,ViewDimension=TEXTURE2D_VIEW,MipLevels=1)),byref(chroma))
   slot=dict(owned=(chroma.value,luma.value,copy.value),copy=copy.value,luma=luma.value,chroma=chroma.value,shape=shape,views=(c_void_p*3)(luma.value,chroma.value,chroma.value));self.slots.append(slot)
  CopySubresourceRegion(self.context,slot['copy'],0,0,0,0,texture,index,None)
  slot.update(frame=frame,serial=self.serials,used=self.serials)
  # Only the two newest slots keep their frames, which the pacer and the screen hold anyway, so no decoder surface stays taken for this.
  for old in sorted(self.slots,key=lambda slot:slot['used'])[:-2]:old['frame']=None
  return slot
 def start_compiling(self):
  """The in-between shaders take about a quarter of a second to compile. That happens on a thread of its own, so no frame waits for it:
  until they are ready the refreshes between frames show the last frame, as without smooth motion."""
  if self.motion_blobs is not None or self.compiling is not None:return
  def run():
   try:
    from in_between import compiled
    self.motion_blobs=compiled()
   except Exception as error:self.smooth_failed=f'{type(error).__name__}: {str(error)[:120]}'
  self.compiling=threading.Thread(target=run,name='PlayBridge in-between shaders',daemon=True);self.compiling.start()
 def motion_work(self):
  from in_between import InBetween
  if self.motion is None:self.motion=InBetween(self.device,self.context,self.motion_blobs)
  return self.motion
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
   self.planes=made;self.plane_shape=shape;self.plane_views=(c_void_p*3)(views[0],views[1],views[-1]);self.arranged=None
  self.views=self.plane_views
  for number,(layout,shrink) in enumerate(PLANES[name]):
   source=frame.planes[number];texture=self.planes[number*2];mapped=Mapped();rows=(frame.height+shrink-1)//shrink;Map(self.context,texture,0,MAP_DISCARD,0,byref(mapped))
   if mapped.RowPitch==source.line_size:ctypes.memmove(mapped.Data,source.buffer_ptr,rows*source.line_size)
   else:
    for row in range(rows):ctypes.memmove(mapped.Data+row*mapped.RowPitch,source.buffer_ptr+row*source.line_size,min(source.line_size,mapped.RowPitch))
   Unmap(self.context,texture,0)
 def release_converted(self):
  for pointer in self.converted:Release(pointer)
  self.converted=None;self.converted_shape=None
 def convert_into(self,width,height):
  """The texture FSR enlarges from, in RGB at the picture's own size."""
  if self.converted_shape==(width,height):return
  if self.converted:self.release_converted()
  texture=c_void_p();shown=c_void_p();drawn=c_void_p()
  CreateTexture2D(self.device,byref(Texture2DDesc(Width=width,Height=height,MipLevels=1,ArraySize=1,Format=RGB10,SampleCount=1,BindFlags=BIND_SHADER|BIND_TARGET)),None,byref(texture))
  CreateRenderTargetView(self.device,texture.value,None,byref(drawn));CreateShaderResourceView(self.device,texture.value,None,byref(shown));Release(texture.value);self.converted=(shown.value,drawn.value);self.converted_shape=(width,height)
 def fill(self,buffer,data):
  mapped=Mapped();Map(self.context,buffer,0,MAP_DISCARD,0,byref(mapped));ctypes.memmove(mapped.Data,data,len(data));Unmap(self.context,buffer,0)
 def arrange(self,frame,interleaved):
  """Sets where the picture goes and how it is filtered, when any of that has changed."""
  key=(frame.width,frame.height,frame.colorspace,frame.color_range,interleaved,self.size,self.fsr,self.split)
  if key==self.arranged:return
  x,y,width,height=fitted(frame.width,frame.height,*self.size);across=frame.width/width;down=frame.height/height;ratio=max(across,down);rows=colour_rows(frame.colorspace,frame.color_range==2)
  self.fill(self.constants,struct.pack('<16f4i4f',frame.width,frame.height,across,down,*rows[0],*rows[1],*rows[2],luma_filter(ratio),int(ratio>2.001),int(interleaved),0,
   DEBAND_RADIUS*height/1080,DEBAND_STEPS/255,x+width//2 if self.split else 0,0))
  self.placement=(x,y,width,height);self.colour=(frame.colorspace,frame.color_range==2)
  self.enlarging=self.fsr and enlarged(ratio)
  if self.enlarging:
   self.convert_into(frame.width,frame.height);self.source=Viewport(0,0,frame.width,frame.height,0,1)
   self.fill(self.scaler,struct.pack('<20f',*easu_constants(frame.width,frame.height,width,height),x,y,2**-RCAS_STOPS,0))
  self.viewport=Viewport(x,y,width,height,0,1);self.whole=Viewport(0,0,self.size[0],self.size[1],0,1);self.arranged=key
 def show(self,frame):
  on_gpu=frame.format.name=='d3d11'
  if on_gpu:
   texture,index=surface_of(frame);device=c_void_p();GetDeviceOfChild(texture,byref(device))
   if device.value==self.device:Release(device.value)
   else:self.attach(device.value)
  elif self.device!=self.own:self.attach(self.own)
  engine=self.engine_for(frame) if on_gpu else None
  self.hdr_wanted=engine is not None and self.hdr_possible()
  if not self.fit():self.pending=True;return False
  if self.kernel.WaitForSingleObject(self.waitable,WAIT_MS):self.pending=True;self.missed();return False
  self.pending=False
  # While in-between pictures are wanted, frames from the GPU go to the ring of copies they are made from. The video engine reads the
  # decoder's own surface, so it needs a copy only for the comparison.
  if on_gpu and self.smooth and self.smooth_failed is None:self.views=self.slot_for(frame)['views']
  elif on_gpu and (engine is None or self.split):self.copy_surface(texture,index)
  elif not on_gpu:self.upload(frame)
  self.arrange(frame,on_gpu or frame.format.name=='nv12')
  if engine is not None:
   try:self.compose((texture,index));return True
   except Exception as error:
    self.stop_engine(error)
    # HDR10 buffers wait for the next frame, in sRGB again. Otherwise the shaders draw this one.
    if self.hdr:self.pending=True;return False
    if not (self.smooth and self.smooth_failed is None):self.copy_surface(texture,index)
  self.compose();return True
 def frame_ratio(self,frame):
  """Texels of the frame to each pixel of the window, along the side that fills it."""
  _,_,width,height=fitted(frame.width,frame.height,*self.wanted);return max(frame.width/width,frame.height/height)
 def engine_for(self,frame):
  """The video engine set up for this frame from the GPU, when it should draw it: to enlarge it with the maker's super resolution, or for
  RTX Video HDR. None leaves the frame to the shaders, as on cards without either."""
  if self.engine_failed is not None or self.device is None:self.engine_active=False;return None
  from gpu_scaler import VideoEngine,can_enlarge
  scale=self.super_resolution and not self.scaling_refused and can_enlarge(self.vendor) and enlarged(self.frame_ratio(frame))
  hdr=self.video_hdr and self.vendor==NVIDIA_VENDOR and self.screen_hdr and self.hdr_refused is None
  if not (scale or hdr):self.engine_active=False;return None
  try:
   if self.engine is None:self.engine=VideoEngine(self.device,self.context,self.vendor)
   texture,_=surface_of(frame);desc=Texture2DDesc();GetTextureDesc(texture,byref(desc))
   self.engine.prepare(frame.width,frame.height,*self.wanted,desc.Format,scale)
  except Exception as error:self.stop_engine(error);return None
  # A driver that says no to super resolution leaves the enlarging to the shaders, FSR 1 among them, for the session.
  if scale and self.engine.scaling is None:self.scaling_refused=True;scale=False
  if not (scale or (hdr and self.engine.hdr_offered and self.engine.context1)):self.engine_active=False;return None
  self.engine_active=True;return self.engine
 def hdr_possible(self):
  engine=self.engine
  return bool(self.video_hdr and self.screen_hdr and self.hdr_refused is None and self.vendor==NVIDIA_VENDOR and engine is not None and engine.hdr_offered and engine.context1)
 def stop_engine(self,error):
  """A fault in the video engine ends it for the session, not the video: the shaders take over from the next frame."""
  self.engine_failed=f'{type(error).__name__}: {str(error)[:120]}';self.engine_active=False;self.hdr_wanted=False
  try:
   self.release_nv12()
   if self.engine:self.engine.release()
  except Exception:pass
  self.engine=None
 def turn_engine(self,super_resolution=None,video_hdr=None):
  """A setting changed, from the window's thread. Turning one on again gives a session where it stopped another try."""
  if super_resolution is not None:self.super_resolution=bool(super_resolution);self.scaling_refused=False
  if video_hdr is not None:self.video_hdr=bool(video_hdr);self.hdr_refused=None
  self.engine_failed=None
 def check_screen(self):
  """Once a second from the window's thread: whether Windows HDR is on for the window's screen, asked only while RTX Video HDR could use it."""
  if self.video_hdr and self.vendor==NVIDIA_VENDOR:
   from gpu_scaler import screen_hdr
   self.screen_hdr=screen_hdr(self.hwnd)
  else:self.screen_hdr=False
 def engine_state(self):
  """What the graphics card's video engine does for the picture now, in words for Settings and the stats: super resolution and HDR."""
  from gpu_scaler import can_enlarge
  engine=self.engine;failed=self.engine_failed and 'stopped: '+self.engine_failed.split(':')[0]
  if not self.super_resolution:scaling='off'
  elif self.vendor and not can_enlarge(self.vendor):scaling='not on this graphics card'+(', so FSR 1 enlarges' if self.fsr else '')
  elif failed:scaling=failed
  elif self.scaling_refused:scaling='the graphics driver said no'+(', so FSR 1 enlarges' if self.fsr else '')
  elif self.engine_active and engine is not None and engine.scaling:scaling='on: '+engine.scaling
  else:scaling='waiting for a window larger than the picture' if self.vendor else 'waiting for the stream'
  if not self.video_hdr:hdr='off'
  elif self.vendor and self.vendor!=NVIDIA_VENDOR:hdr='needs an NVIDIA RTX graphics card'
  elif failed:hdr=failed
  elif self.hdr_refused:hdr='stopped: '+self.hdr_refused
  elif not self.screen_hdr:hdr='waiting for Windows HDR on this screen'
  elif engine is not None and engine.shape and not engine.hdr_offered:hdr='this graphics driver does not offer it'
  elif self.hdr:hdr='on: NVIDIA RTX Video HDR'
  else:hdr='waiting for the stream'
  return {'scaling':scaling,'hdr':hdr}
 def release_nv12(self):
  if self.nv12:
   view=self.engine.inputs.pop((self.nv12['texture'],0),None) if self.engine else None
   if view:Release(view)
   for key in ('chroma','luma','texture'):Release(self.nv12[key])
  self.nv12=None
 def between_source(self,luma,chroma,shape):
  """An in-between picture copied into a surface of the decoder's own format, as (texture, slice), so the video engine draws it as it
  draws frames. None where the card cannot draw into that format: the in-between pictures then go through the shaders."""
  width,height,format=shape
  if self.nv12_failed or format not in VIEWS:return None
  if self.nv12 is None or self.nv12['shape']!=shape:
   self.release_nv12();made=[]
   try:
    texture=c_void_p();CreateTexture2D(self.device,byref(Texture2DDesc(Width=width,Height=height,MipLevels=1,ArraySize=1,Format=format,SampleCount=1,BindFlags=BIND_TARGET|BIND_SHADER)),None,byref(texture));made.append(texture.value)
    for plane in VIEWS[format]:view=c_void_p();CreateRenderTargetView(self.device,texture.value,byref(ViewDesc(Format=plane,ViewDimension=TEXTURE2D_VIEW)),byref(view));made.append(view.value)
   except OSError:
    for pointer in reversed(made):Release(pointer)
    self.nv12_failed=True;return None
   self.nv12=dict(texture=made[0],luma=made[1],chroma=made[2],shape=shape)
  context=self.context;empty=c_void_p()
  for target,view,size in ((self.nv12['luma'],luma,(width,height)),(self.nv12['chroma'],chroma,(width//2,height//2))):
   into=c_void_p(target);source=c_void_p(view)
   OMSetRenderTargets(context,1,byref(into),None);RSSetViewports(context,1,byref(Viewport(0,0,*size,0,1)));PSSetShader(context,self.shaders[b'copy_plane'],None,0);PSSetShaderResources(context,0,1,byref(source));Draw(context,3,0);PSSetShaderResources(context,0,1,byref(empty))
  OMSetRenderTargets(context,0,None,None)
  return self.nv12['texture'],0
 def between(self,a,b,t):
  """The in-between picture at t from frame a (0) to frame b (1), both decoded on this device's GPU at the same size. True once it is
  on its way to the screen; False leaves the screen as it is. A fault here stops in-between pictures for the session, not the video."""
  if not self.smooth or self.smooth_failed is not None or self.device is None:return False
  if self.motion_blobs is None:self.start_compiling();return False
  try:
   if a.format.name!='d3d11' or b.format.name!='d3d11' or (a.width,a.height)!=(b.width,b.height):return False
   for frame in (a,b):
    device=c_void_p();GetDeviceOfChild(surface_of(frame)[0],byref(device));same=device.value==self.device;Release(device.value)
    # A frame from a new decoder waits for its first real frame, which moves the output to the new device.
    if not same:return False
   if not self.fit():return False
   if self.kernel.WaitForSingleObject(self.waitable,WAIT_MS):self.missed();return False
   first=self.slot_for(a);second=self.slot_for(b)
   if first['shape']!=second['shape']:return False
   from in_between import Frame
   size=(a.width,a.height);width,height,_=first['shape'];planes=((width,height),(width//2,height//2))
   luma,chroma=self.motion_work().render(Frame(first['serial'],first['luma'],first['chroma'],size,*planes),Frame(second['serial'],second['luma'],second['chroma'],size,*planes),t)
   # A frame that could not show before is behind this picture now, so it is not shown again after it.
   self.views=(c_void_p*3)(luma,chroma,chroma);self.arrange(a,True)
   source=self.between_source(luma,chroma,first['shape']) if self.engine_active and self.engine is not None else None
   # The shaders draw in sRGB, so HDR10 buffers show the frame again rather than an in-between picture the engine cannot take.
   if source is None and self.hdr:return False
   self.compose(source);self.pending=False;return True
  except Exception as error:
   self.smooth_failed=f'{type(error).__name__}: {str(error)[:120]}'
   try:
    if self.motion:self.motion.release()
   except Exception:pass
   self.motion=None;return False
 def compose(self,source=None):
  """Draws the picture into the window and presents it: the one in self.views through the shaders, or slice source=(texture, index)
  through the graphics card's video engine. Then debanding and sharpening as asked, the comparison and the overlay."""
  context=self.context;empty=c_void_p()
  # HDR10 comes from the video engine alone, and the passes after the scaler work in SDR.
  passes=[] if self.hdr else [name for name,on in ((b'deband',self.deband),(b'rcas' if self.enlarging and source is None else b'sharpen',self.sharpen)) if on]
  textures=[(self.scaled_view,self.scaled,self.scaled_texture)]+([self.second_target()] if len(passes)>1 else [])
  first=c_void_p(textures[0][1] if passes else self.target)
  if source is not None:
   if not self.engine.set_hdr(self.hdr):self.hdr_refused='the graphics driver would not turn RTX Video HDR on'
   # The engine writes outside the pipeline, so nothing there may still hold the texture it writes.
   OMSetRenderTargets(context,0,None,None);PSSetShaderResources(context,0,3,(c_void_p*3)())
   self.engine.draw(*source,textures[0][2] if passes else self.back,self.placement,self.size,*self.colour,self.hdr)
  elif self.enlarging:
   # FSR works on RGB, so the colours are worked out first at the picture's own size, then enlarged.
   picture,drawn=(c_void_p(pointer) for pointer in self.converted)
   PSSetShaderResources(context,0,3,self.views);OMSetRenderTargets(context,1,byref(drawn),None);RSSetViewports(context,1,byref(self.source));PSSetShader(context,self.shaders[b'rgb'],None,0);Draw(context,3,0)
   OMSetRenderTargets(context,1,byref(first),None);ClearRenderTargetView(context,first,BLACK);RSSetViewports(context,1,byref(self.viewport));PSSetShader(context,self.shaders[b'easu'],None,0);PSSetShaderResources(context,0,1,byref(picture));Draw(context,3,0);PSSetShaderResources(context,0,1,byref(empty))
  else:
   OMSetRenderTargets(context,1,byref(first),None);ClearRenderTargetView(context,first,BLACK);RSSetViewports(context,1,byref(self.viewport));PSSetShader(context,self.shaders[b'ps'],None,0);PSSetShaderResources(context,0,3,self.views);Draw(context,3,0)
  # Each pass reads what the one before drew, and the last draws into the window.
  for number,name in enumerate(passes):
   into=c_void_p(self.target if number==len(passes)-1 else textures[(number+1)%2][1]);view=c_void_p(textures[number%2][0])
   OMSetRenderTargets(context,1,byref(into),None);RSSetViewports(context,1,byref(self.whole));PSSetShader(context,self.shaders[name],None,0);PSSetShaderResources(context,0,1,byref(view));Draw(context,3,0);PSSetShaderResources(context,0,1,byref(empty))
  if self.split and not self.hdr:self.draw_split()
  self.draw_hud()
  self.present()
 def draw_split(self):
  """The comparison: left of the middle, the picture as the console sends it with the usual scaling, and a line between the two."""
  context=self.context;target=c_void_p(self.target);x,y,width,height=self.placement
  OMSetRenderTargets(context,1,byref(target),None);RSSetViewports(context,1,byref(self.viewport));PSSetShader(context,self.shaders[b'plain'],None,0);PSSetShaderResources(context,0,3,self.views);Draw(context,3,0)
  RSSetViewports(context,1,byref(Viewport(x+width//2-1,y,2,height,0,1)));PSSetShader(context,self.shaders[b'divider'],None,0);Draw(context,3,0)
  PSSetShaderResources(context,0,3,(c_void_p*3)())
 def set_overlay(self,image):
  """The overlay to draw over the picture from the next frame on: (BGRA bytes, width, height), or None for none. From any thread:
  the graphics card only gets it on the thread that draws."""
  self.hud_wanted=image
 def release_hud(self):
  for pointer in (self.hud_view,self.hud_texture):
   if pointer:Release(pointer)
  self.hud_view=self.hud_texture=None;self.hud_shown=None;self.hud_size=None
 def upload_hud(self,image):
  data,width,height=image
  if self.hud_size!=(width,height):
   self.release_hud();texture=c_void_p();view=c_void_p()
   CreateTexture2D(self.device,byref(Texture2DDesc(Width=width,Height=height,MipLevels=1,ArraySize=1,Format=BGRA8,SampleCount=1,Usage=USAGE_DYNAMIC,BindFlags=BIND_SHADER,CPUAccessFlags=CPU_WRITE)),None,byref(texture))
   CreateShaderResourceView(self.device,texture.value,None,byref(view));self.hud_texture=texture.value;self.hud_view=view.value;self.hud_size=(width,height)
  mapped=Mapped();Map(self.context,self.hud_texture,0,MAP_DISCARD,0,byref(mapped));row=width*4
  try:
   for y in range(height):ctypes.memmove(mapped.Data+y*mapped.RowPitch,data[y*row:(y+1)*row],row)
  finally:Unmap(self.context,self.hud_texture,0)
  self.hud_shown=image
 def draw_hud(self):
  """The overlay in the picture's top left corner, over everything else, when it is wanted and fits."""
  wanted=self.hud_wanted
  if wanted is None:return
  if wanted is not self.hud_shown:self.upload_hud(wanted)
  width,height=self.hud_size;margin=round(HUD_MARGIN*max(1,self.size[1]/1080));x=self.viewport.X+margin;y=self.viewport.Y+margin
  if x+width>self.size[0] or y+height>self.size[1]:return
  context=self.context;target=c_void_p(self.target);view=c_void_p(self.hud_view);empty=c_void_p()
  OMSetRenderTargets(context,1,byref(target),None);RSSetViewports(context,1,byref(Viewport(x,y,width,height,0,1)));OMSetBlendState(context,self.blend,None,0xffffffff)
  PSSetShader(context,self.shaders[b'hud_pq' if self.hdr else b'hud'],None,0);PSSetShaderResources(context,0,1,byref(view));Draw(context,3,0)
  # The in-between pictures and the next frame draw without blending.
  OMSetBlendState(context,None,None,0xffffffff);PSSetShaderResources(context,0,1,byref(empty))
 def swap_flags(self):return FRAME_LATENCY_WAITABLE|(ALLOW_TEARING if self.tearing else 0)
 def present(self):
  # With variable refresh the frame goes now, at its own time; otherwise it waits for the screen's next refresh.
  if self.tearing:Present(self.swap,0,PRESENT_ALLOW_TEARING)
  else:Present(self.swap,1,0)
 def missed(self,now=None):
  """A swap chain that was not ready in time. Several close together mean this PC needs another frame in flight, whatever the cause:
  a copy between two cards, a slow driver, something drawn over the window. Each costs at most a refresh of delay, and stays for the session.
  Fresh misses are needed before the next step."""
  now=time.perf_counter() if now is None else now;self.timeouts+=1;self.misses.append(now)
  while self.misses and now-self.misses[0]>MISS_WINDOW:self.misses.popleft()
  if len(self.misses)>=MISS_LIMIT and self.engine_active and self.engine_failed is None:self.engine_failed='the screen kept waiting for pictures';self.engine_active=False;self.misses.clear();return
  if len(self.misses)>=MISS_LIMIT and in_flight(self.cross,self.extra)<MOST_IN_FLIGHT:self.extra+=1;self.misses.clear()
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
