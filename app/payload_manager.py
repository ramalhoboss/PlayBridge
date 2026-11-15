"""A shelf of PS5 payloads and a developer loop, both on top of payload_sender (which still does the sending and the ELF check).

The shelf reads .elf assets from the GitHub releases of a repository the owner chooses (empty by default: the owner names their own),
keeps the ones they download in a folder beside the preferences, and marks a payload whose release carries a newer copy than the one on
disk. Nothing is sent without the owner; the window's Send asks first, as the single Send-a-payload card already does.

The developer loop watches one .elf the owner is building. When its bytes change it tells the window, which resends it (the owner arms
the watch once, with the full-access warning, and that arming is the OK for the session). A read-only reader of the console's kernel-log
server shows the lines the payload and the system print, so a build can be tried and watched without leaving PlayBridge."""
import json,os,socket,threading,time,urllib.request
from pathlib import Path
from app_version import VERSION
import payload_sender

KLOG_PORT=3232
# The kernel-log server sends a long backlog the moment it connects; those lines are old, not what just happened.
BACKLOG_QUIET=1.0
LINE_LIMIT=4000
CATALOG_EVERY=3600


class CatalogError(ValueError):
 """What went wrong reading a repository's payloads, in words for the owner."""


def default_opener(url,timeout=15):
 """GitHub's releases, as bytes. A generic client name; no account, no PlayBridge details."""
 request=urllib.request.Request(url,headers={'User-Agent':f'PlayBridge/{VERSION}','Accept':'application/vnd.github+json'})
 with urllib.request.urlopen(request,timeout=timeout) as answer:return answer.read()


def releases_url(repo):
 """The API that lists a repository's releases, newest first, or None when the name is not owner/repo."""
 parts=[part for part in str(repo or '').strip().strip('/').split('/') if part]
 if len(parts)!=2 or not all(part.replace('.','').replace('-','').replace('_','').isalnum() for part in parts):return None
 return f'https://api.github.com/repos/{parts[0]}/{parts[1]}/releases?per_page=20'


def read_catalog(data,repo=''):
 """The .elf assets across a repository's releases, each once (its newest release), newest first: name, size, url, tag, when, digest."""
 try:releases=json.loads(data) if isinstance(data,(str,bytes,bytearray)) else data
 except ValueError:raise CatalogError('That repository did not answer with a release list.') from None
 if not isinstance(releases,list):raise CatalogError('That repository has no releases.')
 found={}
 for release in releases:
  if not isinstance(release,dict) or release.get('draft'):continue
  tag=str(release.get('tag_name') or '');when=str(release.get('published_at') or '')
  for asset in release.get('assets') or []:
   name=isinstance(asset,dict) and str(asset.get('name') or '')
   if not name or not name.lower().endswith('.elf') or not asset.get('browser_download_url'):continue
   if name in found:continue
   found[name]=dict(name=name,size=int(asset.get('size') or 0),url=asset['browser_download_url'],tag=tag,repo=repo,
    when=when,digest=str(asset.get('digest') or ''),id=int(asset.get('id') or 0))
 return sorted(found.values(),key=lambda item:item['when'],reverse=True)


class Store:
 """The payloads the owner has downloaded, under a folder, with a note of which release each came from so a newer one shows as an update."""
 def __init__(self,folder):
  self.folder=Path(folder);self.notes={}
  try:kept=json.loads((self.folder/'payloads.json').read_text(encoding='utf-8'))
  except (OSError,ValueError):kept={}
  if isinstance(kept,dict):self.notes={str(name):note for name,note in kept.items() if isinstance(note,dict)}
 def path(self,name):return self.folder/Path(str(name)).name
 def have(self,name):return self.path(name).is_file()
 def bytes_of(self,name):return payload_sender.read_payload(self.path(name))
 def is_update(self,item):
  """True when the shelf's copy of this payload comes from a different release than the one on disk."""
  note=self.notes.get(item['name'])
  return bool(self.have(item['name']) and note and (note.get('digest') or note.get('tag'))!=(item.get('digest') or item.get('tag')))
 def save_note(self,item):
  self.notes[item['name']]=dict(tag=item.get('tag',''),digest=item.get('digest',''),when=item.get('when',''),repo=item.get('repo',''))
  try:
   self.folder.mkdir(parents=True,exist_ok=True)
   spare=self.folder/'payloads.tmp';spare.write_text(json.dumps(self.notes,indent=1,ensure_ascii=False),encoding='utf-8');os.replace(spare,self.folder/'payloads.json')
  except OSError:pass
 def store(self,item,data):
  """Keeps a downloaded payload and remembers its release. data is the asset's bytes, checked as a payload first."""
  payload_sender.check_payload(data);self.folder.mkdir(parents=True,exist_ok=True);self.path(item['name']).write_bytes(data);self.save_note(item)
  return self.path(item['name'])
 def listing(self,catalog):
  """Each payload the repository offers with whether it is on disk and whether the repository's copy is newer."""
  return [dict(item,have=self.have(item['name']),update=self.is_update(item)) for item in catalog]


