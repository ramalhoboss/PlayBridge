"""The Friends page and the PlayStation Network card in Settings, in words: plain functions of psn_link.Psn.view(), so they are tested
without a window. picture(name) turns a picture kept beside the friends' names into an address Qt can show ('' when there is none)."""
import re,time
from pathlib import Path
from urllib.parse import quote
from psn_link import DELETE_WITHIN,MOST_MEMBERS

FILTERS=('All','Online','Favourites')
# Before the sign-in ends, Settings says how many days are left.
ENDS_SOON_DAYS=7

def ago(seconds):
 if seconds<90:return 'just now'
 minutes=seconds/60
 if minutes<60:return f'{round(minutes)} min ago'
 hours=minutes/60
 if hours<24:return f'{round(hours)} h ago'
 days=round(hours/24)
 if days<2:return 'yesterday'
 return f'{days} days ago' if days<31 else 'over a month ago'

def clock(at,now):
 """When a message came: the time today, Yesterday, or the day."""
 if not at:return ''
 there=time.localtime(at);today=time.localtime(now)
 if there[:3]==today[:3]:return time.strftime('%H:%M',there)
 if time.strftime('%Y%m%d',time.localtime(now-86400))==time.strftime('%Y%m%d',there):return 'Yesterday'
 return time.strftime('%d %b',there).lstrip('0')

PLATFORMS=dict(PS5='PS5',PS4='PS4',MOBILE_APP='PlayStation App',PSPC='PC')
def friend_line(friend,now):
 where=friend.get('platform') or '';where=PLATFORMS.get(where,where)
 if friend.get('online') and friend.get('game'):return f"Playing {friend['game']}"+(f' · {where}' if where else '')
 if friend.get('online'):return 'Online'+(f' · {where}' if where else '')
 if friend.get('last'):return f"Last online {ago(max(0,now-friend['last']))}"
 return 'Offline'

def tone(friend):return 'playing' if friend.get('online') and friend.get('game') else 'online' if friend.get('online') else 'off'

# Play this too: the game a friend plays, found among the console's games by its title id, or by its name when the two players have
# different versions of it (the PS4 one and the PS5 one). A game not on the console is searched for in the PlayStation Store instead.
STORE_SEARCH='https://store.playstation.com/search/'
def plain_name(name):
 words=re.sub(r'[^0-9a-z]+',' ',re.sub('[™®©]','',str(name or '').lower())).split()
 return ' '.join(word for word in words if word not in ('ps4','ps5','edition'))
def play_too(friend,games,running=''):
 """What can be done with the game a friend plays: {kind: play|running|store, title, game, tip}, or None when they play nothing.
 games: the console's games [{title, name}]; running: the title open on the PS5."""
 game=friend.get('game') or ''
 if not friend.get('online') or not game:return None
 wanted=str(friend.get('title_id') or '')[:9];name=plain_name(game)
 found=next((g for g in games or [] if not g.get('app') and g.get('title')==wanted),None) if wanted else None
 if found is None and name:found=next((g for g in games or [] if not g.get('app') and plain_name(g.get('name'))==name),None)
 if found is None:return dict(kind='store',title='',game=game,tip=f'Find {game} in the PlayStation Store')
 if found['title']==running:return dict(kind='running',title=found['title'],game=game,tip=f'You are playing {game} too')
 return dict(kind='play',title=found['title'],game=game,tip=f'Play {game} too')
def store_url(game):return STORE_SEARCH+quote(' '.join(str(game or '').split()))

# Where a player found by online ID stands with the player, and what can be done about it: (words, [(action, label, tone)]).
RELATIONS=dict(none=('Not your friend yet',[('add','Send friend request','main')]),sent=('You sent them a friend request',[('cancel','Take back request','plain')]),
 received=('Wants to be your friend',[('accept','Accept','main'),('decline','Decline','plain')]),friend=('Your friend',[('message','Message','main'),('remove','Remove friend','plain')]),
 me=('This is you',[]))
# A result line about a friend change stays this long, in seconds.
LINE_SECONDS=90

def person(p,picture,line,asking=()):
 name=p.get('name') or ''
 return dict(id=p['id'],name=name or 'Loading…',initial=(name or '?')[:1].upper(),picture=picture(p.get('picture')),known=bool(name),line=line,busy=p['id'] in asking)

def plays_for(seconds):
 seconds=max(0,round(seconds or 0));return f'{seconds//60}:{seconds%60:02d}' if seconds else ''

