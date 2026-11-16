"""Trophies from PlayStation Network: the player's trophy level, every game they have trophies in (PS5 and PS4, and the games no longer
on the console), each game's trophies with how many players have them, and a friend's trophies beside them. It also fills in the
Games page for the games whose trophies the console's own files do not give (the PS4 games).

Only read, never written. Everything runs on psn_link.Psn's thread, with its sign-in and inside its request budget, and leaves ROOM
requests for friends and messages. Sony's answers are kept in folder (inside the PSN folder, so signing out forgets them), so the Games
page has them at once on the next start. The wire facts come from the documentation of the psn-api and PSNAWP projects; the code is
PlayBridge's own. A friend can keep their trophies private: Sony then answers 403, and the page says so."""
import hashlib,json,re,threading
from datetime import datetime
from pathlib import Path
import psn_link,trophies as trophy_files

PATH='/trophy/v1'
GRADES=('platinum','gold','silver','bronze')
# The most games Sony gives in one answer, and the most PlayBridge reads for one player.
PAGE=800;MOST_TITLES=8000
# Seconds before the list of games is read again while the Trophies page shows, and before a friend's is.
LIST_EVERY=900;FRIEND_EVERY=600
# Seconds before a reading that failed is tried again.
AGAIN=60
# Sony takes at most 5 game ids in one question about which trophy set a game uses; a game with none is asked about again after a week.
MAP_AT_ONCE=5;MAP_DAYS=7;MAPS_AT_ONCE=2
# Requests left for friends and messages before trophies wait.
ROOM=60
# Pictures from Sony's image server (not counted against the budget): at most this many in one go, each at most this size.
ICONS_AT_ONCE=12;ICON_MOST=1<<20
FILTERS=('All','PS5','PS4','Platinum','Unfinished','Next up')
# Next up, the trophy hunt: the trophies most players have that the player has not, from the latest games they have started and not
# finished (at most HUNT_GAMES), at most HUNT_LISTED of them.
HUNT_GAMES=10;HUNT_LISTED=30
TITLE=re.compile('[A-Z]{4}[0-9]{5}')

def whole(value,low=0,high=None):
 try:number=int(float(value))
 except (TypeError,ValueError,OverflowError):return low
 number=max(low,number);return min(high,number) if high is not None else number
def counts(value):
 value=value if isinstance(value,dict) else {}
 return {grade:whole(value.get(grade)) for grade in GRADES}
def address(value):return psn_link.picture_address(value)
def set_id(value):return value if isinstance(value,str) and trophy_files.SET.fullmatch(value) else ''

def title_from(item):
 """One game from Sony's list: {set, service, version, name, icon, platforms, defined, earned, progress, updated, hidden}, or None."""
 if not isinstance(item,dict) or not set_id(item.get('npCommunicationId')):return None
 platforms=[part.strip() for part in str(item.get('trophyTitlePlatform') or '').split(',') if part.strip()]
 service=item.get('npServiceName') if item.get('npServiceName') in ('trophy','trophy2') else 'trophy2' if 'PS5' in platforms else 'trophy'
 return dict(set=item['npCommunicationId'],service=service,version=str(item.get('trophySetVersion') or '')[:16],name=trophy_files.text(item.get('trophyTitleName'),120),
  icon=address(item.get('trophyTitleIconUrl')),platforms=platforms,defined=counts(item.get('definedTrophies')),earned=counts(item.get('earnedTrophies')),
  progress=whole(item.get('progress'),0,100),updated=psn_link.when(item.get('lastUpdatedDateTime')),hidden=item.get('hiddenFlag') is True)

def summary_from(data):
 """The player's trophy level: {level, tier, progress (0-100, towards the next level), earned}."""
 data=data if isinstance(data,dict) else {}
 return dict(level=whole(data.get('trophyLevel')),tier=whole(data.get('tier'),0,10),progress=whole(data.get('progress'),0,100),earned=counts(data.get('earnedTrophies')))

def trophy_items(data):
 return [item for item in (data.get('trophies') if isinstance(data,dict) else None) or [] if isinstance(item,dict)]

