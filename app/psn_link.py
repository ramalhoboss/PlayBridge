"""PlayStation Network on the PC: the player's friends, who is online and what they play, alerts when a friend comes online or starts a
game (a watched name such as XPS5 among them), and the PSN messages, read and written from PlayBridge.

Signing in. Sony has no sign-in for programs like this one, so PlayBridge never sees the player's password. The player signs in on
playstation.com in their own browser, then opens NPSSO_PAGE, which shows a 64-character code (the NPSSO). PlayBridge trades it once for
tokens, as the PlayStation App does, keeps only the long-lived refresh token, sealed for this Windows user (DPAPI, as the stream key is),
and forgets the code. The refresh token lasts about two months; after that the player pastes a new code.

This is not an official interface: Sony documents none of it and can change or close it at any time. The wire facts come from the
documentation of the psn-api and PSNAWP projects; the code is PlayBridge's own. PlayBridge asks Sony at most MOST times in WINDOW seconds,
under the 300 in 15 minutes Sony is known to allow.

Everything that talks to Sony runs on one thread of its own. The window hands it jobs (sign in, open a conversation, send a message)
and reads a copy of the state (view) and the alerts that fired (take_alerts), so a slow or refused request never holds up the window."""
import collections,hashlib,html,http.client,io,json,queue,re,shutil,threading,time,urllib.error,urllib.parse,urllib.request
from datetime import datetime
from pathlib import Path

AUTH='https://ca.account.sony.com/api/authz/v3/oauth'
NPSSO_PAGE='https://ca.account.sony.com/api/v1/ssocookie'
SIGN_IN_PAGE='https://www.playstation.com/'
API='https://m.np.playstation.com/api'
# Who is signed in, as a number: the profile service takes only account numbers, never "me" (Sony answers 400 to that).
ACCOUNT='https://dms.api.playstation.com/api/v1/devices/accounts/me'
CLIENT='09515159-7237-4370-9b40-3806e67c0891'
REDIRECT='com.scee.psxandroid.scecompcall://redirect'
SCOPE='psn:mobile.v2.core psn:clientapp'
# The PlayStation App's own client id and secret, as the documentation gives them.
BASIC='Basic MDk1MTUxNTktNzIzNy00MzcwLTliNDAtMzgwNmU2N2MwODkxOnVjUGprYTV0bnRCMktxc1A='
AGENT='PlayBridge'
PLATFORMS='PS4,PS5,MOBILE_APP,PSPC'
GROUP_FIELDS='groupName,groupIcon,members,mainThread,joinedTimestamp,modifiedTimestamp,isFavorite,existsNewArrival,notificationSetting'
WINDOW=900;MOST=270
# How often each reading is made again, in seconds: with the Friends page open, and without it.
FRIENDS_EVERY=600;PRESENCE_EVERY=(30,60);GROUPS_EVERY=(30,90);THREAD_EVERY=8;PROFILES_EVERY=10
# A friend's name and picture are asked for again after a week; at most this many in one go, and only while the budget has room.
PROFILE_DAYS=7;PROFILES_AT_ONCE=8;PROFILE_ROOM=80
PRESENCE_BATCH=50;MESSAGES=40;LONGEST=2000
# Friends, as the PlayStation App makes them (its userProfile client, 26.11): POST FRIEND+number sends a friend request, PUT accepts one,
# DELETE declines one, takes back one the player sent, or ends a friendship. The requests either way: FRIEND+receivedRequests, +sentRequests.
FRIEND='/userProfile/v1/internal/users/me/friends/'
# A player found by their exact online ID, on Sony's older profile service (as psn-api and PSNAWP find one).
FIND='https://us-prof.np.community.playstation.net/userProfile/v1/users/{}/profile2'
FIND_FIELDS='accountId,onlineId,currentOnlineId,avatarUrls,friendRelation'
# An online ID: 3 to 16 letters, numbers, hyphens and underscores, starting with a letter (PSN's own rule).
ONLINE_ID=re.compile(r'[A-Za-z][A-Za-z0-9_-]{2,15}')
FRIEND_ACTIONS=('add','accept','decline','cancel','remove')
# How often the friend requests are read again: with the Friends page open, and without it.
REQUESTS_EVERY=(60,300)
# A message's picture, sticker, GIF, voice or video sits in its messageDetail under one of these (the PlayStation App's own names). Sony keeps
# the picture, voice or video of a conversation as a resource of the group, fetched with the sign-in at RESOURCE; a sticker brings its address.
DETAILS=(('imageMessageDetail','picture'),('animatedGifMessageDetail','gif'),('stickerMessageDetail','sticker'),('voiceMessageDetail','voice'),('videoMessageDetail','video'))
RESOURCE='/gamingLoungeGroups/v1/groups/{}/resources/{}'
MEDIA_WORDS=dict(picture='Sent a picture.',gif='Sent a GIF.',sticker='Sent a sticker.',voice='Sent a voice message.',video='Sent a video.')
# The largest picture fetched as a conversation opens, and the largest voice message or video fetched when the player asks for it.
CHAT_PICTURE_MOST=12<<20;CHAT_MEDIA_MOST=96<<20;PICTURES_AT_ONCE=6
# A picture sent from PlayBridge goes up to the group as a resource (its bytes, with their picture type, as the PlayStation App sends
# them); then a message of the App's TextWithImage kind names it, with words under it when the player wrote some. It is made the way
# the App makes it: the long side at the first of SEND_SIDES pixels whose file comes out under SEND_MOST bytes, at full quality (the
# pictures friends send arrive 768 pixels long; a larger one was turned away at Sony's door). A file larger than PICK_MOST is not read.
RESOURCES='/gamingLoungeGroups/v1/groups/{}/resources'
SEND='/gamingLoungeGroups/v1/groups/{}/threads/{}/messages'
PICTURE_MESSAGE=3
SEND_SIDES=(768,640,512,256,128);SEND_MOST=1<<20;PICK_MOST=64<<20
# The rest of a conversation, as the PlayStation App does it (its gamingLoungeGroups client, 26.11). The player can delete a message they
# sent, for everyone, in the DELETE_WITHIN seconds after sending it (the App's DELETE_MESSAGE_LIMIT_TIME); nobody can delete another's on
# PSN, so PlayBridge only takes those off this PC (the conversation's hidden list in folder).
DELETE_MESSAGE='/gamingLoungeGroups/v2/members/me/groups/{}/threads/{}/messages/{}'
DELETE_MEDIA='/gamingLoungeGroups/v1/members/me/groups/{}/threads/{}/messages/{}'
DELETE_WITHIN=600;HIDDEN_MOST=500
# Reactions: the kinds Sony offers come from REACTION_KINDS for the App's reaction version (mobile-v1 with its expanded emoji, else
# unicode). The open conversation's are asked for by message every REACTIONS_EVERY seconds; a player has one reaction on a message at most.
REACTION_KINDS='/gamingLoungeGroups/v1/reactions/{}/definitions'
REACTIONS='/gamingLoungeGroups/v1/members/me/groups/{}/threads/{}/reactions'
REACT='/gamingLoungeGroups/v1/members/me/groups/{}/threads/{}/messages/{}/reactions'
REACTION_VERSIONS=('mobile-v1','unicode');REACTIONS_EVERY=30;REACTION_PICTURES=24
# Read on PSN as the player reads it (the PlayStation App and the PS5 stop calling it new), and "typing", told at most every TYPING_EVERY s.
THREAD='/gamingLoungeGroups/v1/members/me/groups/{}/threads/{}'
NEW_ARRIVAL='/gamingLoungeGroups/v1/members/me/groups/{}/newArrival'
TYPING='/gamingLoungeGroups/v1/groups/{}/typing';TYPING_EVERY=4
# A conversation of the player's: a favourite (the App sends "true" or "false" as words), muted, renamed, people added or taken out, left.
# A group holds at most MOST_MEMBERS people; adding someone to a conversation of two makes a new group (Sony answers with its groupId).
MY_GROUP='/gamingLoungeGroups/v1/members/me/groups/{}'
MUTE='/gamingLoungeGroups/v1/members/me/groups/{}/notificationSetting'
GROUPS='/gamingLoungeGroups/v1/groups'
GROUP='/gamingLoungeGroups/v1/groups/{}'
INVITE='/gamingLoungeGroups/v1/groups/{}/invitees'
MEMBER='/gamingLoungeGroups/v1/groups/{}/members/{}'
MOST_MEMBERS=100;NAME_LONGEST=64
GROUP_CHANGES=('favourite','mute','rename','invite','remove','leave')
# Seconds of quiet after Sony says too many, when it does not say how long.
QUIET=300;UNREACHABLE=60

class Problem(Exception):"""Something to tell the player, in words they can act on."""
class SignedOut(Problem):pass
class Busy(Problem):pass
def asked_for(path):
 """What a request asks for, in the words an error message uses."""
 for part,words in (('/devices/accounts/me','your account number'),('Requests','your friend requests'),('/profile2','a player'),('/resources','the picture'),('/basicPresences','who is online'),('/friends','your friends list'),
  ('/profiles','a profile'),('/reactions','reactions'),('/typing','typing'),('/invitees','the people to add'),('/notificationSetting','alerts for the conversation'),('/messages','messages'),('/gamingLoungeGroups','your chats'),('/trophy/','trophies')):
  if part in path:return words
 return 'something'