def message_row(message,now,before,chat,playing='',fetching='',changing=''):
 """One message of the open conversation: its words, or its picture, sticker, GIF, voice message or video, or a note of the group;
 the reactions on it, and what can be done to it (PSN deletes only the player's own, in the DELETE_WITHIN seconds after sending)."""
 kind=message.get('kind') or 'text';media=message.get('media') or {};kept=message.get('file')
 row=dict(id=message.get('id',''),text=message.get('text',''),mine=bool(message.get('mine')),who=message.get('who',''),when=clock(message.get('at'),now),
  first=message.get('who')!=before and kind!='note',kind=kind,image='',state='',length=plays_for(media.get('seconds')))
 left=DELETE_WITHIN-(now-(message.get('at') or 0)) if message.get('at') else -1
 row.update(reactions=[dict(id=r['id'],emoji=r.get('emoji') or '',picture=chat(r['file']) if r.get('file') else '',count=r.get('count',0),mine=bool(r.get('mine'))) for r in message.get('reactions') or [] if r.get('emoji') or r.get('file')],
  canReact=bool(row['id']) and kind!='note',canDelete=row['mine'] and bool(row['id']) and kind!='note' and left>0,canHide=bool(row['id']),busy=bool(row['id']) and changing==row['id'],
  deleteTip=f'Delete for everyone · {max(1,round(left/60))} min left' if left>0 else '')
 if kind in ('picture','gif','sticker'):
  row['image']=chat(kept) if kept else '';row['state']='ready' if row['image'] else 'gone' if kept=='' else 'loading'
  # Once here, the picture shows with the words the sender wrote under it, if any.
  row['text']={'gone':'PSN did not send this picture. It may be too old.','loading':'Getting the picture…'}.get(row['state'],message.get('caption') or '')
 elif kind in ('voice','video'):
  row['state']='getting' if fetching==row['id'] else 'playing' if playing==row['id'] else ''
  row['text']=('Voice message' if kind=='voice' else 'Video')+(f' · {row["length"]}' if row['length'] else '')
 # Words go to the clipboard as words, a still picture as a picture; any picture here can be saved to a file.
 row['canCopy']=kind=='text' and bool(row['text']) or row['state']=='ready' and kind in ('picture','sticker')
 row['canSave']=row['state']=='ready'
 if row['canSave']:row['saveName']='PSN picture '+time.strftime('%Y-%m-%d %H.%M',time.localtime(message.get('at') or now))+(Path(kept).suffix or '.png')
 return row
def fresh_line(line,now):
 return dict(text=line['text'],tone=line.get('tone','plain')) if (line or {}).get('text') and now-(line.get('at') or now)<LINE_SECONDS else None
def face(person,friends):
 known=friends.get(person.get('id')) or {};name=person.get('name') or known.get('name') or ''
 return dict(id=person.get('id',''),name=name or 'Player',initial=(name or '?')[:1].upper(),picture=known.get('picture',''),line=known.get('line',''),tone=known.get('tone','off'))

