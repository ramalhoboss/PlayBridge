"""The PS5's files, browsed from the PC through the FTP server a homebrew payload already runs on the console (ftpsrv, etaHEN and others).

PlayBridge does not start an FTP server on the PS5. It looks for one on the usual ports, keeps the one that answers, and talks to it
from a single thread of its own, so the window never waits on the network. Copies to the PC go to Downloads\\PS5; copies to the PS5
go into the folder on show, whole folders too. A folder is removed only when it is empty, so nothing is ever deleted that you did not
see listed. Text files and pictures can be looked at without copying them: the start of a text file, a picture whole."""
import calendar,ftplib,os,posixpath,queue,socket,threading,time
from pathlib import Path

PORTS=(2121,1337,21)
TIMEOUT=6
BLOCK=64*1024
# Where people usually go on a PS5: its root, homebrew, the first USB drive and the user's own folder.
PLACES=(('PS5','/'),('Data','/data'),('USB','/mnt/usb0'),('Home','/user/home'))
MONTHS={name:number for number,name in enumerate(('jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'),1)}
# What can be looked at on the PS5 without copying it: the first TEXT_MOST bytes of a text file, and a picture of at most IMAGE_MOST.
TEXT_KINDS={'.txt','.log','.json','.ini','.cfg','.conf','.xml','.md','.csv','.yml','.yaml','.toml','.lua','.js','.py','.sh','.html','.htm','.css','.nfo'}
# The picture kinds the built PlayBridge can draw (its Qt keeps the JPEG and GIF readers, PNG and BMP are built in).
# The picture kinds the built PlayBridge can draw: its Qt keeps the JPEG and GIF readers, and PNG and BMP are built in.
IMAGE_KINDS={'.png','.jpg','.jpeg','.gif','.bmp'}
TEXT_MOST=256*1024;IMAGE_MOST=16*1024*1024


class FileProblem(Exception):
 """What went wrong, in words for the user."""


def downloads():
 return Path.home()/'Downloads'/'PS5'


def free_name(folder,name):
 """name in folder, or 'name (2)' and so on when it is taken, so a copy never replaces a file already on the PC."""
 target=Path(folder)/name
 if not target.exists():return target
 stem,suffix=os.path.splitext(name)
 for number in range(2,1000):
  target=Path(folder)/f'{stem} ({number}){suffix}'
  if not target.exists():return target
 raise FileProblem('There are too many copies of that file in Downloads\\PS5.')


def join(folder,name):return posixpath.join(folder or '/',name)
def parent(path):
 path=(path or '/').rstrip('/')
 return posixpath.dirname(path) or '/'


def clean_name(name):
 """A single name from the server, never a path: a name with a slash or that is . or .. is left out."""
 name=str(name or '')
 return '' if not name or '/' in name or name in ('.','..') else name


def year_of(month,day,now):
 """A listing without a year means the last twelve months: this year, or last year for a date that would be in the future."""
 today=time.localtime(now)
 return today.tm_year-1 if (month,day)>(today.tm_mon,today.tm_mday+1) else today.tm_year


def parse_list_line(line,now=None):
 """One line of a LIST answer in the Unix form (drwxr-xr-x 1 root root 512 Nov 15 12:00 name) or the DOS form (11-15-26 12:00PM <DIR> name):
 {name, folder, link, size, when}, or None for a line that is neither or is . or .."""
 now=time.time() if now is None else now;line=str(line).rstrip('\r\n')
 parts=line.split(None,8)
 if len(parts)==9 and len(parts[0])>=10 and parts[0][0] in '-dlbcps':
  kind=parts[0][0];name=parts[8]
  if kind=='l' and ' -> ' in name:name=name.split(' -> ',1)[0]
  name=clean_name(name)
  if not name:return None
  size=int(parts[4]) if parts[4].isdigit() else 0;month=MONTHS.get(parts[5][:3].lower(),0);day=int(parts[6]) if parts[6].isdigit() else 0;when=0.0
  if month and day:
   try:
    if ':' in parts[7]:hour,minute=(int(value) for value in parts[7].split(':',1));when=time.mktime((year_of(month,day,now),month,day,hour,minute,0,0,0,-1))
    elif parts[7].isdigit():when=time.mktime((int(parts[7]),month,day,0,0,0,0,0,-1))
   except (ValueError,OverflowError):when=0.0
  return dict(name=name,folder=kind=='d',link=kind=='l',size=0 if kind=='d' else size,when=when)
 parts=line.split(None,3)
 if len(parts)==4 and parts[0].count('-')==2 and parts[0].replace('-','').isdigit():
  name=clean_name(parts[3])
  if not name:return None
  folder=parts[2].upper()=='<DIR>';when=0.0
  try:
   month,day,year=(int(value) for value in parts[0].split('-'));year+=2000 if year<70 else 1900 if year<100 else 0
   clock=parts[1].upper();hour,minute=(int(value) for value in clock[:-2].split(':'));hour=hour%12+(12 if clock.endswith('PM') else 0)
   when=time.mktime((year,month,day,hour,minute,0,0,0,-1))
  except (ValueError,OverflowError):pass
  return dict(name=name,folder=folder,link=False,size=0 if folder else int(parts[2]) if parts[2].isdigit() else 0,when=when)
 return None


