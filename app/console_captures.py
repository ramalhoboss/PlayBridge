"""The PS5's own screenshots and clips: found through the payload's control port and copied into this PC's capture folder, where the Media page shows them."""
import posixpath,re
from pathlib import Path
from console_control import LIST,REQUEST,fetch,read_exact,reply_header

ROOTS=('/user/av_contents','/mnt/ext0/user/av_contents','/mnt/ext1/user/av_contents')
PHOTOS=('.jpg','.jpeg','.png','.webp');VIDEOS=('.mp4','.webm')
# Measured on a PS5: each root holds photo, video, thumbnails, content_tmp, sdr and extra. Only the first two are the captures;
# the rest are previews (x.mp4.jpeg), unfinished files and copies the console makes for itself.
KINDS=('photo','video')
# Below photo or video the path names the app that saved the capture, then the game in it, e.g. video/NPXS40087/CUSA03280/04b/x.mp4.
TITLE=re.compile(r'^[A-Z]{4}\d{5}$')
LIST_LIMIT=0x10000;CLIP_LIMIT=0xfffffffe
# What the payload answers to a command it does not know: one from before this feature.
UNKNOWN_COMMAND=22

def listing(sock,path):
 """The console's answer and the folder's entries as (d or f, size, time, name)."""
 name=path.encode('utf8');sock.sendall(REQUEST.pack(b'PBC1',LIST,len(name))+name)
 result,size=reply_header(sock)
 if size>LIST_LIMIT:raise ValueError('Oversized listing')
 body=read_exact(sock,size) if size else b''
 entries=[]
 for line in body.decode('utf8','replace').split('\n'):
  parts=line.split('\t',3)
  if len(parts)!=4 or parts[0] not in ('d','f') or parts[3] in ('','.','..') or '/' in parts[3]:continue
  try:entries.append((parts[0],int(parts[1]),int(parts[2]),parts[3]))
  except ValueError:continue
 return result,entries
def kind_of(name):
 suffix=posixpath.splitext(name)[1].lower()
 return 'Photos' if suffix in PHOTOS else 'Videos' if suffix in VIDEOS else None
def preview(name):
 """The console's own small pictures of a capture, named after it: x.mp4.jpeg, x.png.jpeg."""
 return kind_of(posixpath.splitext(name)[0]) is not None
def game_of(path):
 """The game a capture was taken in: the last title id in its path, or '' when there is none."""
 return next((part for part in reversed(path.split('/')[:-1]) if TITLE.match(part)),'')
def label(title,name_of=None):
 """What a person reads for a title id: the game's name when the library knows it, System for the console's own apps."""
 if not title:return ''
 name=name_of(title) if name_of else title
 return 'System' if name==title and title.startswith('NPXS') else name
def find_captures(sock,roots=ROOTS,depth=5,limit=2000,name_of=None):
 """Every screenshot and clip under the capture roots, newest first, and whether the payload is too old to list them."""
 found=[];folders=[(root+'/'+kind,0) for root in roots for kind in KINDS];old=False
 while folders and len(found)<limit:
  folder,level=folders.pop(0)
  result,entries=listing(sock,folder)
  if result==UNKNOWN_COMMAND and level==0:old=True
  if result:continue
  for kind,size,modified,name in entries:
   path=folder+'/'+name
   if kind=='d' and level<depth:folders.append((path,level+1))
   elif kind=='f' and size>0 and kind_of(name) and not preview(name) and not name.startswith('.'):
    title=game_of(path)
    found.append({'path':path,'name':name,'title':title,'folder':label(title,name_of) or posixpath.basename(folder),'size':size,'modified':modified,'kind':kind_of(name)})
 return sorted(found,key=lambda c:(-c['modified'],c['path']))[:limit],old and not found
def local_name(capture):
 """Where the copy goes: photos with the screenshots, clips with the recordings, named after the game they came from."""
 stem,suffix=posixpath.splitext(capture['name'])
 safe=''.join(c if c.isalnum() or c in ' -_()' else '_' for c in capture['folder']+' '+stem).strip()[:120] or 'capture'
 return Path('Screenshots' if capture['kind']=='Photos' else 'Recordings')/('PS5 '+safe+suffix.lower())
def copied(capture,folder):
 target=Path(folder)/local_name(capture)
 try:return target.is_file() and target.stat().st_size==capture['size']
 except OSError:return False
def copy_capture(sock,capture,folder,progress=None):
 """Copies one capture unless an identical one is already there. Returns where it is, or None if the console refused it."""
 target=Path(folder)/local_name(capture)
 if copied(capture,folder):return target
 target.parent.mkdir(parents=True,exist_ok=True);partial=target.with_name(target.name+'.partial')
 try:
  if not fetch(sock,capture['path'],partial,CLIP_LIMIT,progress):return None
  partial.replace(target);return target
 finally:
  if partial.exists():partial.unlink()
def size_label(size):
 for unit,scale in (('GB',1<<30),('MB',1<<20),('KB',1<<10)):
  if size>=scale:return f'{size/scale:.1f} {unit}'
 return f'{size} B'
