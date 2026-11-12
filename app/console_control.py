"""Game library, console status and power, through the control port the payload opens during a session."""
import json,os,queue,re,socket,sqlite3,struct,tempfile,threading,time
from datetime import datetime
from pathlib import Path
from PIL import Image

CONTROL_PORT=9077
STATUS,FILE,LAUNCH,CLOSE,REST,POWER_OFF,REBOOT,LIST=1,2,3,4,6,7,8,9
REQUEST=struct.Struct('<4sII');REPLY=struct.Struct('<4siI')
SHORT_REPLY=4096;FILE_LIMIT=0x10000000
DATABASE='/system_data/priv/mms/app.db'
# The payload's own logs, which it already lets the PC read: this capture run's, and the control thread's from the run before.
CAPTURE_LOG='/data/ps5screen-av3.txt';PREVIOUS_CONTROL_LOG='/data/playbridge-control.old.txt'
ICON_ROOTS=('/user/appmeta/','/user/appmeta/external/','/mnt/ext0/user/appmeta/','/mnt/ext1/user/appmeta/')
TITLE=re.compile('[A-Z]{4}[0-9]{5}')
# Big enough to fill a 1440p window. Past that, under the page's shading, nobody can tell.
ART_SIZE=(2560,1440)

def is_game_title(title):
 """System apps use the NPXS prefix."""
 return isinstance(title,str) and TITLE.fullmatch(title) is not None and not title.startswith('NPXS')
def running_title(status):
 """The game the console says is open, or an empty string."""
 title=status.get('title','');app=status.get('app',0)
 return title if is_game_title(title) and isinstance(app,int) and app>0 else ''
def menu_in_front(status):
 """True while the console's menu covers the open game, as it does after the PS button. A console that does not say counts as not covered."""
 front=status.get('front','');return bool(running_title(status)) and isinstance(front,str) and front.startswith('NPXS')
def console_line(status):
 """The temperatures the console reported, leaving out any it could not give. Its power reading is not shown: about 4 on the home screen and 16 during a game cannot be watts, and the frequency tells a player nothing."""
 def number(name):
  value=status.get(name);return value if isinstance(value,int) and not isinstance(value,bool) and value>0 else None
 parts=[]
 if number('cpu_c'):parts.append(f"CPU {number('cpu_c')} °C")
 if number('soc_c'):parts.append(f"SoC {number('soc_c')} °C")
 return '  ·  '.join(parts)

def read_exact(sock,size):
 data=bytearray()
 while len(data)<size:
  part=sock.recv(min(size-len(data),65536))
  if not part:raise EOFError('The console closed the control port')
  data.extend(part)
 return bytes(data)
def reply_header(sock):
 magic,result,size=REPLY.unpack(read_exact(sock,REPLY.size))
 if magic!=b'PBR1':raise ValueError('Invalid control reply')
 return result,size
def call(sock,command,body=b''):
 sock.sendall(REQUEST.pack(b'PBC1',command,len(body))+body)
 result,size=reply_header(sock)
 if size>SHORT_REPLY:raise ValueError('Oversized control reply')
 return result,read_exact(sock,size)
def fetch(sock,path,target,limit=FILE_LIMIT,progress=None):
 """Saves one console file. False when the console does not have it or does not allow it."""
 name=path.encode('utf8');sock.sendall(REQUEST.pack(b'PBC1',FILE,len(name))+name)
 result,size=reply_header(sock)
 if result:return False
 if size>limit:raise ValueError('Oversized console file')
 total=size
 with Path(target).open('wb') as out:
  while size:
   part=sock.recv(min(size,65536))
   if not part:raise EOFError('The console closed the control port')
   out.write(part);size-=len(part)
   if progress:progress(total-size,total)
 return True

def when(value):
 """Seconds since 1970 from a date the database keeps as a number or as ISO text; 0 if it says neither."""
 if isinstance(value,(int,float)):return float(value)/1000 if value>1e11 else max(0.0,float(value))
 if isinstance(value,str) and value:
  try:return max(0.0,datetime.fromisoformat(value.replace('Z','+00:00')).timestamp())
  except (ValueError,OSError,OverflowError):
   return when(float(value)) if value.replace('.','',1).isdigit() else 0.0
 return 0.0
