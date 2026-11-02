"""Draws the README's banner, badges and diagram with the app's own pictures from app/scene.py, so they look like the app. Needs the fonts that come with Windows."""
import re,sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'app'))
import scene
from luxury_theme import GOLD_HOVER,rounded_mask

out=root/'docs'/'images'
version=re.search(r"'ProductVersion','([^']+)'",(root/'app'/'version.txt').read_text(encoding='utf-8')).group(1)
INK=(16,16,18);MUTED=(189,189,189)

def backdrop(width,height,centre=(.78,.3)):
 """The library page with no game behind it: near black with a warm light, worked out at full size so the ramp stays smooth."""
 y,x=np.mgrid[0:height,0:width];u=x/(width-1);v=y/(height-1);light=np.exp(-((u-centre[0])**2/.2+(v-centre[1])**2/.24))[...,None]
 return Image.fromarray((np.array((6,6,8),dtype=float)+light*np.array((64,48,20),dtype=float)).round().clip(0,255).astype('uint8'),'RGB')
def finish(image,radius,s):
 """Round corners and a hairline rim, so the picture sits on GitHub's light and dark pages alike."""
 picture=image.convert('RGBA');ring=Image.new('L',(picture.width*2,picture.height*2))
 ImageDraw.Draw(ring).rounded_rectangle((0,0,ring.width-1,ring.height-1),radius*2,outline=70,width=2*s);rim=Image.new('RGBA',picture.size,(255,255,255,0));rim.putalpha(ring.reduce(2));picture.alpha_composite(rim)
 picture.putalpha(rounded_mask(picture.size,0,radius));return picture