def sony_words(raw):
 """Sony's own words in an answer: the error's message and code when it sent one, else the start of the text (a web page's visible
 words, as Sony's front door sends when it turns a request away). '' when there are none."""
 try:data=json.loads(raw or b'{}')
 except ValueError:data=None
 if isinstance(data,dict):
  error=data.get('error') if isinstance(data.get('error'),dict) else data
  message=str(error.get('message') or error.get('error_description') or '').strip();code=error.get('code')
  if message or code:return (message+(f' (code {code})' if code else '')).strip()[:240]
  return ''
 text=(raw or b'').decode('utf-8','replace')
 if re.search(r'<\s*(html|body|h1|p|title)\b',text,re.I):
  text=re.sub(r'(?is)<(head|script|style)\b.*?</\1\s*>',' ',text);text=html.unescape(re.sub(r'<[^>]*>',' ',text))
 text=' '.join(text.split())
 return text[:240] if text.isprintable() else ''
class Answered(Problem):
 """Sony answered a request with an error: status, and Sony's own words about it (sony_words)."""
 def __init__(self,text,status,words=''):super().__init__(text);self.status=status;self.words=words
class Refused(Answered):
 """Sony said no to one request (403: not allowed, such as a friend's private trophies; 404: nothing there). status says which."""

def npsso_from(text):
 """The code from what the player pasted: the 64 characters alone, or the whole of Sony's page ({"npsso":"..."}). None when it holds no code."""
 text=(text or '').strip()
 found=re.search(r'"npsso"\s*:\s*"([A-Za-z0-9]{64})"',text) or re.fullmatch(r'([A-Za-z0-9]{64})',text)
 return found.group(1) if found else None

class _Stay(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):return None
_OPENER=urllib.request.build_opener(_Stay)
def api_path(template,*parts):
 """A PSN address with ids put in as the App puts them, encoded: a message's id is like 1#425961448584099, and an address unencoded
 ended at its '#'."""
 return template.format(*(urllib.parse.quote(str(part),safe='') for part in parts))

def default_opener(method,url,headers,body,timeout=20):
 """One HTTPS request that never follows a redirect. Returns the status, the headers with lower-case names, and the body."""
 request=urllib.request.Request(url,data=body,headers=headers,method=method)
 try:
  with _OPENER.open(request,timeout=timeout) as answer:return answer.status,{k.lower():v for k,v in answer.headers.items()},answer.read()
 except urllib.error.HTTPError as error:
  try:raw=error.read()
  except OSError:raw=b''
  return error.code,{k.lower():v for k,v in (error.headers or {}).items()},raw

class Budget:
 """Requests made in the last WINDOW seconds, so that PlayBridge stays under what Sony allows."""
 def __init__(self,most=MOST,window=WINDOW,clock=time.monotonic):self.most=most;self.window=window;self.clock=clock;self.times=collections.deque()
 def left(self):
  now=self.clock()
  while self.times and now-self.times[0]>=self.window:self.times.popleft()
  return self.most-len(self.times)
 def spend(self):self.times.append(self.clock())

def when(value):
 """A PSN time (milliseconds as text, or an ISO date) as seconds since 1970, or 0."""
 if isinstance(value,(int,float)):return value/1000 if value>1e11 else float(value)
 if not isinstance(value,str) or not value:return 0
 if value.isdigit():return int(value)/1000 if len(value)>11 else float(value)
 try:return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
 except ValueError:return 0

def picture_url(avatars):
 """The sharpest of a profile's small pictures that is not huge."""
 sizes={item.get('size'):item.get('url') for item in avatars or [] if isinstance(item,dict) and item.get('url')}
 return next((sizes[size] for size in ('l','m','xl','s') if sizes.get(size)),'')

PICTURE_MOST=1<<20
def picture_kind(raw):return '.png' if raw[:8]==b'\x89PNG\r\n\x1a\n' else '.jpg' if raw[:3]==b'\xff\xd8\xff' else ''
def picture_address(url):
 """A picture's address as PlayBridge asks for it: https, also when Sony's answer gives it as http (its image servers answer both)."""
 if not isinstance(url,str):return ''
 if url.startswith('https://'):return url
 return 'https://'+url[7:] if url.startswith('http://') else ''
def chat_picture(raw):
 """A picture from a conversation as Qt shows it: (bytes, file ending). PNG, JPEG and GIF as they came; any other picture Pillow reads
 (a WebP sticker, say) as PNG. (b'', '') when it is no picture."""
 if not raw:return b'',''
 kind=picture_kind(raw)
 if kind:return raw,kind
 if raw[:6] in (b'GIF87a',b'GIF89a'):return raw,'.gif'
 try:
  from PIL import Image
  with Image.open(io.BytesIO(raw)) as image:image.load();out=io.BytesIO();image.save(out,'PNG')
 except Exception:return b'',''
 return out.getvalue(),'.png'
def fetch_bytes(opener,url,most):
 """Whatever an https address holds (no sign-in sent), following at most three moves: bytes, or b'' when nothing usable came."""
 address=picture_address(url)
 for _ in range(4):
  if not address:return b''
  try:status,headers,raw=opener('GET',address,{'User-Agent':AGENT,'Accept':'*/*'},None)
  except (OSError,ValueError):return b''
  if status in (301,302,303,307,308) and headers.get('location'):address=picture_address(urllib.parse.urljoin(address,headers['location']));continue
  return raw if status==200 and raw and len(raw)<=most else b''
 return b''
def picture_to_send(raw):
 """A picture as it goes to PSN: (bytes, picture type). Turned the right way up, made smaller to the first of SEND_SIDES that comes
 out under SEND_MOST bytes (a smaller picture stays its size), and written again without what the file says about itself (where a phone
 took it stays home): JPEG at full quality, or PNG when it has see-through parts. Problem, in words, for a file that is no picture, or
 one that moves (the PlayStation App sends those another way)."""
 from PIL import Image,ImageOps
 try:
  with Image.open(io.BytesIO(raw)) as image:
   if getattr(image,'n_frames',1)>1:raise Problem('PlayBridge sends still pictures only. Send moving GIFs from the PlayStation App.')
   image.load();image=ImageOps.exif_transpose(image)
   clear=image.mode in ('RGBA','LA','PA') or image.mode=='P' and 'transparency' in image.info
   image=image.convert('RGBA' if clear else 'RGB')
  for side in SEND_SIDES:
   shown=image.copy();shown.thumbnail((side,side),Image.LANCZOS);out=io.BytesIO()
   if clear:shown.save(out,'PNG',optimize=True)
   else:shown.save(out,'JPEG',quality=100)
   if out.tell()<SEND_MOST:return out.getvalue(),'image/png' if clear else 'image/jpeg'
 except Problem:raise
 except Exception:raise Problem('PlayBridge cannot read that file as a picture.')
 raise Problem('That picture is too large to send.')
def resource_of(raw,headers):
 """The name PSN gave a picture that went up: from the answer's resourceId (or the whole answer when it is only that name), else the
 last part of the address it says it keeps it at. '' when it said none."""
 try:data=json.loads(raw) if raw else None
 except ValueError:data=None
 if isinstance(data,dict):
  inner=data.get('resource') if isinstance(data.get('resource'),dict) else {}
  found=data.get('resourceId') or inner.get('resourceId') or data.get('id')
  if isinstance(found,str) and found.strip():return found.strip()
 if isinstance(data,str) and data.strip():return data.strip()
 place=(headers or {}).get('location') or ''
 return place.rstrip('/').rsplit('/',1)[-1] if '/resources/' in place else ''
def emoji_of(value):
 """An emoji as Sony writes it, as characters: the characters themselves, or their code points in hex ("1F44D", "U+1F44D", "1F9D1 1F3FB").
 '' for anything else."""
 if not isinstance(value,str) or not value.strip():return ''
 text=value.strip()
 if re.fullmatch(r'(?:(?:U\+)?[0-9A-Fa-f]{4,6}[\s,_-]*)+',text):
  try:return ''.join(chr(int(code,16)) for code in re.findall(r'[0-9A-Fa-f]{4,6}',text))
  except (ValueError,OverflowError):return ''
 return '' if text.isascii() else text
def reaction_kinds(data):
 """The reactions Sony offers, in its order: dict(id, emoji, url). From the definitions answer: an object keyed by reaction id, each
 with its unicode and url (as the PlayStation App reads it), or a list of them, or either under one key."""
 if isinstance(data,dict):
  inner=next((data[key] for key in ('reactionDefinitions','definitions','reactions') if isinstance(data.get(key),(dict,list))),None)
  if inner is not None:data=inner
 items=list(data.items()) if isinstance(data,dict) else [('',item) for item in data] if isinstance(data,list) else []
 kinds=[];seen=set()
 for key,item in items:
  if not isinstance(item,dict):continue
  rid=str(item.get('reactionId') or item.get('id') or key).strip();emoji=emoji_of(item.get('unicode'))
  url=item.get('url') if isinstance(item.get('url'),str) and item['url'].startswith(('https://','http://')) else ''
  if rid and rid not in seen and (emoji or url):seen.add(rid);kinds.append(dict(id=rid,emoji=emoji,url=url))
 return kinds
def reaction_lists(data,me_id):
 """The reactions on each message, the most given first: {message uid: [dict(id, emoji, url, count, mine)]}. data is Sony's answer:
 a list of {messageUid, reactions: [{id, accountIds, unicode, url, timestamp}]}, or that list under one key."""
 if isinstance(data,dict):data=next((value for value in data.values() if isinstance(value,list)),[])
 found={}
 for item in data if isinstance(data,list) else []:
  if not isinstance(item,dict) or not item.get('messageUid'):continue
  rows=[]
  for reaction in item.get('reactions') or []:
   if not isinstance(reaction,dict):continue
   people=[str(key.get('accountId') if isinstance(key,dict) else key) for key in reaction.get('accountIds') or []]
   rid=str(reaction.get('id') or reaction.get('reactionId') or '')
   url=reaction.get('url') if isinstance(reaction.get('url'),str) and reaction['url'].startswith(('https://','http://')) else ''
   if rid and people:rows.append(dict(id=rid,emoji=emoji_of(reaction.get('unicode')),url=url,count=len(people),mine=bool(me_id) and str(me_id) in people,at=when(reaction.get('timestamp'))))
  rows.sort(key=lambda row:(-row['count'],row['at']))
  found[str(item['messageUid'])]=rows
 return found
