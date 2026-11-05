"""The library's pictures: the art behind the page, the 3D tiles, the glass cards and the bars. PIL and numpy only, so the tests can draw them without a window."""
import functools,math
from types import SimpleNamespace
import numpy as np
from PIL import Image,ImageChops,ImageDraw,ImageFilter,ImageFont,ImageOps
from luxury_theme import GOLD,GOLD_HOVER,LINE,MUTED,RAISED,TEXT,bold_font,rounded_mask

BILINEAR=Image.Resampling.BILINEAR;BICUBIC=Image.Resampling.BICUBIC;LANCZOS=Image.Resampling.LANCZOS;PERSPECTIVE=Image.Transform.PERSPECTIVE
# Leaves a clear edge around a face, so the bilinear filter smooths its outline at no extra cost.
FACE_MARGIN=3
# How much the corners round, how bright a tile away from the focus is, and how far one swings on its way.
TILE_ROUND=.075;SMALL_LIGHT=.82;TURN_YAW=math.radians(30)

@functools.lru_cache(maxsize=64)
def display_font(pixels,style='SemiBold Condensed'):
 """Windows' DIN-like face, which carries spaced capitals well. Older Windows gets Segoe UI."""
 try:
  font=ImageFont.truetype('bahnschrift.ttf',pixels);font.set_variation_by_name(style);return font
 except (OSError,ValueError):return bold_font(pixels) or ImageFont.load_default(pixels)
WEIGHTS={'semilight':'segoeuisl.ttf','regular':'segoeui.ttf','semibold':'seguisb.ttf'}
@functools.lru_cache(maxsize=64)
def ui_font(pixels,weight='regular'):
 """The library's type, which comes with Windows. Anywhere else PIL's own font keeps the tests drawing."""
 try:return ImageFont.truetype(WEIGHTS[weight],pixels)
 except OSError:return ImageFont.load_default(pixels)

def spaced_width(text,font,tracking):
 return sum(font.getlength(letter) for letter in text)+tracking*max(0,len(text)-1)
def draw_spaced(draw,x,y,text,font,fill,tracking,anchor='l'):
 """Text with room between its letters, which neither PIL nor Tk offers. y is the middle of the line."""
 width=spaced_width(text,font,tracking)
 x-=width/2 if anchor=='m' else width if anchor=='r' else 0
 for letter in text:
  draw.text((x,y),letter,font=font,fill=fill,anchor='lm');x+=font.getlength(letter)+tracking
 return width
def fit_text(draw,text,font,width):
 """The text cut with an ellipsis to fit the width."""
 if draw.textlength(text,font=font)<=width:return text
 while text and draw.textlength(text+'…',font=font)>width:text=text[:-1]
 return text.rstrip()+'…'

def perspective_coefficients(target,source):
 """What PIL needs to send the source's four corners to the target's. It asks where each output pixel comes from, hence the order."""
 rows=[];values=[]
 for (x,y),(u,v) in zip(target,source):
  rows.append((x,y,1,0,0,0,-u*x,-u*y));values.append(u)
  rows.append((0,0,0,x,y,1,-v*x,-v*y));values.append(v)
 return tuple(np.linalg.solve(np.array(rows,dtype=float),np.array(values,dtype=float)))
def turned(point,yaw,pitch,push):
 """A point of the box after turning it, in the camera's space. A positive yaw brings the right edge closer."""
 x,y,z=point
 x,z=x*math.cos(yaw)+z*math.sin(yaw),-x*math.sin(yaw)+z*math.cos(yaw)
 y,z=y*math.cos(pitch)-z*math.sin(pitch),y*math.sin(pitch)+z*math.cos(pitch)
 return x,y,z+push
def on_screen(point,distance):
 x,y,z=point;scale=distance/max(1,distance+z);return x*scale,y*scale
def outward(corners):
 """True when these four corners, listed clockwise as seen from outside, face the camera."""
 return sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(corners,corners[1:]+corners[:1]))>0

def sheen(side):
 """The light on a glossy case: a soft diagonal band and a bright top edge."""
 y,x=np.mgrid[0:side,0:side]/max(1,side-1)
 band=np.clip(1-np.abs(x+y*.7-.42)/.34,0,1)**2*.13+np.clip(.1-y,0,1)*.5
 alpha=Image.fromarray((np.clip(band,0,1)*255).astype('uint8'),'L');light=Image.new('RGBA',(side,side),(255,255,255,255));light.putalpha(alpha)
 return light