def definitions_from(data):
 """A game's trophies in their order: [{id, grade, hidden, name, detail, icon}]."""
 rows=[];seen=set()
 for item in trophy_items(data):
  number=whole(item.get('trophyId'),-1)
  if number<0 or number in seen:continue
  seen.add(number);grade=str(item.get('trophyType') or '').lower()
  rows.append(dict(id=number,grade=grade if grade in GRADES else '',hidden=item.get('trophyHidden') is True,name=trophy_files.text(item.get('trophyName'),120),
   detail=trophy_files.text(item.get('trophyDetail'),400),icon=address(item.get('trophyIconUrl'))))
 return rows

def states_from(data):
 """One player's side of a game: {id: {at, rate}}. at is when the trophy was earned (seconds since 1970; 1 when Sony gives no date;
 0 when not earned) and rate the share of all players who have it, in percent (None when Sony does not say)."""
 found={}
 for item in trophy_items(data):
  number=whole(item.get('trophyId'),-1)
  if number<0:continue
  at=(psn_link.when(item.get('earnedDateTime')) or 1) if item.get('earned') is True else 0
  try:rate=float(item.get('trophyEarnedRate'))
  except (TypeError,ValueError):rate=None
  found[number]=dict(at=at,rate=rate if rate is not None and 0<=rate<=100 else None)
 return found

def merged(definitions,mine,theirs=None):
 """The trophies with when the player earned each, how rare it is, and when the friend earned it (None when there is no friend)."""
 rows=[]
 for row in definitions:
  own=mine.get(row['id']) or {};other=(theirs or {}).get(row['id']) or {}
  rows.append(dict(row,earned=own.get('at',0),rate=own.get('rate') if own.get('rate') is not None else other.get('rate'),theirs=other.get('at',0) if theirs is not None else None))
 return rows

def title_tally(title):
 """How far along a game is from the list's counts alone, in the shape trophies.tally gives."""
 earned,defined=title['earned'],title['defined']
 return dict(earned=sum(earned.values()),total=sum(defined.values()),progress=title['progress'],platinum=(earned['platinum']>0) if defined['platinum'] else None,
  grades={grade:[earned[grade],defined[grade]] for grade in GRADES})

def console_set(title,definitions,mine):
 """A game's trophies in the shape ConsoleLink.trophy_set gives, from PSN: {set, name, trophies, tally, known, last, source}.
 With only the list's counts read so far, trophies is empty and the tally comes from the counts."""
 rows=[dict(id=row['id'],grade=row['grade'],hidden=row['hidden'],name=row['name'],detail=row['detail'],earned=row['earned'] if row['earned']>1 else (title['updated'] if row['earned'] else 0))
  for row in merged(definitions or [],mine)] if mine is not None else []
 have={row['id']:row['earned'] for row in rows if row['earned']}
 tally=trophy_files.tally(rows,have) if rows and mine is not None else title_tally(title)
 return dict(set=title['set'],name=title['name'],trophies=rows,tally=tally,known=True,last=max(have.values(),default=0),source='psn')

def in_common(mine,theirs):
 """The games both players have trophies in, the player's latest first: [(mine, theirs)]."""
 by={title['set']:title for title in theirs}
 return [(title,by[title['set']]) for title in mine if title['set'] in by]

