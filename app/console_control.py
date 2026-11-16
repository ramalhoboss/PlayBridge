"""Game library, console status and power, through the control port the payload opens during a session."""
import collections,hashlib,json,os,queue,re,socket,sqlite3,struct,tempfile,threading,time
from datetime import datetime
from pathlib import Path
from PIL import Image
import trophies as trophy_files
import fan_target
from performance import PerformanceLog

CONTROL_PORT=9077
STATUS,FILE,LAUNCH,CLOSE,REST,POWER_OFF,REBOOT,LIST,RANGE,FAN=1,2,3,4,6,7,8,9,10,11
# Play away from home ends: the payload leaves once no stream is running (payload/away-rules.h).
AWAY_END=12
REQUEST=struct.Struct('<4sII');REPLY=struct.Struct('<4siI')
SHORT_REPLY=4096;FILE_LIMIT=0x10000000
# The most the payload returns for one request for part of a file, and the most the PC reads of one file inside a trophy set.
RANGE_MOST=0x100000;TROPHY_PART_MOST=8<<20
# Trophies earned at once whose pictures are read, the newest ones.
TROPHY_ICONS_MOST=4
# While a game runs, the seconds between two reads of the player's trophy record for it.
TROPHY_WATCH_EVERY=10
TROPHY_SET_FILE='/user/trophy2/nobackup/conf/{}/TROPHY.UCP';TROPHY_RECORD='/user/home/{}/trophy2/nobackup/data/{}/TRPTITLE.DAT'
APP_ROOTS=('/user/app/','/mnt/ext0/user/app/','/mnt/ext1/user/app/')
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
def degrees(status,name):
 """A temperature the console reported, in °C, or None when it could not read that sensor. The payload checks each reading and sends -1 for one it did not get."""
 value=status.get(name);return value if isinstance(value,int) and not isinstance(value,bool) and value>0 else None
def console_line(status):
 """The temperatures the console reported, leaving out any it could not give. The frequency tells a player nothing, so it is not shown."""
 return '  ·  '.join(f'{label} {value} °C' for label,value in (('CPU',degrees(status,'cpu_c')),('SoC',degrees(status,'soc_c'))) if value)

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
def fetch_range(sock,path,offset,length):
 """Part of a console file, at most RANGE_MOST bytes, and shorter past its end. None when the console does not have the file,
 does not allow it, or runs a payload from before part reads."""
 body=struct.pack('<QI',offset,length)+path.encode('utf8');sock.sendall(REQUEST.pack(b'PBC1',RANGE,len(body))+body)
 result,size=reply_header(sock)
 if result:
  if size:read_exact(sock,size)
  return None
 if size>length:raise ValueError('Oversized control reply')
 return read_exact(sock,size)