def message_media(message):
 """A message's picture, GIF, sticker, voice message or video: kind, the group resource that holds it, its address when it brings one,
 and how long it plays (seconds). None for words."""
 detail=message.get('messageDetail') if isinstance(message.get('messageDetail'),dict) else {}
 for key,kind in DETAILS:
  part=detail.get(key) if isinstance(detail.get(key),dict) else message.get(key)
  if not isinstance(part,dict):continue
  url=next((part[name] for name in ('imageUrl','url','gifUrl','previewUrl','thumbnailUrl') if isinstance(part.get(name),str) and part[name].startswith(('https://','http://'))),'')
  played=part.get('playbackTime') or part.get('duration') or 0
  seconds=float(played)/1000 if isinstance(played,(int,float)) and played>600 else float(played) if isinstance(played,(int,float)) else 0
  return dict(kind=kind,resource=str(part.get('resourceId') or ''),url=url,seconds=seconds)
 return None
def reaction_key(url):
 """The name a reaction's picture is kept under, beside the conversations' pictures."""
 return 'reaction-'+hashlib.sha1(str(url).encode()).hexdigest()[:20]
def media_key(group_id,media):
 """The name a conversation's picture or recording is kept under: the same one for the same thing, safe in a file name."""
 return hashlib.sha1(f'{group_id}|{media.get("resource") or media.get("url")}'.encode()).hexdigest()[:24]
def get_picture(opener,url,most=PICTURE_MOST):
 """A PNG or JPEG from Sony's image servers: (bytes, file ending), or (b'', '') when none came. https first, then the address as Sony
 gave it when that was http and https brought no picture; at most three moves to another address on the way."""
 first=picture_address(url)
 if not first:return b'',''
 for start in [first]+([url] if url.startswith('http://') else []):
  address=start
  for _ in range(4):
   try:status,headers,raw=opener('GET',address,{'User-Agent':AGENT,'Accept':'image/png,image/jpeg'},None)
   except (OSError,ValueError):break
   if status in (301,302,303,307,308) and headers.get('location'):
    address=urllib.parse.urljoin(address,headers['location'])
    if address.startswith(('https://','http://')):continue
    break
   kind=picture_kind(raw or b'')
   if status==200 and kind and len(raw)<=most:return raw,kind
   break
 return b'',''

def message_text(message):
 media=message_media(message)
 if media:return MEDIA_WORDS[media['kind']]
 body=message.get('body')
 if isinstance(body,str) and body.strip():return body
 return 'Sent something PlayBridge cannot show yet. It shows in the PlayStation App.'

def watched_words(text):return [word.strip().lower() for word in re.split(r'[,;\n]',text or '') if word.strip()]

def presence_alerts(before,after,names,wants,favourites=()):
 """What changed between two presence readings: a friend came online, started a game, or started one whose name holds a watched word.
 before is None for the first reading, which only sets where things stand. Returns (kind, title, text) for each."""
 if before is None:return []
 words=watched_words(wants.get('watch',''));fired=[];favourites=set(favourites)
 for key,now in after.items():
  was=before.get(key)
  if was is None or not now.get('online'):continue
  if wants.get('favourites_only') and key not in favourites:continue
  name=names.get(key) or 'A friend';game=now.get('game') or '';where=now.get('platform') or 'PSN'
  came=not was.get('online');started=bool(game) and game!=(was.get('game') or '')
  watched=started and any(word in game.lower() for word in words)
  if watched:fired.append(('watch',f'{name} is in {game}',f'On {where}. You asked to be told about {game}.'))
  elif came and wants.get('online',True):fired.append(('online',f'{name} is online',f'Playing {game} on {where}.' if game else f'On {where}.'))
  elif started and wants.get('games',False):fired.append(('game',f'{name} is playing {game}',f'On {where}.'))
 return fired