class TrophyBook:
 """The trophies the Trophies page and the Games page show. The window says what it wants (watch, show_set, compare_with,
 want_titles) and reads view() and console_set(); poll(), on the PSN thread, reads what is wanted from Sony."""
 def __init__(self,psn,folder):
  self.psn=psn;self.folder=Path(folder);self.lock=threading.Lock()
  # changes moves with anything the Trophies page shows, shelf_changes only with what the Games page shows.
  self.changes=0;self.shelf_changes=0
  self.watching=False;self.hunting=False;self.open=None;self.friend='';self.problem=''
  self.list_fresh=False;self.list_next=0;self.list_at=0
  kept=self.load('list.json')
  self.summary=summary_from(kept.get('summary')) if kept.get('summary') else None
  self.titles=[title for title in map(title_from,kept.get('titles') or []) if title]
  self.raw_titles=[item for item in kept.get('titles') or [] if isinstance(item,dict)]
  # Which trophy set each console game uses ({title: {at, item}}, item None when it has none on PSN), and the games still to ask about.
  self.map={key:value for key,value in self.load('map.json').items() if TITLE.fullmatch(key) and isinstance(value,dict)};self.map_wanted=[];self.shelf=set()
  # The sets' trophies ({set: {version, trophies}}, read from disk when first needed) and the player's side of each ({set: {updated, trophies}}).
  self.definitions={};self.mine={key:value for key,value in self.load('mine.json').items() if set_id(key) and isinstance(value,dict)}
  self.friend_titles={};self.friend_sets={};self.next_try={}
  self.icons={};self.icon_wanted=[];self.icon_failed=set()
  try:
   for path in (self.folder/'icons').iterdir():self.icons[path.stem]=path.name
  except OSError:pass

 # Kept on disk.
 def load(self,name):
  try:data=json.loads((self.folder/name).read_text(encoding='utf8'))
  except (OSError,ValueError):return {}
  return data if isinstance(data,dict) else {}
 def save(self,name,data):
  try:
   self.folder.mkdir(parents=True,exist_ok=True);part=self.folder/(name+'.part')
   part.write_text(json.dumps(data,ensure_ascii=False),encoding='utf8');part.replace(self.folder/name)
  except OSError:pass
 def set_rows(self,key):
  """A set's trophies, from memory or from disk; None when PlayBridge has not read them."""
  found=self.definitions.get(key)
  if found is None and set_id(key):
   kept=self.load(f'sets/{key}.json')
   if kept:found=self.definitions[key]=dict(version=str(kept.get('version') or ''),rows=definitions_from(kept))
  return found

 # The window's side.
 def watch(self,on):
  """The Trophies page shows (on) or not: while it shows, the list is read again every LIST_EVERY seconds."""
  self.watching=bool(on)
  if on:self.psn.wake()
 def hunt(self,on):
  """Next up shows (on) or not: while it shows, the trophies of the games in the hunt are read, one game at a time."""
  self.hunting=bool(on)
  if on:self.psn.wake()
 def refresh(self):
  self.list_next=0;self.list_fresh=False;self.next_try.clear()
  with self.lock:self.friend_titles.pop(self.friend,None);self.friend_sets={key:value for key,value in self.friend_sets.items() if key[0]!=self.friend}
  self.psn.wake()
 def show_set(self,key):
  key=set_id(key)
  if not key:return
  title=self.title_of(key);self.open=(key,title['service'] if title else 'trophy2');self.psn.wake()
  with self.lock:self.changes+=1
 def close_set(self):
  self.open=None
  with self.lock:self.changes+=1
 def compare_with(self,account):
  account=str(account or '');self.friend=account if account.isdigit() else ''
  with self.lock:self.changes+=1
  if self.friend:self.psn.wake()
 def want_titles(self,titles):
  """The console games whose trophies the console does not give: asked about on PSN, and their trophies read for the Games page."""
  fresh=False;now=self.psn.clock()
  for title in titles:
   if not TITLE.fullmatch(str(title)):continue
   self.shelf.add(title);known=self.map.get(title)
   if title in self.map_wanted or known and (known.get('item') or now-known.get('at',0)<MAP_DAYS*86400):continue
   self.map_wanted.append(title);fresh=True
  if fresh:self.psn.wake()
 def want_icons(self,urls):
  fresh=False
  for url in urls:
   if url and url not in self.icon_wanted and url not in self.icon_failed and not self.icon_file(url):self.icon_wanted.append(url);fresh=True
  if fresh:self.psn.wake()
 def icon_file(self,url):
  return self.icons.get(hashlib.sha1(url.encode()).hexdigest()[:20],'') if url else ''
 def title_of(self,key):
  """A set's line in the player's list, or from the question about a console game."""
  found=next((title for title in self.titles if title['set']==key),None)
  if found:return found
  for value in self.map.values():
   title=title_from(value.get('item'))
   if title and title['set']==key:return title
  return None
 def console_set(self,title_id):
  """A console game's trophies from PSN, for the Games page, or None when PSN has none for it (or PlayBridge has not asked yet)."""
  with self.lock:
   entry=self.map.get(title_id);title=title_from((entry or {}).get('item'))
   if not title:return None
   listed=next((found for found in self.titles if found['set']==title['set']),None)
   title=listed or title;rows=self.set_rows(title['set']);mine=self.mine.get(title['set'])
   return console_set(title,rows['rows'] if rows else [],states_from(mine) if mine and rows else None)
 def view(self):
  """A copy of where things stand, for the Trophies page."""
  with self.lock:
   opened=None
   if self.open:
    key=self.open[0];title=self.title_of(key);rows=self.set_rows(key);mine=self.mine.get(key);theirs=self.friend_sets.get((self.friend,key)) if self.friend else None
    opened=dict(set=key,title=title,rows=merged(rows['rows'],states_from(mine) if mine else {},theirs.get('states') if theirs else ({} if self.friend else None)) if rows else [],
     loading=rows is None or mine is None,theirs=theirs)
   friend=self.friend_titles.get(self.friend) if self.friend else None
   hunt=None
   if self.hunting:
    hunt=[]
    for title in hunt_titles(self.titles):
     rows=self.set_rows(title['set']);mine=self.mine.get(title['set'])
     hunt.append((title,rows['rows'] if rows else None,states_from(mine) if mine and rows else None))
   return dict(summary=self.summary,titles=list(self.titles),listed=self.list_fresh or bool(self.titles),open=opened,friend=self.friend,friend_list=friend,problem=self.problem,changes=self.changes,hunt=hunt)

 # The thread's side.
 def forget(self):
  with self.lock:
   self.summary=None;self.titles=[];self.raw_titles=[];self.map={};self.map_wanted=[];self.definitions={};self.mine={};self.friend_titles={};self.friend_sets={}
   self.icons={};self.icon_wanted=[];self.open=None;self.friend='';self.list_fresh=False;self.list_next=0;self.changes+=1;self.shelf_changes+=1
 def due(self,key,now):return now>=self.next_try.get(key,0)
 def tried(self,key,now):self.next_try[key]=now+AGAIN
 def poll(self):
  now=self.psn.clock()
  if (not self.list_fresh or self.watching and now-self.list_at>=LIST_EVERY) and now>=self.list_next:self.read_list(now)
  if self.open:self.read_set(now,*self.open)
  if self.friend and self.watching:self.read_friend(now)
  if self.hunting and self.watching:self.read_hunt(now)
  self.read_maps(now)
  self.fill_shelf(now)
  self.fetch_icons()
 def read_list(self,now):
  self.list_next=now+AGAIN
  summary=self.psn.call('GET',f'{PATH}/users/me/trophySummary',room=ROOM);items=self.read_titles('me')
  titles=[title for title in map(title_from,items) if title];titles.sort(key=lambda title:-title['updated'])
  with self.lock:
   was={title['set']:title['updated'] for title in self.titles}
   self.summary=summary_from(summary);self.titles=titles;self.raw_titles=items;self.list_fresh=True;self.list_at=now;self.list_next=now+LIST_EVERY;self.changes+=1
   # A game with trophies since the last reading: the player's side of it is read again when it is next needed.
   for title in titles:
    if title['set'] in self.mine and was.get(title['set'],0)<title['updated']:self.mine[title['set']]['stale']=True
  self.save('list.json',dict(summary=summary,titles=items))
 def read_titles(self,account):
  items=[];offset=0
  while offset<MOST_TITLES:
   data=self.psn.call('GET',f'{PATH}/users/{account}/trophyTitles',dict(limit=PAGE,offset=offset),room=ROOM)
   part=[item for item in data.get('trophyTitles') or [] if isinstance(item,dict)];items+=part;offset+=len(part)
   if not part or offset>=whole(data.get('totalItemCount')):break
  return items
 def read_set(self,now,key,service):
  """The open game: its trophies (again only when its version changed), the player's side and the friend's."""
  title=self.title_of(key)
  with self.lock:rows=self.set_rows(key);mine=self.mine.get(key)
  if (rows is None or title and title['version'] and rows['version']!=title['version']) and self.due(('set',key),now):
   self.tried(('set',key),now);self.read_definitions(key,service,title)
  if (mine is None or mine.get('stale')) and self.due(('mine',key),now):self.tried(('mine',key),now);self.read_mine(key,service,title)
  if self.friend and self.due(('theirs',self.friend,key),now):
   with self.lock:theirs=self.friend_sets.get((self.friend,key))
   if theirs is None or now-theirs['at']>=FRIEND_EVERY:self.tried(('theirs',self.friend,key),now);self.read_theirs(now,self.friend,key,service)
 def all_trophies(self,path,service):
  """Every trophy of a set from one of Sony's lists, page after page when Sony splits it."""
  items=[];offset=0
  while True:
   query=dict(npServiceName=service)
   if offset:query['offset']=offset
   data=self.psn.call('GET',path,query,room=ROOM);part=trophy_items(data);items+=part
   following=whole(data.get('nextOffset'))
   if not part or following<=offset or len(items)>=4096:return dict(data,trophies=items)
   offset=following
 def read_definitions(self,key,service,title):
  try:data=self.all_trophies(f'{PATH}/npCommunicationIds/{key}/trophyGroups/all/trophies',service)
  except psn_link.Refused:data={}
  version=title['version'] if title else str(data.get('trophySetVersion') or '')[:16]
  kept=dict(version=version,trophies=trophy_items(data))
  with self.lock:self.definitions[key]=dict(version=version,rows=definitions_from(kept));self.changes+=1;self.shelf_changes+=key in self.shelf_sets()
  self.save(f'sets/{key}.json',kept)
 def read_mine(self,key,service,title):
  try:data=self.all_trophies(f'{PATH}/users/me/npCommunicationIds/{key}/trophyGroups/all/trophies',service)
  except psn_link.Refused:data={}
  with self.lock:self.mine[key]=dict(updated=title['updated'] if title else 0,trophies=trophy_items(data));self.changes+=1;self.shelf_changes+=key in self.shelf_sets();kept=dict(self.mine)
  self.save('mine.json',kept)
 def read_theirs(self,now,account,key,service):
  try:states=states_from(self.all_trophies(f'{PATH}/users/{account}/npCommunicationIds/{key}/trophyGroups/all/trophies',service));why=''
  except psn_link.Refused as refused:states={};why='private' if refused.status==403 else 'none'
  with self.lock:self.friend_sets[(account,key)]=dict(at=now,states=states,why=why);self.changes+=1
 def read_friend(self,now):
  account=self.friend
  with self.lock:known=self.friend_titles.get(account)
  if known is not None and now-known['at']<FRIEND_EVERY or not self.due(('friend',account),now):return
  self.tried(('friend',account),now)
  try:titles=[title for title in map(title_from,self.read_titles(account)) if title];private=False
  except psn_link.Refused as refused:
   if refused.status!=403:raise
   titles=[];private=True
  with self.lock:self.friend_titles[account]=dict(at=now,titles=titles,private=private);self.changes+=1
 def read_hunt(self,now):
  """One game of the hunt not read yet: its trophies, then the player's side (which carries how many players have each)."""
  for title in hunt_titles(self.titles):
   key=title['set']
   with self.lock:rows=self.set_rows(key);mine=self.mine.get(key)
   if (rows is None or title['version'] and rows['version']!=title['version']) and self.due(('set',key),now):self.tried(('set',key),now);self.read_definitions(key,title['service'],title);return
   if (mine is None or mine.get('stale')) and self.due(('mine',key),now):self.tried(('mine',key),now);self.read_mine(key,title['service'],title);return
 def shelf_sets(self):
  return {set_id((value.get('item') or {}).get('npCommunicationId')) for key,value in self.map.items() if key in self.shelf}
 def read_maps(self,now):
  for _ in range(MAPS_AT_ONCE):
   batch=self.map_wanted[:MAP_AT_ONCE]
   if not batch or not self.due(('map',),now):return
   # A question Sony did not answer is asked again only after AGAIN seconds.
   self.tried(('map',),now)
   try:data=self.psn.call('GET',f'{PATH}/users/me/titles/trophyTitles',dict(npTitleIds=','.join(title+'_00' for title in batch)),room=ROOM)
   except psn_link.Refused:data={}
   found={}
   for entry in data.get('titles') or []:
    if not isinstance(entry,dict):continue
    key=str(entry.get('npTitleId') or '')[:9];items=[item for item in entry.get('trophyTitles') or [] if title_from(item)]
    if key in batch and items:found[key]=items[0]
   with self.lock:
    for title in batch:self.map[title]=dict(at=now,item=found.get(title))
    self.map_wanted=self.map_wanted[len(batch):];self.shelf_changes+=bool(found);kept=dict(self.map)
   self.next_try.pop(('map',),None);self.save('map.json',kept)
 def fill_shelf(self,now):
  """The trophies of one console game PSN knows, so the Games page lists them: its set, then the player's side."""
  for key in sorted(self.shelf_sets()-{''}):
   title=self.title_of(key)
   if title is None:continue
   with self.lock:rows=self.set_rows(key);mine=self.mine.get(key)
   if (rows is None or title['version'] and rows['version']!=title['version']) and self.due(('set',key),now):self.tried(('set',key),now);self.read_definitions(key,title['service'],title);return
   if (mine is None or mine.get('stale')) and self.due(('mine',key),now):self.tried(('mine',key),now);self.read_mine(key,title['service'],title);return
 def fetch_icons(self):
  """Games' and trophies' pictures from Sony's image server, kept beside the lists. Not counted against the budget: another server."""
  for _ in range(ICONS_AT_ONCE):
   if not self.icon_wanted:return
   url=self.icon_wanted.pop(0);key=hashlib.sha1(url.encode()).hexdigest()[:20]
   raw,kind=psn_link.get_picture(self.psn.opener,url,ICON_MOST)
   if not raw:self.icon_failed.add(url);continue
   try:(self.folder/'icons').mkdir(parents=True,exist_ok=True);(self.folder/'icons'/(key+kind)).write_bytes(raw)
   except OSError:self.icon_failed.add(url);continue
   with self.lock:self.icons[key]=key+kind;self.changes+=1

