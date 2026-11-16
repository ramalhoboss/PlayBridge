"""The PS5's performance, as its own sensors and counters give it: the frames the game draws each second (console_control.GameRate),
the CPU and SoC temperatures and the power its chip and memory draw. The overlay shows them over the picture, drawn by the graphics
card into the picture itself (d3d11_presenter), and each game that ran long enough leaves a summary in the session history."""
import collections,json,threading,time
from pathlib import Path

# Quarter-second points of the game's frame rate: the last minute, for the overlay's graph.
POINTS=240
# A game kept open for less than this leaves no summary: a launch and a close tell nothing.
SHORTEST=60
# Summaries kept in the history file, newest last.
KEEP=300
# The game counts as at its usual rate within this many frames a second of it.
NEAR_RATE=2
# The rates games are held to. A game whose fastest seconds sit on one of them runs in that mode; any other is unlocked.
CAPS=(30,40,60,120)
# Points kept of a session's rate for its graph: each the average and the lowest of its stretch of the session.
CURVE=180

def percentile(values,share):
 """The value below which share percent of values lie, by nearest rank. None for no values."""
 if not values:return None
 ordered=sorted(values);return ordered[min(len(ordered)-1,max(0,int(len(ordered)*share/100+.5)-1))]
def mode_of(rates):
 """The game's mode as its rate shows it: the cap its fastest seconds (the 95th percentile) sit on, 'Unlocked' for none, '' for no rate."""
 top=percentile([value for value in rates if value>=1],95)
 if top is None:return ''
 for cap in CAPS:
  if abs(top-cap)<=NEAR_RATE:return f'{cap} fps'
 return 'Unlocked'