def cover_art(icon,side,name=''):
 """A game's picture at a size. A game without one gets its initial."""
 if icon is not None:return icon.convert('RGB').resize((side,side),LANCZOS)
 art=Image.new('RGB',(side,side),RAISED);ImageDraw.Draw(art).text((side/2,side/2),(name or '?')[0].upper(),font=display_font(max(8,side//3)),fill=GOLD,anchor='mm');return art
def cover_faces(icon,side,name=''):
 """The pictures wrapped around a case: the front with its gloss, the white rim that marks the focus, and the edges coloured from the art."""
 depth=max(3,round(side*.07));radius=max(3,round(side*TILE_ROUND));art=cover_art(icon,side,name)
 lit=art.convert('RGBA');lit.alpha_composite(sheen(side));lit.putalpha(rounded_mask((side,side),0,radius))
 front=Image.new('RGBA',(side+2*FACE_MARGIN,side+2*FACE_MARGIN));front.paste(lit,(FACE_MARGIN,FACE_MARGIN))
 line=max(2,round(side*.02));ring=Image.new('L',(side*4,side*4));ImageDraw.Draw(ring).rounded_rectangle((0,0,side*4-1,side*4-1),radius*4,outline=255,width=line*4)
 rim=Image.new('RGBA',front.size);white=Image.new('RGBA',(side,side),(255,255,255,255));white.putalpha(ring.reduce(4));rim.paste(white,(FACE_MARGIN,FACE_MARGIN))
 ringed=front.copy();ringed.alpha_composite(rim)
 def strip(box,size):
  piece=art.crop(box).resize(size,BILINEAR);dark=ImageChops.multiply(piece,Image.new('RGB',size,(104,100,96))).convert('RGBA')
  edge=Image.new('RGBA',(size[0]+2*FACE_MARGIN,size[1]+2*FACE_MARGIN));edge.paste(dark,(FACE_MARGIN,FACE_MARGIN));return edge
 return {'front':front,'ringed':ringed,'rim':rim,'side':side,'depth':depth,
  'left':strip((0,0,2,side),(depth,side)),'right':strip((side-2,0,side,side),(depth,side)),
  'top':strip((0,0,side,2),(side,depth)),'bottom':strip((0,side-2,side,side),(side,depth))}
def render_cover(faces,yaw=0.0,pitch=0.0,rim=1.0,quality=BILINEAR):
 """The case in 3D. rim is how much of the white rim shows. Returns the picture and where its corner sits relative to the case's centre on screen."""
 side=faces['side'];depth=faces['depth'];half=side/2;distance=side*2.5;front_z=-depth/2;back_z=depth/2
 def place(corner):return on_screen(turned(corner,yaw,pitch,0),distance)
 front=[(-half,-half,front_z),(half,-half,front_z),(half,half,front_z),(-half,half,front_z)]
 boxes={
  'left':[(-half,-half,back_z),(-half,-half,front_z),(-half,half,front_z),(-half,half,back_z)],
  'right':[(half,-half,front_z),(half,-half,back_z),(half,half,back_z),(half,half,front_z)],
  'top':[(-half,-half,back_z),(half,-half,back_z),(half,-half,front_z),(-half,-half,front_z)],
  'bottom':[(-half,half,front_z),(half,half,front_z),(half,half,back_z),(-half,half,back_z)],
 }
 drawn=[]
 for name,corners in boxes.items():
  points=[place(corner) for corner in corners]
  if outward(points):drawn.append((name,points))
 points=[place(corner) for corner in front]
 everything=points+[p for _,group in drawn for p in group]
 left=math.floor(min(p[0] for p in everything))-2;top=math.floor(min(p[1] for p in everything))-2
 width=math.ceil(max(p[0] for p in everything))-left+3;height=math.ceil(max(p[1] for p in everything))-top+3
 sprite=Image.new('RGBA',(width,height))
 def put(picture,corners,source_size):
  w,h=source_size
  source=[(FACE_MARGIN,FACE_MARGIN),(FACE_MARGIN+w,FACE_MARGIN),(FACE_MARGIN+w,FACE_MARGIN+h),(FACE_MARGIN,FACE_MARGIN+h)]
  target=[(x-left,y-top) for x,y in corners]
  return picture.transform((width,height),PERSPECTIVE,perspective_coefficients(target,source),quality)
 for name,corners in drawn:
  size=(faces['depth'],side) if name in ('left','right') else (side,faces['depth'])
  sprite.alpha_composite(put(faces[name],corners,size))
 if rim>=1:face=faces['ringed']
 elif rim<=0:face=faces['front']
 else:face=Image.blend(faces['front'],faces['ringed'],rim)
 sprite.alpha_composite(put(face,points,(side,side)))
 return sprite,left,top
def dimmed(sprite,strength):
 """The picture darker, with the same shape, so the tiles away from the focus recede."""
 level=round(255*strength);flat=ImageChops.multiply(sprite.convert('RGB'),Image.new('RGB',sprite.size,(level,level,level)));flat.putalpha(sprite.getchannel('A'));return flat
def flat_tile(icon,side,name=''):
 """A tile away from the focus: square to the camera, a little dimmed, with a faint rim."""
 tile=cover_art(icon,side,name).convert('RGBA');radius=max(3,round(side*TILE_ROUND))
 ring=Image.new('L',(side*4,side*4));ImageDraw.Draw(ring).rounded_rectangle((0,0,side*4-1,side*4-1),radius*4,outline=46,width=4)
 white=Image.new('RGBA',(side,side),(255,255,255,255));white.putalpha(ring.reduce(4));tile.alpha_composite(white);tile.putalpha(rounded_mask((side,side),0,radius))
 return dimmed(tile,SMALL_LIGHT)
@functools.lru_cache(maxsize=4)
def focus_glow(side):
 """The soft light around the focused tile, a little warm, as big as the tile plus its spread."""
 spread=round(side*.16);size=side+2*spread;mask=Image.new('L',(size,size));ImageDraw.Draw(mask).rounded_rectangle((spread,spread,size-spread-1,size-spread-1),round(side*TILE_ROUND),fill=120)
 light=Image.new('RGBA',(size,size),(255,232,190,255));light.putalpha(mask.filter(ImageFilter.GaussianBlur(spread*.42)));return light

def page_layout(width,height):
 """Where everything stands on the library page, in proportion to the window. A small window shrinks everything rather than losing any of it."""
 unit=min(height/1000,width/1500);margin=round(58*unit);bar=max(26,round(46*unit));bar_y=round(24*unit)
 small=max(56,round(124*unit));focus=round(small*1.48);gap=max(6,round(14*unit));row_y=bar_y+bar+round(24*unit);pad=max(6,round(22*unit))
 band_y=max(bar_y+bar,row_y-pad);band_height=row_y+focus+pad-band_y
 hints=max(22,round(38*unit));hints_y=height-hints-round(14*unit)
 card_height=max(70,round(146*unit));card_width=max(120,round(252*unit));card_gap=max(6,round(14*unit));cards_y=hints_y-round(22*unit)-card_height
 pill=max(30,round(58*unit));pill_width=round(pill*5.4);pill_y=cards_y-round(30*unit)-pill
 meta=max(12,round(20*unit));meta_y=pill_y-round(24*unit)-meta//2
 title_size=max(22,round(66*unit));title_bottom=meta_y-meta//2-round(12*unit);title_width=round(min(width*.62,1500*unit));title_top=max(band_y+band_height,title_bottom-round(title_size*2.5))
 cards=[(margin+index*(card_width+card_gap),cards_y,margin+index*(card_width+card_gap)+card_width,cards_y+card_height) for index in range(4)]
 return SimpleNamespace(width=width,height=height,unit=unit,margin=margin,bar=bar,bar_y=bar_y,small=small,focus=focus,half=focus//2,gap=gap,row_y=row_y,pad=pad,band_y=band_y,band_height=band_height,
  name_x=margin+focus+gap+round(6*unit),name_y=row_y+small+(focus-small)//2+round(4*unit),name_size=max(12,round(25*unit)),hints=hints,hints_y=hints_y,cards=cards,cards_y=cards_y,card_height=card_height,card_width=card_width,
  pill=pill,pill_width=pill_width,pill_y=pill_y,option_x=margin+pill_width+round(14*unit),meta=meta,meta_y=meta_y,title_size=title_size,title_bottom=title_bottom,title_top=title_top,title_width=title_width)
def tile_pose(offset,layout):
 """Where a tile stands at a distance from the focus: the middle of it across and down, its side, and how far from the focus it is from 0 to 1."""
 reach=min(1.0,abs(offset));ease=reach*reach*(3-2*reach);side=layout.focus+(layout.small-layout.focus)*ease;step=layout.small+layout.gap
 if offset>=0:
  near=layout.margin+layout.focus+layout.gap;left=layout.margin+(near-layout.margin)*ease if offset<1 else near+(offset-1)*step
 else:
  near=layout.margin-layout.gap-layout.small;left=layout.margin+(near-layout.margin)*ease if offset>-1 else near+(offset+1)*step
 return left+side/2,layout.row_y+side/2,side,reach
def turn_of(offset):
 """A tile on its way to or from the focus swings on its axis, and is square to the camera at both ends of the trip."""
 return math.copysign(TURN_YAW*math.sin(min(1.0,abs(offset))*math.pi),offset)

@functools.lru_cache(maxsize=2)
def scrim(size):
 """How much of the art shows at each point: less at the top for the row, at the left for the words and at the bottom for the cards. Worked out small, because nothing in it is sharp."""
 y,x=np.mgrid[0:90,0:160];u=x/159;v=y/89
 left=np.clip(1-u/.62,0,1)**1.3*.7;top=np.clip(1-v/.4,0,1)**1.5*.58;bottom=np.clip((v-.38)/.62,0,1)**1.25*.84
 light=Image.fromarray((((1-left)*(1-top)*(1-bottom))*255).astype('uint8'),'L').resize(size,BICUBIC);return Image.merge('RGB',(light,light,light))
@functools.lru_cache(maxsize=2)
def grain(size):
 """Fine noise, because so gentle a ramp in so few steps of dark would show bands."""
 noise=Image.effect_noise(size,2.6);return Image.merge('RGB',(noise,noise,noise))
def no_art(size):
 """The page with no game behind it: near black, with blue light from the top right and violet low on the right, original to PlayBridge."""
 y,x=np.mgrid[0:90,0:160];u=x/159;v=y/89
 blue=np.exp(-((u-.78)**2/.09+(v-.3)**2/.12))[...,None]*np.array((16,46,132),dtype=float)
 violet=np.exp(-((u-.95)**2/.05+(v-.85)**2/.1))[...,None]*np.array((72,26,112),dtype=float)
 return Image.fromarray(np.clip(np.array((8,9,14),dtype=float)+blue+violet,0,255).astype('uint8'),'RGB').resize(size,BICUBIC)
def hero_picture(art,cover,size):
 """The page behind everything. A game's own art fills it. A game without art has its cover: far out of focus behind, and large and sharp on the right, melting into the blur."""
 width,height=size
 if art is not None:image=ImageOps.fit(art.convert('RGB'),size,BICUBIC,centering=(.5,.35))
 elif cover is not None:
  flat=cover.convert('RGB');image=flat.resize((48,27),BILINEAR).filter(ImageFilter.GaussianBlur(2.4)).resize(size,BICUBIC);image=ImageChops.multiply(image,Image.new('RGB',size,(150,150,150)))
  side=min(width,height);big=flat.resize((side,side),BICUBIC);across=np.clip(np.linspace(0,1,64)/.62,0,1)[None,:]**1.2;down=np.clip(np.linspace(1,0,64)/.28,0,1)[:,None]
  image.paste(big,(width-side,0),Image.fromarray((across*down*255).astype('uint8'),'L').resize((side,side),BICUBIC))
 else:image=no_art(size)
 return ImageChops.add(ImageChops.multiply(image,scrim(size)),grain(size),1,-128)
def glass(image,box,radius):
 """A sheet of frosted glass on the picture: what is behind it blurred and darkened, with a hairline rim."""
 x0,y0,x1,y1=box;size=(x1-x0,y1-y0);soft=image.crop(box).reduce(4).filter(ImageFilter.GaussianBlur(5)).resize(size,BILINEAR);sheet=Image.blend(soft,Image.new('RGB',size,(14,15,18)),.5)
 image.paste(sheet,(x0,y0),rounded_mask(size,0,radius))
 ring=Image.new('L',(size[0]*2,size[1]*2));ImageDraw.Draw(ring).rounded_rectangle((0,0,size[0]*2-1,size[1]*2-1),radius*2,outline=64,width=2);image.paste((255,255,255),(x0,y0),ring.reduce(2))
def shadowed(image,place,paint,spread):
 """Words on the art, with a soft dark halo so that they read over anything. paint draws in white on a mask."""
 x0,y0,x1,y1=place;mask=Image.new('L',(x1-x0,y1-y0));paint(ImageDraw.Draw(mask))
 image.paste((0,0,0),(x0,y0),mask.filter(ImageFilter.GaussianBlur(spread)).point([value*3//5 for value in range(256)]));image.paste((255,255,255),(x0,y0),mask)
def title_lines(name,width,pixels):
 """A name on one line or two, in the largest type that fits, which is never larger than asked."""
 words=name.replace('™','').replace('®','').split() or ['?'];size=pixels
 while True:
  font=ui_font(size,'semilight');lines=[[]]
  for word in words:
   trial=' '.join(lines[-1]+[word])
   if lines[-1] and font.getlength(trial)>width:lines.append([word])
   else:lines[-1].append(word)
  if size<=14 or (len(lines)<=2 and all(font.getlength(' '.join(line))<=width for line in lines)):return font,[' '.join(line) for line in lines][:2]
  size-=2
def card_words(image,box,caption,big,small,unit):
 """A card's three lines on the glass."""
 x0,y0,x1,y1=box;draw=ImageDraw.Draw(image);pad=round(18*unit);room=x1-x0-2*pad
 draw.text((x0+pad,y0+round(30*unit)),caption,font=ui_font(max(9,round(15*unit))),fill='#BDBDBD',anchor='lm')
 draw.text((x0+pad,y0+round(74*unit)),fit_text(draw,big,ui_font(max(12,round(31*unit)),'semilight'),room),font=ui_font(max(12,round(31*unit)),'semilight'),fill='#FFFFFF',anchor='lm')
 draw.text((x0+pad,y0+round(115*unit)),fit_text(draw,small,ui_font(max(9,round(15*unit))),room),font=ui_font(max(9,round(15*unit))),fill='#BDBDBD',anchor='lm')
def library_page(art,cover,layout,name,line,cards):
 """Everything on the page that stays put for one game, as one picture. cards holds a (caption, big, small) for each card whose words are known now."""
 image=hero_picture(art,cover,(layout.width,layout.height));font,lines=title_lines(name,layout.title_width,layout.title_size);step=round(font.size*1.14);top=layout.title_bottom-step*len(lines)
 pad=font.size
 def title(draw):
  for index,text in enumerate(lines):draw.text((pad,pad+index*step+step/2),text,font=font,fill=255,anchor='lm')
 shadowed(image,(layout.margin-pad,top-pad,min(layout.width,layout.margin+layout.title_width+pad),layout.title_bottom+pad),title,round(font.size*.16))
 def meta(draw):draw.text((pad,pad+layout.meta/2),line,font=ui_font(layout.meta),fill=225,anchor='lm')
 shadowed(image,(layout.margin-pad,layout.meta_y-layout.meta//2-pad,min(layout.width,layout.margin+layout.title_width+pad),layout.meta_y+layout.meta//2+pad+2),meta,3)
 for box in layout.cards:
  if box[2]<=layout.width:glass(image,box,round(14*layout.unit))
 for box,words in zip(layout.cards,cards):
  if box[2]<=layout.width:card_words(image,box,*words,layout.unit)
 return image
def live_cards(layout,stream,console):
 """The two cards that change while the page shows, on a clear background, starting at the third card. stream is (fps as 0-1, reading, a line, another); console is card words."""
 boxes=layout.cards[2:];x0=boxes[0][0];y0=layout.cards_y;image=Image.new('RGBA',(boxes[1][2]-x0,layout.card_height))
 box=(0,0,boxes[0][2]-x0,layout.card_height);unit=layout.unit;side=round(92*unit);draw=ImageDraw.Draw(image);pad=round(18*unit);fraction,reading,first,second=stream
 draw.text((pad,round(30*unit)),'Stream',font=ui_font(max(9,round(15*unit))),fill='#BDBDBD',anchor='lm')
 gauge=glass_gauge(side,fraction,reading);image.alpha_composite(gauge,(pad,round(46*unit)));text_x=pad+side+round(12*unit);room=box[2]-pad-text_x
 draw.text((text_x,round(74*unit)),fit_text(draw,first,ui_font(max(9,round(17*unit))),room),font=ui_font(max(9,round(17*unit))),fill='#FFFFFF',anchor='lm')
 draw.text((text_x,round(102*unit)),fit_text(draw,second,ui_font(max(9,round(15*unit))),room),font=ui_font(max(9,round(15*unit))),fill='#BDBDBD',anchor='lm')
 card_words(image,(boxes[1][0]-x0,0,boxes[1][2]-x0,layout.card_height),*console,unit)
 return image
@functools.lru_cache(maxsize=128)
def glass_gauge(size,fraction,reading):
 """A round gauge for the glass: a faint track, a gold arc and its reading."""
 scale=4;full=size*scale;image=Image.new('RGBA',(full,full));draw=ImageDraw.Draw(image);width=max(scale*2,round(full*.05));box=(width,width,full-width-1,full-width-1)
 draw.ellipse(box,outline=(255,255,255,44),width=width);fraction=max(0.0,min(1.0,fraction))
 if fraction>0:draw.arc(box,-90,-90+360*fraction,fill=GOLD_HOVER,width=width)
 draw.text((full/2,full/2-full*.04),reading,font=ui_font(round(size*.3)*scale,'semilight'),fill='#FFFFFF',anchor='mm');draw.text((full/2,full/2+full*.2),'FPS',font=ui_font(round(size*.13)*scale),fill='#BDBDBD',anchor='mm')
 return image.reduce(scale)
def name_line(layout,name):
 """The focused game's name beside its tile, on a clear background."""
 size=layout.name_size;room=layout.width-layout.name_x-layout.margin;font=ui_font(size);image=Image.new('L',(room+2*size,size*3));draw=ImageDraw.Draw(image)
 draw.text((size,size*1.5),fit_text(draw,name.replace('™','').replace('®',''),font,room),font=font,fill=255,anchor='lm')
 sprite=Image.new('RGBA',image.size);sprite.paste((0,0,0,255),(0,0),image.filter(ImageFilter.GaussianBlur(max(2,size/7))).point([value*3//5 for value in range(256)]));sprite.paste((255,255,255,255),(0,0),image)
 return sprite,layout.name_x-size,layout.name_y-round(size*1.5)

def play_pill(width,height,text,hovering=False,enabled=True,busy=None):
 """The page's main action, solid white, gold under the pointer. busy is the angle of the waiting arc."""
 scale=4;size=(width*scale,height*scale);image=Image.new('RGBA',size);draw=ImageDraw.Draw(image);radius=size[1]/2;ink=(16,16,18,255) if enabled else (70,70,72,255)
 draw.rounded_rectangle((0,0,size[0]-1,size[1]-1),radius,fill=(243,215,120,255) if hovering else (250,250,250,255) if enabled else (178,178,180,235))
 font=ui_font(round(height*.4)*scale,'semibold');label=font.getlength(text);mark=size[1]*.3;gap=size[1]*.26;x=(size[0]-label-mark-gap)/2;cy=size[1]/2
 if busy is not None:draw.arc((x,cy-mark*.62,x+mark*1.24,cy+mark*.62),busy,busy+250,fill=ink,width=scale*2+2);x-=mark*.12
 else:draw.polygon(((x+mark*.1,cy-mark*.62),(x+mark*.1,cy+mark*.62),(x+mark*1.1,cy)),fill=ink)
 draw.text((x+mark+gap,cy),text,font=font,fill=ink,anchor='lm')
 return image.reduce(scale)
def round_button(side,mark,hovering=False,selected=False):
 """A glass circle with a white sign in it."""
 scale=4;full=side*scale;image=Image.new('RGBA',(full,full));draw=ImageDraw.Draw(image);draw.ellipse((0,0,full-1,full-1),fill=(255,255,255,235) if selected else (255,255,255,64) if hovering else (24,25,28,150),outline=(255,255,255,120 if hovering else 58),width=scale)
 ink=(16,16,18,255) if selected else (255,255,255,255);m=full/2;r=full*.2;line=max(scale+1,round(full*.052))
 if mark=='search':
  c=m-r*.2;draw.ellipse((c-r*.82,c-r*.82,c+r*.82,c+r*.82),outline=ink,width=line);draw.line((c+r*.6,c+r*.6,m+r*1.08,m+r*1.08),fill=ink,width=line)
 elif mark=='settings':
  for turn in range(8):
   angle=math.radians(turn*45);draw.line((m+math.cos(angle)*r*.8,m+math.sin(angle)*r*.8,m+math.cos(angle)*r*1.3,m+math.sin(angle)*r*1.3),fill=ink,width=line+scale)
  draw.ellipse((m-r,m-r,m+r,m+r),outline=ink,width=line+scale//2);draw.ellipse((m-r*.3,m-r*.3,m+r*.3,m+r*.3),fill=ink)
 elif mark=='fullscreen':
  a=r*1.2;b=r*.55
  for sx,sy in ((-1,-1),(1,-1),(1,1),(-1,1)):draw.line((m+sx*(a-b),m+sy*a,m+sx*a,m+sy*a,m+sx*a,m+sy*(a-b)),fill=ink,width=line,joint='curve')
 elif mark=='power':
  draw.arc((m-r*1.1,m-r*1.0,m+r*1.1,m+r*1.2),-58,238,fill=ink,width=line);draw.line((m,m-r*1.3,m,m-r*.1),fill=ink,width=line)
 elif mark=='more':
  for at in (-1,0,1):draw.ellipse((m+at*r*.95-r*.2,m-r*.2,m+at*r*.95+r*.2,m+r*.2),fill=ink)
 return image.reduce(scale)
def key_cap(text,height):
 """A key or a shoulder button in the hint bar and the tabs."""
 scale=4;font=ui_font(round(height*.54)*scale,'semibold');width=max(height*scale,round(font.getlength(text))+height*scale*7//10);image=Image.new('RGBA',(width,height*scale));draw=ImageDraw.Draw(image)
 draw.rounded_rectangle((0,0,width-1,height*scale-1),height*scale*.26,outline=(255,255,255,190),width=scale+1,fill=(255,255,255,26))
 draw.text((width/2,height*scale/2),text,font=font,fill=(255,255,255,255),anchor='mm');return image.reduce(scale)
def pad_mark(kind,height):
 """A controller's face button, drawn here as plain shapes."""
 scale=4;full=height*scale;image=Image.new('RGBA',(full,full));draw=ImageDraw.Draw(image);draw.ellipse((0,0,full-1,full-1),outline=(255,255,255,190),width=scale+1,fill=(255,255,255,26));m=full/2;r=full*.2;line=scale+2
 if kind=='cross':draw.line((m-r,m-r,m+r,m+r),fill='#FFFFFF',width=line);draw.line((m-r,m+r,m+r,m-r),fill='#FFFFFF',width=line)
 elif kind=='circle':draw.ellipse((m-r,m-r,m+r,m+r),outline='#FFFFFF',width=line)
 elif kind=='square':draw.rectangle((m-r,m-r,m+r,m+r),outline='#FFFFFF',width=line)
 return image.reduce(scale)
def top_bar(layout,state):
 """The row across the top of every page: the tabs and the shelf on the left, the console, the clock and the round buttons on the right. state['tab'] is the tab that is showing, and state['selected'] a round button that is. Returns the picture and where to click, in the page's coordinates."""
 unit=layout.unit;height=layout.bar+round(26*unit);image=Image.new('RGBA',(layout.width,height));draw=ImageDraw.Draw(image);y=layout.bar/2;x=layout.margin;hits={};hover=state.get('hover')
 def add(key,box):hits[key]=(box[0],box[1]+layout.bar_y,box[2],box[3]+layout.bar_y)
 cap_height=round(layout.bar*.56)
 if state.get('pad'):cap=key_cap('L1',cap_height);image.alpha_composite(cap,(x,round(y-cap.height/2)));x+=cap.width+round(16*unit)
 font=ui_font(round(27*unit),'semibold');dim=ui_font(round(27*unit));tab_gap=round(30*unit)
 for key,label in (('games','Games'),('live','Live'),('media','Media')):
  on=key==state.get('tab','games');face=font if on else dim;width=face.getlength(label)
  draw.text((x,y),label,font=face,fill=(255,255,255,255) if on or hover==key else (255,255,255,165),anchor='lm')
  if on:
   mark=max(2,round(3*unit));draw.rounded_rectangle((x,y+round(21*unit),x+width,y+round(21*unit)+mark),mark/2,fill=GOLD_HOVER)
  add(key,(round(x)-round(10*unit),0,round(x+width)+round(10*unit),layout.bar));x+=width+tab_gap
 if state.get('pad'):cap=key_cap('R1',cap_height);image.alpha_composite(cap,(round(x-tab_gap+round(16*unit)),round(y-cap.height/2)));x+=cap.width+round(4*unit)
 side=layout.bar;right=layout.width-layout.margin
 for key in reversed(('search','settings','fullscreen','power')):
  right-=side;picture=round_button(side,key,hover==key,key==state.get('selected') or key=='search' and bool(state.get('searching')));image.alpha_composite(picture,(right,0));add(key,(right,0,right+side,side))
  if hover==key:
   label=dict(search='Search',settings='Settings',fullscreen='Full screen',power='Power')[key];draw.text((right+side/2,side+round(13*unit)),label,font=ui_font(max(9,round(14*unit))),fill='#FFFFFF',anchor='mm')
  right-=round(12*unit)
 right-=round(10*unit);clock=state.get('clock','');draw.text((right,y),clock,font=ui_font(round(24*unit)),fill='#FFFFFF',anchor='rm');right-=round(font.getlength(clock))+round(20*unit)
 status=state.get('status','');small=ui_font(round(18*unit))
 if status:
  draw.text((right,y),status,font=small,fill=(255,255,255,200),anchor='rm');right-=round(small.getlength(status))+round(12*unit);r=max(2,round(4*unit));colour=GOLD_HOVER if state.get('online') else (150,150,150,255);draw.ellipse((right-2*r,y-r,right,y+r),fill=colour);right-=2*r+round(20*unit)
 left_end=x+round(6*unit)
 if state.get('searching') or state.get('search'):
  field_height=round(layout.bar*.86);field=round(330*unit);field_x=max(left_end,right-field);text=state.get('search','');box=Image.new('RGBA',(field*4,field_height*4));d=ImageDraw.Draw(box);d.rounded_rectangle((0,0,box.width-1,box.height-1),box.height/2,fill=(20,21,24,190),outline=(255,255,255,120),width=4)
  shown=(text or 'Type a name')+('|' if state.get('searching') else '');f=ui_font(round(field_height*.46)*4);d.text((box.height*.5,box.height/2),fit_text(d,shown,f,box.width-box.height),font=f,fill=(255,255,255,255) if text else (190,190,190,255),anchor='lm');picture=box.reduce(4);image.alpha_composite(picture,(round(field_x),round(y-field_height/2)))
 else:
  shelf=state.get('shelf','');chip=round(layout.bar*.74);f=ui_font(round(chip*.5))
  if shelf and left_end+f.getlength(shelf)+chip*2<right:
   width=round(f.getlength(shelf)+chip*1.5);box=Image.new('RGBA',(width*4,chip*4));d=ImageDraw.Draw(box);d.rounded_rectangle((0,0,box.width-1,box.height-1),box.height/2,fill=(255,255,255,60) if hover=='shelf' else (24,25,28,130),outline=(255,255,255,70),width=4)
   d.text((chip*2,box.height/2),shelf,font=ui_font(round(chip*.5)*4),fill=(255,255,255,255),anchor='lm');a=box.width-chip*2.1;b=box.height/2;s=chip*.42;d.line((a,b-s*.4,a+s,b+s*.5,a+2*s,b-s*.4),fill=(255,255,255,220),width=5,joint='curve');picture=box.reduce(4);at=round(left_end);image.alpha_composite(picture,(at,round(y-chip/2)));add('shelf',(at,0,at+width,layout.bar))
 return image,hits
def hint_bar(layout,hints,line,notice):
 """The bar along the bottom: what is happening on the left in small type, what the keys do on the right. Each hint is (a key or a button shape, what it does)."""
 unit=layout.unit;image=Image.new('RGBA',(layout.width,layout.hints));draw=ImageDraw.Draw(image);y=layout.hints/2;font=ui_font(max(9,round(16*unit)));right=layout.width-layout.margin;cap=max(14,round(layout.hints*.66))
 for kind,label in reversed(hints):
  width=font.getlength(label);draw.text((right,y),label,font=font,fill=(255,255,255,205),anchor='rm');right-=round(width)+round(9*unit)
  mark=pad_mark(kind,cap) if kind in ('cross','circle','square') else key_cap(kind,cap);right-=mark.width;image.alpha_composite(mark,(right,round(y-mark.height/2)));right-=round(26*unit)
 if line:draw.text((layout.margin,y),fit_text(draw,line,font,max(10,right-layout.margin)),font=font,fill=GOLD_HOVER if notice else (255,255,255,170),anchor='lm')
 return image
def drop_menu(items,selected,unit):
 """A small list on glass, for the power button and the three dots. Returns the picture and each row's top and bottom."""
 row=round(44*unit);font=ui_font(max(10,round(19*unit)));width=round(max([font.getlength(label) for _,label in items]+[120*unit])+60*unit);height=row*len(items)+round(14*unit);top=round(7*unit);scale=2
 image=Image.new('RGBA',(width*scale,height*scale));draw=ImageDraw.Draw(image);draw.rounded_rectangle((0,0,image.width-1,image.height-1),round(14*unit)*scale,fill=(20,21,24,244),outline=(255,255,255,70),width=scale);rows=[];big=ui_font(max(10,round(19*unit))*scale)
 for index,(_,label) in enumerate(items):
  y=(top+index*row)*scale
  if index==selected:draw.rounded_rectangle((round(7*unit)*scale,y,image.width-round(7*unit)*scale,y+row*scale),round(9*unit)*scale,fill=(250,250,250,255))
  draw.text((round(26*unit)*scale,y+row*scale/2),label,font=big,fill=(16,16,18,255) if index==selected else (255,255,255,255),anchor='lm');rows.append((top+index*row,top+(index+1)*row))
 return image.reduce(scale),rows
@functools.lru_cache(maxsize=256)
def ring_gauge(size,fraction,big,small):
 """A round gauge: a dim track, a gold arc with rounded ends and its reading in the middle."""
 scale=4;full=size*scale;image=Image.new('RGBA',(full,full));draw=ImageDraw.Draw(image);width=round(full*.04);box=(width,width,full-width-1,full-width-1)
 draw.ellipse(box,outline=LINE,width=width)
 fraction=max(0.0,min(1.0,fraction))
 if fraction>0:
  draw.arc(box,-90,-90+360*fraction,fill=GOLD,width=width)
  for turn in (0,fraction):
   angle=math.radians(-90+360*turn);r=(full-2*width)/2-width/2+1;cx=full/2+math.cos(angle)*r;cy=full/2+math.sin(angle)*r
   draw.ellipse((cx-width/2,cy-width/2,cx+width/2,cy+width/2),fill=GOLD)
 draw.text((full/2,full/2-full*.035),big,font=display_font(round(size*.25)*scale,'SemiBold'),fill=TEXT,anchor='mm')
 draw_spaced(draw,full/2,full/2+full*.16,small,display_font(round(size*.07)*scale,'Regular'),MUTED,round(size*.012)*scale,'m')
 return image.reduce(scale)