def page(view,now,chosen='All',picture=lambda name:'',running='',chat=lambda name:'',playing='',games=(),running_title=''):
 """What the Friends page shows. The player at the top stands as in the top bar (standing), running being the game open on the PS5.
 chat turns a kept picture of a conversation into an address Qt shows; playing is the voice message playing now. games are the
 console's games and running_title the one open, for Play this too."""
 voice=playing
 me=view.get('me') or {};mine=(me.get('name') or '').lower();friends=view.get('friends') or []
 rows=[dict(id=f['id'],name=f.get('name') or 'Loading…',initial=(f.get('name') or '?')[:1].upper(),line=friend_line(f,now),tone=tone(f),picture=picture(f.get('picture')),
  favourite=bool(f.get('favourite')),known=bool(f.get('name')),playToo=play_too(f,games,running_title)) for f in friends]
 online=sum(1 for row in rows if row['tone']!='off');playing=sum(1 for row in rows if row['tone']=='playing')
 shown=[row for row in rows if chosen=='All' or chosen=='Online' and row['tone']!='off' or chosen=='Favourites' and row['favourite']]
 asking=set(view.get('asking') or [])
 requests=[dict(person(p,picture,'Wants to be your friend',asking),kind='received') for p in view.get('received') or []]
 requests+=[dict(person(p,picture,'You sent a friend request',asking),kind='sent') for p in view.get('sent') or []]
 shown_requests=requests if chosen=='All' else []
 empty=''
 if not rows and not shown_requests:empty='Loading your friends…' if view.get('state')=='on' and not view.get('updated') else 'You have no friends on PSN yet. Select Add friend to find someone by their online ID.'
 elif not rows:empty=''
 elif not shown:empty='None of your friends is online right now.' if chosen=='Online' else 'Select the star beside a friend to make them a favourite.'
  # Everyone the player can put in a conversation (their friends, names known), and each friend by account number for the faces.
 by_id={row['id']:row for row in rows if row['known']}
 everyone=sorted(([dict(id=r['id'],name=r['name'],initial=r['initial'],picture=r['picture'],line=r['line'],tone=r['tone']) for r in by_id.values()]),key=lambda f:f['name'].lower())
 groups=[]
 for group in view.get('groups') or []:
  last=group.get('last') or ''
  if last and (group.get('last_from') or '').lower()==mine:last='You: '+last
  people=[face(p,by_id) for p in group.get('people') or []]
  groups.append(dict(id=group['id'],name=group.get('name') or 'Conversation',last=last,when=clock(group.get('at'),now),unread=bool(group.get('unread')),
   kind=group.get('kind','direct'),favourite=bool(group.get('favourite')),muted=bool(group.get('muted')),faces=people[:2],more=max(0,len(people)-2)))
 thread=None
 if view.get('thread'):
  name=next((g['name'] for g in groups if g['id']==view['thread']),'Conversation');messages=[];before=None
  changing=view.get('changing') or ''
  for message in view.get('messages') or []:
   messages.append(message_row(message,now,before,chat,voice,view.get('fetching',''),changing))
   if message.get('kind')!='note':before=message.get('who')
  sent=view.get('send_line') or {}
  group=next((g for g in view.get('groups') or [] if g['id']==view['thread']),{});kind=group.get('kind','direct')
  people=[face(p,by_id) for p in group.get('people') or []];inside={p['id'] for p in people}
  partner=people[0] if kind=='direct' and people else None
  if kind=='group':about=f'{len(people)+1} people'+(' · Muted' if group.get('muted') else '');about_tone='off'
  else:about=(partner or {}).get('line','')+(' · Muted' if group.get('muted') else '');about_tone=(partner or {}).get('tone','off')
  thread=dict(id=view['thread'],name=name,messages=messages,loading=not messages,
   sendLine=dict(text=sent['text'],tone=sent.get('tone','plain')) if sent.get('text') and now-(sent.get('at') or now)<LINE_SECONDS else None,
   kind=kind,favourite=bool(group.get('favourite')),muted=bool(group.get('muted')),people=people,about=about.strip(' ·'),aboutTone=about_tone,
   canRename=kind=='group',canLeave=kind=='group',canRemove=kind=='group',named=bool(group.get('named')),
   invitable=[f for f in everyone if f['id'] not in inside][:max(0,MOST_MEMBERS-1-len(people))],
   chatLine=fresh_line(view.get('chat_line'),now),busy=bool(changing),reactionsReady=bool(view.get('reactions_ready')),
   reactionKinds=[dict(id=k['id'],emoji=k.get('emoji') or '',picture=chat(k['file']) if k.get('file') else '') for k in view.get('reaction_kinds') or [] if k.get('emoji') or k.get('file')])
 summary=f'{online} friend{"s" if online!=1 else ""} online · {playing} playing' if rows else ''
 stand=standing(view,running)
 # The add-friend card: what was asked, PSN's answer, and the player found with what can be done.
 found=view.get('finding') or {};line=view.get('friend_line') or {};fresh=bool(line.get('text')) and now-(line.get('at') or now)<LINE_SECONDS
 who=None
 if found.get('id'):
  words,actions=RELATIONS.get(found.get('relation'),RELATIONS['none'])
  who=dict(person(dict(id=found['id'],name=found.get('name'),picture=found.get('picture')),picture,words,asking),actions=[dict(kind=k,label=l,tone=t) for k,l,t in actions])
 find=dict(state=found.get('state',''),asked=found.get('asked',''),text=found.get('text',''),tone=found.get('tone','plain'),person=who,
  line=dict(text=line['text'],tone=line.get('tone','plain')) if fresh and who and line.get('id')==who['id'] else None)
 return dict(state=view.get('state','out'),problem=view.get('problem',''),friends=shown,filter=chosen,requests=shown_requests,requestCount=len(view.get('received') or []),
  requestsProblem=view.get('requests_problem',''),find=find,friendLine=dict(text=line['text'],tone=line.get('tone','plain')) if fresh else None,
  me=dict(name=me.get('name',''),picture=picture(me.get('picture')),line=stand['detail'],tone=stand['tone'],why=stand['why']),
  filters=list(FILTERS),summary=summary,empty=empty,groups=groups,thread=thread,sending=bool(view.get('sending')),unread=sum(1 for g in groups if g['unread']),count=len(rows),playing=voice,
  everyone=everyone,chatLine=fresh_line(view.get('chat_line'),now),changing=bool(view.get('changing')))

