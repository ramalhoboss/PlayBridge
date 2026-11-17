"""The phone page's More panel, for a paired phone: your games, to start one on the PS5; the captures on this PC, to look at and save;
and what PlayBridge noted during this session.

The page asks with its pairing token in a header. A picture or video element and a download link cannot send a header, so a capture
opens through a ticket: an address that works while it is in use and for two minutes after, and never longer than three hours.

Small pictures are made one at a time and kept while PlayBridge runs, so a phone scrolling through a hundred recordings never takes
the processor from the stream."""
import hashlib,io,secrets,threading,time
from pathlib import Path

TICKET_IDLE=120
TICKET_LONGEST=3*3600
TICKETS=32
THUMB=(360,203)
ICON=(192,192)
CAPTURES=60

def capture_id(path):return hashlib.sha256(str(path).encode('utf8','replace')).hexdigest()[:20]

class Panel:
 """games(): [dict(title, name, running)], hidden games left out; icon(title): a picture's path or None; start(title, switch): a dict
 with state ('started', 'open', 'ask' or 'problem') and text; captures(): CaptureItems (path, kind, size, modified), newest first;
 log(): lines; thumbnail(path, size): a PIL image from a recording, or None."""
 def __init__(self,games,icon,start,captures,log,thumbnail=None,clock=time.monotonic):
  self.games=games;self.icon=icon;self.start=start;self.captures=captures;self.log=log;self.thumbnail=thumbnail;self.clock=clock
  self.lock=threading.Lock();self.making=threading.Lock();self.known={};self.tickets={};self.small={}
 def titles(self):return {game['title'] for game in self.games()}
 def game_list(self):
  return [dict(id=game['title'],name=game.get('name') or game['title'],running=bool(game.get('running'))) for game in self.games()]
 def start_game(self,title,switch=False):
  if title not in self.titles():return dict(state='problem',text='That game is not in your library.')
  return self.start(title,bool(switch))
 def cached(self,key,make):
  """A small picture made once: make() gives JPEG or PNG bytes, or None."""
  with self.lock:
   if key in self.small:return self.small[key]
  with self.making:
   with self.lock:
    if key in self.small:return self.small[key]
   try:data=make()
   except (OSError,ValueError,SyntaxError,MemoryError):data=None
  if data is None:return None
  with self.lock:
   if len(self.small)>CAPTURES*4:self.small.clear()
   self.small[key]=data
  return data
 def icon_bytes(self,title):
  """A game's picture, made small enough for a phone's grid."""
  if title not in self.titles():return None
  path=self.icon(title)
  if not path:return None
  try:stamp=Path(path).stat().st_mtime_ns
  except OSError:return None
  def make():
   from PIL import Image
   with Image.open(path) as source:
    source.thumbnail(ICON);image=source.convert('RGBA');out=io.BytesIO();image.save(out,'PNG',optimize=True);return out.getvalue()
  return self.cached(('icon',title,stamp),make)
 def capture_list(self):
  known={capture_id(item.path):item for item in list(self.captures())[:CAPTURES]}
  with self.lock:self.known=known
  return [dict(id=key,name=item.path.name,kind=item.kind,size=item.size,when=time.strftime('%d %b %H:%M',time.localtime(item.modified))) for key,item in known.items()]
 def item(self,key):
  with self.lock:return self.known.get(str(key))
 def thumb_bytes(self,key):
  """A small JPEG of a photo, or of a still from a recording."""
  item=self.item(key)
  if item is None:return None
  def make():
   if item.kind=='Videos':
    image=self.thumbnail(item.path,THUMB) if self.thumbnail else None
    if image is None:return None
   else:
    from PIL import Image
    with Image.open(item.path) as source:source.thumbnail(THUMB);image=source.convert('RGB')
   out=io.BytesIO();image.convert('RGB').save(out,'JPEG',quality=78);return out.getvalue()
  return self.cached(('thumb',key,item.modified),make)
 def ticket(self,key):
  """An address to look at or save a capture, or None."""
  item=self.item(key)
  if item is None:return None
  now=self.clock();name=secrets.token_urlsafe(18)
  with self.lock:
   self.tickets={k:v for k,v in self.tickets.items() if self.fresh(v,now)}
   while len(self.tickets)>=TICKETS:self.tickets.pop(next(iter(self.tickets)))
   self.tickets[name]=[item,now,now]
  return f'/api/file/{name}'
 @staticmethod
 def fresh(ticket,now):return now-ticket[2]<TICKET_IDLE and now-ticket[1]<TICKET_LONGEST
 def redeem(self,name):
  """The capture a ticket is for, while it is fresh; each use keeps it so for two minutes more."""
  now=self.clock()
  with self.lock:
   ticket=self.tickets.get(str(name))
   if ticket is None:return None
   if not self.fresh(ticket,now):self.tickets.pop(str(name),None);return None
   ticket[2]=now;return ticket[0]
 def log_lines(self):return [str(line) for line in self.log()][-200:]
