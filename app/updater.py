"""New versions of PlayBridge from its GitHub releases.

The newest release is read from GitHub's public API. When it is newer than this copy, its PlayBridge.exe is downloaded into the
update folder next to the preferences, slowly enough not to disturb a stream, and kept only when its SHA-256 matches the line for
it in the same release's SHA256SUMS.txt. A running EXE cannot be replaced on Windows, so the new EXE does the swap itself: started
with --finish-update and the old EXE's path, it waits for the old one to close, copies itself over it and, when asked, opens it.
A copy run from source only says that a new version is out.

The EXE it replaces is kept in the update folder's previous folder under its version, so Settings can go back to it: the kept EXE
is then started the same way, with --no-keep, and puts itself back. Going back turns automatic updates off, or the newer version
would come straight back.

On the beta channel the newest release counts whether or not GitHub marks it a pre-release (tags such as v1.8.0-beta.2); a final
version is newer than its own betas. Leaving the channel never goes back to an older version: the next final one is waited for."""
import hashlib,json,os,re,subprocess,sys,threading,time,traceback,urllib.request
from pathlib import Path
from app_version import VERSION

REPOSITORY='ramalhoboss/PlayBridge'
LATEST=os.environ.get('PLAYBRIDGE_UPDATE_URL') or f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
RELEASES=os.environ.get('PLAYBRIDGE_RELEASES_URL') or f'https://api.github.com/repos/{REPOSITORY}/releases?per_page=20'
CHANNELS=('stable','beta')
BETA_NOTE=('Beta versions come out before the final ones: new things sooner, and sometimes bugs. Turned off again, PlayBridge waits for the '
 'next final version and never goes back to an older one.')
EXE='PlayBridge.exe';SUMS='SHA256SUMS.txt';PREVIOUS='previous'
CHECK_EVERY=6*3600;FIRST_CHECK=8
# About 12 Mbps: a 4K stream at 80 Mbps over Wi-Fi keeps its room.
DOWNLOAD_RATE=1_500_000
WAIT_FOR_CLOSE=120
DETACHED=0x00000008|0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

def parse_version(text):
 """'v1.6.0' or '1.6.0' as (1,6,0); anything else as None."""
 found=re.fullmatch(r'v?(\d+)\.(\d+)(?:\.(\d+))?',str(text or '').strip())
 return tuple(int(part or 0) for part in found.groups()) if found else None
# A version with its stage: 1.8.0-beta.2 is (1,8,0,1,2); a final version has the highest stage, so it comes after its betas.
STAGES={'alpha':0,'beta':1,'rc':2,None:3}
def version_key(text):
 """'v1.8.0-beta.2' as (1,8,0,1,2), '1.7.1' as (1,7,1,3,0); anything else as None."""
 found=re.fullmatch(r'v?(\d+)\.(\d+)(?:\.(\d+))?(?:-(alpha|beta|rc)\.?(\d+)?)?',str(text or '').strip(),re.I)
 if not found:return None
 major,minor,patch,stage,number=found.groups()
 return (int(major),int(minor),int(patch or 0),STAGES[stage.lower() if stage else None],int(number or 0))
def version_name(text):
 """A version as PlayBridge writes it: '1.8.0' or '1.8.0-beta.2'."""
 key=version_key(text)
 if key is None:return None
 stage=next(name for name,value in STAGES.items() if value==key[3])
 return '.'.join(map(str,key[:3]))+(f'-{stage}.{key[4]}' if stage else '')
def is_newer(version,current=VERSION):
 theirs,ours=version_key(version),version_key(current)
 return bool(theirs and ours and theirs>ours)
def read_release(data,beta=False):
 """The parts of a GitHub release this needs, or None when it is a draft, a pre-release (unless beta) or lacks the EXE or its checksums."""
 if not isinstance(data,dict) or data.get('draft') or data.get('prerelease') and not beta:return None
 version=version_key(data.get('tag_name'))
 if version and version[3]!=STAGES[None] and not beta:return None
 assets={asset.get('name'):asset for asset in data.get('assets') or [] if isinstance(asset,dict)}
 exe,sums=assets.get(EXE),assets.get(SUMS)
 if not version or not exe or not sums or not exe.get('browser_download_url') or not sums.get('browser_download_url'):return None
 return dict(version=version_name(data.get('tag_name')),page=data.get('html_url') or f'https://github.com/{REPOSITORY}/releases/latest',exe_url=exe['browser_download_url'],
  exe_size=int(exe.get('size') or 0),sums_url=sums['browser_download_url'])