def play_seconds(value):
 """Play time kept as seconds or as H:MM:SS; None if it is neither."""
 if isinstance(value,int):return value if value>=0 else None
 if isinstance(value,str):
  if value.isdigit():return int(value)
  parts=value.split(':')
  if len(parts)==3 and all(part.isdigit() for part in parts):return int(parts[0])*3600+int(parts[1])*60+int(parts[2])
 return None
def game_detail(game):
 """The line under a game's name."""
 parts=[]
 if game.get('played'):
  try:parts.append(datetime.fromtimestamp(game['played']).strftime('%d %b %Y'))
  except (OSError,OverflowError,ValueError):pass
 seconds=game.get('seconds')
 if seconds:parts.append(f'{seconds//3600} h' if seconds>=3600 else f'{max(1,seconds//60)} min')
 return '  ·  '.join(parts) or game['title']
def clean_name(name):
 """A game's name without control characters, the console's private glyphs or decorative symbols the card's font does not have."""
 return ''.join(c for c in str(name or '') if c.isprintable() and not '\u2190'<=c<='\u2bff').strip()
def console_file(value):
 """A file's path from the database, without the date it adds at the end. Empty if it is anything else."""
 path=value.split('?')[0] if isinstance(value,str) else ''
 return path if path.startswith('/') and path.isascii() else ''
def stamp(value):
 """The database's whole note on a file, date included: it changes when the console replaces the file. Empty if it is anything else."""
 return value if isinstance(value,str) and len(value)<=512 and value.isascii() and value.isprintable() else ''
def rows(db,table,names):
 """Rows as dictionaries, with only the columns this firmware has."""
 have={row[1] for row in db.execute(f'PRAGMA table_info("{table}")')}
 wanted=[name for name in names if name in have]
 if 'titleId' not in wanted:return
 for row in db.execute('SELECT '+','.join(f'"{name}"' for name in wanted)+f' FROM "{table}"'):yield dict(zip(wanted,row))
def read_games(path,user=None):
 """The games in a copy of the console's database, last played first. What the rows say only ever fills text on a card."""
 db=sqlite3.connect(str(path))
 try:
  db.execute('PRAGMA trusted_schema=OFF')
  tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  if 'tbl_contentinfo' not in tables:return []
  games={}
  for row in rows(db,'tbl_contentinfo',('titleId','titleName','lastAccessTime','installTime','appType','icon0Info','pic0Info','snd0Info','size')):
   title=row['titleId']
   # Type 0 is what the console itself runs and homebrew tools, which have no place on a shelf of games.
   if not is_game_title(title) or row.get('appType')==0:continue
   name=clean_name(row.get('titleName'))[:80] or title
   size=row.get('size')
   games[title]={'title':title,'name':name,'played':when(row.get('lastAccessTime')) or when(row.get('installTime')),'seconds':None,'installed':when(row.get('installTime')),'size':size if isinstance(size,int) and size>0 else 0,'icon':console_file(row.get('icon0Info')),'art':console_file(row.get('pic0Info')),'music':console_file(row.get('snd0Info')),'stamps':{kind:stamp(row.get(column)) for kind,column in (('icon','icon0Info'),('art','pic0Info'),('music','snd0Info'))}}
  personal=[name for name in tables if re.fullmatch('tbl_iconinfo_[0-9]+',name)]
  mine=f'tbl_iconinfo_{user:010d}' if isinstance(user,int) and user>0 else ''
  table=mine if mine in tables else personal[0] if len(personal)==1 else ''
  if table:
   for row in rows(db,table,('titleId','lastPlayedDate','lastPlayedDateOnConsole','lastAccessTime','playedTimeOnConsole')):
    game=games.get(row['titleId'])
    if game is None:continue
    played=when(row.get('lastPlayedDateOnConsole')) or when(row.get('lastPlayedDate')) or when(row.get('lastAccessTime'))
    if played:game['played']=played
    game['seconds']=play_seconds(row.get('playedTimeOnConsole'))
 finally:db.close()
 return sorted(games.values(),key=lambda game:(-game['played'],game['name'].lower()))