def from_facts(name,facts):
 """One MLSD entry as the same {name, folder, link, size, when}, or None for this folder, its parent or a bad name."""
 kind=str(facts.get('type','')).lower();name=clean_name(name)
 if not name or kind in ('cdir','pdir'):return None
 when=0.0;modify=str(facts.get('modify',''))[:14]
 if len(modify)==14 and modify.isdigit():
  try:when=float(calendar.timegm((int(modify[:4]),int(modify[4:6]),int(modify[6:8]),int(modify[8:10]),int(modify[10:12]),int(modify[12:14]))))
  except (ValueError,OverflowError):when=0.0
 folder=kind=='dir';link='slink' in kind
 size=int(facts['size']) if str(facts.get('size','')).isdigit() and not folder else 0
 return dict(name=name,folder=folder,link=link,size=size,when=when)


def arranged(entries):
 """Folders first, then files, each by name without regard to case."""
 return sorted(entries,key=lambda entry:(not (entry['folder'] or entry['link']),entry['name'].lower()))


def size_text(size):
 if size<1024:return f'{size} B'
 for unit in ('KB','MB','GB'):
  size/=1024
  if size<1024 or unit=='GB':return f'{size:.0f} {unit}' if size>=100 else f'{size:.1f} {unit}'


def when_text(when):
 return time.strftime('%d %b %Y  %H:%M',time.localtime(when)).lstrip('0') if when else ''


def problem_text(error):
 """An FTP or network failure in words."""
 if isinstance(error,FileProblem):return str(error)
 if isinstance(error,ftplib.error_perm):
  reply=str(error).strip()
  return f'The PS5 refused that ({reply[:80]}).' if reply else 'The PS5 refused that.'
 if isinstance(error,(socket.timeout,TimeoutError)):return 'The PS5 stopped answering.'
 if isinstance(error,ConnectionRefusedError):return 'The FTP server on the PS5 is not running any more.'
 if isinstance(error,(ftplib.Error,OSError,EOFError)):return 'The connection to the PS5 was lost.'
 return f'That did not work: {error}'


class Stopped(Exception):
 """A copy that was stopped on purpose."""
class Enough(Exception):
 """As much of a file as a look at it needs."""


def preview_kind(name,size=0):
 """'text' or 'image' when a file can be looked at without copying it, else ''. A picture too big to show whole is ''."""
 suffix=os.path.splitext(str(name))[1].lower()
 if suffix in TEXT_KINDS:return 'text'
 if suffix in IMAGE_KINDS and size<=IMAGE_MOST:return 'image'
 return ''
def image_type(data):
 """The file ending a picture's first bytes say it has, or '' when they are not a picture Qt shows."""
 if data[:8]==b'\x89PNG\r\n\x1a\n':return '.png'
 if data[:3]==b'\xff\xd8\xff':return '.jpg'
 if data[:6] in (b'GIF87a',b'GIF89a'):return '.gif'
 if data[:2]==b'BM':return '.bmp'
 return ''
def preview_of(name,data,cut=False):
 """What a look at a file shows: {kind: 'text', text, cut}, {kind: 'image', ending}, or {kind: 'none', why}."""
 kind=preview_kind(name)
 if kind=='image':
  ending=image_type(data);return dict(kind='image',ending=ending) if ending else dict(kind='none',why=f'{name} is not a picture PlayBridge can show.')
 if kind=='text':
  if b'\0' in data[:8192]:return dict(kind='none',why=f'{name} is not plain text. Copy it to this PC to open it.')
  try:text=data.decode('utf-8-sig')
  except UnicodeDecodeError as error:
   # A look that stopped part way can end inside a letter; anything else that is not UTF-8 is read as Windows text.
   text=data[:error.start].decode('utf-8-sig') if cut and error.start>=len(data)-3 else data.decode('cp1252',errors='replace')
  return dict(kind='text',text=text.replace('\r\n','\n').replace('\r','\n'),cut=cut)
 return dict(kind='none',why=f'PlayBridge shows text files and pictures. Copy {name} to this PC to open it.')