def prompt(status,source=False):
 """What PlayBridge asks once a new version is in, or None: 'install' when it is downloaded and checked, 'page' when this copy
 cannot put it in itself (run from source). Later on 'install' still puts it in when PlayBridge closes."""
 version=status.get('version')
 if not version:return None
 if status.get('installable'):
  return dict(kind='install',version=version,title=f'PlayBridge {version} is ready',action='Restart and update',cancel='Later',
   text=f'A new version of PlayBridge came out on GitHub. It is downloaded and checked. Restart now to go from {status.get("current",VERSION)} '
        f'to {version}, or select Later: it then goes in by itself when you close PlayBridge.')
 if status.get('state')=='available':
  return dict(kind='page',version=version,title=f'PlayBridge {version} is out',action='Open the release page',cancel='Later',
   text='This copy runs from source, so it does not update itself. The release page has the new version and its source code.' if source
        else 'Download the new version from its release page on GitHub.')
 return None
def checksum_for(text,name=EXE):
 """The SHA-256 that a SHA256SUMS.txt gives for one file, or None."""
 for line in str(text).splitlines():
  parts=line.strip().split()
  if len(parts)==2 and parts[1].lstrip('*')==name and re.fullmatch(r'[0-9a-fA-F]{64}',parts[0]):return parts[0].lower()
 return None
def fetch(url,timeout=10,api=False):
 headers={'User-Agent':f'PlayBridge/{VERSION}'}
 if api:headers['Accept']='application/vnd.github+json'
 return urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=timeout)
def start_program(command):
 """Starts a PlayBridge EXE on its own. A one-file EXE started from another would otherwise reuse the first one's unpacked files."""
 return subprocess.Popen([str(part) for part in command],close_fds=True,creationflags=DETACHED,env=dict(os.environ,PYINSTALLER_RESET_ENVIRONMENT='1'))
def frozen():return bool(getattr(sys,'frozen',False))

