"""Each game's saves, copied from the PS5 to this PC: when the game closes, and whenever asked. Only read: PlayBridge never writes to
the console. The saves are copied as the console keeps them, sealed for that console and that user, so a copy is a backup of this
console's saves, not something a PC or another console opens.
Each copy is a folder of its own, named after when it was made, and a game gets a new one only when its saves changed. A file that did
not change since the copy before is the same file on disk (a hard link), so it takes no room again. The console link's thread reads the
files a part at a time between its status questions, and only while no game runs: a game writes its saves while it plays."""
import json,os,re,shutil,threading,time
from datetime import datetime
from pathlib import Path
from console_captures import listing
from console_control import RANGE_MOST,fetch_range,running_title,user_folder

# PS5 games keep their saves under savedata_prospero, PS4 games under savedata, each in a folder named after the game's title id.
KINDS=(('savedata_prospero','PS5'),('savedata','PS4'))
TITLE=re.compile(r'^[A-Z]{4}\d{5}$')
# How deep below a game's own folder files are looked for, and the most files one game's copy may have.
DEPTH=4;MOST_FILES=512
# Copies kept for each game; older ones go to the Recycle Bin.
KEEP=10
# What the payload answers for a folder it may not list: one from before save backups.
REFUSED=13
# The payload ends the link on a request longer than this, so a deeper path is left out rather than asked for. A part's request carries
# 12 bytes before the path.
BODY_MOST=128;RANGE_HEADER=12
# While the PC shows the stream, one part (RANGE_MOST bytes) at most this often, so the copy takes little of the Wi-Fi from the video.
LIVE_GAP=1.0
STAMP='%Y-%m-%d %H.%M.%S';MANIFEST='backup.json'

def safe(text):return ''.join(c if c.isalnum() or c in ' -_()' else '_' for c in text).strip()[:80] or 'Game'