def load_games(path):
 try:saved=json.loads(Path(path).read_text(encoding='utf8'))
 except (OSError,ValueError):return []
 return [game for game in saved if isinstance(game,dict) and is_game_title(game.get('title')) and isinstance(game.get('name'),str)] if isinstance(saved,list) else []
def load_kept(path):
 """For each game, what the console's database said about each file when the PC read it: {title: {'icon'|'art'|'music': note}}."""
 try:saved=json.loads(Path(path).read_text(encoding='utf8'))
 except (OSError,ValueError):return {}
 if not isinstance(saved,dict):return {}
 return {title:{kind:note for kind,note in notes.items() if kind in ('icon','art','music') and isinstance(note,str)} for title,notes in saved.items() if is_game_title(title) and isinstance(notes,dict)}
def same_bytes(one,two):
 try:return Path(one).read_bytes()==Path(two).read_bytes()
 except OSError:return False
def replace_soon(partial,target,tries=20):
 """Windows refuses to replace a file while something reads it, as the window does for a moment when it draws a cover. A moment later it can."""
 for attempt in range(tries):
  try:Path(partial).replace(target);return
  except PermissionError:
   if attempt==tries-1:raise
   time.sleep(.05)
def save_icon(source,target):
 """Keeps a copy large enough for a cover on a big screen, and says whether it differs from the one already kept. Fails on anything that is not an image."""
 with Image.open(source) as image:
  image=image.convert('RGB');image.thumbnail((512,512))
  partial=Path(target).with_suffix('.partial');image.save(partial,'PNG')
 # The same picture comes out as the same file, so an icon read again only counts when the console has a new one.
 if same_bytes(partial,target):partial.unlink();return False
 replace_soon(partial,target);return True
def save_art(source,target):
 """Keeps a game's background art as a picture the page opens quickly. Fails on anything that is not an image."""
 with Image.open(source) as image:
  image=image.convert('RGB');image.thumbnail(ART_SIZE)
  partial=Path(target).with_suffix('.partial');image.save(partial,'JPEG',quality=90)
 replace_soon(partial,target)

class GameFlow:
 """Follows what the console runs, so the app knows when the grid gives way to the video and back."""
 PATIENCE=90
 def __init__(self):
  self.waiting=None;self.since=0;self.running='';self.after_close=None
 def launch(self,title,now):
  self.waiting=title;self.since=now
 def replace(self,title,now):
  """The console allows one game at a time, so the next one starts after this one has closed."""
  self.after_close=title;self.since=now
 def update(self,title,now):
  """None, or what changed: 'launch' for the game waiting on a close, 'started', 'failed' or 'closed'."""
  was,self.running=self.running,title
  if self.after_close:
   if not title:self.waiting,self.after_close=self.after_close,None;self.since=now;return 'launch'
   if now-self.since>self.PATIENCE:self.after_close=None;return 'failed'
   return None
  if self.waiting:
   if title==self.waiting:self.waiting=None;return 'started'
   if now-self.since>self.PATIENCE:self.waiting=None;return 'failed'
   return None
  return 'closed' if was and not title else None