class Updater:
 """Checks, downloads and hands over to the new EXE. Its state is read by the window: idle, checking, current, downloading, ready,
 available (from source, or with downloads off), failed."""
 def __init__(self,folder,automatic=True,on_change=None,rate=DOWNLOAD_RATE,channel='stable'):
  self.folder=Path(folder);self.automatic=automatic;self.on_change=on_change;self.rate=rate;self.channel=channel if channel in CHANNELS else 'stable'
  self.state='idle';self.version=None;self.page=None;self.progress=0.0;self.reason='';self.checked_at=None;self.file=None;self.revision=0
  self.lock=threading.Lock();self.stop=threading.Event();self.wake=threading.Event();self.busy=False;self.thread=None
  # Only an update run by another EXE changes what is kept, so it is looked at once.
  self.previous=kept_previous(self.folder/PREVIOUS)
 def status(self):
  with self.lock:return dict(state=self.state,version=self.version,progress=self.progress,reason=self.reason,checked_at=self.checked_at,current=VERSION,
   automatic=self.automatic,installable=self.state=='ready' and frozen(),page=self.page,revision=self.revision,channel=self.channel,
   previous=self.previous[0] if self.previous and frozen() else None)
 def set_automatic(self,on):
  """Update automatically on or off; turned on, it looks at once."""
  with self.lock:self.automatic=bool(on);self.revision+=1
  if self.automatic:self.wake.set()
 def set_channel(self,channel):
  """Beta versions on or off. A beta downloaded and waiting is dropped when they go off; either way it looks again at once."""
  channel=channel if channel in CHANNELS else 'stable'
  with self.lock:
   if channel==self.channel:return
   self.channel=channel;self.revision+=1
   if channel=='stable' and self.version and (version_key(self.version) or (0,))[3:4]!=(STAGES[None],):self.state='idle';self.version=None;self.file=None;self.progress=0.0
  self.wake.set()
 def text(self):
  s=self.status();state=s['state'];version=s['version']
  if state=='checking':return 'Looking for a new version…'
  if state=='current':return f'PlayBridge {VERSION} is the latest version'+(', betas included.' if s['channel']=='beta' else '.')+(f' Checked at {time.strftime("%H:%M",time.localtime(s["checked_at"]))}.' if s['checked_at'] else '')
  if state=='downloading':return f'Downloading PlayBridge {version}… {round(s["progress"]*100)}%'
  if state=='ready':return f'PlayBridge {version} is ready. It installs when you close PlayBridge, or now with Restart and update.'
  if state=='available':return f'PlayBridge {version} is out. Download it from the GitHub page.' if not frozen() else f'PlayBridge {version} is out. Select Check now to download it.'
  if state=='failed':return s['reason'] or 'The update check did not finish.'
  return f'This is PlayBridge {VERSION}.'
 def set(self,**values):
  with self.lock:
   # The window redraws on a new revision: every change of state, and the progress one percent at a time.
   if any(key!='progress' and getattr(self,key)!=value for key,value in values.items()) or int(values.get('progress',self.progress)*100)!=int(self.progress*100):self.revision+=1
   for key,value in values.items():setattr(self,key,value)
  if self.on_change:
   try:self.on_change()
   except Exception:pass
 def start(self):
  """Checks a few seconds after opening and then every six hours, while automatic updates are on."""
  if self.thread:return
  self.thread=threading.Thread(target=self.loop,name='PlayBridge updates',daemon=True);self.thread.start()
 def loop(self):
  if self.stop.wait(FIRST_CHECK):return
  while not self.stop.is_set():
   if self.automatic:self.run(download=True)
   self.wake.wait(CHECK_EVERY);self.wake.clear()
 def check_now(self):
  """From the Check now button: looks at once and downloads what it finds, whether or not updates are automatic."""
  threading.Thread(target=self.run,kwargs=dict(download=True),name='PlayBridge update check',daemon=True).start()
 def run(self,download=True):
  with self.lock:
   if self.busy or self.state=='ready':return
   self.busy=True
  try:
   self.set(state='checking',reason='')
   try:release=self.newest()
   except Exception as error:
    self.keep_error(error);self.set(state='failed',reason=f'Could not reach GitHub to look for a new version ({type(error).__name__}).');return
   if not release or not is_newer(release['version']):self.set(state='current',checked_at=time.time(),version=None);return
   self.set(version=release['version'],page=release['page'],checked_at=time.time())
   if not frozen() or not download:self.set(state='available');return
   self.download(release)
  finally:
   with self.lock:self.busy=False
 def newest(self):
  """The newest release this channel takes, or None."""
  if self.channel!='beta':
   with fetch(LATEST,api=True) as answer:return read_release(json.loads(answer.read(1_000_000).decode('utf8')))
  with fetch(RELEASES,api=True) as answer:data=json.loads(answer.read(4_000_000).decode('utf8'))
  found=[release for release in (read_release(item,beta=True) for item in (data if isinstance(data,list) else [])) if release]
  return max(found,key=lambda release:version_key(release['version']),default=None)
 def download(self,release):
  self.folder.mkdir(parents=True,exist_ok=True)
  final=self.folder/f'PlayBridge-{release["version"]}.exe';partial=final.with_suffix('.exe.partial')
  try:
   with fetch(release['sums_url']) as answer:wanted=checksum_for(answer.read(100_000).decode('utf8','replace'))
   if not wanted:raise ValueError('the release has no checksum for PlayBridge.exe')
   if final.is_file() and digest(final)==wanted:self.set(state='ready',file=final,progress=1.0);return
   self.set(state='downloading',progress=0.0)
   hasher=hashlib.sha256();size=0;began=time.perf_counter();total=release['exe_size']
   with fetch(release['exe_url'],timeout=30) as answer,open(partial,'wb') as out:
    while not self.stop.is_set():
     chunk=answer.read(262144)
     if not chunk:break
     out.write(chunk);hasher.update(chunk);size+=len(chunk)
     if total:self.set(progress=min(1.0,size/total))
     # Never faster than the rate, so the download stays out of the stream's way.
     if self.rate:
      ahead=size/self.rate-(time.perf_counter()-began)
      if ahead>0:self.stop.wait(ahead)
   if self.stop.is_set():raise InterruptedError('PlayBridge closed during the download')
   if total and size!=total:raise ValueError(f'the download stopped at {size} of {total} bytes')
   if hasher.hexdigest()!=wanted:raise ValueError('the download did not match its checksum')
   with open(partial,'rb') as f:
    if f.read(2)!=b'MZ':raise ValueError('the download is not a Windows program')
   os.replace(partial,final);self.set(state='ready',file=final,progress=1.0)
  except Exception as error:
   try:partial.unlink(missing_ok=True)
   except OSError:pass
   if not self.stop.is_set():
    # The checks below say what was wrong in a few words; a network error's own text is long and in the system's language.
    self.keep_error(error);why=str(error) if isinstance(error,ValueError) else f'the download did not finish ({type(error).__name__})'
    self.set(state='failed',reason=f'PlayBridge {release["version"]} was not kept: {why}.')
 def keep_error(self,error):
  """The whole error of the last failed check or download, in update-error.log beside the downloads, for when the short reason
  in Settings is not enough."""
  try:
   self.folder.mkdir(parents=True,exist_ok=True)
   (self.folder/'update-error.log').write_text(time.strftime('%Y-%m-%d %H:%M:%S ')+f'PlayBridge {VERSION}\n'+''.join(traceback.format_exception(error)),encoding='utf8')
  except OSError:pass
 def install(self,relaunch=False):
  """Starts the new EXE, which replaces this one once it has closed. The caller closes PlayBridge right after."""
  status=self.status()
  if not status['installable'] or not self.file or not Path(self.file).is_file():return False
  command=[str(self.file),'--finish-update',str(Path(sys.executable).resolve())]+(['--relaunch'] if relaunch else [])
  try:start_program(command)
  except OSError as error:self.set(state='failed',reason=f'The new version did not start: {error}.');return False
  return True
 def go_back(self):
  """Starts the kept older EXE, which puts itself back in place of this one once it has closed, and opens it. The caller turns
  automatic updates off first and closes PlayBridge right after."""
  if not frozen() or not self.previous or not Path(self.previous[1]).is_file():return False
  command=[str(self.previous[1]),'--finish-update',str(Path(sys.executable).resolve()),'--relaunch','--no-keep']
  try:start_program(command)
  except OSError as error:self.set(state='failed',reason=f'PlayBridge {self.previous[0]} did not start: {error}.');return False
  return True
 def close(self):self.stop.set();self.wake.set()

