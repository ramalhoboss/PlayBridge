"""What is drawn over the game: the performance panel (performance.py), the speedrun timer (run_timer.py), a trophy as it unlocks,
the buttons pressed on this PC's controller and the newest messages in your Twitch chat (twitch_chat.py). On screen the graphics card draws it into the picture (d3d11_presenter); in a live stream it
is drawn into each frame before the frame is made again (live_broadcast). Every number in it comes from the console or this PC."""
import colorsys,functools,io,re
from performance import font,overlay_image
import pad_input as pads

PANEL=(8,8,10,150);EDGE=(212,175,55,70);GOLD=(235,212,142,255);WHITE=(255,255,255,255);SOFT=(200,200,205,255)
AHEAD=(110,220,140,255);BEHIND=(240,110,100,255);IDLE=(255,255,255,70)
GRADES={'platinum':(190,215,235,255),'gold':(235,190,60,255),'silver':(200,200,210,255),'bronze':(205,130,70,255)}
WIDTH=250;GAP=8
# Twitch chat: the badges' colours, Twitch's purple for the panel's dot, and the colours Twitch gives a name that has none chosen.
BADGES={'broadcaster':(235,64,64,255),'moderator':(40,200,90,255),'vip':(236,72,200,255),'subscriber':(160,110,255,255)}
TWITCH=(160,110,255,255)
NAME_COLOURS=('#FF0000','#0000FF','#008000','#B22222','#FF7F50','#9ACD32','#FF4500','#2E8B57','#DAA520','#D2691E','#5F9EA0','#1E90FF','#FF69B4','#8A2BE2','#00FF7F')
# Lines of chat at most, lines of one message at most, and how long a new message stays lit.
CHAT_LINES=9;MESSAGE_LINES=4;FRESH=3.0

def blank(width,height,s):
 from PIL import Image,ImageDraw
 image=Image.new('RGBA',(width,height),(0,0,0,0));draw=ImageDraw.Draw(image)
 draw.rounded_rectangle((0,0,width-1,height-1),radius=round(10*s),fill=PANEL,outline=EDGE,width=max(1,round(s)))
 return image,draw

def scale_of(scale):return max(.75,min(2.5,scale))

def timer_image(view,scale=1.0):
 """The timer: the game, the time, the last split against the best one, and the best run."""
 s=scale_of(scale);pad=round(12*s);width=round(WIDTH*s);rows=[line for line in (view['split'],view['best']) if line]
 height=pad+round(15*s)+round(40*s)+round(17*s)*len(rows)+pad
 image,draw=blank(width,height,s);y=pad
 draw.text((pad,y),(view['name'] or 'Speedrun')[:28],font=font(round(12*s)),fill=GOLD);y+=round(15*s)
 colour=IDLE if view['state']=='idle' else WHITE;draw.text((pad,y-round(4*s)),view['time'],font=font(round(34*s),True),fill=colour)
 if view['delta']:
  small=font(round(13*s),True);draw.text((width-pad-round(draw.textlength(view['delta'],font=small)),y+round(16*s)),view['delta'],font=small,fill=AHEAD if view['ahead'] else BEHIND)
 y+=round(40*s)
 for line in rows:draw.text((pad,y),line[:40],font=font(round(12*s)),fill=SOFT);y+=round(17*s)
 return image

