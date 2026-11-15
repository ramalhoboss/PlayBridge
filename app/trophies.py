"""A game's trophies, from the console's own files and only read: which set a game uses (npbind.dat), the set's trophies with their names and
grades (TROPHY.UCP), and which of them the player has and since when (TRPTITLE.DAT). How these files are laid out was worked out on a real
console by OpenPSApp (github.com/marcelorsdd/OpenPSApp, GPL-3.0). Nothing here trusts a file: anything out of place is a ValueError."""
import hashlib,json,re,struct

SET=re.compile('NPWR[0-9]{5}_[0-9]{2}')
UCP_MAGIC=0xb228c60a;UCP_TABLE=0x60;UCP_ENTRY=64;UCP_MOST=4096
NPBIND_MAGIC=0xd294a018;NPBIND_RECORDS=0x80;NPBIND_SET=0x0010
T2_VERSION=0x10000;T2_HEADER=64;T2_PAGE=1024;T2_STRIDE=T2_PAGE+32;T2_STREAM=48;T2_ENTRY=32;T2_STATES=0x800;T2_MOST=16<<20
EARNED=0x11
# Seconds from the year 1 to 1970: the console counts microseconds from the year 1.
EPOCH=62135596800
GRADES={'P':'platinum','G':'gold','S':'silver','B':'bronze'}
# What each grade is worth on the console's progress bar, which leaves the platinum out.
POINTS={'platinum':180,'gold':90,'silver':30,'bronze':15}
# A trophy's own picture in its set's file: a PNG of at most this size.
PNG=b'\x89PNG\r\n\x1a\n';ICON_MOST=1<<20
# The text a set's names may be in, first the game's own default, then English.
LANGUAGES=('en-US','en-GB')

def be16(data,at):return struct.unpack_from('>H',data,at)[0]
def be32(data,at):return struct.unpack_from('>I',data,at)[0]
def be64(data,at):return struct.unpack_from('>Q',data,at)[0]

def set_of(data):
 """The trophy set an npbind.dat names, or '' if it names none."""
 if len(data)<NPBIND_RECORDS+4 or be32(data,0)!=NPBIND_MAGIC:return ''
 at=NPBIND_RECORDS
 while at+4<=len(data):
  tag,size=be16(data,at),be16(data,at+2)
  if at+4+size>len(data):break
  if tag==NPBIND_SET:
   value=bytes(data[at+4:at+4+size]).split(b'\0')[0].decode('ascii','replace');return value if SET.fullmatch(value) else ''
  at+=4+size
 return ''

def ucp_count(head):
 """How many files a TROPHY.UCP holds, from its first 0x60 bytes. The table after them is that many times 64 bytes long."""
 if len(head)<UCP_TABLE or be32(head,0)!=UCP_MAGIC:raise ValueError('Not a trophy set')
 count=be32(head,0x10)
 if be32(head,0x14)!=UCP_ENTRY or not 0<count<=UCP_MOST:raise ValueError('Trophy set table out of range')
 return count
def ucp_table(head,table):
 """The files a TROPHY.UCP holds: {name: (offset, size)}."""
 count=ucp_count(head)
 if len(table)<count*UCP_ENTRY:raise ValueError('Trophy set table cut short')
 files={}
 for index in range(count):
  at=index*UCP_ENTRY;name=bytes(table[at:at+32]).split(b'\0')[0]
  if not name or any(c<=0x20 or c>=0x7f or c in b'/\\' for c in name):raise ValueError('Trophy set entry has a bad name')
  files[name.decode('ascii')]=(be64(table,at+32),be64(table,at+40))
 return files
def icon_place(files,number):
 """Where a trophy's own picture (trop0001.png) sits in its set's file, (offset, size), or None."""
 wanted=f'trop{number:04d}.png'
 for name,place in files.items():
  if name.lower()==wanted:return place if 0<place[1]<=ICON_MOST else None
 return None
def meta_name(files,default=''):
 """The file with the trophies' names: in the game's own language, else in English, else in any it has."""
 for language in ((default,) if default else ())+LANGUAGES:
  if f'tropmeta_{language}.json' in files:return f'tropmeta_{language}.json'
 for name in sorted(files):
  if name.startswith('tropmeta_en') and name.endswith('.json'):return name
 return next((name for name in sorted(files) if name.startswith('tropmeta_') and name.endswith('.json')),'')
def text(value,most):
 return ''.join(c for c in value if c.isprintable()).strip()[:most] if isinstance(value,str) else ''