def digest(path):
 hasher=hashlib.sha256()
 with open(path,'rb') as f:
  for chunk in iter(lambda:f.read(1048576),b''):hasher.update(chunk)
 return hasher.hexdigest()

def finish(target,relaunch=False,source=None,wait=WAIT_FOR_CLOSE,start=None,say=None,keep=None,old_version=None):
 """Run by the new EXE: waits for the old one at target to close, puts this EXE in its place and, when asked, opens it. With keep,
 a folder, the old EXE is copied there first under its version, for Go back. Returns 0 when it did, 1 when the old file could
 not be replaced in time."""
 source=Path(source or sys.executable);target=Path(target);partial=target.with_name(target.name+'.update')
 kept=keep_copy(target,keep,old_version) if keep else None
 try:
  # The copy goes next to the old EXE first, so the swap itself is one rename once the old one lets go.
  with open(source,'rb') as src,open(partial,'wb') as out:
   for chunk in iter(lambda:src.read(1048576),b''):out.write(chunk)
  deadline=time.monotonic()+wait
  while True:
   try:os.replace(partial,target);break
   except PermissionError:
    if time.monotonic()>=deadline:raise
    time.sleep(.25)
 except OSError as error:
  for path in (partial,kept):
   try:path and path.unlink(missing_ok=True)
   except OSError:pass
  (say or alert)(f'PlayBridge could not replace {target}:\n{error}\n\nThe new version is saved as {source}. Close PlayBridge and copy it over the old file.')
  return 1
 if kept:settle_copy(kept)
 if relaunch:
  try:(start or (lambda path:start_program([path])))(target)
  except OSError as error:(say or alert)(f'PlayBridge was updated but did not open again: {error}');return 1
 return 0