def settings(view,wants,problem,now):
 """The PlayStation Network card in Settings › Connections."""
 state=view.get('state','out');me=view.get('me') or {};friends=view.get('friends') or []
 if state=='on':
  online=sum(1 for f in friends if f.get('online'))
  text=f"Signed in as {me.get('name') or 'your account'}."+(f' {len(friends)} friends, {online} online.' if friends else '');tone='news'
  until=view.get('signed_until') or 0;left=(until-now)/86400
  if until and left<ENDS_SOON_DAYS:text+=f' Your sign-in ends in {max(1,round(left))} day{"s" if round(left)!=1 else ""}: paste a new code before then.'
 elif state=='signing':text,tone='Signing in…','plain'
 elif state=='expired':text,tone='Your PSN sign-in has ended. Sign in on playstation.com again and paste a new code.','error'
 else:text,tone='Not signed in.','plain'
 shown=problem or view.get('problem') or ''
 return dict(psnState=dict(text=text,tone=tone),psnOn=state=='on',psnSigning=state=='signing',psnProblem=shown,psnOnline=bool(wants.get('online',True)),
  psnGames=bool(wants.get('games',False)),psnMessages=bool(wants.get('messages',True)),psnRequests=bool(wants.get('requests',True)),psnFavsOnly=bool(wants.get('favourites_only',False)),psnWatch=wants.get('watch',''))

OFFLINE_WHY='Your friends see you offline too. You show online while a PlayStation of yours is signed in to PSN, unless it is set to appear offline.'
def elsewhere_why(running,where):
 return f'Your friends see you online{" in the " + where if where=="PlayStation App" else " on " + where if where else ""}, not {running}: a game on your PS5 shows to them only while that PS5 is signed in to PSN.'
def standing(view,running=''):
 """How the player stands on PSN, the one answer the top bars and the Friends page both show, so they never disagree. The tone (the
 green dot) is PSN's own word for the player's account, which is what friends see; it is never assumed. running, the game open on the
 PS5 PlayBridge is linked to, names what is played when PSN does not, without making the player online: a PS5 that is not signed in to
 PSN shows offline there. line is short, for the top bar; detail is the Friends page's; why says what offline means there."""
 state=view.get('state','out');mine=view.get('presence')
 if state=='signing':return dict(line='Signing in…',detail='Signing in to PSN…',tone='off',why='')
 if not mine:return dict(line='Signed in',detail='Signed in · waiting for PSN',tone='off',why='')
 where=PLATFORMS.get(mine.get('platform') or '',mine.get('platform') or '');on=f' · {where}' if where else ''
 if mine.get('online'):
  game=mine.get('game')
  if game:return dict(line='Playing '+game,detail='Playing '+game+on,tone='playing',why='')
  return dict(line='Online',detail='Online'+on,tone='online',why=elsewhere_why(running,where) if running else '')
 if running:return dict(line='Playing '+running,detail=f'Playing {running} · offline on PSN',tone='off',why=OFFLINE_WHY)
 return dict(line='Offline',detail='Offline on PSN',tone='off',why=OFFLINE_WHY)
def chip(view,running='',picture=lambda name:''):
 """The player in the top bar: picture, name and how they stand on PSN (standing), or a way to sign in."""
 state=view.get('state','out');me=view.get('me') or {}
 if state in ('out','expired'):return dict(state=state,name='PSN',line='Sign in' if state=='out' else 'Sign in again',tone='off',picture='',initial='',plus=False)
 name=me.get('name') or 'PSN';stand=standing(view,running)
 return dict(state=state,name=name,line=stand['line'],tone=stand['tone'],picture=picture(me.get('picture')),initial=name[:1].upper(),plus=bool(me.get('plus')))
def menu_items(view,level=0):
 """The PSN menu under the player's picture: (key, label) or (key, label, how it stands), in the order shown."""
 state=view.get('state','out')
 if state!='on':return [('psn_settings','Sign in to PSN' if state in ('out','expired') else 'PSN settings')]
 friends=view.get('friends') or [];online=sum(1 for friend in friends if friend.get('online'));unread=sum(1 for group in view.get('groups') or [] if group.get('unread'))
 def row(key,label,mark):return (key,label,mark) if mark else (key,label)
 waiting=len(view.get('received') or [])
 return [row('psn_friends','Friends',f'{waiting} request{"s" if waiting!=1 else ""}' if waiting else f'{online} online' if friends else ''),row('psn_messages','Messages',f'{unread} new' if unread else ''),
  row('psn_trophies','Trophies',f'Level {level}' if level else ''),('psn_settings','PSN settings'),('psn_refresh','Refresh'),('psn_sign_out','Sign out')]
def wants_from(saved):
 """The alerts the player chose, from the settings file."""
 watch=saved.get('psn_watch','XPS5')
 return dict(online=bool(saved.get('psn_online',True)),games=bool(saved.get('psn_games',False)),messages=bool(saved.get('psn_messages',True)),requests=bool(saved.get('psn_requests',True)),
  watch=watch if isinstance(watch,str) else 'XPS5',favourites_only=bool(saved.get('psn_favourites_only',False)))

def favourites_from(saved):
 kept=saved.get('psn_favourites',[])
 return {str(key) for key in kept if str(key).isdigit()} if isinstance(kept,list) else set()