def trophy_set(conf,meta=None):
 """The set's own name and its trophies in their order, from tropconf.json and a tropmeta file: {name, trophies: [{id, grade, hidden, name, detail}]}."""
 conf=json.loads(conf) if isinstance(conf,(bytes,str)) else conf
 if not isinstance(conf,dict) or not isinstance(conf.get('trophies'),list):raise ValueError('Trophy set has no list')
 trophies=[];index={}
 for item in conf['trophies']:
  if not isinstance(item,dict):continue
  try:number=int(item.get('id'))
  except (TypeError,ValueError):continue
  if number<0 or number in index:continue
  grade=GRADES.get(str(item.get('grade') or '')[:1].upper(),'')
  index[number]=len(trophies);trophies.append(dict(id=number,grade=grade,hidden=item.get('hidden') is True,name='',detail=''))
 name=''
 try:meta=json.loads(meta) if isinstance(meta,(bytes,str)) else meta
 except ValueError:meta=None
 data=meta.get('metadata') if isinstance(meta,dict) else None
 if isinstance(data,dict):
  title=data.get('titleMetadata');name=text(title.get('name'),120) if isinstance(title,dict) else ''
  for item in data.get('trophyMetadata') or ():
   if not isinstance(item,dict):continue
   try:at=index.get(int(item.get('id')))
   except (TypeError,ValueError):continue
   if at is not None:trophies[at].update(name=text(item.get('name'),120),detail=text(item.get('detail'),400))
 return dict(name=name,trophies=trophies,default=text(conf.get('defaultLanguage'),16))

def earned(data):
 """When the player earned each trophy they have: {id: seconds since 1970}. Every page of the file must match its SHA-256."""
 data=memoryview(bytes(data))
 if len(data)<T2_HEADER or bytes(data[:4])!=b'T2PD' or be32(data,4)!=T2_VERSION or be64(data,8)!=T2_STRIDE:raise ValueError('Not a trophy record')
 pages=be64(data,32)
 if not 0<pages<=T2_MOST//T2_STRIDE or len(data)!=T2_HEADER+pages*T2_STRIDE:raise ValueError('Trophy record size does not match its pages')
 stream=bytearray()
 for page in range(pages):
  at=T2_HEADER+page*T2_STRIDE;part=bytes(data[at:at+T2_PAGE]);digest=bytes(data[at+T2_PAGE:at+T2_STRIDE])
  if hashlib.sha256(part).digest()!=digest and (any(digest) or any(part)):raise ValueError(f'Trophy record page {page} is damaged')
  stream+=part
 if bytes(stream[:4])!=b'T2TD' or be32(stream,4)!=T2_VERSION:raise ValueError('Trophy record has no table')
 count=be32(stream,8)
 if not 0<count<=64 or T2_STREAM+count*T2_ENTRY>len(stream):raise ValueError('Trophy record directory out of range')
 for entry in range(count):
  at=T2_STREAM+entry*T2_ENTRY
  if be32(stream,at)!=T2_STATES:continue
  payload,version,repeat,offset=be32(stream,at+4),be32(stream,at+8),be32(stream,at+12),be64(stream,at+16);stride=16+payload
  if version!=1 or payload<0x30 or not 0<repeat<=4096 or offset>len(stream) or repeat*stride>len(stream)-offset:raise ValueError('Trophy record table out of range')
  found={}
  for row in range(repeat):
   record=offset+row*stride
   if be32(stream,record)!=T2_STATES:raise ValueError('Trophy record row out of place')
   number,flags,first,second=be32(stream,record+0x10),be32(stream,record+0x14),be64(stream,record+0x20),be64(stream,record+0x30)
   if flags==EARNED and first and second:found[number]=max(0,first//1000000-EPOCH)
  return found
 raise ValueError('Trophy record has no trophies')

def tally(trophies,have):
 """How far along a set is, as the console counts it: {earned, total, progress (0-100), platinum (None, False or True), grades}."""
 grades={grade:[0,0] for grade in POINTS};points=[0,0];platinum=None;count=0
 for trophy in trophies:
  got=trophy['id'] in have;count+=got;grade=trophy['grade']
  if grade in grades:grades[grade][0]+=got;grades[grade][1]+=1
  if grade=='platinum':platinum=bool(platinum) or got;continue
  points[1]+=POINTS.get(grade,0);points[0]+=POINTS.get(grade,0) if got else 0
 return dict(earned=count,total=len(trophies),progress=points[0]*100//points[1] if points[1] else 0,platinum=platinum,grades=grades)
def last_earned(have):
 return max(have.values(),default=0)