def download(item,opener=default_opener):
 """An asset's bytes, checked as a payload. Raises CatalogError when it cannot be fetched or is not a payload."""
 if item.get('size') and item['size']>payload_sender.LIMIT:raise CatalogError('That payload is larger than 64 MB.')
 try:data=opener(item['url'])
 except OSError:raise CatalogError('That payload could not be downloaded.') from None
 try:return payload_sender.check_payload(bytes(data))
 except payload_sender.PayloadError as problem:raise CatalogError(str(problem)) from None


class Shelf:
 """The payload shelf for one repository: it fetches the catalog on a thread, keeps the listing, and holds the Store. The window reads
 `items` and `status`; `refresh` and `fetch` are safe to call from the UI thread (the work runs on its own)."""
 def __init__(self,store,repo='',opener=default_opener,clock=time.monotonic):
  self.store=store;self.opener=opener;self.clock=clock;self.repo=str(repo or '').strip()
  self.catalog=[];self.status='';self.fetched_at=0.0;self._lock=threading.Lock();self._busy=False
 def set_repo(self,repo):
  repo=str(repo or '').strip()
  if repo!=self.repo:self.repo=repo;self.catalog=[];self.status='';self.fetched_at=0.0
 def items(self):
  with self._lock:return self.store.listing(self.catalog)
 def fetch(self,on_done=None):
  """Reads the repository's releases on a thread. on_done() runs when it finishes, for the window to repaint."""
  if self._busy or not self.repo:
   if not self.repo:self.status='Name a repository (owner/name) with .elf payloads in its releases.'
   return
  url=releases_url(self.repo)
  if url is None:self.status='That is not a repository name. Use owner/name.';return
  self._busy=True;self.status='Reading payloads…'
  def work():
   try:catalog=read_catalog(self.opener(url),self.repo);status='' if catalog else 'That repository has no .elf payloads in its releases.'
   except CatalogError as problem:catalog=None;status=str(problem)
   except OSError:catalog=None;status='That repository could not be reached.'
   with self._lock:
    if catalog is not None:self.catalog=catalog
    self.status=status;self.fetched_at=self.clock()
   self._busy=False
   if on_done:on_done()
  threading.Thread(target=work,name='PlayBridge payloads',daemon=True).start()
 def refresh(self,on_done=None):
  if self.clock()-self.fetched_at>=CATALOG_EVERY or not self.catalog:self.fetch(on_done)


class Watch:
 """One .elf the owner is building, watched for changes so the window can resend it. Nothing is sent here; only the change is reported."""
 def __init__(self,path,clock=time.time):
  self.path=Path(path);self.clock=clock;self.stamp=self._stamp();self.seen=self.clock()
 def _stamp(self):
  try:info=self.path.stat();return (info.st_mtime_ns,info.st_size)
  except OSError:return None
 def changed(self):
  """True once when the file's bytes look different from last time (and it is there)."""
  stamp=self._stamp()
  if stamp is None or stamp==self.stamp:return False
  self.stamp=stamp;self.seen=self.clock();return True
 def read(self):
  """The watched file as a payload, or a PayloadError."""
  return payload_sender.read_payload(self.path)


class KernelLog:
 """A read-only reader of the console's kernel-log server (port 3232): it only listens, never sends. Lines arrive on a thread and
 the window takes them a few at a time. The long backlog the server sends on connect is dropped, so only fresh lines show."""
 def __init__(self,host,port=KLOG_PORT,opener=None,clock=time.monotonic):
  self.host=host;self.port=port;self.clock=clock;self.lines=[];self.error='';self.running=False
  self._open=opener or (lambda:socket.create_connection((self.host,self.port),5))
  self._lock=threading.Lock();self._thread=None;self._sock=None;self._stop=False
 def start(self):
  if self.running:return
  self.running=True;self._stop=False;self.error='';self._thread=threading.Thread(target=self._run,name='PlayBridge klog',daemon=True);self._thread.start()
 def _run(self):
  try:sock=self._sock=self._open()
  except OSError:
   with self._lock:self.error='The kernel log did not answer. Check the console IP and that it is on.'
   self.running=False;return
  started=self.clock();rest=b''
  try:
   sock.settimeout(1.0)
   while not self._stop:
    try:chunk=sock.recv(8192)
    except socket.timeout:continue
    except OSError:break
    if not chunk:break
    rest+=chunk;*whole,rest=rest.split(b'\n')
    fresh=self.clock()-started>=BACKLOG_QUIET
    if whole and fresh:
     with self._lock:
      self.lines.extend(line.decode('utf-8','replace').rstrip('\r') for line in whole);del self.lines[:-LINE_LIMIT]
  finally:
   try:sock.close()
   except OSError:pass
   self.running=False
 def take(self):
  """The lines since the last call, and clears them."""
  with self._lock:lines,self.lines=self.lines,[];return lines
 def stop(self):
  self._stop=True
  try:
   if self._sock:self._sock.close()
  except OSError:pass
  self.running=False