def hunt_titles(titles):
 """The games of the hunt: started (a trophy earned), not finished and not hidden, the latest first."""
 return [title for title in titles if sum(title['earned'].values()) and title['progress']<100 and not title['hidden']][:HUNT_GAMES]

def hunt_rows(entries,most=HUNT_LISTED):
 """The trophies not earned yet in the games of the hunt, the one most players have first: [(rate, title, trophy)]. The platinum is left
 out (it comes with the others), and so is a trophy Sony gives no share for."""
 found=[]
 for title,rows,states in entries or []:
  if rows is None or states is None:continue
  for row in rows:
   state=states.get(row['id']) or {}
   if state.get('at') or row['grade']=='platinum' or state.get('rate') is None:continue
   found.append((state['rate'],title,row))
 found.sort(key=lambda item:(-item[0],item[1]['name'].lower(),item[2]['id']))
 return found[:most]

# A trophy that may be lost by playing on: what its own words say. PSN does not mark missable trophies, so this is only read from the
# description, and the page says why it warns.
CUES=((re.compile(r'\bmissable\b',re.I),lambda found:'its description says it can be missed'),
 (re.compile(r'\b(chapter|mission|episode|act|part)\s+([0-9]+|[ivx]+)\b',re.I),lambda found:f'it belongs to {found.group(1).capitalize()} {found.group(2).upper()}'),
 (re.compile(r'\b(?:in a single|in one)\s+(playthrough|run|life|sitting|session|attempt|save)\b',re.I),lambda found:f'it has to be done in one {found.group(1).lower()}'),
 (re.compile(r'\bwithout\s+(dying|being (?:seen|spotted|detected|hit)|taking (?:any )?damage|killing|reloading|saving|failing)\b',re.I),lambda found:f'it has to be done without {found.group(1).lower()}'),
 (re.compile(r'\b(?:on|at)\s+(hard|crushing|hardest|grounded|insane|nightmare|expert|legendary|survivor|extreme|brutal|realistic)\b',re.I),lambda found:f'it needs {found.group(1).capitalize()} difficulty'),
 (re.compile(r'\bbefore\b',re.I),lambda found:'it has to happen before something else in the game'))