class Psn:
 """The player's PSN account, friends and messages. folder keeps the friends' names and pictures; token is the saved refresh token
 and the time it ends ((None, 0) when signed out); save_token(token, until) keeps a new one, sealed by the caller."""
 def __init__(self,folder,token=(None,0),save_token=None,opener=None,clock=time.time):
  self.folder=Path(folder);self.opener=opener or default_opener;self.clock=clock;self.save_token=save_token or (lambda token,until:None)
  self.refresh,self.refresh_until=token if token and token[0] else (None,0);self.access=None;self.access_until=0
  self.budget=Budget(clock=clock);self.lock=threading.Lock();self.jobs=queue.Queue();self.stopping=threading.Event();self.thread=None
  self.alerts=queue.Queue();self.wants=dict(online=True,games=False,messages=True,watch='XPS5',favourites_only=False);self.favourites=set()
  self.state='on' if self.refresh else 'out';self.problem='';self.me={};self.me_id='';self.presence_me=None;self.friend_ids=[];self.friends={};self.profiles=self.load_profiles()
  self.groups=[];self.thread_id=None;self.messages=[];self.sending=False;self.focused=False;self.updated=0;self.friends_at=0;self.quiet_until=0
  self.due=dict(friends=0,presence=0,groups=0,thread=0,profiles=0,requests=0);self.last_presence=None;self.last_groups=None;self.seen=set()
  # Friend requests: the account numbers that asked the player (received) and that the player asked (sent). finding is the last search
  # by online ID; asking holds the numbers an answer is on its way for; friend_line is what the last change came to, in words.
  self.received=[];self.sent=[];self.last_received=None;self.finding={};self.asking=set();self.friend_line={}
  # The conversations' pictures and recordings kept in folder/chat, by media_key: the file's name, or '' when Sony sent none. fetching
  # is the recording on its way; on_media(kind, path, message id) gets a voice message or video once it is here (the window plays or opens it).
  self.media={};self.fetching='';self.on_media=lambda kind,path,message_id:None;self.requests_problem=''
  # What came of the last picture sent (words and their tone), shown above the box to write in.
  self.send_line={}
  # The rest of the conversation: the reactions on the open one's messages (by message uid) and the kinds Sony offers (reaction_version
  # names them, kinds_asked once a session); the messages taken off this PC only (by conversation, kept in folder); the last message
  # told read on PSN (by conversation); changing, the message or 'group' a change is on its way for; chat_line, what came of the last one.
  self.reactions={};self.reaction_kinds=[];self.reaction_version='';self.kinds_asked=False;self.hidden=self.load_hidden()
  self.told_read={};self.typed_at=0;self.changing='';self.chat_line={};self.due['reactions']=0
  # Readers that share this thread, the sign-in and the budget (the trophies): each has poll() and forget(), called on this thread.
  self.helpers=[]
 # The window's side.
 def start(self):
  if self.thread is None or not self.thread.is_alive():self.stopping.clear();self.thread=threading.Thread(target=self.run,name='PlayBridge PSN',daemon=True);self.thread.start()
 def stop(self):
  self.stopping.set();self.jobs.put(None)
  if self.thread is not None:self.thread.join(timeout=1)
 def sign_in(self,text):
  """Takes what the player pasted. Returns what is wrong with it, or '' when it was handed to the thread."""
  code=npsso_from(text)
  if code is None:return 'That is not the code. Copy the 64 letters and numbers after "npsso" on Sony\'s page.'
  with self.lock:self.state='signing';self.problem=''
  self.jobs.put(('sign_in',code));return ''
 def sign_out(self):self.jobs.put(('sign_out',))
 def open_chat(self,group_id):self.jobs.put(('open',group_id))
 def close_chat(self):self.jobs.put(('close',))
 def chat_with(self,account_id):self.jobs.put(('chat_with',account_id))
 def send(self,group_id,text):
  text=(text or '').strip()[:LONGEST]
  if not text:return False
  with self.lock:self.sending=True
  self.jobs.put(('send',group_id,text));return True
 def send_picture(self,group_id,path,caption='',passing=False):
  """Sends the picture in a file to a conversation, with the player's words under it when there are some. A passing file (one PlayBridge
  made, from a picture pasted in) is deleted once it went or failed."""
  if self.sending:return False
  with self.lock:self.sending=True;self.send_line={}
  self.jobs.put(('picture',group_id,str(path),(caption or '').strip()[:LONGEST],bool(passing)));return True
 def delete_message(self,group_id,message_id):
  """Deletes a message the player sent, for everyone in the conversation (PSN allows it for DELETE_WITHIN seconds after sending)."""
  if self.changing or not message_id:return False
  with self.lock:self.changing=str(message_id);self.chat_line={}
  self.jobs.put(('delete',str(group_id),str(message_id)));return True
 def hide_message(self,group_id,message_id):
  """Takes a message off this PC only: it stays on PSN for everyone. Its kept picture or recording goes with it."""
  gid=str(group_id);uid=str(message_id)
  if not uid:return
  with self.lock:
   kept=self.hidden.setdefault(gid,[])
   if uid not in kept:kept.append(uid);del kept[:-HIDDEN_MOST]
   gone=[m for m in self.messages if m.get('id')==uid];self.messages=[m for m in self.messages if m.get('id')!=uid];self.reactions.pop(uid,None)
   self.chat_line=dict(text='Removed from this PC. Everyone in the conversation still has it.',tone='news',at=self.clock())
  self.save_hidden()
  for message in gone:self.drop_media(message)
 def react(self,group_id,message_id,reaction_id):
  """Gives a message a reaction, or takes the player's back when it is the one they gave (one reaction each, as on PSN)."""
  if self.changing or not message_id or not reaction_id:return False
  with self.lock:self.changing=str(message_id);self.chat_line={}
  self.jobs.put(('react',str(group_id),str(message_id),str(reaction_id)));return True
 def note(self,text,tone='news'):
  """Words about the open conversation from the window (a message copied, a picture saved), shown where a change's result shows."""
  with self.lock:self.chat_line=dict(text=text,tone=tone,at=self.clock()) if text else {}
 def typing(self,group_id):
  """Tells the conversation the player is writing, at most every TYPING_EVERY seconds."""
  now=self.clock()
  if not group_id or now-self.typed_at<TYPING_EVERY:return
  self.typed_at=now;self.jobs.put(('typing',str(group_id)))
 def change_group(self,kind,group_id,value=None):
  """favourite or mute (value True or False), rename (the new name), invite (account numbers), remove (one account number) or leave."""
  if kind not in GROUP_CHANGES or self.changing or not group_id:return False
  with self.lock:self.changing='group';self.chat_line={}
  self.jobs.put(('group',kind,str(group_id),value));return True
 def new_group(self,account_ids,name=''):
  """A new group with these friends (at least two), named when a name is given; it opens once PSN made it."""
  ids=list(dict.fromkeys(str(key) for key in account_ids or [] if str(key).isdigit()))[:MOST_MEMBERS-1]
  if len(ids)<2 or self.changing:return False
  with self.lock:self.changing='group';self.chat_line={}
  self.jobs.put(('new_group',ids,' '.join(str(name or '').split())[:NAME_LONGEST]));return True
 def refresh_now(self):self.jobs.put(('refresh',))
 def find(self,text):
  """Looks for a player by their exact online ID; the answer lands in finding."""
  name=' '.join(str(text or '').split())
  if not ONLINE_ID.fullmatch(name):
   with self.lock:self.finding=dict(state='done',asked=name,text='An online ID has 3 to 16 letters, numbers, hyphens and underscores, and starts with a letter.',tone='error')
   return
  with self.lock:self.finding=dict(state='asking',asked=name)
  self.jobs.put(('find',name))
 def clear_find(self):
  with self.lock:self.finding={}
 def befriend(self,kind,account_id):
  """kind: add (send a friend request), accept or decline (one received), cancel (one sent) or remove (end a friendship)."""
  key=str(account_id)
  if kind not in FRIEND_ACTIONS or not key.isdigit() or key in self.asking:return
  with self.lock:self.asking.add(key)
  self.jobs.put(('befriend',kind,key))
 def wake(self):
  """Has the thread look at once at what a helper was asked for."""
  self.jobs.put(('wake',))
 def focus(self,on):
  if on and not self.focused:self.jobs.put(('refresh',))
  self.focused=on
 def take_alerts(self):
  fired=[]
  while not self.alerts.empty():fired.append(self.alerts.get_nowait())
  return fired
 def view(self):
  """A copy of where things stand, for the window."""
  with self.lock:
   friends=[dict(self.friends.get(key,{}),id=key,name=self.name_of(key),picture=self.picture_of(key),favourite=key in self.favourites) for key in self.friend_ids]
   friends.sort(key=lambda f:(0 if f.get('game') and f.get('online') else 1 if f.get('online') else 2,-(f.get('last') or 0) if not f.get('online') else 0,f['name'].lower()))
   return dict(state=self.state,problem=self.problem,me=dict(self.me),presence=dict(self.presence_me) if self.presence_me else None,friends=friends,groups=[dict(group) for group in self.groups],thread=self.thread_id,
    messages=[dict(message,file=self.media.get((message.get('media') or {}).get('key')),reactions=[dict(row,file=self.media.get(reaction_key(row['url']),'') if row['url'] and not row['emoji'] else '') for row in self.reactions.get(message.get('id'),[])]) for message in self.messages],sending=self.sending,updated=self.updated,signed_until=self.refresh_until,
    received=[self.person(key) for key in self.received],sent=[self.person(key) for key in self.sent],finding=dict(self.finding),asking=sorted(self.asking),
    friend_line=dict(self.friend_line),fetching=self.fetching,requests_problem=self.requests_problem,send_line=dict(self.send_line),
    reaction_kinds=[dict(kind,file=self.media.get(reaction_key(kind['url']),'') if kind['url'] and not kind['emoji'] else '') for kind in self.reaction_kinds],
    chat_line=dict(self.chat_line),changing=self.changing,reactions_ready=self.kinds_asked)
 def person(self,key):return dict(id=key,name=self.name_of(key),picture=self.picture_of(key))
 def open_media(self,message_id):
  """Fetches the voice message or video of a message in the open conversation, then hands it to on_media."""
  message=next((m for m in self.messages if m.get('id')==message_id and m.get('media')),None)
  if message is None or self.fetching:return
  with self.lock:self.fetching=message_id
  self.jobs.put(('media',self.thread_id,message_id))
 def media_file(self,name):
  """A kept picture or recording, as a path, or None."""
  path=self.folder/'chat'/name if name else None
  return path if path is not None and path.is_file() else None
 def name_of(self,key):return (self.profiles.get(key) or {}).get('name') or ''
 def picture_of(self,key):
  path=(self.profiles.get(key) or {}).get('file')
  return path if path and (self.folder/'pictures'/path).is_file() else ''
 # The thread's side.
 def run(self):
  while not self.stopping.is_set():
   try:job=self.jobs.get(timeout=1)
   except queue.Empty:job=None
   if self.stopping.is_set():break
   try:
    if job:self.do(job)
    if self.refresh and self.clock()>=self.quiet_until:self.poll()
   except SignedOut as error:self.set_problem(str(error),'expired' if self.refresh_until else 'out')
   except Busy:pass
   except Problem as error:self.set_problem(str(error))
   # A connection that broke part way (http.client's own errors are not OSErrors) is the same as no connection: never the end of this thread.
   except (OSError,ValueError,http.client.HTTPException) as error:
    self.set_problem('PSN cannot be reached right now. PlayBridge tries again in a minute.');self.quiet_until=self.clock()+UNREACHABLE
    if job and job[0]=='send':
     with self.lock:self.sending=False
 def set_problem(self,text,state=None):
  with self.lock:
   self.problem=text;self.sending=False
   if state:self.state=state
   elif self.state=='signing':self.state='on' if self.refresh else 'out'
 def do(self,job):
  kind=job[0]
  if kind=='sign_in':self.exchange(job[1])
  elif kind=='sign_out':self.forget()
  elif kind=='refresh':
   # The friends list changes seldom: read again only when the last reading is a minute old.
   friends=self.due['friends'];self.due={key:0 for key in self.due};self.due['friends']=min(friends,self.friends_at+60);self.quiet_until=min(self.quiet_until,self.clock())
  elif kind=='open':
   with self.lock:
    self.thread_id=job[1];self.messages=[];self.reactions={};self.due['reactions']=0
    for group in self.groups:
     if group['id']==job[1]:group['unread']=False;self.seen.add((group['id'],group['uid']))
   self.due['thread']=0
  elif kind=='close':
   with self.lock:self.thread_id=None;self.messages=[];self.reactions={}
  elif kind=='chat_with':self.start_chat(job[1])
  elif kind=='send':self.post_message(job[1],job[2])
  elif kind=='picture':self.post_picture(*job[1:])
  elif kind=='find':self.find_player(job[1])
  elif kind=='befriend':self.change_friend(job[1],job[2])
  elif kind=='media':self.fetch_recording(job[1],job[2])
  elif kind=='delete':self.change('deleting the message',self.erase_message,job[1],job[2])
  elif kind=='react':self.change('the reaction',self.toggle_reaction,job[1],job[2],job[3])
  elif kind=='typing':self.tell_typing(job[1])
  elif kind=='group':self.change({'favourite':'the favourite','mute':'muting the conversation','rename':'the new name','invite':'adding them','remove':'taking them out','leave':'leaving the group'}[job[1]],self.alter_group,*job[1:])
  elif kind=='new_group':self.change('the new group',self.make_group,job[1],job[2])
 def poll(self):
  now=self.clock();quick=self.focused
  if now>=self.due['friends']:self.read_friends();self.due['friends']=now+FRIENDS_EVERY
  if now>=self.due['presence'] and (self.friend_ids or self.me_id):self.read_presence();self.due['presence']=now+PRESENCE_EVERY[0 if quick else 1]
  if now>=self.due['profiles']:self.read_profiles();self.due['profiles']=now+PROFILES_EVERY
  if now>=self.due['groups'] and (quick or self.wants.get('messages',True)):self.read_groups();self.due['groups']=now+GROUPS_EVERY[0 if quick else 1]
  if self.thread_id and quick and now>=self.due['thread']:self.read_thread();self.due['thread']=now+THREAD_EVERY
  # Reactions are extras: a refusal or a full budget leaves them as they were, never a problem on the page.
  if self.thread_id and quick and self.messages and now>=self.due['reactions']:
   self.due['reactions']=now+REACTIONS_EVERY
   try:self.read_reactions()
   except (Answered,Busy):pass
  # Set before asking, so that a refusal is asked about again only at the next turn.
  if now>=self.due['requests']:self.due['requests']=now+REQUESTS_EVERY[0 if quick else 1];self.read_requests()
  for helper in self.helpers:
   # An answer in a shape nobody expected says so on the page and is asked again later; it never ends this thread.
   try:helper.poll()
   except (AttributeError,TypeError,KeyError,IndexError) as error:raise Problem('PSN sent trophies PlayBridge could not read. PlayBridge tries again soon.') from error
 # Tokens.
 def token_request(self,values):
  body=urllib.parse.urlencode(values).encode();self.budget.spend()
  status,headers,raw=self.opener('POST',AUTH+'/token',{'Content-Type':'application/x-www-form-urlencoded','Authorization':BASIC,'User-Agent':AGENT},body)
  try:data=json.loads(raw or b'{}')
  except ValueError:data={}
  return status,data
 def keep(self,data):
  now=self.clock();self.access=data['access_token'];self.access_until=now+float(data.get('expires_in') or 3600)
  if data.get('refresh_token'):
   self.refresh=data['refresh_token'];self.refresh_until=now+float(data.get('refresh_token_expires_in') or 60*86400);self.save_token(self.refresh,self.refresh_until)
 def exchange(self,code):
  query=urllib.parse.urlencode(dict(access_type='offline',client_id=CLIENT,redirect_uri=REDIRECT,response_type='code',scope=SCOPE))
  self.budget.spend();status,headers,raw=self.opener('GET',AUTH+'/authorize?'+query,{'Cookie':'npsso='+code,'User-Agent':AGENT},None)
  got=urllib.parse.parse_qs(urllib.parse.urlsplit(headers.get('location','')).query)
  if not got.get('code'):
   with self.lock:self.state='on' if self.refresh else 'out'
   raise Problem(f'Sony answered {status}. Try again in a minute.' if status>=500 else 'Sony did not take that code. Sign in on playstation.com again, open the code page and copy the new code.')
  status,data=self.token_request(dict(code=got['code'][0],redirect_uri=REDIRECT,grant_type='authorization_code',token_format='jwt'))
  if status!=200 or not data.get('access_token'):
   with self.lock:self.state='on' if self.refresh else 'out'
   raise Problem(f'Sony did not hand out a sign-in ({status}). Copy a new code and try again.')
  self.keep(data)
  with self.lock:
   self.state='on';self.problem='';self.me={};self.me_id='';self.presence_me=None;self.friend_ids=[];self.friends={};self.groups=[];self.last_presence=None;self.last_groups=None
   self.received=[];self.sent=[];self.last_received=None;self.finding={};self.asking=set();self.friend_line={}
  self.due={key:0 for key in self.due};self.read_me()
 def access_token(self):
  if self.access and self.clock()<self.access_until-60:return self.access
  if not self.refresh:raise SignedOut('Sign in to PSN in Settings › Connections.')
  status,data=self.token_request(dict(refresh_token=self.refresh,grant_type='refresh_token',token_format='jwt',scope=SCOPE))
  if status in (400,401,403):
   self.refresh=None;self.access=None;self.save_token(None,0)
   raise SignedOut('Your PSN sign-in has ended. Paste a new code in Settings › Connections.')
  if status!=200 or not data.get('access_token'):raise Problem(f'PSN answered {status} while signing in again. PlayBridge tries again soon.')
  self.keep(data);return self.access
 def forget(self):
  self.refresh=None;self.refresh_until=0;self.access=None;self.save_token(None,0);self.profiles={}
  shutil.rmtree(self.folder,ignore_errors=True)
  for helper in self.helpers:helper.forget()
  with self.lock:
   self.state='out';self.problem='';self.me={};self.me_id='';self.presence_me=None;self.friend_ids=[];self.friends={};self.groups=[];self.thread_id=None;self.messages=[]
   self.last_presence=None;self.last_groups=None;self.seen=set()
   self.received=[];self.sent=[];self.last_received=None;self.finding={};self.asking=set();self.friend_line={};self.media={};self.fetching='';self.send_line={}
   self.reactions={};self.reaction_kinds=[];self.reaction_version='';self.kinds_asked=False;self.hidden={};self.told_read={};self.changing='';self.chat_line={}
 # Requests.
 def call(self,method,path,query=None,body=None,room=0,read=True,upload=None):
  """One request to the PSN API (a path under API, or a whole https address), the access token renewed first when it has run out.
  Busy when the budget has no room for it; Answered (Refused for 403 and 404) when Sony answers with an error. read=False leaves the
  answer unread, for changes whose answer says nothing PlayBridge needs; read='whole' hands back (status, headers, body) as they came.
  upload, (bytes, type), sends those bytes as they are in place of a JSON body."""
  if self.budget.left()<=room:raise Busy()
  token=self.access_token()
  url=(path if path.startswith('https://') else API+path)+('?'+urllib.parse.urlencode(query,safe=',') if query else '')
  headers={'Authorization':'Bearer '+token,'Accept':'*/*' if read=='whole' else 'application/json','Accept-Language':'en-US','User-Agent':AGENT}
  data=None
  if body is not None:headers['Content-Type']='application/json; charset=utf-8';data=json.dumps(body).encode()
  if upload is not None:data,headers['Content-Type']=upload
  self.budget.spend();status,answer,raw=self.opener(method,url,headers,data)
  if status==401:
   self.access=None;token=self.access_token();headers['Authorization']='Bearer '+token;self.budget.spend();status,answer,raw=self.opener(method,url,headers,data)
  if status==429:
   wait=answer.get('retry-after','');self.quiet_until=self.clock()+(int(wait) if wait.isdigit() else QUIET)
   raise Problem('Sony asked PlayBridge to slow down. Friends and messages come back in a few minutes.')
  if status>=400:raise (Refused if status in (403,404) else Answered)(f'PSN answered {status} when asked for {asked_for(path)}. PlayBridge tries again soon.',status,sony_words(raw))
  with self.lock:
   if self.problem and self.state=='on':self.problem=''
  if read=='whole':return status,answer,raw
  return json.loads(raw) if raw and read else {}
 def read_me(self):
  # The account number first (asked once a sign-in), then the profile by that number.
  if not self.me_id:
   key=str(self.call('GET',ACCOUNT).get('accountId') or '')
   if not key.isdigit():raise Problem('PSN did not say which account is signed in. PlayBridge tries again soon.')
   self.me_id=key
  data=self.call('GET',f'/userProfile/v1/internal/users/{self.me_id}/profiles')
  with self.lock:self.me=dict(name=data.get('onlineId',''),picture_url=picture_url(data.get('avatars')),plus=bool(data.get('isPlus')))
  self.fetch_picture('me',self.me['picture_url'])
 def read_friends(self):
  data=self.call('GET','/userProfile/v1/internal/users/me/friends',dict(limit=1000))
  ids=[str(key) for key in data.get('friends') or [] if str(key).isdigit()]
  with self.lock:
   self.friend_ids=ids;self.friends={key:self.friends.get(key,{}) for key in ids};self.updated=self.friends_at=self.clock()
  if not self.me:self.read_me()
  # A picture that did not come with the profile is asked for again with the friends list.
  elif not self.me.get('picture') and self.me.get('picture_url'):self.fetch_picture('me',self.me['picture_url'])
 def read_presence(self):
  """Who is online and what they play, the player too (for the top bar): the player's own number rides along with the friends'."""
  seen={};everyone=self.friend_ids+([self.me_id] if self.me_id and self.me_id not in self.friend_ids else [])
  for start in range(0,len(everyone),PRESENCE_BATCH):
   part=everyone[start:start+PRESENCE_BATCH]
   data=self.call('GET','/userProfile/v2/internal/users/basicPresences',dict(type='primary',accountIds=','.join(part),platforms=PLATFORMS,withOwnGameTitleInfo='true'))
   for item in data.get('basicPresences') or []:
    key=str(item.get('accountId',''));info=item.get('primaryPlatformInfo') or {};games=item.get('gameTitleInfoList') or []
    game=games[0] if games and isinstance(games[0],dict) else {}
    seen[key]=dict(online=info.get('onlineStatus')=='online' or item.get('availability')=='availableToPlay',platform=info.get('platform') or '',
     game=game.get('titleName') or '',title_id=game.get('npTitleId') or '',last=when(info.get('lastOnlineDate') or item.get('lastAvailableDate')))
  mine=seen.pop(self.me_id,None) if self.me_id else None
  with self.lock:self.presence_me=mine
  names={key:self.name_of(key) for key in seen}
  for alert in presence_alerts(self.last_presence,seen,names,self.wants,self.favourites):self.alerts.put(alert)
  self.last_presence=seen
  with self.lock:
   for key,value in seen.items():
    if key in self.friends:self.friends[key]=value
   self.updated=self.clock()
 def read_profiles(self):
  """Names and pictures of the friends PlayBridge does not know yet or knew more than a week ago, the ones online first."""
  now=self.clock();stale=[key for key in dict.fromkeys(self.received+self.friend_ids+self.sent) if now-(self.profiles.get(key) or {}).get('at',0)>PROFILE_DAYS*86400]
  stale.sort(key=lambda key:key not in self.received and not (self.friends.get(key) or {}).get('online'))
  changed=False
  for key in stale[:PROFILES_AT_ONCE]:
   try:data=self.call('GET',f'/userProfile/v1/internal/users/{key}/profiles',room=PROFILE_ROOM)
   except Busy:break
   # A friend whose profile Sony keeps back (or an account that is gone) keeps what PlayBridge knew and is asked again next week;
   # it never holds back the friends after it.
   except Refused:data={}
   url=picture_url(data.get('avatars'));known=self.profiles.get(key) or {}
   with self.lock:self.profiles[key]=dict(name=data.get('onlineId') or known.get('name',''),url=url or known.get('url',''),file=known.get('file',''),at=now)
   self.fetch_picture(key,url);changed=True
  if changed:self.save_profiles()
 def fetch_picture(self,key,url):
  """A small picture from Sony's image server, kept beside the names. Not counted against the API budget: another server."""
  raw,kind=get_picture(self.opener,url)
  if not raw:return
  name=key+kind;path=self.folder/'pictures'/name
  try:
   path.parent.mkdir(parents=True,exist_ok=True)
   for old in path.parent.glob(key+'.*'):
    if old.name!=name:old.unlink()
   path.write_bytes(raw)
  except OSError:return
  with self.lock:
   if key=='me':self.me['picture']=name
   else:self.profiles.setdefault(key,{})['file']=name
 def load_profiles(self):
  try:data=json.loads((self.folder/'profiles.json').read_text(encoding='utf8'))
  except (OSError,ValueError):return {}
  return {str(key):value for key,value in data.items() if isinstance(value,dict)} if isinstance(data,dict) else {}
 def save_profiles(self):
  with self.lock:data=json.dumps(self.profiles,ensure_ascii=False)
  try:self.folder.mkdir(parents=True,exist_ok=True);(self.folder/'profiles.json').write_text(data,encoding='utf8')
  except OSError:pass
 # Friend requests.
 def read_requests(self):
  """The friend requests either way. A new one from someone is an alert (its sender's name asked for first, when not known)."""
  def numbers(data,key):
   found=[]
   for item in data.get(key) or []:
    number=str(item.get('accountId','') if isinstance(item,dict) else item)
    if number.isdigit() and number not in found:found.append(number)
   return found
  # A refusal leaves the requests as they were and says so beside them, never over the whole page: friends and messages carry on.
  try:received=numbers(self.call('GET',FRIEND+'receivedRequests'),'receivedRequests');sent=numbers(self.call('GET',FRIEND+'sentRequests'),'sentRequests')
  except Refused as error:
   with self.lock:self.requests_problem=f'PSN did not give your friend requests (answer {error.status}). PlayBridge asks again in a few minutes.'
   return
  with self.lock:self.requests_problem=''
  new=[key for key in received if self.last_received is not None and key not in self.last_received]
  for key in new:
   if not self.name_of(key):self.learn(key)
  with self.lock:self.received=received;self.sent=sent
  if self.wants.get('requests',True):
   for key in new:self.alerts.put(('request',f'{self.name_of(key) or "A player"} sent you a friend request','Accept or decline it on the Friends page.'))
  self.last_received=received
 def learn(self,key,name='',url=None):
  """Keeps one player's name and picture beside the friends': from their profile, or from what a search already gave."""
  if url is None:
   try:data=self.call('GET',f'/userProfile/v1/internal/users/{key}/profiles',room=PROFILE_ROOM)
   except (Busy,Refused):return
   name=data.get('onlineId') or '';url=picture_url(data.get('avatars'))
  known=self.profiles.get(key) or {}
  with self.lock:self.profiles[key]=dict(name=name or known.get('name',''),url=url or known.get('url',''),file=known.get('file',''),at=self.clock())
  self.fetch_picture(key,url);self.save_profiles()
 def find_player(self,name):
  """One player by their online ID: their number, name and picture, and where they stand with the player."""
  def done(**found):
   with self.lock:self.finding=dict(dict(state='done',asked=name,text='',tone='plain'),**found)
  try:data=self.call('GET',FIND.format(urllib.parse.quote(name)),dict(fields=FIND_FIELDS))
  except SignedOut:
   with self.lock:self.finding={}
   raise
  except Answered as error:
   if error.status==404:done(text=f'No player on PSN is called {name}. Check the spelling: it is their online ID, as their profile shows it.',tone='error')
   else:done(text=f'PSN would not look for {name}: answer {error.status}'+(f', "{error.words}"' if error.words else '')+'.',tone='error')
   return
  except Busy:done(text='PlayBridge asked PSN a lot in the last minutes. Try again in a few.',tone='error');return
  except Problem as error:done(text=str(error),tone='error');return
  except (OSError,ValueError,http.client.HTTPException):done(text='PSN cannot be reached right now. Try again in a minute.',tone='error');return
  profile=data.get('profile') if isinstance(data.get('profile'),dict) else {}
  key=str(profile.get('accountId') or '')
  if not key.isdigit():done(text=f'No player on PSN is called {name}.',tone='error');return
  shown=profile.get('currentOnlineId') or profile.get('onlineId') or name
  avatars=[dict(size=item.get('size'),url=item.get('avatarUrl') or item.get('url')) for item in profile.get('avatarUrls') or [] if isinstance(item,dict)]
  self.learn(key,shown,picture_url(avatars))
  done(id=key,name=shown,relation=self.relation(key,profile.get('friendRelation')))
 def relation(self,key,said=''):
  """Where a player stands with the player: me, friend, sent (asked by the player), received (asked the player) or none."""
  if key==self.me_id:return 'me'
  if key in self.friend_ids or said=='friend':return 'friend'
  if key in self.sent:return 'sent'
  if key in self.received:return 'received'
  return 'none'
 def change_friend(self,kind,key):
  """Sends, accepts, declines or takes back a friend request, or ends a friendship, and says what came of it in friend_line."""
  name=self.name_of(key) or 'that player';text,tone='','news'
  try:self.call({'add':'POST','accept':'PUT'}.get(kind,'DELETE'),FRIEND+key,body={} if kind=='add' else None,read=False)
  except SignedOut:
   with self.lock:self.asking.discard(key)
   raise
  except Answered as error:text,tone=f'PSN refused it: answer {error.status}'+(f', "{error.words}"' if error.words else '')+'.','error'
  except Busy:text,tone='PlayBridge asked PSN a lot in the last minutes. Try again in a few.','error'
  except Problem as error:text,tone=str(error),'error'
  except (OSError,ValueError,http.client.HTTPException):text,tone='PSN cannot be reached right now. Try again in a minute.','error'
  else:
   text=dict(add=f'Friend request sent to {name}.',accept=f'You and {name} are friends now.',decline=f"You declined {name}'s friend request.",
    cancel=f'You took back your friend request to {name}.',remove=f'{name} is no longer your friend.')[kind];text=text[:1].upper()+text[1:]
   with self.lock:
    if kind=='add' and key not in self.sent:self.sent.append(key)
    if kind in ('accept','decline') and key in self.received:self.received.remove(key)
    if kind=='cancel' and key in self.sent:self.sent.remove(key)
    if kind=='accept' and key not in self.friend_ids:self.friend_ids.append(key);self.friends[key]={}
    if kind=='remove' and key in self.friend_ids:self.friend_ids.remove(key);self.friends.pop(key,None)
    if self.finding.get('id')==key:self.finding=dict(self.finding,relation=self.relation(key))
   self.due['requests']=0
   if kind in ('accept','remove'):self.due['friends']=0;self.due['presence']=0
  with self.lock:self.asking.discard(key);self.friend_line=dict(text=text,tone=tone,id=key,at=self.clock())
 # Messages.
 def read_groups(self):
  data=self.call('GET','/gamingLoungeGroups/v1/members/me/groups',dict(includeFields=GROUP_FIELDS,limit=200,offset=0))
  mine=(self.me.get('name') or '').lower();groups=[]
  for item in data.get('groups') or []:
   gid=item.get('groupId');thread=item.get('mainThread') or {};latest=thread.get('latestMessage') or {};sender=latest.get('sender') or {}
   if not gid:continue
   members=[m for m in item.get('members') or [] if isinstance(m,dict)];others=[m.get('onlineId','') for m in members if (m.get('onlineId') or '').lower()!=mine]
   named=((item.get('groupName') or {}).get('value') or '').strip()
   label=named or ', '.join(name for name in others if name) or 'Conversation'
   uid=latest.get('messageUid') or '';from_me=(sender.get('onlineId') or '').lower()==mine
   # A group of several (Sony's multi), else a conversation of two; a named one of two is a group someone left.
   kind=str(item.get('groupType') or '').lower();kind='group' if kind=='multi' or kind!='direct' and (len(members)>2 or bool(named)) else 'direct'
   setting=item.get('notificationSetting') if isinstance(item.get('notificationSetting'),dict) else {}
   groups.append(dict(id=gid,thread=thread.get('threadId') or gid,name=label,members=others,partner=next((str(m.get('accountId')) for m in members if (m.get('onlineId') or '').lower()!=mine),'') if len(members)==2 else '',
    people=[dict(id=str(m.get('accountId') or ''),name=m.get('onlineId') or '') for m in members if (m.get('onlineId') or '').lower()!=mine],kind=kind,named=bool(named),
    favourite=item.get('isFavorite') in (True,'true'),muted=setting.get('isMute') in (True,'true'),read_uid=thread.get('readMessageUid') or '',
    last=message_text(latest) if latest else '',last_from=sender.get('onlineId',''),at=when(latest.get('createdTimestamp') or item.get('modifiedTimestamp')),uid=uid,
    unread=bool(uid) and not from_me and uid!=thread.get('readMessageUid') and (gid,uid) not in self.seen))
  groups.sort(key=lambda g:(not g['favourite'],-g['at']))
  if self.last_groups is not None and self.wants.get('messages',True):
   for group in groups:
    before=self.last_groups.get(group['id'])
    if group['uid'] and group['uid']!=before and group['unread'] and not group['muted'] and not (self.focused and self.thread_id==group['id']):
     self.alerts.put(('message',f'{group["last_from"] or group["name"]} on PSN',group['last'][:140]))
  self.last_groups={group['id']:group['uid'] for group in groups}
  with self.lock:self.groups=groups
 def thread_of(self,group_id):return next((g['thread'] for g in self.groups if g['id']==group_id),group_id)
 def read_thread(self):
  gid=self.thread_id;tid=self.thread_of(gid)
  data=self.call('GET',api_path('/gamingLoungeGroups/v1/members/me/groups/{}/threads/{}/messages',gid,tid),dict(limit=MESSAGES))
  mine=(self.me.get('name') or '').lower();messages=[]
  with self.lock:hidden=set(self.hidden.get(gid,[]))
  for item in data.get('messages') or []:
   if item.get('messageUid') in hidden:continue
   sender=item.get('sender') or {};media=message_media(item)
   # The group's own notes (made, someone added, a message deleted) come as other kinds of message with words: shown apart, never as a bubble.
   note=media is None and item.get('messageType') not in (1,None) and isinstance(item.get('body'),str) and bool(item['body'].strip())
   # A picture can bring words under it (the PlayStation App's TextWithImage).
   caption=item['body'].strip() if media and isinstance(item.get('body'),str) else ''
   messages.append(dict(id=item.get('messageUid',''),who=sender.get('onlineId',''),mine=(sender.get('onlineId') or '').lower()==mine and not note,text=message_text(item),
    at=when(item.get('createdTimestamp')),kind='note' if note else media['kind'] if media else 'text',media=dict(media,key=media_key(gid,media)) if media else None,caption=caption))
  messages.sort(key=lambda m:m['at'])
  # The pictures, GIFs and stickers shown in it, newest first, a few at a time.
  wanted=[m['media'] for m in reversed(messages) if m['media'] and m['kind'] in ('picture','gif','sticker') and m['media']['key'] not in self.media]
  for media in wanted[:PICTURES_AT_ONCE]:
   try:self.fetch_picture_of(gid,media)
   except Busy:break
  with self.lock:
   if self.thread_id==gid:
    if [m['id'] for m in messages]!=[m.get('id') for m in self.messages]:self.due['reactions']=0
    self.messages=messages
    for group in self.groups:
     if group['id']==gid:group['unread']=False;self.seen.add((gid,group['uid']))
  self.tell_read(gid,tid,messages)
 def fetch_media_bytes(self,gid,media,most):
  """A message's picture or recording: from the group's resource with the sign-in (following Sony to another address when it moves
  it there), or from the address a sticker brings. b'' when none came; Busy when the budget has no room."""
  if media.get('resource'):
   try:status,headers,raw=self.call('GET',api_path(RESOURCE,gid,media['resource']),room=PROFILE_ROOM,read='whole')
   except Refused:return b''
   if status in (301,302,303,307,308) and headers.get('location'):return fetch_bytes(self.opener,headers['location'],most)
   if raw[:1]==b'{':
    # An address to fetch it from, in a few words of JSON.
    try:data=json.loads(raw)
    except ValueError:return b''
    url=next((v for v in (data.get(k) for k in ('url','downloadUrl','resourceUrl')) if isinstance(v,str)),'') if isinstance(data,dict) else ''
    return fetch_bytes(self.opener,url,most) if url else b''
   return raw if status==200 and len(raw)<=most else b''
  return fetch_bytes(self.opener,media.get('url',''),most) if media.get('url') else b''
 def keep_media(self,key,raw,ending):
  name=key+ending if raw else ''
  if name:
   try:(self.folder/'chat').mkdir(parents=True,exist_ok=True);(self.folder/'chat'/name).write_bytes(raw)
   except OSError:name=''
  with self.lock:self.media[key]=name
  return name
 def fetch_picture_of(self,gid,media):
  raw,ending=chat_picture(self.fetch_media_bytes(gid,media,CHAT_PICTURE_MOST))
  self.keep_media(media['key'],raw,ending)
 def fetch_recording(self,gid,message_id):
  """A voice message or video, fetched once and kept; on_media plays or opens it. A refusal says so on the page."""
  try:
   message=next((m for m in self.messages if m.get('id')==message_id),None);media=(message or {}).get('media')
   if not media:return
   name=self.media.get(media['key'])
   if not self.media_file(name):
    raw=self.fetch_media_bytes(gid,media,CHAT_MEDIA_MOST)
    if not raw:raise Problem(f'PSN did not send the {"voice message" if media["kind"]=="voice" else "video"}. It may be too old, or only for the PlayStation App.')
    name=self.keep_media(media['key'],raw,'.mp4' if media['kind']=='video' else '.voice')
   path=self.media_file(name)
   if path is not None:self.on_media(media['kind'],path,message_id)
  finally:
   with self.lock:self.fetching=''
 def post_picture(self,gid,path,caption='',passing=False):
  """The picture up to the group, then the message that names it. It shows in the conversation at once, from the copy kept here; what
  went wrong lands in send_line, in words."""
  source=Path(path)
  try:
   try:raw=source.read_bytes() if source.stat().st_size<=PICK_MOST else None
   except OSError:raise Problem('PlayBridge could not open that file.')
   if raw is None:raise Problem('That file is too large to be a picture PlayBridge can send.')
   data,kind=picture_to_send(raw)
   # Which of the two steps Sony said no to: the picture going up, or the message that shows it.
   went_up=False
   try:
    status,headers,answer=self.call('POST',api_path(RESOURCES,gid),upload=(data,kind),read='whole')
    resource=resource_of(answer,headers)
    if not resource:raise Problem('PSN took the picture but did not say where it keeps it, so it was not sent.')
    went_up=True
    message=dict(messageType=PICTURE_MESSAGE,messageDetail=dict(imageMessageDetail=dict(resourceId=resource)))
    if caption:message['body']=caption
    self.call('POST',api_path(SEND,gid,self.thread_of(gid)),body=message,read=False)
   except Answered as error:
    said=f'answer {error.status}'+(f', "{error.words}"' if error.words else '')
    raise Problem(f'The picture went up, but PSN refused the message that shows it: {said}.' if went_up else f'PSN refused the picture as it went up: {said}.')
   except Busy:raise Problem('PlayBridge asked PSN a lot in the last minutes. Try again in a few.')
   except (OSError,ValueError,http.client.HTTPException):raise Problem('PSN cannot be reached right now. Try again in a minute.')
   media=dict(kind='picture',resource=resource,url='',seconds=0);key=media_key(gid,media)
   self.keep_media(key,data,'.png' if kind=='image/png' else '.jpg')
   with self.lock:
    if self.thread_id==gid:self.messages.append(dict(id='',who=self.me.get('name',''),mine=True,text=MEDIA_WORDS['picture'],at=self.clock(),kind='picture',media=dict(media,key=key),caption=caption))
   self.due['thread']=0;self.due['groups']=0
  except SignedOut:raise
  except Problem as error:
   with self.lock:self.send_line=dict(text=str(error),tone='error',at=self.clock())
  finally:
   with self.lock:self.sending=False
   if passing:source.unlink(missing_ok=True)
 def post_message(self,gid,text):
  tid=self.thread_of(gid)
  try:self.call('POST',api_path(SEND,gid,tid),body=dict(messageType=1,body=text))
  finally:
   with self.lock:self.sending=False
  with self.lock:
   if self.thread_id==gid:self.messages.append(dict(id='',who=self.me.get('name',''),mine=True,text=text,at=self.clock()))
  self.due['thread']=0;self.due['groups']=0
 def tell_read(self,gid,tid,messages):
  """Tells PSN the player read the open conversation up to its newest message, once for each new one, as the PlayStation App does."""
  latest=next((m['id'] for m in reversed(messages) if m.get('id')),'');group=next((g for g in self.groups if g['id']==gid),{})
  if not latest or not self.focused or latest==self.told_read.get(gid) or latest==group.get('read_uid'):return
  self.told_read[gid]=latest
  try:
   self.call('PATCH',api_path(THREAD,gid,tid),body=dict(readMessageUid=latest),read=False,room=PROFILE_ROOM)
   self.call('DELETE',api_path(NEW_ARRIVAL,gid),dict(timestamp=str(int(self.clock()*1000))),read=False,room=PROFILE_ROOM)
  except (Answered,Busy):pass
 def tell_typing(self,gid):
  try:self.call('POST',api_path(TYPING,gid),read=False,room=PROFILE_ROOM)
  except (Answered,Busy):pass
 def change(self,what,work,*args):
  """One change to a conversation: what came of it (work's words) lands in chat_line; what names it when Sony refuses."""
  def say(text,tone):
   with self.lock:self.chat_line=dict(text=text,tone=tone,at=self.clock()) if text else {}
  try:say(work(*args),'news')
  except SignedOut:raise
  except Answered as error:say(f'PSN refused {what}: answer {error.status}'+(f', "{error.words}"' if error.words else '')+'.','error')
  except Busy:say('PlayBridge asked PSN a lot in the last minutes. Try again in a few.','error')
  except Problem as error:say(str(error),'error')
  except (OSError,ValueError,http.client.HTTPException):say('PSN cannot be reached right now. Try again in a minute.','error')
  finally:
   with self.lock:self.changing=''
 def erase_message(self,gid,uid):
  message=next((m for m in self.messages if m.get('id')==uid),None)
  if message is None or not message.get('mine'):raise Problem('PSN lets you delete only the messages you sent. You can remove this one from this PC.')
  if self.clock()-(message.get('at') or 0)>DELETE_WITHIN:raise Problem('PSN lets you delete a message only in the 10 minutes after you send it. You can still remove it from this PC.')
  tid=self.thread_of(gid)
  # The App's delete; its older one, for a picture, when Sony does not know the newer one there.
  try:self.call('DELETE',api_path(DELETE_MESSAGE,gid,tid,uid),read=False)
  except Refused as error:
   if error.status!=404:raise
   self.call('DELETE',api_path(DELETE_MEDIA,gid,tid,uid),read=False)
  with self.lock:self.messages=[m for m in self.messages if m.get('id')!=uid];self.reactions.pop(uid,None)
  self.drop_media(message);self.due['thread']=0;self.due['groups']=0
  return 'Deleted for everyone in the conversation.'
 def drop_media(self,message):
  """Deletes the kept picture or recording of a message no other shown message uses."""
  key=(message.get('media') or {}).get('key')
  if not key or any((m.get('media') or {}).get('key')==key for m in self.messages):return
  with self.lock:name=self.media.pop(key,'')
  if name:(self.folder/'chat'/name).unlink(missing_ok=True)
 def load_hidden(self):
  try:data=json.loads((self.folder/'hidden.json').read_text(encoding='utf-8'))
  except (OSError,ValueError):return {}
  return {str(k):[str(u) for u in v][-HIDDEN_MOST:] for k,v in data.items() if isinstance(v,list)} if isinstance(data,dict) else {}
 def save_hidden(self):
  with self.lock:data=json.dumps(self.hidden)
  try:self.folder.mkdir(parents=True,exist_ok=True);(self.folder/'hidden.json').write_text(data,encoding='utf-8')
  except OSError:pass
 def load_reaction_kinds(self):
  """The reactions Sony offers, asked once a session: the App's expanded set first, else the plain emoji. A kind that comes as a
  picture only has its picture kept, a few at a time. A full budget or another refusal leaves it to ask again later."""
  if self.kinds_asked:return
  try:
   for version in REACTION_VERSIONS:
    try:kinds=reaction_kinds(self.call('GET',api_path(REACTION_KINDS,version),room=PROFILE_ROOM))
    except Refused:continue
    if kinds:
     with self.lock:self.reaction_kinds=kinds;self.reaction_version=version
     break
   self.kinds_asked=True
  except (Answered,Busy):return
  self.keep_reaction_pictures(self.reaction_kinds)
 def keep_reaction_pictures(self,rows):
  for row in [r for r in rows if r['url'] and not r['emoji'] and reaction_key(r['url']) not in self.media][:REACTION_PICTURES]:
   raw,ending=get_picture(self.opener,row['url'])
   self.keep_media(reaction_key(row['url']),raw,ending)
 def read_reactions(self):
  gid=self.thread_id;tid=self.thread_of(gid)
  uids=[m['id'] for m in self.messages if m.get('id') and m.get('kind')!='note']
  if not gid or not uids:return
  self.load_reaction_kinds()
  data=self.call('POST',api_path(REACTIONS,gid,tid),body=dict(messageUids=uids,reactionVersion=self.reaction_version or REACTION_VERSIONS[-1]),room=PROFILE_ROOM)
  found=reaction_lists(data,self.me_id)
  self.keep_reaction_pictures([row for rows in found.values() for row in rows])
  with self.lock:
   if self.thread_id==gid:self.reactions={uid:found[uid] for uid in uids if found.get(uid)}
 def toggle_reaction(self,gid,uid,rid):
  tid=self.thread_of(gid);mine=next((r for r in self.reactions.get(uid,[]) if r['mine']),None)
  self.load_reaction_kinds()
  if mine and mine['id']==rid:
   self.call('DELETE',api_path(REACT+'/{}',gid,tid,uid,rid),read=False);self.set_reaction(uid,None)
  else:
   self.call('POST',api_path(REACT,gid,tid,uid),body=dict(reactionId=rid,reactionVersion=self.reaction_version or REACTION_VERSIONS[-1]),read=False);self.set_reaction(uid,rid)
  self.due['reactions']=self.clock()+REACTIONS_EVERY/3
  return ''
 def set_reaction(self,uid,rid):
  """The player's reaction on a message as it is now, at once, before PSN is read again: the one given before goes."""
  with self.lock:
   rows=[dict(r) for r in self.reactions.get(uid,[])]
   for row in rows:
    if row['mine']:row['mine']=False;row['count']-=1
   rows=[r for r in rows if r['count']>0]
   if rid:
    row=next((r for r in rows if r['id']==rid),None)
    if row is None:
     kind=next((k for k in self.reaction_kinds if k['id']==rid),dict(id=rid,emoji='',url=''))
     row=dict(id=rid,emoji=kind['emoji'],url=kind['url'],count=0,mine=False,at=self.clock());rows.append(row)
    row['mine']=True;row['count']+=1
   rows.sort(key=lambda r:(-r['count'],r['at']));self.reactions[uid]=rows
 def set_group(self,gid,**values):
  with self.lock:
   for group in self.groups:
    if group['id']==gid:group.update(values)
 def alter_group(self,kind,gid,value):
  group=next((g for g in self.groups if g['id']==gid),None)
  if group is None:raise Problem('That conversation is not on PSN any more.')
  people=[p['id'] for p in group.get('people') or []]
  if kind=='favourite':
   self.call('PATCH',api_path(MY_GROUP,gid),body=dict(isFavorite='true' if value else 'false'),read=False);self.set_group(gid,favourite=bool(value))
   done='Pinned to the top of your conversations.' if value else 'No longer a favourite conversation.'
  elif kind=='mute':
   self.call('PATCH',api_path(MUTE,gid),body=dict(isMute=bool(value)),read=False);self.set_group(gid,muted=bool(value))
   done='Muted on PSN: no alerts for its new messages.' if value else 'Alerts for its new messages are back on.'
  elif kind=='rename':
   name=' '.join(str(value or '').split())[:NAME_LONGEST]
   if not name:raise Problem('Type a name for the group.')
   self.call('PATCH',api_path(GROUP,gid),body=dict(groupName=dict(value=name)),read=False);self.set_group(gid,name=name,named=True)
   done=f'The group is now called {name}.'
  elif kind=='invite':
   ids=[str(key) for key in value or [] if str(key).isdigit() and str(key) not in people]
   if not ids:raise Problem('Choose who to add.')
   if len(people)+1+len(ids)>MOST_MEMBERS:raise Problem(f'A group holds at most {MOST_MEMBERS} people.')
   data=self.call('POST',api_path(INVITE,gid),body=dict(invitees=[dict(accountId=key) for key in ids]))
   moved=str(data.get('groupId') or '') if isinstance(data,dict) else ''
   names=', '.join(self.name_of(key) or 'A friend' for key in ids)
   done=f'{names} {"is" if len(ids)==1 else "are"} in the conversation now.'
   # Someone added to a conversation of two: Sony makes a new group of all of them, which opens.
   if moved and moved!=gid:
    with self.lock:
     self.groups.insert(0,dict(group,id=moved,thread=moved,kind='group',named=False,people=group.get('people',[])+[dict(id=key,name=self.name_of(key)) for key in ids],partner='',uid='',unread=False,read_uid='',last='',at=self.clock()))
     self.thread_id=moved;self.messages=[];self.reactions={}
    done=f'A new group with {names} and {group["name"]} is open.'
   if isinstance(data,dict) and data.get('hasAllAccountInvited') is False:done+=' PSN could not add everyone you chose.'
  elif kind=='remove':
   key=str(value or '')
   if key not in people:raise Problem('They are not in this group.')
   self.call('DELETE',api_path(MEMBER,gid,key),read=False);self.set_group(gid,people=[p for p in group['people'] if p['id']!=key])
   done=f'{self.name_of(key) or "They"} left the group.'
  else:
   self.call('DELETE',api_path(MEMBER,gid,'me'),read=False)
   with self.lock:
    self.groups=[g for g in self.groups if g['id']!=gid]
    if self.thread_id==gid:self.thread_id=None;self.messages=[];self.reactions={}
   done=f'You left {group["name"]}.'
  self.due['groups']=0;self.due['thread']=0
  return done
 def make_group(self,ids,name):
  data=self.call('POST',GROUPS,body=dict(invitees=[dict(accountId=key) for key in ids]))
  gid=str(data.get('groupId') or '') if isinstance(data,dict) else ''
  if not gid:raise Problem('PSN did not make the group. Try again in a minute.')
  label=name or ', '.join(self.name_of(key) or 'Friend' for key in ids)
  with self.lock:
   self.groups.insert(0,dict(id=gid,thread=(data.get('mainThread') or {}).get('threadId') or gid,name=label,members=[self.name_of(key) for key in ids],
    people=[dict(id=key,name=self.name_of(key)) for key in ids],partner='',kind='group',named=bool(name),favourite=False,muted=False,read_uid='',last='',last_from='',at=self.clock(),uid='',unread=False))
   self.thread_id=gid;self.messages=[];self.reactions={}
  self.due['groups']=0;self.due['thread']=0
  if name:
   try:self.call('PATCH',api_path(GROUP,gid),body=dict(groupName=dict(value=name)),read=False)
   except Answered as error:return f'The group is made, but PSN refused its name: answer {error.status}.'
  return f'Your group with {len(ids)} friends is open.'
 def start_chat(self,account_id):
  """Opens the conversation with one friend, the one already there or a new one."""
  if self.last_groups is None:self.read_groups()
  group=next((g for g in self.groups if g.get('partner')==str(account_id)),None)
  if group is None:
   data=self.call('POST','/gamingLoungeGroups/v1/groups',body=dict(invitees=[dict(accountId=str(account_id))]))
   gid=data.get('groupId')
   if not gid:raise Problem('PSN did not open the conversation. Try again in a minute.')
   with self.lock:self.groups.insert(0,dict(id=gid,thread=(data.get('mainThread') or {}).get('threadId') or gid,name=self.name_of(str(account_id)) or 'Conversation',members=[self.name_of(str(account_id))],partner=str(account_id),
    people=[dict(id=str(account_id),name=self.name_of(str(account_id)))],kind='direct',named=False,favourite=False,muted=False,read_uid='',last='',last_from='',at=self.clock(),uid='',unread=False))
  else:gid=group['id']
  with self.lock:self.thread_id=gid;self.messages=[];self.reactions={}
  self.due['thread']=0
