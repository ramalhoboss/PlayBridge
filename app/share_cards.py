"""Cards to share: pictures of what PlayBridge measured, drawn with Pillow in the app's gold-on-black look, at 1200 x 675 so they fit
a post on any social network. performance_card draws a Performance Lab report, wrapped_card a year of play."""
from PIL import Image,ImageDraw,ImageFilter,ImageFont

WIDTH,HEIGHT=1200,675
GOLD=(212,175,55);GOLD_SOFT=(235,212,142);WHITE=(246,246,248);MUTED=(176,176,186);DIM=(118,118,128);PANEL=(255,255,255,14)
MARGIN=56

_fonts={}
def face(size,weight='regular'):
 """Segoe UI in light, regular or semibold from Windows, or Pillow's own font where it is missing."""
 key=(size,weight)
 if key not in _fonts:
  name={'light':'segoeuil.ttf','semibold':'seguisb.ttf','bold':'segoeuib.ttf'}.get(weight,'segoeui.ttf')
  try:_fonts[key]=ImageFont.truetype('C:/Windows/Fonts/'+name,size)
  except OSError:
   try:_fonts[key]=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',size)
   except OSError:_fonts[key]=ImageFont.load_default()
 return _fonts[key]

def fit(draw,text,size,weight,width):
 """The text and font that fit width: smaller down to two thirds of size, then cut with an ellipsis."""
 for step in range(size,max(10,size*2//3)-1,-2):
  font=face(step,weight)
  if draw.textlength(text,font=font)<=width:return text,font
 font=face(max(10,size*2//3),weight)
 while text and draw.textlength(text+'…',font=font)>width:text=text[:-1]
 return text.rstrip()+'…',font

_ground=[]
def background():
 """The card's ground: near black with a warm glow from the top right, and a gold hairline inside the edge. Drawn once, then copied."""
 if not _ground:
  image=Image.new('RGB',(WIDTH,HEIGHT),(10,10,13))
  glow=Image.new('L',(WIDTH,HEIGHT),0);ImageDraw.Draw(glow).ellipse((WIDTH-520,-420,WIDTH+380,380),fill=150)
  glow=glow.filter(ImageFilter.GaussianBlur(160));warm=Image.new('RGB',(WIDTH,HEIGHT),(58,46,14));image=Image.composite(warm,image,glow)
  ImageDraw.Draw(image).rounded_rectangle((18,18,WIDTH-19,HEIGHT-19),radius=26,outline=(212,175,55),width=1);_ground.append(image)
 return _ground[0].copy()

def overlay(image,box,radius=18,fill=PANEL,outline=(255,255,255,26)):
 """A glass panel over the card."""
 layer=Image.new('RGBA',image.size,(0,0,0,0));ImageDraw.Draw(layer).rounded_rectangle(box,radius=radius,fill=fill,outline=outline,width=1)
 image.paste(Image.alpha_composite(image.convert('RGBA'),layer).convert('RGB'))

def chip(draw,x,y,text,size=17,ink=GOLD_SOFT,line=GOLD):
 """A rounded label; returns its right edge."""
 font=face(size,'semibold');width=round(draw.textlength(text,font=font))+28;height=size+16
 draw.rounded_rectangle((x,y,x+width,y+height),radius=height//2,outline=line,width=1);draw.text((x+14,y+height/2),text,font=font,fill=ink,anchor='lm')
 return x+width

def header(draw,label):
 draw.text((MARGIN,58),'PLAYBRIDGE',font=face(15,'semibold'),fill=GOLD,anchor='lm')
 draw.text((MARGIN+draw.textlength('PLAYBRIDGE',font=face(15,'semibold'))+14,58),label.upper(),font=face(15),fill=MUTED,anchor='lm')

def footer(draw,text):
 draw.text((WIDTH-MARGIN,HEIGHT-68),text,font=face(15),fill=DIM,anchor='rm')

def frame_times(curve):
 """The graph's points from a session's rate curve: (average frame time, slowest frame time) in ms, None where the game drew nothing."""
 out=[]
 for point in curve or []:
  try:average,low=float(point[0]),float(point[1])
  except (TypeError,ValueError,IndexError):out.append(None);continue
  out.append(None if average<1 else (1000/average,1000/max(low,1) if low>=1 else None))
 return out

def graph(image,box,curve,mode,minutes):
 """The frame-time graph of the latest session in box, with a guide at the mode's frame time."""
 overlay(image,box);draw=ImageDraw.Draw(image);x0,y0,x1,y1=box
 title='Frame time of the last session, ms'+(f'  ·  {minutes:.0f} min' if minutes else '')
 draw.text((x0+22,y0+26),title,font=face(16,'semibold'),fill=WHITE,anchor='lm')
 points=frame_times(curve);known=[point for point in points if point]
 left,right,top,bottom=x0+64,x1-24,y0+58,y1-30
 if not known:
  draw.text(((x0+x1)/2,(y0+y1)/2),'No graph for this game yet',font=face(18),fill=MUTED,anchor='mm');return
 first=(mode or '').split()[:1];cap=int(first[0]) if first and first[0].isdigit() else None
 averages=sorted(point[0] for point in known);guide=1000/cap if cap else averages[len(averages)//2]
 worst=sorted(point[1] for point in known if point[1]);high=worst[int(len(worst)*.98)] if worst else averages[-1]
 scale=min(100.0,max(guide*2.2,high*1.1,averages[-1]*1.1))
 def y_of(ms):return bottom-(min(ms,scale)/scale)*(bottom-top)
 # The scale: the guide at the mode's frame time and the top value.
 for ms,ink in ((guide,GOLD),(scale,DIM)):
  y=y_of(ms);draw.text((left-12,y),f'{ms:.1f}' if ms<100 else f'{ms:.0f}',font=face(14),fill=ink,anchor='rm')
 y=y_of(guide)
 for x in range(left,right,14):draw.line((x,y,min(x+7,right),y),fill=(212,175,55),width=1)
 draw.line((left,bottom,right,bottom),fill=(70,70,78),width=1)
 step=(right-left)/max(1,len(points)-1)
 # The slowest moment of each stretch as a faint spike above its average, then the average as the line.
 for i,point in enumerate(points):
  if point and point[1] and point[1]>point[0]*1.05:draw.line((left+i*step,y_of(point[0]),left+i*step,y_of(point[1])),fill=(120,98,40),width=2)
 path=[]
 for i,point in enumerate(points):
  if point is None:
   if len(path)>1:draw.line(path,fill=GOLD_SOFT,width=3,joint='curve')
   path=[];continue
  path.append((left+i*step,y_of(point[0])))
 if len(path)>1:draw.line(path,fill=GOLD_SOFT,width=3,joint='curve')
 elif len(path)==1:draw.ellipse((path[0][0]-3,path[0][1]-3,path[0][0]+3,path[0][1]+3),fill=GOLD_SOFT)

def stat(draw,x,y,label,value,width):
 draw.text((x,y),label,font=face(14,'semibold'),fill=MUTED)
 text,font=fit(draw,value,34,'light',width);draw.text((x,y+20),text,font=font,fill=WHITE)

def performance_card(report):
 """A Performance Lab report as a Pillow RGB image."""
 from performance_lab import day,duration,stability
 image=background();draw=ImageDraw.Draw(image);header(draw,'Performance Lab')
 name,font=fit(draw,report.get('name') or report.get('title') or 'PS5 game',50,'semibold',WIDTH-2*MARGIN)
 draw.text((MARGIN,90),name,font=font,fill=WHITE)
 sessions=report.get('sessions') or 0
 right=chip(draw,MARGIN,166,report.get('mode') or 'Unlocked')
 draw.text((right+16,166+16),f"{sessions} {'session' if sessions==1 else 'sessions'}  ·  {duration(report.get('minutes'))}  ·  last played {day(report.get('last'))}",font=face(17),fill=MUTED,anchor='lm')
 # The big number: the average rate over every session in this mode.
 average=report.get('fps_average')
 draw.text((MARGIN-6,232),f'{average:.0f}' if average is not None else '—',font=face(150,'light'),fill=WHITE)
 draw.text((MARGIN,408),'AVERAGE FPS',font=face(16,'semibold'),fill=GOLD)
 steady=stability(report)
 if steady:draw.text((MARGIN,434),steady,font=face(17),fill=MUTED)
 column=(430-MARGIN)//3
 low1=report.get('fps_low1');low01=report.get('fps_low01');lowest=report.get('fps_lowest')
 stats=[('1% LOW',f'{low1:.0f}' if low1 is not None else '—'),('0.1% LOW',f'{low01:.0f}' if low01 is not None else '—'),('LOWEST',f'{lowest:.0f}' if lowest is not None else '—')]
 for i,(label,value) in enumerate(stats):stat(draw,MARGIN+i*column,478,label,value,column-12)
 graph(image,(470,232,WIDTH-MARGIN,560),report.get('curve'),report.get('mode') or '',report.get('curve_minutes'))
 draw=ImageDraw.Draw(image);x=MARGIN
 for text in [t for t in (f"CPU up to {report['cpu_max']} °C" if report.get('cpu_max') else '',f"SoC up to {report['soc_max']} °C" if report.get('soc_max') else '',
   f"{report['watts_average']:.0f} W average, {report['watts_max']:.0f} W at most" if report.get('watts_average') is not None and report.get('watts_max') is not None else '') if t]:
  x=chip(draw,x,592,text,15,WHITE,(90,90,100))+10
 footer(draw,'Measured on the PS5 by PlayBridge')
 return image

def wrapped_card(year,level=None):
 """PlayBridge Wrapped: one year of play (game_stats.year) as a Pillow RGB image. level is the PSN trophy level as it stands now
 ({level, counts of each grade}) when the player is signed in, else None."""
 image=background();draw=ImageDraw.Draw(image);header(draw,'Wrapped')
 which=year.get('year') or '';title=f'Your {which} so far' if year.get('soFar') else f'Your {which}'
 draw.text((MARGIN,90),title,font=face(50,'semibold'),fill=WHITE)
 draw.text((MARGIN-6,160),year.get('hours') or '0 h',font=face(130,'light'),fill=WHITE)
 draw.text((MARGIN,322),'PLAYED ON PS5',font=face(16,'semibold'),fill=GOLD)
 column=(560-MARGIN)//4
 numbers=[('DAYS',year.get('days',0)),('SESSIONS',year.get('sessions',0)),('GAMES',year.get('games',0)),('TROPHIES',year.get('trophies',0))]
 for i,(label,value) in enumerate(numbers):stat(draw,MARGIN+i*column,366,label,str(value),column-12)
 lines=[]
 if year.get('month'):lines.append(f"Busiest month: {year['month']}")
 if (year.get('streak') or 0)>1:lines.append(f"Best run: {year['streak']} days in a row")
 if year.get('weekday'):lines.append(f"You played most on {year['weekday']}")
 longest=year.get('longest')
 if longest:lines.append(f"Longest session: {longest['text']} of {longest['name']}")
 y=452
 for line in lines[:4]:
  text,font=fit(draw,line,19,'regular',560-MARGIN);draw.text((MARGIN,y),text,font=font,fill=MUTED);y+=31
 # Most played, with a bar for each.
 box=(610,150,WIDTH-MARGIN,560);overlay(image,box);draw=ImageDraw.Draw(image);x0,y0,x1,y1=box
 draw.text((x0+26,y0+30),'Most played',font=face(18,'semibold'),fill=WHITE,anchor='lm')
 top=year.get('top') or []
 if not top:draw.text(((x0+x1)/2,(y0+y1)/2),'No games this year yet',font=face(18),fill=MUTED,anchor='mm')
 for i,game in enumerate(top[:5]):
  y=y0+72+i*66;place=f'{i+1}'
  draw.text((x0+26,y+12),place,font=face(22,'light'),fill=GOLD_SOFT,anchor='lm')
  hours_text=game.get('text') or '';hours_width=draw.textlength(hours_text,font=face(17,'semibold'))
  name,font=fit(draw,game.get('name') or 'PS5 game',19,'regular',x1-x0-80-hours_width-26)
  draw.text((x0+60,y+12),name,font=font,fill=WHITE,anchor='lm');draw.text((x1-26,y+12),hours_text,font=face(17,'semibold'),fill=GOLD_SOFT,anchor='rm')
  share=max(0.0,min(1.0,float(game.get('share') or 0)));left,right=x0+60,x1-26
  draw.rounded_rectangle((left,y+32,right,y+38),radius=3,fill=(40,40,46))
  if share>0:draw.rounded_rectangle((left,y+32,left+max(6,(right-left)*share),y+38),radius=3,fill=GOLD)
 draw=ImageDraw.Draw(image)
 if level:
  x=chip(draw,MARGIN,592,f"PSN trophy level {level.get('level',0)}",15,WHITE,(90,90,100))+10
  counts={item['grade']:item['count'] for item in level.get('counts') or []}
  if counts.get('platinum'):chip(draw,x,592,f"{counts['platinum']} platinum{'s' if counts['platinum']!=1 else ''}",15,WHITE,(90,90,100))
 footer(draw,'Played on PS5 with PlayBridge')
 return image

def save(image,path):
 """Writes the card as a PNG; returns the path."""
 image.save(path,'PNG',optimize=True);return path