def watch_out(name,detail):
 """Why a trophy may be missed, from its name and description: 'it belongs to Chapter 4', or ''."""
 text=f'{name or ""}. {detail or ""}'
 for pattern,why in CUES:
  found=pattern.search(text)
  if found:return why(found)
 return ''

def hunt_view(entries,icon=lambda url:''):
 """Next up, in words: the rows, and a line on how many games are still being read."""
 if entries is None:return [],''
 rows=[]
 for rate,title,row in hunt_rows(entries):
  secret=row['hidden']
  rows.append(dict(set=title['set'],id=row['id'],game=title['name'] or title['set'],grade=row['grade'],name='Hidden trophy' if secret else row['name'] or f"Trophy {row['id']}",
   detail='Keep playing to find out what it is.' if secret else row['detail'],icon='' if secret else icon(row['icon']),gameIcon=icon(title['icon']),
   rare=f'{rate:.1f}% of players have it',watch='' if secret else watch_out(row['name'],row['detail'])))
 waiting=sum(1 for _,found,states in entries if found is None or states is None)
 if not entries:line='Start a game with trophies, and the trophies you have left that most players earned show here.'
 elif waiting:line=f"Reading {waiting} of your {len(entries)} games in progress…" if len(entries)>1 else 'Reading your game in progress…'
 elif not rows:line='No trophies left to show in your games in progress.'
 else:line=f"The trophies most players have, from your {len(entries)} games in progress." if len(entries)>1 else 'The trophies most players have, from your game in progress.'
 if any(row['watch'] for row in rows) and not waiting:line+=' Watch out marks a trophy its own words tie to a point in the game: check a guide before you move on.'
 return rows,line