@functools.lru_cache(maxsize=8)
def icon_picture(data,size):
 """A trophy's own picture (PNG bytes) as a square of this size with rounded corners, or None when it cannot be read."""
 from PIL import Image,ImageChops,ImageDraw
 try:
  with Image.open(io.BytesIO(data)) as source:
   if source.format!='PNG' or max(source.size)>2048:return None
   picture=source.convert('RGBA').resize((size,size),Image.Resampling.LANCZOS)
 except Exception:return None
 mask=Image.new('L',(size,size),0);ImageDraw.Draw(mask).rounded_rectangle((0,0,size-1,size-1),radius=max(2,size//6),fill=255)
 picture.putalpha(ImageChops.multiply(picture.getchannel('A'),mask));return picture

def trophy_image(trophy,scale=1.0):
 """A trophy that just unlocked: its own picture (or its grade's colour when the console gave none), its name and the game."""
 s=scale_of(scale);pad=round(12*s);width=round(WIDTH*s);height=pad*2+round(34*s)
 image,draw=blank(width,height,s);size=round(34*s);picture=icon_picture(trophy['icon'],size) if trophy.get('icon') else None
 if picture is not None:image.alpha_composite(picture,(pad,pad));left=pad+size+round(10*s)
 else:
  colour=GRADES.get(trophy.get('grade'),GOLD);r=round(11*s);cx=pad+r;cy=height//2
  draw.ellipse((cx-r,cy-r,cx+r,cy+r),fill=colour);left=pad+2*r+round(10*s)
 draw.text((left,pad-round(2*s)),'Trophy unlocked',font=font(round(11*s)),fill=SOFT)
 draw.text((left,pad+round(13*s)),(trophy.get('name') or (trophy.get('grade') or 'A trophy').capitalize())[:30],font=font(round(15*s),True),fill=WHITE)
 return image

def pad_image(state,scale=1.0):
 """This PC's controller as it is held now: shoulder buttons and triggers, the D-pad, both sticks and the four face buttons."""
 s=scale_of(scale);width=round(WIDTH*s);height=round(96*s);image,draw=blank(width,height,s)
 def on(bit):return bool(state.buttons&bit)
 def box(x,y,w,h,lit,radius=3):draw.rounded_rectangle((x,y,x+w,y+h),radius=round(radius*s),fill=GOLD if lit else (255,255,255,40),outline=(255,255,255,90),width=1)
 u=s;top=round(10*u);bar_w=round(40*u);bar_h=round(8*u)
 # Triggers fill as far as they are pressed; the shoulder buttons light up.
 for x,value,bit in ((round(14*u),state.l2,pads.L1),(width-round(14*u)-bar_w,state.r2,pads.R1)):
  draw.rounded_rectangle((x,top,x+bar_w,top+bar_h),radius=round(3*u),fill=(255,255,255,40),outline=(255,255,255,90),width=1)
  if value:draw.rounded_rectangle((x,top,x+max(2,round(bar_w*value/255)),top+bar_h),radius=round(3*u),fill=GOLD)
  box(x,top+bar_h+round(4*u),bar_w,round(7*u),on(bit))
 # D-pad.
 cx,cy,k=round(42*u),round(62*u),round(10*u)
 for dx,dy,bit in ((0,-1,pads.UP),(1,0,pads.RIGHT),(0,1,pads.DOWN),(-1,0,pads.LEFT)):box(cx+dx*k-k//2,cy+dy*k-k//2,k,k,on(bit),2)
 # Sticks: where each one points, and lit when pressed in.
 for sx,x_value,y_value,bit in ((round(98*u),state.lx,state.ly,pads.L3),(width-round(98*u),state.rx,state.ry,pads.R3)):
  r=round(13*u);sy=round(66*u);draw.ellipse((sx-r,sy-r,sx+r,sy+r),fill=GOLD if on(bit) else (255,255,255,30),outline=(255,255,255,90),width=1)
  dot=round(5*u);px=sx+round((x_value-128)/128*(r-dot));py=sy+round((y_value-128)/128*(r-dot));draw.ellipse((px-dot,py-dot,px+dot,py+dot),fill=WHITE)
 # Face buttons.
 cx,cy,k=width-round(42*u),round(62*u),round(11*u)
 for dx,dy,bit in ((0,-1,pads.TRIANGLE),(1,0,pads.CIRCLE),(0,1,pads.CROSS),(-1,0,pads.SQUARE)):
  r=round(5*u);x=cx+dx*k;y=cy+dy*k;draw.ellipse((x-r,y-r,x+r,y+r),fill=GOLD if on(bit) else (255,255,255,40),outline=(255,255,255,110),width=1)
 return image

def readable(colour,name):
 """A name's colour, made light enough to read on the dark panel. A name with none chosen gets one of Twitch's, the same each time."""
 if not re.match(r'^#[0-9A-Fa-f]{6}$',colour or ''):colour=NAME_COLOURS[sum(name.encode())%len(NAME_COLOURS)]
 r,g,b=(int(colour[i:i+2],16)/255 for i in (1,3,5));hue,light,saturation=colorsys.rgb_to_hls(r,g,b)
 r,g,b=colorsys.hls_to_rgb(hue,max(light,.66),min(saturation,.85));return (round(r*255),round(g*255),round(b*255),255)

@functools.lru_cache(maxsize=8)
def emoji_font(size):
 """Windows' colour emoji font, or None where it is missing."""
 from PIL import ImageFont
 try:return ImageFont.truetype('C:/Windows/Fonts/seguiemj.ttf',size)
 except OSError:return None

def is_emoji(character):
 code=ord(character)
 return code>=0x1F000 or 0x2600<=code<=0x27BF or code in (0x200D,0xFE0F,0x2B50,0x2B55,0x2B1B,0x2B1C,0x231A,0x231B,0x23F0,0x23F3,0x2934,0x2935,0x3030,0x303D)

def runs(text):
 """The text in pieces, each all emoji or all not, so each is drawn with the font that has it."""
 pieces=[]
 for character in text:
  emoji=is_emoji(character)
  if pieces and pieces[-1][0]==emoji:pieces[-1][1]+=character
  else:pieces.append([emoji,character])
 return pieces

class Writer:
 """Measures and draws text that mixes words and colour emoji."""
 def __init__(self,draw,size,bold=False):
  self.draw=draw;self.font=font(size,bold);self.emoji=emoji_font(round(size*.92))
 def length(self,text):
  return sum(self.draw.textlength(piece,font=self.emoji if emoji and self.emoji else self.font) for emoji,piece in runs(text))
 def write(self,image,x,y,text,fill):
  for emoji,piece in runs(text):
   if emoji and self.emoji:
    piece=piece.replace('\u200d','').replace('\ufe0f','')
    if piece:self.draw.text((x,y+1),piece,font=self.emoji,embedded_color=True)
    x+=self.draw.textlength(piece,font=self.emoji) if piece else 0
   else:self.draw.text((x,y),piece,font=self.font,fill=fill);x+=self.draw.textlength(piece,font=self.font)
  return x

def wrapped(writer,text,first,room):
 """text broken into lines: the first one first wide, the rest room wide. A word too long for a line is broken inside."""
 lines=[];line='';width=first
 for word in re.split(r'(\s+)',text):
  if not word:continue
  if writer.length(line+word)<=width:line+=word;continue
  if line.strip():lines.append(line.rstrip());line='';width=room
  word=word.lstrip()
  while word and writer.length(word)>width:
   cut=len(word)
   while cut>1 and writer.length(word[:cut])>width:cut-=1
   lines.append(word[:cut]);word=word[cut:];width=room
  line=word
 if line.strip() or not lines:lines.append(line.rstrip())
 return lines

def chat_image(view,scale=1.0):
 """The newest chat messages under the channel's name: badges, the name in its colour, and the words, with colour emoji. The newest
 message is lit for a moment. view: dict(channel=..., messages=Chat.view(...), now=...)."""
 from PIL import Image,ImageDraw
 s=scale_of(scale);pad=round(12*s);width=round(WIDTH*s);room=width-2*pad;line_height=round(18*s);size=round(13*s)
 measure=ImageDraw.Draw(Image.new('RGBA',(1,1)));plain=Writer(measure,size);strong=Writer(measure,size,True)
 laid=[]
 for message in reversed(view['messages']):
  text=re.sub(r'[\x00-\x1f\x7f]','',message['text'])[:400].strip()
  if message['kind']=='event':
   head=round(12*s);lines=wrapped(plain,text,room-head,room-head)
  else:
   name=message['name'][:25];dots=len(message['badges'])*round(10*s)
   head=dots+strong.length(name)+(plain.length(' ') if message['kind']=='action' else plain.length(': '))
   lines=wrapped(plain,text,max(room//3,room-head),room)
  # A long message shows its first lines and ends in an ellipsis.
  if len(lines)>MESSAGE_LINES:
   lines=lines[:MESSAGE_LINES];last=lines[-1]
   while last and plain.length(last+'…')>room:last=last[:-1]
   lines[-1]=last.rstrip()+'…'
  # Whole messages only: an older one that no longer fits is left out.
  if laid and sum(len(item[2]) for item in laid)+len(lines)>CHAT_LINES:break
  laid.append((message,head,lines))
 laid.reverse()
 shown_lines=sum(len(lines) for _,_,lines in laid)
 height=pad+round(16*s)+round(6*s)+shown_lines*line_height+pad
 image,draw=blank(width,height,s);plain.draw=strong.draw=draw
 # The channel's name with Twitch's purple beside it.
 r=round(4*s);cy=pad+round(8*s);draw.ellipse((pad,cy-r,pad+2*r,cy+r),fill=TWITCH)
 draw.text((pad+2*r+round(7*s),pad-round(1*s)),'#'+view['channel'],font=font(round(12*s),True),fill=SOFT)
 y=pad+round(16*s)+round(6*s);now=view.get('now',0)
 for message,head,lines in laid:
  # A new message is lit for a moment: a soft band behind it and a gold mark at its left, both fading.
  age=now-message['at']
  if 0<=age<FRESH:
   light=1-age/FRESH;top=y+round(1*s);bottom=y+len(lines)*line_height-round(1*s)
   draw.rounded_rectangle((pad-round(7*s),top,width-pad+round(7*s),bottom),radius=round(6*s),fill=(255,255,255,round(26*light)))
   draw.rounded_rectangle((pad-round(7*s),top,pad-round(5*s),bottom),radius=round(1*s),fill=GOLD[:3]+(round(255*light),))
  for index,line in enumerate(lines):
   x=pad
   if message['kind']=='event':
    if index==0:
     k=round(4*s);cx=pad+k;cy=y+line_height//2+round(1*s);draw.polygon([(cx,cy-k),(cx+k,cy),(cx,cy+k),(cx-k,cy)],fill=GOLD)
    plain.write(image,x+head,y,line,GOLD)
   elif index==0:
    for badge in message['badges']:
     dot=round(3*s);cy=y+line_height//2+round(1*s);draw.ellipse((x,cy-dot,x+2*dot,cy+dot),fill=BADGES[badge]);x+=round(10*s)
    colour=readable(message['colour'],message['name'])
    x=strong.write(image,x,y,message['name'][:25],colour)
    x=plain.write(image,x,y,' ' if message['kind']=='action' else ': ',SOFT)
    plain.write(image,x,y,line,colour if message['kind']=='action' else WHITE)
   else:plain.write(image,x,y,line,WHITE)
   y+=line_height
 return image

def stack(images,scale=1.0):
 """The panels one under the other, as one image with transparency."""
 from PIL import Image
 images=[image for image in images if image is not None]
 if not images:return None
 gap=round(GAP*scale_of(scale));width=max(image.width for image in images);height=sum(image.height for image in images)+gap*(len(images)-1)
 out=Image.new('RGBA',(width,height),(0,0,0,0));y=0
 for image in images:out.paste(image,(0,y));y+=image.height+gap
 return out

def render(perf=None,stream=None,timer=None,trophy=None,pad=None,scale=1.0,chat=None):
 """The overlay, (BGRA bytes, width, height), or None when nothing is to be shown. perf: PerformanceLog.view(); stream: the stream's own
 numbers (performance.overlay_lines); timer: RunTimer.view(); trophy: the trophy that just unlocked; pad: a pad_input.PadState;
 chat: the chat panel's view, see chat_image."""
 image=stack([overlay_image(perf,stream or {},scale) if perf is not None else None,timer_image(timer,scale) if timer is not None else None,
  trophy_image(trophy,scale) if trophy is not None else None,pad_image(pad,scale) if pad is not None else None,
  chat_image(chat,scale) if chat and chat.get('messages') else None],scale)
 return (image.tobytes('raw','BGRA'),image.width,image.height) if image is not None else None