def user_folder(user):
 """A user's own folder on the console: the id as eight lowercase hexadecimal digits. Empty without a user."""
 return f'{user&0xffffffff:08x}' if isinstance(user,int) and not isinstance(user,bool) and user not in (0,-1) else ''

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
   # Type 0 is what the console itself runs (NPXS, left out) and homebrew apps, which go on the Apps shelf instead of among the games.
   if not is_game_title(title):continue
   app=row.get('appType')==0
   name=clean_name(row.get('titleName'))[:80] or title
   size=row.get('size')
   games[title]={'title':title,'name':name,'played':when(row.get('lastAccessTime')) or when(row.get('installTime')),'seconds':None,'installed':when(row.get('installTime')),'size':size if isinstance(size,int) and size>0 else 0,'icon':console_file(row.get('icon0Info')),'art':console_file(row.get('pic0Info')),'music':console_file(row.get('snd0Info')),'stamps':{kind:stamp(row.get(column)) for kind,column in (('icon','icon0Info'),('art','pic0Info'),('music','snd0Info'))}}
   if app:games[title]['app']=True
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
def load_trophies(path):
 """What the PC kept of the console's trophies: {'user': folder, 'games': {title: set}, 'sets': {set: {key, name, trophies}}, 'earned': {folder: {set: {id: when}}}}.
 Anything that does not look as written is left out, so a damaged file only means reading again."""
 book=dict(user='',games={},sets={},earned={})
 try:saved=json.loads(Path(path).read_text(encoding='utf8'))
 except (OSError,ValueError):return book
 if not isinstance(saved,dict):return book
 book['user']=saved.get('user') if isinstance(saved.get('user'),str) and re.fullmatch('[0-9a-f]{8}',saved.get('user')) else ''
 games=saved.get('games');sets=saved.get('sets');earned=saved.get('earned')
 if isinstance(games,dict):book['games']={title:name for title,name in games.items() if is_game_title(title) and isinstance(name,str) and (not name or trophy_files.SET.fullmatch(name))}
 if isinstance(sets,dict):
  for name,kept in sets.items():
   if not trophy_files.SET.fullmatch(str(name)) or not isinstance(kept,dict) or not isinstance(kept.get('trophies'),list):continue
   rows=[row for row in kept['trophies'] if isinstance(row,dict) and isinstance(row.get('id'),int) and row.get('grade') in ('',*trophy_files.POINTS) and isinstance(row.get('name'),str) and isinstance(row.get('detail'),str)]
   book['sets'][name]=dict(key=str(kept.get('key',''))[:64],name=str(kept.get('name',''))[:120],trophies=[dict(id=row['id'],grade=row['grade'],hidden=row.get('hidden') is True,name=row['name'][:120],detail=row['detail'][:400]) for row in rows])
 if isinstance(earned,dict):
  for folder,sets in earned.items():
   if not re.fullmatch('[0-9a-f]{8}',str(folder)) or not isinstance(sets,dict):continue
   book['earned'][folder]={name:{int(number):int(at) for number,at in have.items() if str(number).isdigit() and isinstance(at,int)} for name,have in sets.items() if trophy_files.SET.fullmatch(str(name)) and isinstance(have,dict)}
 return book
def load_hidden(path):
 try:saved=json.loads(Path(path).read_text(encoding='utf8'))
 except (OSError,ValueError):return set()
 return {title for title in saved if is_game_title(title)} if isinstance(saved,list) else set()
def save_json(target,value):
 """Writes the whole file or nothing, so a crash in the middle leaves the last copy."""
 target=Path(target);partial=target.with_suffix('.partial')
 try:partial.write_text(json.dumps(value),encoding='utf8');partial.replace(target);return True
 except OSError:return False
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

class GameRate:
 """The game's own frame rate, from the display's frame count that each status answer carries: how much it grew over about the last
 second of the console's clock. None without a game, with a payload too old to count, or when the count stopped coming."""
 SPAN=1.0;STALE=2.0
 def __init__(self):self.reset()
 def reset(self):self.samples=collections.deque();self.fps=None;self.moved_at=None
 def add(self,info,now):
  state=info.get('fps_state') if isinstance(info,dict) else None;flips=info.get('flips') if isinstance(info,dict) else None;at=info.get('flips_us') if isinstance(info,dict) else None
  if state!=0 or type(flips) is not int or type(at) is not int:self.reset();return
  last=self.samples[-1] if self.samples else None
  # A smaller count or an earlier clock is another game or another payload: start again.
  if last and (flips<last[1] or at<last[0]):self.samples.clear();last=None
  if last is None or at!=last[0]:self.samples.append((at,flips));self.moved_at=now
  # The console's reading thread has stopped: show nothing rather than an old number.
  if self.moved_at is not None and now-self.moved_at>self.STALE:self.fps=None;return
  while len(self.samples)>2 and (at-self.samples[1][0])/1e6>=self.SPAN:self.samples.popleft()
  first=self.samples[0];span=(at-first[0])/1e6
  self.fps=(flips-first[1])/span if span>=.5 else None