def exe_version(path):
 """The version a Windows program's details give ('1.8.0', '1.9.0-beta.1'), or None."""
 try:
  import ctypes
  from ctypes import wintypes
  dll=ctypes.WinDLL('version')
  dll.GetFileVersionInfoSizeW.argtypes=(wintypes.LPCWSTR,ctypes.POINTER(wintypes.DWORD));dll.GetFileVersionInfoSizeW.restype=wintypes.DWORD
  dll.GetFileVersionInfoW.argtypes=(wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p);dll.GetFileVersionInfoW.restype=wintypes.BOOL
  dll.VerQueryValueW.argtypes=(ctypes.c_void_p,wintypes.LPCWSTR,ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(wintypes.UINT));dll.VerQueryValueW.restype=wintypes.BOOL
  size=dll.GetFileVersionInfoSizeW(str(path),None)
  if not size:return None
  data=ctypes.create_string_buffer(size)
  if not dll.GetFileVersionInfoW(str(path),0,size,data):return None
  pointer=ctypes.c_void_p();length=wintypes.UINT()
  # The written version first, which keeps a beta's name, in the language the details name; the four numbers otherwise.
  tables=[]
  if dll.VerQueryValueW(data,'\\VarFileInfo\\Translation',ctypes.byref(pointer),ctypes.byref(length)) and length.value>=4:
   language,page=(ctypes.c_uint16*2).from_address(pointer.value);tables.append(f'{language:04X}{page:04X}')
  for table in tables+['040904B0']:
   if dll.VerQueryValueW(data,f'\\StringFileInfo\\{table}\\ProductVersion',ctypes.byref(pointer),ctypes.byref(length)) and length.value:
    named=version_name(ctypes.wstring_at(pointer.value,length.value).rstrip('\0'))
    if named:return named
  if not dll.VerQueryValueW(data,'\\',ctypes.byref(pointer),ctypes.byref(length)) or length.value<52:return None
  info=(ctypes.c_uint32*13).from_address(pointer.value)
  if info[0]!=0xFEEF04BD:return None
  return f'{info[2]>>16}.{info[2]&0xFFFF}.{info[3]>>16}'
 except (OSError,AttributeError,ValueError):return None

def keep_copy(target,folder,version=None):
 """Copies the EXE about to be replaced into folder as PlayBridge-<version>.exe.partial; the path, or None when its version is
 unknown or the copy failed. A running EXE can be read, so this happens while the old one is still closing."""
 version=version_name(version or exe_version(target))
 if not version:return None
 folder=Path(folder);partial=folder/f'PlayBridge-{version}.exe.partial'
 try:
  folder.mkdir(parents=True,exist_ok=True)
  with open(target,'rb') as src,open(partial,'wb') as out:
   for chunk in iter(lambda:src.read(1048576),b''):out.write(chunk)
  return partial
 except OSError:
  try:partial.unlink(missing_ok=True)
  except OSError:pass
  return None

def settle_copy(partial):
 """The replaced EXE is kept for good: the copy gets its name and whatever was kept before goes."""
 final=partial.with_name(partial.name[:-len('.partial')])
 try:os.replace(partial,final)
 except OSError:return
 for path in final.parent.glob('PlayBridge-*.exe*'):
  if path!=final:
   try:path.unlink()
   except OSError:pass

def kept_previous(folder,current=VERSION):
 """The older EXE the last update kept, as (version, path), or None."""
 best=None
 for path in Path(folder).glob('PlayBridge-*.exe'):
  version=version_name(path.name[len('PlayBridge-'):-len('.exe')])
  if not version or not is_newer(current,version) or best and not is_newer(version,best[0]):continue
  try:
   with open(path,'rb') as f:
    if f.read(2)!=b'MZ':continue
  except OSError:continue
  best=(version,path)
 return best

def alert(text):
 try:
  import ctypes
  ctypes.windll.user32.MessageBoxW(None,text,'PlayBridge update',0x30)
 except Exception:print(text,file=sys.stderr)

def tidy(folder,current=VERSION,tries=30):
 """Removes downloads that are this version or older; the EXE that just finished may still be closing, so it tries for a while."""
 folder=Path(folder)
 for _ in range(tries):
  left=[]
  for path in folder.glob('PlayBridge-*.exe*'):
   version=version_name(path.name[len('PlayBridge-'):].split('.exe')[0])
   if path.name.endswith('.partial') or not version or not is_newer(version,current):
    try:path.unlink()
    except OSError:left.append(path)
  if not left:return True
  time.sleep(1)
 return False