# The Trophies page, in words: plain functions of TrophyBook.view(), so they are tested without a window.
def day(seconds):
 if not seconds:return ''
 if seconds<=1:return 'Earned'
 try:return datetime.fromtimestamp(seconds).strftime('%d %b %Y').lstrip('0')
 except (OSError,OverflowError,ValueError):return ''
def platform_of(title):
 platforms=title['platforms'];return 'PS5' if 'PS5' in platforms else 'PS4' if 'PS4' in platforms else (platforms[0] if platforms else '')
def wanted(title,chosen):
 if chosen=='PS5':return 'PS5' in title['platforms']
 if chosen=='PS4':return 'PS5' not in title['platforms']
 if chosen=='Platinum':return title['earned']['platinum']>0
 if chosen=='Unfinished':return title['progress']<100
 return True
def grade_counts(earned,defined=None):
 return [dict(grade=grade,count=earned[grade],of=defined[grade] if defined else -1) for grade in GRADES if not defined or defined[grade]]
def title_row(title,icon,theirs=None):
 done=sum(title['earned'].values());total=sum(title['defined'].values())
 return dict(set=title['set'],name=title['name'] or title['set'],initial=(title['name'] or '?')[:1].upper(),icon=icon(title['icon']),platform=platform_of(title),share=title['progress']/100,
  percent=f"{title['progress']}%",line=f'{done} of {total} trophies',counts=grade_counts(title['earned'],title['defined']),platinum=title['earned']['platinum']>0,
  when=('Last trophy '+day(title['updated'])) if done and title['updated'] else 'No trophies yet',
  theirs=theirs['progress']/100 if theirs else -1,theirsPercent=f"{theirs['progress']}%" if theirs else '')