def banner(s=2):
 width,height=1600*s,500*s;image=backdrop(width,height);draw=ImageDraw.Draw(image);m=64*s
 # The top bar, as on every page.
 x=m
 for index,label in enumerate(('Games','Live','Media')):
  font=scene.ui_font(27*s,'semibold' if index==0 else 'regular');draw.text((x,56*s),label,font=font,fill=(255,255,255) if index==0 else (165,165,165),anchor='lm')
  if index==0:draw.rounded_rectangle((x,77*s,x+font.getlength(label),80*s),2*s,fill=GOLD_HOVER)
  x+=font.getlength(label)+30*s
 side=46*s;x=width-m-side
 for mark in ('power','fullscreen','settings','search'):
  button=scene.round_button(side,mark);image.paste(button,(x,56*s-side//2),button);x-=side+6*s
 font=scene.ui_font(19*s);status='PS5  ·  Online';right=x+side-18*s;draw.text((right,56*s),status,font=font,fill=(235,235,235),anchor='rm')
 dot=right-font.getlength(status)-16*s;draw.ellipse((dot-4*s,56*s-4*s,dot+4*s,56*s+4*s),fill=GOLD_HOVER)
 # The name and the line under it, as a game's title on its page.
 title=scene.ui_font(112*s,'semilight');pad=title.size;middle=188*s
 scene.shadowed(image,(0,middle-pad,m+1000*s,middle+pad),lambda d:d.text((m,pad),'PlayBridge',font=title,fill=255,anchor='lm'),round(title.size*.16))
 line=scene.ui_font(28*s);scene.shadowed(image,(0,258*s,m+1000*s,318*s),lambda d:d.text((m,30*s),'Your PS5 games, video and audio on your Windows PC.',font=line,fill=225,anchor='lm'),3*s)
 # Three glass cards, as under a game.
 card_width,card_height,gap,top=252*s,146*s,14*s,326*s;boxes=[(m+i*(card_width+gap),top,m+i*(card_width+gap)+card_width,top+card_height) for i in range(3)]
 for box in boxes:scene.glass(image,box,14*s)
 unit=s;x0,y0=boxes[0][:2];draw=ImageDraw.Draw(image);pad=18*s
 draw.text((x0+pad,y0+30*s),'Stream',font=scene.ui_font(15*s),fill=MUTED,anchor='lm');gauge=scene.glass_gauge(92*s,1,'60');image.paste(gauge,(x0+pad,y0+46*s),gauge)
 draw.text((x0+pad+104*s,y0+74*s),'3840×2160',font=scene.ui_font(17*s),fill=(255,255,255),anchor='lm');draw.text((x0+pad+104*s,y0+102*s),'Up to 80 Mbps',font=scene.ui_font(15*s),fill=MUTED,anchor='lm')
 scene.card_words(image,boxes[1],'Console','PS5 13.60','Payload Manager',unit);scene.card_words(image,boxes[2],'Your PC','Windows x64','Direct3D 11 · WASAPI',unit)
 # The app's own tile in focus on the right.
 side=250*s;left,upper=1140*s,130*s;glow=scene.focus_glow(side);spread=(glow.width-side)//2;image.paste(glow,(left-spread,upper-spread),glow)
 ring=Image.new('L',((side+16*s)*2,)*2);ImageDraw.Draw(ring).rounded_rectangle((0,0,ring.width-1,ring.height-1),round((side+16*s)*.23)*2,outline=255,width=4*s*2)
 image.paste((255,255,255),(left-8*s,upper-8*s),ring.reduce(2))
 icon=Image.open(root/'app'/'assets'/'playbridge.png').convert('RGBA').resize((side,side),Image.Resampling.LANCZOS);image.paste(icon,(left,upper),icon)
 # The hint bar.
 x=width-m;y=468*s;font=scene.ui_font(17*s)
 for key,label in reversed((('F8','Screenshot'),('F9','Record'),('F10','Replay'),('Enter','Play'))):
  x-=round(font.getlength(label));draw.text((x,y),label,font=font,fill=(225,225,225),anchor='lm');cap=scene.key_cap(key,26*s);x-=cap.width+10*s;image.paste(cap,(x,y-cap.height//2),cap);x-=28*s
 finish(image,28*s,s).save(out/'banner.png',optimize=True)

def badge(name,label,value,solid=False,s=3):
 """A pill like the app's buttons: white for the main action, glass for the rest."""
 height=36*s;small=scene.ui_font(15*s);big=scene.ui_font(15*s,'semibold');pad=16*s;mark=12*s if solid else 0
 width=round(pad*2+(mark+8*s if mark else 0)+(small.getlength(label)+7*s if label else 0)+big.getlength(value))
 image=Image.new('RGBA',(width,height));draw=ImageDraw.Draw(image);y=height/2
 draw.rounded_rectangle((0,0,width-1,height-1),height/2,fill=(250,250,250,255) if solid else (20,20,22,255),outline=(205,205,205,255) if solid else (74,74,74,255),width=s)
 x=pad
 if solid:
  draw.line((x+mark/2,y-mark*.55,x+mark/2,y+mark*.3),fill=INK,width=2*s);draw.line((x,y,x+mark/2,y+mark*.5,x+mark,y),fill=INK,width=2*s,joint='curve');draw.line((x,y+mark*.75,x+mark,y+mark*.75),fill=INK,width=2*s);x+=mark+8*s
 if label:draw.text((x,y),label,font=small,fill=(70,70,72) if solid else MUTED,anchor='lm');x+=small.getlength(label)+7*s
 draw.text((x,y),value,font=big,fill=INK if solid else (255,255,255),anchor='lm');image.save(out/name,optimize=True)

def diagram(s=2):
 width,height=1400*s,276*s;image=backdrop(width,height,(.85,.1));draw=ImageDraw.Draw(image);m=38*s
 scene.draw_spaced(draw,m,47*s,'ONE LOCAL NETWORK  ·  VIDEO, AUDIO AND CONTROL',scene.display_font(19*s),MUTED,3*s)
 steps=(('Payload Manager','ELF loader · port 9021','Receives PlayBridge.elf'),('PS5 payload','Native H.264 + AAC capture','Status, games and power'),('Local network','Stream · port 9076','Control · port 9077'),('PlayBridge PC','GPU decoding → Direct3D 11','Audio → WASAPI'))
 gap=56*s;card_width=(width-2*m-3*gap)//4;top,bottom=88*s,238*s
 for index,(name,first,second) in enumerate(steps):
  x0=m+index*(card_width+gap);box=(x0,top,x0+card_width,bottom);scene.glass(image,box,14*s);draw=ImageDraw.Draw(image)
  draw.text((x0+20*s,top+40*s),name,font=scene.ui_font(23*s,'semibold'),fill=(255,255,255),anchor='lm')
  for row,text in enumerate((first,second)):draw.text((x0+20*s,top+84*s+row*30*s),text,font=scene.ui_font(17*s),fill=MUTED,anchor='lm')
  if index<3:
   x=x0+card_width+12*s;y=(top+bottom)//2;end=x+gap-24*s;draw.line((x,y,end,y),fill=GOLD_HOVER,width=3*s);draw.line((end-10*s,y-9*s,end,y,end-10*s,y+9*s),fill=GOLD_HOVER,width=3*s,joint='curve')
   if index==2:draw.line((x+10*s,y-9*s,x,y,x+10*s,y+9*s),fill=GOLD_HOVER,width=3*s,joint='curve')
 finish(image,20*s,s).save(out/'architecture.png',optimize=True)

if __name__=='__main__':
 banner();diagram()
 badge('badge-download.png','Download','v'+version,solid=True)
 for name,label,value in (('badge-windows.png','Windows','x64'),('badge-ps5.png','PS5','13.60'),('badge-4k.png','Up to','4K60'),('badge-license.png','License','GPL-3.0')):badge(name,label,value)