class ConsoleLink:
 """Owns the control connection: one thread per capture session, which ends with the session."""
 # Often enough that the console's menu, after the PS button or a game closing on the console, is on the PC for only a moment.
 STATUS_EVERY=.25;LOG_EVERY=.1
 # Trophies from elsewhere for the games whose trophies the console's files do not give (psn_trophies.TrophyBook, set by the app), and
 # what has changed on this side: the page redraws when either moves.
 more_trophies=None;own_revision=0
 @property
 def revision(self):
  more=self.more_trophies;return self.own_revision+(more.shelf_changes if more is not None else 0)
 @revision.setter
 def revision(self,value):
  more=self.more_trophies;self.own_revision=value-(more.shelf_changes if more is not None else 0)
 def __init__(self,folder,notify=lambda message:None):
  # connect(host, port): the control connection, sealed when the payload holds this PC's key (secure_link.Pairing.connect).
  self.connect=lambda host,port:socket.create_connection((host,port),2)
  self.folder=Path(folder);self.small_icons=self.folder/'icons';self.icons=self.folder/'covers';self.arts=self.folder/'art';self.tracks=self.folder/'music';self.notify=notify;self.status={};self.online=False;self.revision=0;self.refreshing=False;self.jobs=queue.SimpleQueue();self.session=None;self.want_library=True
  # checks: the icons already on the PC, read again once each session, since an app on the console can change its icon without the database saying so.
  self.browsing=False;self.focus='';self.extras=[];self.checks=[]
  # When set, each session keeps copies of the payload's logs in this folder on the PC, numbered by session.
  self.log_folder=None;self.log_session=0
  self.games=load_games(self.folder/'games.json');self.kept=load_kept(self.folder/'kept.json')
  # Trophies: the games whose sets are still to read this session, and whether the payload can read part of a file (None until asked).
  self.trophy_lock=threading.Lock();self.trophy_book=load_trophies(self.folder/'trophies.json');self.trophy_jobs=[];self.can_range=None;self.played=''
  self.hidden=load_hidden(self.folder/'hidden.json')
  # The saves copied to the PC (save_backup.SaveBackup), set by the app; it works between status questions while no game runs.
  self.saves=None
  # Each game's fan level (fan_target.FanProfiles), set by the app. The target is sent once a status answer shows it is not in place,
  # never twice for the same answer, and not again for FAN_WAIT seconds after the console refuses it.
  self.fans=None;self.fan_error=0;self.fan_wait_until=0.0;self.status_count=0;self.fan_sent=-1
  self.game_rate=GameRate()
  # Each game's frame rate, temperatures and power while it runs, and a summary of it once it ends.
  self.performance=PerformanceLog(self.folder/'sessions.json',self.game_name,notify)
  # The running game's trophy record, read again and again: the game, its set, what it had at the last read and when (seconds since
  # 1970). on_trophy(title, earned, since) hears of each trophy that appears, from this thread.
  self.on_trophy=None;self.watch_title='';self.watch_name='';self.watch_have=None;self.watch_read=0;self.watch_at=0
 @property
 def game_fps(self):
  """The running game's frames per second as the PS5 counts them, or None."""
  return self.game_rate.fps if self.online else None
 def begin(self,host):
  self.end();stop=threading.Event();self.session=stop;self.want_library=True;self.log_session+=1
  threading.Thread(target=self.run,args=(host,stop),name='PlayBridge console link',daemon=True).start()
 def end(self):
  if self.session is not None:self.session.set();self.session=None
  self.online=False;self.status={};self.game_rate.reset()
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
    with self.connect(host,CONTROL_PORT) as sock:
     sock.settimeout(15);sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1);self.serve(sock,stop)
   except (OSError,EOFError,ValueError,struct.error):pass
   if self.session is stop:self.online=False;self.status={}
   stop.wait(1)
 def serve(self,sock,stop):
  while True:
   try:self.jobs.get_nowait()
   except queue.Empty:break
  status_at=0;missing=[];log_at=0;self.can_range=None
  if self.log_folder is not None:self.keep(sock,PREVIOUS_CONTROL_LOG,'control-before')
  while not stop.is_set():
   now=time.monotonic()
   if now>=status_at:
    _,body=call(sock,STATUS);status_at=now+self.STATUS_EVERY;info=json.loads(body)
    if isinstance(info,dict) and self.session is stop:self.status=info;self.status_count+=1;self.online=True;self.game_rate.add(info,now);self.performance.add(info,self.game_rate.fps,running_title(info));self.game_closed(running_title(info))
   if self.log_folder is not None and now>=log_at:self.keep(sock,CAPTURE_LOG,'capture');log_at=now+self.LOG_EVERY
   try:command,body,done=self.jobs.get(timeout=.02 if self.want_library or missing or self.check_due() or self.trophy_due() or self.extra_due() or self.saves_due() else .1)
   except queue.Empty:
    if self.want_library:missing=self.read_library(sock)
    elif missing:self.fetch_icon(sock,missing.pop(0))
    elif self.fan_due():self.send_fan(sock)
    elif self.watch_due():self.watch_trophies(sock)
    elif self.saves_due():self.saves.step(sock,self.status)
    elif self.check_due():self.fetch_icon(sock,self.next_check())
    elif self.trophy_due():self.read_trophies(sock,self.next_trophy())
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
   self.games=games;self.revision+=1;self.extras=self.extras_missing(games);self.trophy_jobs=[game['title'] for game in games]
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

 # Trophies, read only, from the console's own files, one game at a time and only while someone browses with no game open.
 def game_closed(self,title):
  """A game that was open and is not any more may have new trophies, so its record is read again first."""
  played,self.played=self.played,title
  if played and played!=title:
   if played in self.trophy_jobs:self.trophy_jobs.remove(played)
   self.trophy_jobs.insert(0,played)
   # A game writes its saves as it closes, so its copy is made once it has.
   if self.saves is not None:self.saves.game_closed(played)
 def saves_due(self):return self.saves is not None and self.saves.due(self.status)
 FAN_WAIT=30
 def fan_level(self):return self.fans.get(running_title(self.status)) if self.fans is not None else 'own'
 def fan_due(self):
  return self.fans is not None and self.status_count!=self.fan_sent and time.monotonic()>=self.fan_wait_until and fan_target.wanted(self.status,self.fan_level()) is not None
 def send_fan(self,sock):
  want=fan_target.wanted(self.status,self.fan_level());self.fan_sent=self.status_count
  result,_=call(sock,FAN,bytes([want]));self.fan_error=result
  if result:self.fan_wait_until=time.monotonic()+self.FAN_WAIT
 def trophy_due(self):
  return bool(self.trophy_jobs) and self.can_range is not False and self.quiet()
 def next_trophy(self):
  """The next game whose trophies to read, the game in focus first."""
  chosen=self.focus if self.focus in self.trophy_jobs else self.trophy_jobs[0];self.trophy_jobs.remove(chosen);return chosen
 def read_part(self,sock,path,offset,size):
  """One file inside a trophy set, in as many requests as it takes. None if the console gives less than the set's table says."""
  if not 0<size<=TROPHY_PART_MOST:return None
  data=bytearray()
  while len(data)<size:
   part=fetch_range(sock,path,offset+len(data),min(RANGE_MOST,size-len(data)))
   if not part:return None
   data+=part
  return bytes(data)
 def read_set_name(self,sock,title):
  """The trophy set a game uses, from its npbind.dat: beside its icon first, then where the console installs games."""
  icon=self.game(title).get('icon') or '';places=[icon.rsplit('/',1)[0]+'/trophy2/npbind.dat'] if icon.count('/')>1 else []
  places+=[root+title+'/trophy2/npbind.dat' for root in ICON_ROOTS]+[root+title+'/sce_sys/trophy2/npbind.dat' for root in APP_ROOTS]
  with tempfile.TemporaryDirectory(dir=self.folder) as temporary:
   raw=Path(temporary)/'npbind'
   for place in dict.fromkeys(places):
    if fetch(sock,place,raw,limit=1<<16):
     name=trophy_files.set_of(raw.read_bytes())
     if name:return name
  return ''
 def read_trophies(self,sock,title):
  """One game's trophies: the set it uses, the set's list only when the console's copy changed, and the player's record.
  A file that cannot be read leaves what the PC kept as it was. Errors on the connection itself still end the connection."""
  if self.can_range is None:
   # A payload from before part reads refuses the request, and the PC then leaves trophies alone for this session.
   self.can_range=fetch_range(sock,DATABASE,0,16) is not None
   if not self.can_range:return
  with self.trophy_lock:name=self.trophy_book['games'].get(title,'')
  name=name or self.read_set_name(sock,title)
  if not name:return self.keep_trophies(title,'')
  path=TROPHY_SET_FILE.format(name);head=fetch_range(sock,path,0,trophy_files.UCP_TABLE)
  # The console keeps a set's file only once the game has been opened: until then the PC only remembers which set it is.
  if head is None:return self.keep_trophies(title,name)
  try:count=trophy_files.ucp_count(head)
  except ValueError:return
  table=fetch_range(sock,path,trophy_files.UCP_TABLE,count*trophy_files.UCP_ENTRY)
  if table is None:return
  key=hashlib.sha1(head+table).hexdigest()
  with self.trophy_lock:kept=self.trophy_book['sets'].get(name)
  if kept is None or kept['key']!=key:
   try:files=trophy_files.ucp_table(head,table)
   except ValueError:return
   conf=self.read_part(sock,path,*files['tropconf.json']) if 'tropconf.json' in files else None
   if conf is None:return
   try:meta_file=trophy_files.meta_name(files,trophy_files.trophy_set(conf)['default'])
   except ValueError:return
   meta=self.read_part(sock,path,*files[meta_file]) if meta_file else None
   try:made=trophy_files.trophy_set(conf,meta)
   except ValueError:return
   kept=dict(key=key,name=made['name'],trophies=made['trophies'])
  folder=user_folder(self.status.get('user'));have=self.read_record(sock,folder,name) if folder else None
  self.keep_trophies(title,name,kept,folder,have)
 def read_record(self,sock,folder,name):
  """Which trophies of a set the player has and since when, {id: seconds since 1970}, or None when the record cannot be used."""
  with tempfile.TemporaryDirectory(dir=self.folder) as temporary:
   raw=Path(temporary)/'record'
   # No record yet means the player has not earned anything in this game.
   if not fetch(sock,TROPHY_RECORD.format(folder,name),raw,limit=trophy_files.T2_MOST+trophy_files.T2_HEADER):return {}
   try:return trophy_files.earned(raw.read_bytes())
   except ValueError:return None
 def watch_due(self):
  return self.can_range is not False and bool(running_title(self.status)) and time.monotonic()>=self.watch_at
 def watch_trophies(self,sock):
  """While a game runs, the player's record for it every TROPHY_WATCH_EVERY seconds: a trophy that was not there at the last read
  was earned since. The first read of each game only notes what it had, so trophies earned while PlayBridge was closed stay quiet."""
  title=running_title(self.status);folder=user_folder(self.status.get('user'));self.watch_at=time.monotonic()+TROPHY_WATCH_EVERY
  if self.can_range is None:
   self.can_range=fetch_range(sock,DATABASE,0,16) is not None
   if not self.can_range:return
  if title!=self.watch_title:
   self.watch_title=title;self.watch_have=None
   with self.trophy_lock:self.watch_name=self.trophy_book['games'].get(title) or ''
   if not self.watch_name:self.watch_name=self.read_set_name(sock,title)
  name=self.watch_name
  if not name or not folder:return
  have=self.read_record(sock,folder,name)
  if have is None:return
  before,since=self.watch_have,self.watch_read;self.watch_have=have;self.watch_read=time.time()
  if before is None:return
  new=sorted(set(have)-set(before))
  if not new:return
  # A full read keeps the new record and brings the set's names, if the PC did not have them yet.
  self.read_trophies(sock,title);found=self.trophy_set(title) or {};rows={row['id']:row for row in found.get('trophies',[])}
  # And each one's own picture, for the overlay.
  icons=self.read_trophy_icons(sock,name,new[-TROPHY_ICONS_MOST:])
  earned=[dict(id=number,name=rows.get(number,{}).get('name',''),grade=rows.get(number,{}).get('grade',''),at=have[number],icon=icons.get(number)) for number in new]
  self.revision+=1
  if self.on_trophy:self.on_trophy(title,earned,since)
 def read_trophy_icons(self,sock,name,numbers):
  """Trophies' own pictures from their set's file, {id: PNG bytes}. A picture that cannot be read is left out."""
  path=TROPHY_SET_FILE.format(name);head=fetch_range(sock,path,0,trophy_files.UCP_TABLE)
  try:count=trophy_files.ucp_count(head or b'')
  except ValueError:return {}
  table=fetch_range(sock,path,trophy_files.UCP_TABLE,count*trophy_files.UCP_ENTRY)
  try:files=trophy_files.ucp_table(head,table or b'')
  except ValueError:return {}
  icons={}
  for number in numbers:
   place=trophy_files.icon_place(files,number);data=self.read_part(sock,path,*place) if place else None
   if data and data.startswith(trophy_files.PNG):icons[number]=data
  return icons
 def keep_trophies(self,title,name,kept=None,folder='',have=None):
  """Keeps what was read and tells the page, only when something differs from what the PC had."""
  with self.trophy_lock:
   book=self.trophy_book;changed=book['games'].get(title)!=name;book['games'][title]=name
   if kept is not None and book['sets'].get(name)!=kept:book['sets'][name]=kept;changed=True
   if folder and book['user']!=folder:book['user']=folder;changed=True
   if folder and have is not None and book['earned'].get(folder,{}).get(name)!=have:book['earned'].setdefault(folder,{})[name]=have;changed=True
   if changed:save_json(self.folder/'trophies.json',book)
  if changed and kept is not None:self.revision+=1
 def trophy_user(self):
  return user_folder(self.status.get('user')) or self.trophy_book['user']
 def trophy_set(self,title):
  """A game's trophies as the page shows them: {set, name, trophies (each with when it was earned, 0 if not), tally, known, last}.
  known is False until the player's record has been read. None when the PC knows no set for the game. The console's own files come
  first; when they give nothing for a game (a PS4 game), the trophies from PSN stand in, when the player signed in to it."""
  own=self.own_trophy_set(title)
  if (own is None or not own['known']) and self.more_trophies is not None:
   more=self.more_trophies.console_set(title)
   if more is not None:return more
  return own
 def own_trophy_set(self,title):
  """The same, from the console's own files only."""
  with self.trophy_lock:
   book=self.trophy_book;name=book['games'].get(title);kept=book['sets'].get(name) if name else None
   if kept is None:return None
   mine=book['earned'].get(self.trophy_user(),{});have=dict(mine.get(name,{}))
   rows=[dict(row,earned=have.get(row['id'],0)) for row in kept['trophies']]
  return dict(set=name,name=kept['name'],trophies=rows,tally=trophy_files.tally(kept['trophies'],have),known=name in mine,last=trophy_files.last_earned(have))
 def trophy_totals(self,titles):
  """Across these games: {earned, platinum, games}. None when the PC knows no trophies for any of them."""
  earned=platinum=games=0;seen=set()
  for title in titles:
   found=self.trophy_set(title)
   if found is None or not found['known'] or found['set'] in seen:continue
   seen.add(found['set']);games+=1;earned+=found['tally']['earned'];platinum+=found['tally']['platinum'] is True
  return dict(earned=earned,platinum=platinum,games=games) if games else None

 # Games the player chose not to see on the shelf. Only the PC keeps this; the console is not touched.
 def set_hidden(self,title,on):
  if not is_game_title(title) or on==(title in self.hidden):return
  if on:self.hidden.add(title)
  else:self.hidden.discard(title)
  save_json(self.folder/'hidden.json',sorted(self.hidden));self.revision+=1