class SaveBackup:
 """root(): where the copies go. name_of(title): a game's name. notify(text): tells the window. recycle(path): to the Recycle Bin."""
 def __init__(self,root,name_of=None,notify=None,recycle=None,clock=time.time,streaming=None,ticks=time.monotonic):
  self.root=root;self.name_of=name_of or (lambda title:title);self.notify=notify or (lambda text:None);self.recycle=recycle;self.clock=clock
  # streaming(): whether the PC shows the stream now. ticks(): seconds, for the pace.
  self.streaming=streaming or (lambda:False);self.ticks=ticks;self.part_at=0.0
  self.lock=threading.Lock();self.wanted=[];self.plan=None;self.interrupted=False;self.auto=True;self.old_payload=False
  self.status='';self.version=0
 def say(self,text):self.status=text;self.version+=1
 def ask(self,title=None):
  """A game's saves, or every game's with None, to copy once no game runs."""
  key=title or '*'
  with self.lock:
   if key not in self.wanted:self.wanted.append(key)
  if title is None:self.say('Every game\'s saves will be copied as soon as no game runs.')
 def game_closed(self,title):
  if self.auto and title and not self.old_payload:self.ask(title)
 def busy(self):return self.plan is not None or bool(self.wanted)
 def due(self,status):
  """Whether there is something to do now. A game that opens stops the copy; the game's copy then starts again once it closes."""
  if not self.busy() or not user_folder(status.get('user')):return False
  if running_title(status):
   if self.plan is not None:self.interrupted=True
   return False
  return self.plan is None or not self.streaming() or self.ticks()>=self.part_at
 def step(self,sock,status):
  """One piece of work: finding a game's files, or one part of one file."""
  if self.interrupted:self.abandon(again=True);self.interrupted=False
  if self.plan is None:self.start(sock,user_folder(status.get('user')))
  else:self.copy_part(sock)
 # ---- What to copy
 def games(self,sock,folder,key):
  """{title: [(kind label, console folder)]} for the games asked for. None when the payload does not allow it."""
  found={}
  for kind,label in KINDS:
   base=f'/user/home/{folder}/{kind}'
   if key=='*':
    result,entries=listing(sock,base)
    if result==REFUSED:return None
    titles=[name for flag,_,_,name in entries if flag=='d' and TITLE.match(name)] if result==0 else []
   else:titles=[key]
   for title in titles:found.setdefault(title,[]).append((label,f'{base}/{title}'))
  return found
 def files(self,sock,places):
  """Every file of one game: (path on the console, path in the copy, size, time). None when the payload refuses the folder."""
  out=[];folders=[(label,path,label,0) for label,path in places]
  while folders and len(out)<MOST_FILES:
   label,path,inside,level=folders.pop(0);result,entries=listing(sock,path)
   if result==REFUSED:return None
   if result:continue
   for flag,size,modified,name in entries:
    where=path+'/'+name;long=len(where.encode('utf8'))
    if flag=='d' and level<DEPTH and long<=BODY_MOST:folders.append((label,where,inside+'/'+name,level+1))
    elif flag=='f' and not name.startswith('.') and long<=BODY_MOST-RANGE_HEADER:out.append(dict(path=where,rel=inside+'/'+name,size=size,modified=modified))
  return sorted(out,key=lambda item:item['rel'])
 def game_folder(self,title):return Path(self.root())/f'{safe(self.name_of(title))} ({title})'
 def copies(self,title):
  """This game's copies on this PC, oldest first, each with its manifest."""
  found=[];root=Path(self.root())
  # A game whose name changed keeps its older copies under the name it had.
  folders=sorted(root.glob(f'* ({title})')) if root.is_dir() else []
  for folder in folders:
   if not folder.is_dir():continue
   for copy in folder.iterdir():
    try:kept=json.loads((copy/MANIFEST).read_text(encoding='utf-8'))
    except (OSError,ValueError):continue
    if isinstance(kept,dict) and isinstance(kept.get('files'),list):found.append((copy,kept))
  return sorted(found,key=lambda item:str(item[1].get('made','')))
 def start(self,sock,folder):
  with self.lock:
   if not self.wanted:return
   key=self.wanted.pop(0)
  places=self.games(sock,folder,key)
  if places is None:return self.refused()
  jobs=[];same=0
  for title,where in sorted(places.items()):
   files=self.files(sock,where)
   if files is None:return self.refused()
   if not files:continue
   before=self.copies(title);last=before[-1][1]['files'] if before else None
   if last==[dict(rel=f['rel'],size=f['size'],modified=f['modified']) for f in files]:same+=1;continue
   jobs.append(dict(title=title,files=files,previous=before[-1][0] if before else None))
  if not jobs:
   if key=='*':self.say('Every game\'s saves on this PC are up to date.' if same else 'The PS5 has no saves for this user.')
   elif same:self.say(f'{self.name_of(key)}: its saves did not change since the last copy.')
   return
  self.plan=dict(jobs=jobs,index=0,file=0,offset=0,total=sum(f['size'] for job in jobs for f in job['files']),done=0,target=None,made=[])
 def refused(self):
  self.old_payload=True
  with self.lock:self.wanted.clear()
  self.say('The PlayBridge.elf on your PS5 cannot read saves yet. Load the one from this version to copy them.')
 # ---- Copying
 def copy_part(self,sock):
  plan=self.plan;job=plan['jobs'][plan['index']]
  if plan['target'] is None:
   plan['target']=self.game_folder(job['title'])/datetime.fromtimestamp(self.clock()).strftime(STAMP)
   if plan['target'].exists():plan['target']=plan['target'].with_name(plan['target'].name+f' {plan["index"]}')
  item=job['files'][plan['file']];target=plan['target']/item['rel'];partial=target.with_name(target.name+'.partial')
  if plan['offset']==0:
   target.parent.mkdir(parents=True,exist_ok=True)
   if self.reuse(job,item,target):return self.next_file(item['size'])
   partial.write_bytes(b'')
  if plan['offset']<item['size']:
   self.part_at=self.ticks()+LIVE_GAP
   part=fetch_range(sock,item['path'],plan['offset'],min(RANGE_MOST,item['size']-plan['offset']))
   if not part:return self.failed(job)
   with partial.open('ab') as out:out.write(part)
   plan['offset']+=len(part);plan['done']+=len(part)
   self.say(f'Copying {self.name_of(job["title"])}\'s saves: {plan["done"]*100//max(1,plan["total"])}%')
   if plan['offset']<item['size']:return
  partial.replace(target);self.next_file(0)
 def reuse(self,job,item,target):
  """A file the copy before already has, unchanged: the same file on disk again."""
  previous=job['previous']
  if previous is None:return False
  try:kept=json.loads((previous/MANIFEST).read_text(encoding='utf-8'))['files']
  except (OSError,ValueError,KeyError,TypeError):return False
  if dict(rel=item['rel'],size=item['size'],modified=item['modified']) not in kept:return False
  source=previous/item['rel']
  try:
   if source.stat().st_size!=item['size']:return False
  except OSError:return False
  try:os.link(source,target)
  except OSError:
   try:shutil.copy2(source,target)
   except OSError:return False
  return True
 def next_file(self,counted):
  plan=self.plan;job=plan['jobs'][plan['index']];plan['done']+=counted;plan['file']+=1;plan['offset']=0
  if plan['file']<len(job['files']):return
  # The game's copy is whole: its manifest says what it holds, then the oldest copies beyond KEEP go.
  made=datetime.fromtimestamp(self.clock()).isoformat(timespec='seconds')
  manifest=dict(title=job['title'],name=self.name_of(job['title']),made=made,files=[dict(rel=f['rel'],size=f['size'],modified=f['modified']) for f in job['files']])
  (plan['target']/MANIFEST).write_text(json.dumps(manifest,indent=1),encoding='utf-8');plan['made'].append(job['title']);self.prune(job['title'])
  plan['index']+=1;plan['file']=0;plan['target']=None
  if plan['index']<len(plan['jobs']):return
  names=', '.join(self.name_of(title) for title in plan['made'][:3])+(' and more' if len(plan['made'])>3 else '')
  size=plan['total'];self.plan=None
  self.say(f'Saves copied to this PC: {names} ({size/1048576:.1f} MB).');self.notify(f'Saves of {names} copied to this PC.')
 def prune(self,title):
  copies=self.copies(title)
  for folder,_ in copies[:max(0,len(copies)-KEEP)]:
   if not (self.recycle and self.recycle(folder)):break
 def failed(self,job):
  self.say(f'{self.name_of(job["title"])}: the PS5 stopped giving its saves, so this copy was left out. It is tried again when the game closes next.')
  self.abandon(again=False)
 def abandon(self,again):
  """Drops the copy in progress. again: the game it was on is asked for once more."""
  plan=self.plan;self.plan=None
  if plan is None:return
  if plan['target'] is not None and plan['target'].exists():shutil.rmtree(plan['target'],ignore_errors=True)
  if again:
   with self.lock:
    for other in plan['jobs'][plan['index']:]:
     if other['title'] not in self.wanted:self.wanted.insert(0,other['title'])