def curve(rates,points=CURVE):
 """The session's rate in at most points stretches, each [average, lowest] of the moments the game drew, [0, 0] for a stretch it drew
 nothing in (a pause or the console's menu), for its graph."""
 if not rates:return []
 size=max(1,-(-len(rates)//points));out=[]
 for start in range(0,len(rates),size):
  part=[value for value in rates[start:start+size] if value>=1]
  out.append([round(sum(part)/len(part),1),round(min(part),1)] if part else [0,0])
 return out

def watts(status):
 """The power the console's chip and memory draw, (GPU, CPU, memory) in watts, or None when it gave no reading. The payload sends -1 for
 a reading it did not get, and older payloads send no such fields."""
 parts=[status.get(name) for name in ('gpu_mw','cpu_mw','mem_mw')] if isinstance(status,dict) else []
 if len(parts)!=3 or any(type(value) is not int or value<0 for value in parts) or not sum(parts):return None
 return tuple(value/1000 for value in parts)

def reading(status,name):
 """A temperature the console read, in °C, or None."""
 value=status.get(name) if isinstance(status,dict) else None
 return value if type(value) is int and value>0 else None

class GameSession:
 """What one game did while it ran, from the status answers that came every quarter second."""
 def __init__(self,title,name,now,wall):
  self.title=title;self.name=name;self.started=now;self.last=now;self.wall=wall;self.rates=[];self.cpu=[];self.soc=[];self.power=[]
 def add(self,status,game_fps,now):
  self.last=now
  if game_fps is not None:self.rates.append(game_fps)
  for values,value in ((self.cpu,reading(status,'cpu_c')),(self.soc,reading(status,'soc_c'))):
   if value is not None:values.append(value)
  parts=watts(status)
  if parts is not None:self.power.append(parts)
 def summary(self):
  """The session as it is kept: rates in frames a second, temperatures in °C, power in watts. None for what the console never gave.
  The rates leave out the moments the game drew nothing, as on a pause or the console's menu: that is not the game slowing down."""
  rates=[value for value in self.rates if value>=1];usual=round(sorted(rates)[len(rates)//2]) if rates else None
  def mean(values):return round(sum(values)/len(values),1) if values else None
  out=dict(title=self.title,name=self.name,started=self.wall,minutes=round((self.last-self.started)/60,1),
   fps_average=mean(rates),fps_lowest=round(min(rates),1) if rates else None,fps_usual=usual,
   at_usual=round(100*sum(1 for value in rates if value>=usual-NEAR_RATE)/len(rates)) if rates else None,
   cpu_max=max(self.cpu) if self.cpu else None,cpu_average=mean(self.cpu),soc_max=max(self.soc) if self.soc else None,soc_average=mean(self.soc))
  if rates:out.update(fps_low1=round(percentile(rates,1),1),fps_low01=round(percentile(rates,.1),1),mode=mode_of(rates),curve=curve(self.rates))
  if self.power:
   totals=[sum(parts) for parts in self.power]
   out.update(watts_average=mean(totals),watts_max=round(max(totals),1),gpu_watts=mean([p[0] for p in self.power]),cpu_watts=mean([p[1] for p in self.power]),memory_watts=mean([p[2] for p in self.power]))
  return out

def report_line(summary):
 """One sentence for a finished game, with only what the console measured."""
 parts=[]
 if summary.get('fps_average') is not None:parts.append(f"{summary['fps_average']:.0f} fps on average, {summary['fps_lowest']:.0f} at its lowest")
 if summary.get('cpu_max'):parts.append(f"CPU up to {summary['cpu_max']} °C")
 if summary.get('watts_average') is not None:parts.append(f"{summary['watts_average']:.0f} W on average")
 return f"{summary['name']}: "+', '.join(parts) if parts else ''

def report_details(summary):
 """The lines of a finished game in the session panel."""
 lines=[f"{summary['name']}  ·  {summary['minutes']:.0f} min"]
 if summary.get('fps_average') is not None:lines.append(f"{summary['fps_average']:.1f} fps average  ·  lowest {summary['fps_lowest']:.0f}  ·  {summary['at_usual']}% at {summary['fps_usual']}")
 temps=[f"{label} up to {summary[key]} °C" for label,key in (('CPU','cpu_max'),('SoC','soc_max')) if summary.get(key)]
 if temps:lines.append('  ·  '.join(temps))
 if summary.get('watts_average') is not None:lines.append(f"{summary['watts_average']:.0f} W average, {summary['watts_max']:.0f} W at most  ·  GPU {summary['gpu_watts']:.0f}  ·  CPU {summary['cpu_watts']:.0f}  ·  memory {summary['memory_watts']:.0f}")
 return lines

class PerformanceLog:
 """Fed by the console link's thread with each status answer; read by the window for the overlay. Thread-safe."""
 def __init__(self,path,name_of=lambda title:title,notify=None,clock=time.monotonic,wall=time.time):
  self.path=Path(path);self.name_of=name_of;self.notify=notify;self.clock=clock;self.wall=wall;self.lock=threading.Lock()
  self.points=collections.deque(maxlen=POINTS);self.status={};self.game_fps=None;self.session=None;self.last_report=None
 def add(self,status,game_fps,title):
  """One status answer, the game's rate as counted then, and the running game's title id ('' with none)."""
  now=self.clock();finished=None
  with self.lock:
   if self.session is not None and self.session.title!=title:finished=self.close()
   if title and self.session is None:self.session=GameSession(title,self.name_of(title),now,round(self.wall()))
   if self.session is not None:self.session.add(status,game_fps,now)
   self.status=dict(status) if isinstance(status,dict) else {};self.game_fps=game_fps;self.points.append(game_fps if title else None)
  if finished:self.keep(finished)
 def end(self):
  """PlayBridge closes: the game that was running ends here too. A stream that drops and comes back keeps the same game going."""
  with self.lock:finished=self.close() if self.session is not None else None;self.points.clear();self.status={};self.game_fps=None
  if finished:self.keep(finished)
 def close(self):
  session,self.session=self.session,None
  if session.last-session.started<SHORTEST:return None
  summary=session.summary();self.last_report=summary;return summary
 def keep(self,summary):
  try:history=json.loads(self.path.read_text(encoding='utf-8')) if self.path.is_file() else []
  except (OSError,ValueError):history=[]
  if not isinstance(history,list):history=[]
  history=(history+[summary])[-KEEP:]
  try:self.path.parent.mkdir(parents=True,exist_ok=True);self.path.write_text(json.dumps(history,indent=1),encoding='utf-8')
  except OSError:pass
  line=report_line(summary)
  if line and self.notify:self.notify(line)
 def history(self):
  try:history=json.loads(self.path.read_text(encoding='utf-8'))
  except (OSError,ValueError):return []
  return history if isinstance(history,list) else []
 def view(self):
  """What the overlay shows now."""
  with self.lock:
   session=self.session
   return dict(status=dict(self.status),game_fps=self.game_fps,points=list(self.points),name=session.name if session else '',
    lowest=round(min(session.rates[-POINTS:])) if session and session.rates else None)

def overlay_lines(view,stream):
 """The overlay's text, top to bottom, from the performance view and the stream's own numbers. stream: dict with 'picture', 'mbps',
 'pc_ms' and 'smooth' (the rate smooth motion shows, or None). Returns (name, big rate, its note, lines)."""
 status=view['status'];fps=view['game_fps']
 big=f"{fps:.0f}" if fps is not None else '—'
 note='FPS'+(f"  ·  lowest {view['lowest']}" if view.get('lowest') is not None else '')
 if fps is not None and stream.get('smooth'):note=f"FPS  →  {stream['smooth']} smooth"
 lines=[]
 temps=[f'{label} {value}°' for label,value in (('CPU',reading(status,'cpu_c')),('SoC',reading(status,'soc_c'))) if value]
 # The fans' target, when PlayBridge set a lower one.
 aim=status.get('fan_set')
 if isinstance(aim,int) and not isinstance(aim,bool) and aim>0:temps.append(f'Fans aim {aim}°')
 if temps:lines.append('   '.join(temps))
 parts=watts(status)
 if parts:lines.append(f'{sum(parts):.0f} W   GPU {parts[0]:.0f}  CPU {parts[1]:.0f}  RAM {parts[2]:.0f}')
 shown=[value for value in (stream.get('picture'),f"{stream['mbps']:.0f} Mbps" if stream.get('mbps') is not None else None,f"PC {stream['pc_ms']:.0f} ms" if stream.get('pc_ms') is not None else None) if value]
 if shown:lines.append('   '.join(shown))
 return view.get('name') or 'PS5',big,note,lines

_fonts={}
def font(size,bold=False):
 """Segoe UI from Windows, or Pillow's own font where it is missing."""
 from PIL import ImageFont
 key=(size,bold)
 if key not in _fonts:
  try:_fonts[key]=ImageFont.truetype('C:/Windows/Fonts/'+('seguisb.ttf' if bold else 'segoeui.ttf'),size)
  except OSError:_fonts[key]=ImageFont.load_default()
 return _fonts[key]

def render_overlay(view,stream,scale=1.0):
 """The overlay as an image with transparency: (BGRA bytes, width, height)."""
 image=overlay_image(view,stream,scale);return image.tobytes('raw','BGRA'),image.width,image.height
def overlay_image(view,stream,scale=1.0):
 """The overlay as a Pillow RGBA image."""
 from PIL import Image,ImageDraw
 name,big,note,lines=overlay_lines(view,stream)
 s=max(.75,min(2.5,scale));pad=round(12*s);width=round(250*s);graph=round(34*s);line=round(17*s)
 height=pad+round(15*s)+round(34*s)+graph+round(8*s)+line*len(lines)+pad
 image=Image.new('RGBA',(width,height),(0,0,0,0));draw=ImageDraw.Draw(image)
 draw.rounded_rectangle((0,0,width-1,height-1),radius=round(10*s),fill=(8,8,10,150),outline=(212,175,55,70),width=max(1,round(s)))
 y=pad;draw.text((pad,y),name[:28],font=font(round(12*s)),fill=(235,212,142,255));y+=round(15*s)
 big_font=font(round(30*s),True);draw.text((pad,y-round(4*s)),big,font=big_font,fill=(255,255,255,255))
 left=pad+round(draw.textlength(big,font=big_font))+round(8*s);draw.text((left,y+round(14*s)),note,font=font(round(11*s)),fill=(200,200,205,255));y+=round(34*s)
 # The game's frame rate over the last minute: the line is the rate, the faint rule the usual one.
 points=view['points'];known=[value for value in points if value is not None]
 if known:
  top=max(60.0,max(known));x0=pad;x1=width-pad;y0=y;y1=y+graph
  usual=sorted(known)[len(known)//2];rule=y1-(usual/top)*(y1-y0);draw.line((x0,rule,x1,rule),fill=(212,175,55,60),width=1)
  step=(x1-x0)/max(1,len(points)-1);path=[]
  for i,value in enumerate(points):
   if value is None:
    if len(path)>1:draw.line(path,fill=(235,212,142,255),width=max(1,round(1.5*s)))
    path=[];continue
   path.append((x0+i*step,y1-(min(value,top)/top)*(y1-y0)))
  if len(path)>1:draw.line(path,fill=(235,212,142,255),width=max(1,round(1.5*s)))
 y+=graph+round(8*s)
 for text in lines:draw.text((pad,y),text,font=font(round(12*s)),fill=(225,225,230,255));y+=line
 return image