def put_plan(paths,folder):
 """What sending these files and folders makes on the PS5: the folders to make, each before what goes in it, and (file, place) for each file."""
 folders=[];sends=[]
 for path in map(Path,paths):
  if path.is_dir():
   top=join(folder,clean_name(path.name) or 'Folder');folders.append(top)
   for here,inner,names in os.walk(path):
    inner.sort();inside=Path(here).relative_to(path).parts;base=join(top,'/'.join(inside)) if inside else top
    folders+=[join(base,name) for name in inner]
    sends+=[(Path(here)/name,join(base,name)) for name in sorted(names)]
  elif path.is_file():sends.append((path,join(folder,path.name)))
 return folders,sends


class FileSession:
 """One FTP connection to the PS5 and the one thread that uses it. The window asks for work with ask() and takes the answers with take():
 dicts of kind, the job's values, ok, problem and value. progress is (done, total) bytes while a copy runs, read by the window."""
 def __init__(self,host,factory=ftplib.FTP,ports=PORTS,clock=time.monotonic):
  self.host=host;self.factory=factory;self.ports=tuple(ports);self.clock=clock
  self.jobs=queue.Queue();self.answers=queue.Queue();self.thread=None;self.ftp=None;self.port=None;self.banner=''
  self.progress=None;self.stopping=threading.Event();self.busy=''
 # The window's side.
 def ask(self,kind,**values):
  if self.thread is None or not self.thread.is_alive():
   self.thread=threading.Thread(target=self.run,name='PlayBridge files',daemon=True);self.thread.start()
  self.jobs.put((kind,values))
 def take(self):
  answers=[]
  while True:
   try:answers.append(self.answers.get_nowait())
   except queue.Empty:return answers
 def stop_copy(self):self.stopping.set()
 def close(self):
  if self.thread is not None and self.thread.is_alive():self.jobs.put(None)
 # The thread's side.
 def run(self):
  while True:
   job=self.jobs.get()
   if job is None:self.hang_up();return
   kind,values=job;work=getattr(self,'do_'+kind,None)
   if work is None:continue
   self.busy=kind;self.stopping.clear()
   try:
    try:value=work(**values)
    except (EOFError,ConnectionError,socket.timeout,TimeoutError,ftplib.error_temp,ftplib.error_reply) as error:
     # The server closes a connection left alone for a while: one new connection and one more try, unless it was a copy half done.
     if kind in ('get','put') and self.progress and self.progress[0]:raise error
     self.hang_up();value=work(**values)
    self.answers.put(dict(values,kind=kind,ok=True,problem='',value=value))
   except Stopped:
    self.hang_up();self.answers.put(dict(values,kind=kind,ok=False,problem='Stopped.',value=None))
   except Exception as error:
    if not isinstance(error,(ftplib.error_perm,FileProblem)):self.hang_up()
    self.answers.put(dict(values,kind=kind,ok=False,problem=problem_text(error),value=None))
   finally:self.busy='';self.progress=None
 def hang_up(self):
  ftp,self.ftp=self.ftp,None
  if ftp is not None:
   try:ftp.quit()
   except Exception:
    try:ftp.close()
    except Exception:pass
 def host_name(self):return self.host() if callable(self.host) else self.host
 def link(self):
  """The connection, made on first use: the port that answered last time first, then the others."""
  if self.ftp is not None:return self.ftp
  host=self.host_name();ports=((self.port,) if self.port else ())+tuple(port for port in self.ports if port!=self.port);last=None
  for port in ports:
   ftp=self.factory()
   try:
    self.banner=ftp.connect(host,port,timeout=TIMEOUT)
   except (OSError,EOFError,ftplib.Error) as error:
    last=error
    try:ftp.close()
    except Exception:pass
    continue
   try:ftp.login()
   except ftplib.error_perm:pass
   try:ftp.voidcmd('TYPE I')
   except ftplib.Error:pass
   self.ftp=ftp;self.port=port;return ftp
  raise FileProblem(f'No FTP server answered on the PS5 at {host} (ports {", ".join(map(str,self.ports))}). Start one from your homebrew menu, then try again.') from last
 def entries(self,path):
  # Into the folder first, then the listing of where it stands: simple servers take no path after LIST, or none with spaces.
  ftp=self.link();ftp.cwd(path or '/')
  try:
   found=[from_facts(name,facts) for name,facts in ftp.mlsd('',['type','size','modify'])]
  except (ftplib.error_perm,ftplib.error_reply):
   lines=[];ftp.retrlines('LIST',lines.append);found=[parse_list_line(line) for line in lines]
  return arranged([entry for entry in found if entry])
 def do_connect(self):self.link();return dict(port=self.port,banner=self.banner.split('\n')[0][:120])
 def do_list(self,path):return dict(path=path or '/',entries=self.entries(path or '/'),port=self.port)
 def walk(self,path):
  """Every file under a folder: (path on the PS5, path inside the folder, size)."""
  files=[];folders=[(path,'')]
  while folders:
   folder,inside=folders.pop()
   for entry in self.entries(folder):
    here=join(folder,entry['name']);within=posixpath.join(inside,entry['name']) if inside else entry['name']
    if entry['folder']:folders.append((here,within))
    elif not entry['link']:files.append((here,within,entry['size']))
  return files
 def copy_down(self,ftp,remote,target,total):
  part=target.with_name(target.name+'.part');target.parent.mkdir(parents=True,exist_ok=True)
  try:
   with open(part,'wb') as out:
    def take(block):
     if self.stopping.is_set():raise Stopped()
     out.write(block);self.progress=(self.progress[0]+len(block),total)
    ftp.retrbinary('RETR '+remote,take,BLOCK)
  except BaseException:
   # A copy cut short leaves nothing half written on the PC.
   try:part.unlink()
   except OSError:pass
   raise
  os.replace(part,target)
 def do_get(self,path,folder=False,size=0,into=None):
  """A file, or a whole folder, from the PS5 into Downloads\\PS5 (or into). The PC copy is new: nothing on the PC is replaced."""
  ftp=self.link();into=Path(into) if into else downloads();name=posixpath.basename(path.rstrip('/')) or 'PS5'
  if not folder:
   target=free_name(into,name);self.progress=(0,size);self.copy_down(ftp,path,target,size);return dict(saved=str(target),count=1)
  files=self.walk(path);total=sum(size for _,_,size in files);base=free_name(into,name);self.progress=(0,total)
  for remote,inside,_ in files:self.copy_down(ftp,remote,base.joinpath(*inside.split('/')),total)
  if not files:base.mkdir(parents=True,exist_ok=True)
  return dict(saved=str(base),count=len(files))
 def do_put(self,files,folder):
  """Files and whole folders from the PC into a folder on the PS5. The window asks first when one would replace something there."""
  ftp=self.link();folders,sends=put_plan(files,folder);self.progress=(0,sum(path.stat().st_size for path,_ in sends))
  for place in folders:
   # A folder already there is used as it is.
   try:ftp.mkd(place)
   except ftplib.error_perm:pass
  for path,place in sends:
   with open(path,'rb') as source:
    def sent(block):
     if self.stopping.is_set():raise Stopped()
     self.progress=(self.progress[0]+len(block),self.progress[1])
    ftp.storbinary('STOR '+place,source,BLOCK,sent)
  return dict(folder=folder,count=len(sends))
 def do_peek(self,path,name,look,size=0):
  """A look at a file without copying it: the first TEXT_MOST bytes of a text file, or a whole picture."""
  if look=='image' and size>IMAGE_MOST:raise FileProblem(f'{name} is too big to show here. Copy it to this PC to open it.')
  ftp=self.link();most=TEXT_MOST if look=='text' else IMAGE_MOST;data=bytearray()
  def take(block):
   if self.stopping.is_set():raise Stopped()
   data.extend(block)
   if len(data)>most:raise Enough()
  try:ftp.retrbinary('RETR '+path,take,BLOCK)
  except Enough:
   # The rest of the file is not wanted: this connection is dropped and the next job makes a new one.
   self.hang_up()
  return dict(name=name,look=look,data=bytes(data[:most]),cut=len(data)>most)
 def do_mkdir(self,folder,name):
  name=clean_name(name)
  if not name:raise FileProblem('A folder name cannot hold a slash or be . or ..')
  self.link().mkd(join(folder,name));return dict(folder=folder,name=name)
 def do_rename(self,folder,old,new):
  new=clean_name(new)
  if not new:raise FileProblem('A name cannot hold a slash or be . or ..')
  self.link().rename(join(folder,old),join(folder,new));return dict(folder=folder,name=new)
 def do_remove(self,folder,name,is_folder):
  ftp=self.link();path=join(folder,name)
  if not is_folder:ftp.delete(path);return dict(folder=folder,name=name)
  try:ftp.rmd(path)
  except ftplib.error_perm as error:
   if self.entries(path):raise FileProblem(f'{name} is not empty. Delete what is inside it first.') from None
   raise error
  return dict(folder=folder,name=name)