def page(state,view,friends,chosen='All',icon=lambda url:'',me=None):
 """What the Trophies page shows. state is the PSN sign-in's (on, out, signing, expired); friends is [(id, name)]."""
 names={key:name for key,name in friends};friend=view.get('friend') or '';friend_name=names.get(friend,'your friend') if friend else ''
 summary=view.get('summary');titles=view.get('titles') or [];friend_list=view.get('friend_list')
 theirs={}
 if friend and friend_list and not friend_list.get('private'):theirs={title['set']:title for title in friend_list['titles']}
 comparing=bool(friend and friend_list and not friend_list.get('private'))
 shown=[title for title in titles if wanted(title,chosen) and (not comparing or title['set'] in theirs)]
 rows=[title_row(title,icon,theirs.get(title['set'])) for title in shown]
 if friend and friend_list is None:friend_line=f'Reading {friend_name}\'s trophies…'
 elif friend and friend_list.get('private'):friend_line=f'{friend_name} keeps their trophies private.'
 elif comparing:friend_line=f"{len(in_common(titles,friend_list['titles']))} games in common with {friend_name}."
 else:friend_line=''
 empty=''
 if not view.get('listed'):empty='Reading your trophies from PSN…'
 elif not titles:empty='No trophies on your PSN account yet.'
 elif not rows:empty=f'No games in common with {friend_name} here.' if comparing else 'No games on this list.'
 opened=None
 hunt=hunt_view(view.get('hunt'),icon) if chosen=='Next up' else ([],'')
 if view.get('open'):
  found=view['open'];title=found['title'];their=found.get('theirs');why=(their or {}).get('why','')
  trophy_rows=[]
  for row in found['rows']:
   secret=row['hidden'] and not row['earned']
   trophy_rows.append(dict(id=row['id'],grade=row['grade'],name='Hidden trophy' if secret else row['name'] or f"Trophy {row['id']}",detail='Keep playing to find out what it is.' if secret else row['detail'],
    icon=icon(row['icon']) if not secret else '',earned=bool(row['earned']),when=day(row['earned']),rare=f"{row['rate']:.1f}% of players" if row['rate'] is not None else '',
    theirs=(day(row['theirs']) or 'Not yet') if row['theirs'] is not None and friend and their is not None and not why else '',theirsEarned=bool(row['theirs'])))
  have={row['id']:row['earned'] for row in found['rows'] if row['earned']}
  tally=trophy_files.tally(found['rows'],have) if found['rows'] else (title_tally(title) if title else None)
  line=f"{tally['earned']} of {tally['total']} earned  ·  {tally['progress']}%"+('  ·  Platinum earned' if tally['platinum'] else '') if tally else ''
  theirs_line=''
  if friend:
   if their is None:theirs_line=f'Reading {friend_name}\'s trophies…'
   elif why=='private':theirs_line=f'{friend_name} keeps their trophies private.'
   elif why=='none':theirs_line=f'{friend_name} has no trophies in this game.'
   else:theirs_line=f"{friend_name}: {sum(1 for row in found['rows'] if row['theirs'])} of {len(found['rows'])} earned"
  opened=dict(set=found['set'],name=(title or {}).get('name') or found['set'],icon=icon((title or {}).get('icon','')),platform=platform_of(title) if title else '',line=line,
   share=(tally['progress']/100) if tally else 0,platinum=bool(tally and tally['platinum']),rows=trophy_rows,loading=found['loading'] and not trophy_rows,theirsLine=theirs_line,
   friendName=friend_name if friend and their is not None and not why else '')
 level=dict(level=summary['level'],tier=summary['tier'],share=summary['progress']/100,counts=grade_counts(summary['earned']),total=sum(summary['earned'].values())) if summary else None
 return dict(state=state,problem=view.get('problem',''),me=me or {},level=level,filters=list(FILTERS),filter=chosen,friends=['Nobody']+[name for _,name in friends if name],
  friendName=friend_name,friendLine=friend_line,comparing=comparing,titles=rows if chosen!='Next up' else [],count=len(rows),empty=empty if chosen!='Next up' or not view.get('listed') else '',open=opened,
  hunting=chosen=='Next up',hunt=hunt[0],huntLine=hunt[1])