class ConsoleLink:
 """Owns the control connection: one thread per capture session, which ends with the session."""
 # Often enough that the console's menu, after the PS button or a game closing on the console, is on the PC for only a moment.
 STATUS_EVERY=.25;LOG_EVERY=.1
 def __init__(self,folder,notify=lambda message:None):
  self.folder=Path(folder);self.small_icons=self.folder/'icons';self.icons=self.folder/'covers';self.arts=self.folder/'art';self.tracks=self.folder/'music';self.notify=notify;self.status={};self.online=False;self.revision=0;self.refreshing=False;self.jobs=queue.SimpleQueue();self.session=None;self.want_library=True
  # checks: the icons already on the PC, read again once each session, since an app on the console can change its icon without the database saying so.
  self.browsing=False;self.focus='';self.extras=[];self.checks=[]
  # When set, each session keeps copies of the payload's logs in this folder on the PC, numbered by session.
  self.log_folder=None;self.log_session=0
  self.games=load_games(self.folder/'games.json');self.kept=load_kept(self.folder/'kept.json')
 def begin(self,host):
  self.end();stop=threading.Event();self.session=stop;self.want_library=True;self.log_session+=1
  threading.Thread(target=self.run,args=(host,stop),name='PlayBridge console link',daemon=True).start()
 def end(self):
  if self.session is not None:self.session.set();self.session=None
  self.online=False;self.status={}
 def send(self,command,body=b'',done=None):
  """Queues a command. False without a connection, so that nothing fires later by surprise."""
  if not self.online:return False
  self.jobs.put((command,body,done));return True
 def work(self,job,done):
  """Runs job(sock) on the link's connection, between status readings, and gives done what it returns."""
  if not self.online:return False
  self.jobs.put((job,b'',done));return True
 def keep(self,sock,path,name):
  """Copies one payload log to this session's file, replacing the earlier copy only once the new one has arrived whole."""
  target=self.log_folder/f'session-{self.log_session}-{name}.txt';part=target.with_suffix('.part')
  if fetch(sock,path,part,limit=1<<20):os.replace(part,target)
 def last_look(self,wait=.4):
  """One more copy of the capture log as the stream ends, while the payload may still answer."""
  if self.log_folder is None or not self.online:return
  done=threading.Event()
  if self.work(lambda sock:self.keep(sock,CAPTURE_LOG,'capture-end'),lambda _:done.set()):done.wait(wait)
 def launch(self,title,done=None):
  return is_game_title(title) and self.send(LAUNCH,title.encode('ascii'),done)
 def refresh(self):
  self.want_library=True
 def game_name(self,title):
  return next((game['name'] for game in self.games if game['title']==title),title)
 def icon(self,title):
  """The large picture, or the small one an earlier version kept, until the large one has arrived."""
  for folder in (self.icons,self.small_icons):
   path=folder/(title+'.png')
   if path.is_file():return path
  return None
 def art(self,title):
  path=self.arts/(title+'.jpg');return path if path.is_file() else None
 def music_file(self,title):
  path=self.tracks/(title+'.at9');return path if path.is_file() else None
 def run(self,host,stop):
  while not stop.is_set():
   try:
    with socket.create_connection((host,CONTROL_PORT),2) as sock:
     sock.settimeout(15);sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1);self.serve(sock,stop)
   except (OSError,EOFError,ValueError,struct.error):pass
   if self.session is stop:self.online=False;self.status={}
   stop.wait(1)
 def serve(self,sock,stop):
  while True:
   try:self.jobs.get_nowait()
   except queue.Empty:break
  status_at=0;missing=[];log_at=0
  if self.log_folder is not None:self.keep(sock,PREVIOUS_CONTROL_LOG,'control-before')
  while not stop.is_set():
   now=time.monotonic()
   if now>=status_at:
    _,body=call(sock,STATUS);status_at=now+self.STATUS_EVERY;info=json.loads(body)
    if isinstance(info,dict) and self.session is stop:self.status=info;self.online=True
   if self.log_folder is not None and now>=log_at:self.keep(sock,CAPTURE_LOG,'capture');log_at=now+self.LOG_EVERY
   try:command,body,done=self.jobs.get(timeout=.02 if self.want_library or missing or self.check_due() or self.extra_due() else .1)
   except queue.Empty:
    if self.want_library:missing=self.read_library(sock)
    elif missing:self.fetch_icon(sock,missing.pop(0))
    elif self.check_due():self.fetch_icon(sock,self.next_check())
    elif self.extra_due():self.fetch_extra(sock,self.next_extra())
    continue
   if callable(command):result=command(sock)
   else:result,_=call(sock,command,body)
   if done is not None:done(result)
 def read_library(self,sock):
  """Takes the database and returns the icons to read now: those still missing and those the database says changed. Every other icon is read again later, while someone browses."""
  self.want_library=False;self.refreshing=True
  try:
   self.icons.mkdir(parents=True,exist_ok=True)
   with tempfile.TemporaryDirectory(dir=self.folder) as temporary:
    copy=Path(temporary)/'app.db'
    if not fetch(sock,DATABASE,copy):self.notify('The PS5 did not share its game list.');return []
    fetch(sock,DATABASE+'-wal',Path(temporary)/'app.db-wal')
    try:games=read_games(copy,self.status.get('user'))
    except sqlite3.Error:self.notify('Unable to read the game list from the PS5.');return []
   self.games=games;self.revision+=1;self.extras=self.extras_missing(games)
   (self.folder/'games.json').write_text(json.dumps(games),encoding='utf8')
   now=[game['title'] for game in games if not (self.icons/(game['title']+'.png')).is_file() or self.changed(game,'icon')]
   self.checks=[game['title'] for game in games if game['title'] not in now]
   return now
  finally:self.refreshing=False
 def changed(self,game,kind):
  """Whether the database's note on a game's file differs from the one kept when the PC read it. Unknown counts as changed."""
  note=game.get('stamps',{}).get(kind,'')
  return self.kept.get(game['title'],{}).get(kind)!=note
 def remember(self,title,kind,note):
  """Keeps the note on a file the PC now holds, so the next session knows whether the console has replaced it."""
  if self.kept.get(title,{}).get(kind)==note:return
  self.kept.setdefault(title,{})[kind]=note
  target=self.folder/'kept.json';partial=target.with_suffix('.partial')
  try:partial.write_text(json.dumps(self.kept),encoding='utf8');partial.replace(target)
  except OSError:pass
 def game(self,title):
  return next((game for game in self.games if game['title']==title),{'title':title})
 def fetch_icon(self,sock,title):
  """Reads a game's icon, where the database says the console keeps it first. An icon that came back the same changes nothing on the page."""
  game=self.game(title);places=[game['icon']] if game.get('icon') else []
  places+=[place for place in (root+title+'/icon0.png' for root in ICON_ROOTS) if place not in places]
  with tempfile.TemporaryDirectory(dir=self.folder) as temporary:
   raw=Path(temporary)/'icon'
   for place in places:
    if fetch(sock,place,raw):
     try:
      if save_icon(raw,self.icons/(title+'.png')):self.revision+=1
     except Exception:return
     self.remember(title,'icon',game.get('stamps',{}).get('icon',''));return
 def quiet(self):
  """Someone is looking at the library with no game open: reading a file holds up the console's status, and a game's video comes first."""
  return self.browsing and not running_title(self.status)
 def check_due(self):
  return bool(self.checks) and self.quiet()
 def next_check(self):
  """The next icon to read again, the game in focus first."""
  chosen=self.focus if self.focus in self.checks else self.checks[0];self.checks.remove(chosen);return chosen
 def extras_missing(self,games):
  """The art and music to read: first what is missing, then what the console has replaced since the PC read it.
  A file that turned out unusable leaves a mark, so that it is not read again at every start, only once the console has another."""
  missing=[];replaced=[]
  for game in games:
   for kind,folder,suffix in (('art',self.arts,'.jpg'),('music',self.tracks,'.at9')):
    if not game.get(kind):continue
    job=(kind,game['title'],game[kind],game.get('stamps',{}).get(kind,''))
    if not (folder/(game['title']+suffix)).exists() and not (folder/(game['title']+'.none')).exists():missing.append(job)
    elif self.changed(game,kind):replaced.append(job)
  return missing+replaced
 def extra_due(self):
  return bool(self.extras) and self.quiet()
 def next_extra(self):
  """The next file to read, the game in focus first."""
  chosen=next((job for job in self.extras if job[1]==self.focus),self.extras[0]);self.extras.remove(chosen);return chosen
 def fetch_extra(self,sock,job):
  kind,title,path,note=job;folder=self.arts if kind=='art' else self.tracks;folder.mkdir(parents=True,exist_ok=True)
  target=folder/(title+('.jpg' if kind=='art' else '.at9'));mark=folder/(title+'.none')
  with tempfile.TemporaryDirectory(dir=self.folder) as temporary:
   raw=Path(temporary)/'file'
   # A refusal may only mean an older payload, so it leaves no mark.
   if not fetch(sock,path,raw):return
   try:
    if kind=='art':save_art(raw,target)
    else:replace_soon(raw,target)
    mark.unlink(missing_ok=True);self.revision+=1
   # Still held open on the PC: nothing is wrong with the file, so it is read again next time.
   except PermissionError:return
   except Exception:
    # What the console has now cannot be used, so the old copy goes too: the page shows what the console shows.
    mark.touch()
    if target.exists():target.unlink(missing_ok=True);self.revision+=1
   self.remember(title,kind,note)
