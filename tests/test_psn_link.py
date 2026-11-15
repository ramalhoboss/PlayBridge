"""PlayStation Network: the pasted code is traded for tokens and forgotten, the refresh token is renewed and dropped when Sony ends it,
friends and their presence are read with alerts only for what changed, messages are read, sent and alerted, and the budget holds."""
import re
import json,shutil,sys,tempfile,unittest,urllib.parse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import psn_link

CODE='A'*64
PNG=b'\x89PNG\r\n\x1a\nfake'

class FakeSony:
 """Answers like Sony's sign-in and API servers, and writes down every request."""
 def __init__(self):
  self.requests=[];self.code_ok=True;self.refresh_ok=True;self.presence={};self.friends=['111','222','333'];self.groups=[];self.messages={};self.sent=[];self.created=[];self.limited=False
  self.names={'111':'NightOwl','222':'ModSquad','333':'Viewer42','900':'Player1','444':'Stranger7','555':'Asker','666':'Newbie'}
  # Friend requests either way, every change asked for (method, number, body), and an answer to give the next change instead of 204.
  self.received=[];self.sent_requests=[];self.changes=[];self.change_answer=None;self.requests_refused=False
  # A group's resources: pictures and recordings by resource id; 'moved' answers with an address elsewhere.
  self.resources={'r1':PNG,'v1':b'OggS-voice'}
  # Pictures sent up as resources (headers, bytes), and the answer to give: the new resource's name, or (status, body) for a refusal
  # (a body of bytes goes as it is, as a gateway's own error page does); message_answer, when set, refuses a message the same way.
  self.uploads=[];self.upload_answer=dict(resourceId='up1');self.message_answer=None
  # The rest of a conversation: every change asked for (method, path under the API, body, query), the answer to give the next one
  # instead of 204 ((status, body)), the reactions Sony offers by version, the reactions on messages, and whether the newer delete is known.
  self.chat_changes=[];self.chat_answer=None;self.reaction_defs={'unicode':{'1':dict(unicode='1F44D',url='https://image.example/r1.png'),'2':dict(unicode='2764 FE0F'),'7':dict(url='https://image.example/r7.png')}}
  self.reaction_state=[];self.newer_delete=True;self.invite_answer=dict(hasAllAccountInvited=True)
 def __call__(self,method,url,headers,body):
  self.requests.append((method,url,headers,body));parts=urllib.parse.urlsplit(url);path=parts.path;query=urllib.parse.parse_qs(parts.query)
  def answer(data,status=200):return status,{},data if isinstance(data,bytes) else json.dumps(data).encode()
  if path.endswith('/oauth/authorize'):
   if headers.get('Cookie')!='npsso='+CODE or not self.code_ok:return 302,{'location':'com.scee.psxandroid.scecompcall://redirect/?error=login_required&error_code=4165'},b''
   return 302,{'location':'com.scee.psxandroid.scecompcall://redirect/?code=v3.ABCDEF&cid=x'},b''
  if path.endswith('/oauth/token'):
   form=urllib.parse.parse_qs(body.decode())
   if form['grant_type']==['authorization_code']:return answer(dict(access_token='access-1',expires_in=3600,refresh_token='refresh-1',refresh_token_expires_in=5184000))
   if not self.refresh_ok:return answer({'error':'invalid_grant'},400)
   return answer(dict(access_token='access-2',expires_in=3600))
  if headers.get('Authorization','').startswith('Bearer ')is False and 'm.np.playstation.com' in url:return answer({},401)
  if self.limited and 'm.np.playstation.com' in url:return 429,{'retry-after':'120'},b''
  if parts.netloc=='dms.api.playstation.com' and path=='/api/v1/devices/accounts/me':return answer(dict(accountId='900',region='PT',language='pt'))
  if path.endswith('/users/me/profiles'):return answer(dict(error=dict(referenceId='x',code=2240513,message='Bad request: invalid accountId')),400)
  if path.endswith('/users/900/profiles'):return answer(dict(onlineId='Player1',avatars=[dict(size='s',url='http://image.example/me-s.png'),dict(size='l',url='http://image.example/me-l.png')]))
  if path.endswith('/users/me/friends'):return answer(dict(friends=self.friends))
  if path.endswith('/users/me/friends/receivedRequests'):
   if self.requests_refused:return answer({'error':'not here'},404)
   return answer(dict(receivedRequests=[dict(accountId=key) for key in self.received]))
  if path.endswith('/users/me/friends/sentRequests'):return answer(dict(sentRequests=[dict(accountId=key) for key in self.sent_requests]))
  if '/users/me/friends/' in path and method in ('POST','PUT','DELETE'):
   key=path.rsplit('/',1)[1];self.changes.append((method,key,json.loads(body) if body else None))
   if self.change_answer:status,raw=self.change_answer;return status,{},raw
   return 204,{},b''
  if parts.netloc=='us-prof.np.community.playstation.net' and path.endswith('/profile2'):
   wanted=urllib.parse.unquote(path.split('/')[-2]);key=next((k for k,v in self.names.items() if v.lower()==wanted.lower()),None)
   if key is None:return answer(dict(error=dict(code=2105356,message='User not found')),404)
   return answer(dict(profile=dict(onlineId=self.names[key],accountId=key,avatarUrls=[dict(size='l',avatarUrl=f'http://image.example/{key}.png')],friendRelation='friend' if key in self.friends else 'no')))
  if '/gamingLoungeGroups/v1/groups/' in path and path.endswith('/resources') and method=='POST':
   self.uploads.append((headers,body))
   if isinstance(self.upload_answer,dict):return answer(self.upload_answer)
   return answer(self.upload_answer[1],self.upload_answer[0])
  if '/gamingLoungeGroups/v1/groups/' in path and '/resources/' in path:
   rid=path.rsplit('/',1)[1]
   if rid=='moved':return 302,{'location':'https://cdn.example/picture.jpg'},b''
   return (200,{},self.resources[rid]) if rid in self.resources else answer({'error':'gone'},404)
  if url=='https://cdn.example/picture.jpg':return 200,{},b'\xff\xd8\xff\xe0jpeg'
  if url=='https://cdn.example/sticker.png':return 200,{},PNG
  if path.endswith('/profiles'):
   key=path.split('/')[-2];return answer(dict(onlineId=self.names[key],avatars=[dict(size='m',url=f'https://image.example/{key}.png')]))
  if path.endswith('/basicPresences'):
   ids=query['accountIds'][0].split(',')
   return answer(dict(basicPresences=[dict(accountId=key,**self.presence.get(key,dict(availability='unavailable',primaryPlatformInfo=dict(onlineStatus='offline',platform='PS5',lastOnlineDate='2026-11-14T10:00:00Z')))) for key in ids]))
  if '/gamingLoungeGroups/' in path and '/reactions/' in path and path.endswith('/definitions'):
   version=path.split('/')[-2];return answer(self.reaction_defs[version]) if version in self.reaction_defs else answer({'error':'no'},404)
  # Sony allows no POST on a message itself (what a reaction sent to an address cut at the message id's '#' became).
  if method=='POST' and '/gamingLoungeGroups/' in path and re.search(r'/messages/[^/]+$',path):return answer(dict(error=dict(code=2285701,message='Method Not Allowed')),405)
  if '/members/me/groups/' in path and path.endswith('/reactions') and '/messages/' not in path:
   self.chat_changes.append((method,path.split('/api',1)[1],json.loads(body) if body else None,query));return answer(self.reaction_state)
  if '/gamingLoungeGroups/' in path and (method in ('PATCH','DELETE','PUT') or method=='POST' and (path.endswith(('/typing','/invitees')) or '/reactions' in path)):
   if method=='DELETE' and '/v2/' in path and not self.newer_delete:return answer({'error':'not here'},404)
   self.chat_changes.append((method,path.split('/api',1)[1],json.loads(body) if body else None,query))
   if self.chat_answer:status,raw=self.chat_answer;self.chat_answer=None;return status,{},raw
   if path.endswith('/invitees'):return answer(self.invite_answer)
   return 204,{},b''
  if path.endswith('/members/me/groups'):return answer(dict(groups=self.groups))
  if '/members/me/groups/' in path and path.endswith('/messages'):return answer(dict(messages=self.messages.get(path.split('/')[-4],[])))
  if path.endswith('/messages') and method=='POST':
   self.sent.append((path,json.loads(body)))
   if self.message_answer:return answer(self.message_answer[1],self.message_answer[0])
   return answer(dict(messageUid='9',createdTimestamp='1763200000000'))
  if path.endswith('/gamingLoungeGroups/v1/groups') and method=='POST':self.created.append(json.loads(body));return answer(dict(groupId='g-new',mainThread=dict(threadId='g-new')))
  if url.startswith('https://image.example/'):return 200,{},PNG
  return answer({'error':'not here'},404)
 def online(self,key,game=None):
  self.presence[key]=dict(availability='availableToPlay',primaryPlatformInfo=dict(onlineStatus='online',platform='PS5'),gameTitleInfoList=[dict(npTitleId='PPSA1',titleName=game)] if game else [])
 def group(self,gid,members,uid,sender,body,read=None):
  return dict(groupId=gid,groupName=dict(value=''),members=[dict(accountId=k,onlineId=self.names[k]) for k in members],
   mainThread=dict(threadId=gid,readMessageUid=read,latestMessage=dict(messageUid=uid,messageType=1,body=body,createdTimestamp='1763200000000',sender=dict(onlineId=self.names[sender]))))

class Clock:
 def __init__(self):self.now=1_000_000.0
 def __call__(self):return self.now

class PsnTests(unittest.TestCase):
 def setUp(self):
  self.folder=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,self.folder,True)
  self.sony=FakeSony();self.clock=Clock();self.saved=[]
  self.psn=psn_link.Psn(self.folder/'psn',save_token=lambda token,until:self.saved.append((token,until)),opener=self.sony,clock=self.clock)
 def signed_in(self):
  self.assertEqual(self.psn.sign_in(CODE),'');self.psn.do(self.psn.jobs.get_nowait());return self.psn
 def test_the_profile_is_asked_for_by_account_number(self):
  psn=self.signed_in();asked=[url for _,url,_,_ in self.sony.requests]
  self.assertIn(psn_link.ACCOUNT,asked);self.assertFalse(any('/users/me/profiles' in url for url in asked),'Sony answers 400 to "me" there')
  self.assertTrue(any(url.endswith('/users/900/profiles') for url in asked));self.assertEqual(psn.view()['problem'],'')
  self.clock.now+=psn_link.FRIENDS_EVERY+1;psn.me={};psn.read_friends()
  self.assertEqual([url for _,url,_,_ in self.sony.requests].count(psn_link.ACCOUNT),1,'the account number is asked for once a sign-in')
 def test_a_refusal_says_what_was_asked_for(self):
  psn=self.signed_in();original=self.sony.__class__.__call__
  def odd(sony,method,url,headers,body):
   if url.split('?')[0].endswith('/users/me/friends'):return 400,{},b'{}'
   return original(sony,method,url,headers,body)
  self.sony.__class__.__call__=odd;self.addCleanup(setattr,self.sony.__class__,'__call__',original)
  with self.assertRaises(psn_link.Problem) as caught:psn.read_friends()
  self.assertIn('400 when asked for your friends list',str(caught.exception))
 def test_pictures_come_over_https_follow_moves_and_fall_back(self):
  seen=[]
  def opener(method,url,headers,body):
   seen.append(url)
   if url=='https://a.example/p.png':return 302,{'location':'/q.png'},b''
   if url=='https://a.example/q.png':return 200,{},PNG
   if url.startswith('https://b.example/'):raise OSError('no https here')
   if url=='http://b.example/p.jpg':return 200,{},b'\xff\xd8\xff\xe0jpeg'
   if url=='https://c.example/web.png':return 200,{},b'RIFF\0\0\0\0WEBP'
   return 404,{},b''
  self.assertEqual(psn_link.get_picture(opener,'http://a.example/p.png'),(PNG,'.png'));self.assertEqual(seen,['https://a.example/p.png','https://a.example/q.png'])
  self.assertEqual(psn_link.get_picture(opener,'http://b.example/p.jpg')[1],'.jpg','https that fails falls back to the address Sony gave')
  self.assertEqual(psn_link.get_picture(opener,'https://c.example/web.png'),(b'',''),'only PNG and JPEG are kept');seen.clear()
  self.assertEqual(psn_link.get_picture(opener,'https://c.example/none.png'),(b'',''));self.assertEqual(seen,['https://c.example/none.png'],'an https address is not tried as http')
  self.assertEqual(psn_link.get_picture(opener,'ftp://x.example/y.png'),(b'',''))
  self.assertEqual(psn_link.get_picture(opener,'http://a.example/p.png',most=4),(b'',''),'a picture over the limit is not kept')
 def test_a_missing_picture_of_mine_is_asked_for_again(self):
  original=self.sony.__class__.__call__;down=[True]
  def flaky(sony,method,url,headers,body):
   if 'image.example/me' in url and down[0]:raise OSError('image server down')
   return original(sony,method,url,headers,body)
  self.sony.__class__.__call__=flaky;self.addCleanup(setattr,self.sony.__class__,'__call__',original)
  psn=self.signed_in();self.assertNotIn('picture',psn.view()['me'])
  down[0]=False;psn.read_friends();self.assertEqual(psn.view()['me']['picture'],'me.png')
 def test_a_friend_sony_keeps_back_does_not_stop_the_others(self):
  psn=self.signed_in();psn.read_friends();original=self.sony.__class__.__call__
  def odd(sony,method,url,headers,body):
   if url.endswith('/users/111/profiles'):return 403,{},b'{}'
   return original(sony,method,url,headers,body)
  self.sony.__class__.__call__=odd;self.addCleanup(setattr,self.sony.__class__,'__call__',original)
  psn.read_profiles()
  self.assertEqual((psn.name_of('222'),psn.name_of('333')),('ModSquad','Viewer42'));self.assertEqual(psn.name_of('111'),'')
  self.assertTrue((self.folder/'psn'/'profiles.json').is_file())
 def test_the_code_is_found_in_what_was_pasted(self):
  self.assertEqual(psn_link.npsso_from('  '+CODE+'\n'),CODE);self.assertEqual(psn_link.npsso_from('{"npsso":"'+CODE+'"}'),CODE)
  self.assertIsNone(psn_link.npsso_from('A'*63));self.assertIsNone(psn_link.npsso_from('password123'))
  self.assertIn('not the code',self.psn.sign_in('hello'));self.assertEqual(self.psn.view()['state'],'out')
 def test_sign_in_keeps_only_the_refresh_token(self):
  psn=self.signed_in()
  self.assertEqual(self.saved,[('refresh-1',self.clock.now+5184000)]);self.assertEqual(psn.view()['state'],'on');self.assertEqual(psn.view()['me']['name'],'Player1')
  authorize=self.sony.requests[0];self.assertNotIn('follow',authorize[1]);self.assertIn('access_type=offline',authorize[1]);self.assertEqual(authorize[2]['Cookie'],'npsso='+CODE)
  token=self.sony.requests[1];self.assertEqual(token[2]['Authorization'],psn_link.BASIC);self.assertNotIn(CODE.encode(),token[3])
  # Nothing PlayBridge keeps on disk holds the code.
  for path in self.folder.rglob('*'):
   if path.is_file():self.assertNotIn(CODE.encode(),path.read_bytes())
  self.assertTrue((self.folder/'psn'/'pictures'/'me.png').is_file())
 def test_a_refused_code_says_so(self):
  self.sony.code_ok=False;self.psn.sign_in(CODE)
  with self.assertRaises(psn_link.Problem) as caught:self.psn.do(self.psn.jobs.get_nowait())
  self.assertIn('did not take that code',str(caught.exception));self.assertEqual(self.psn.view()['state'],'out');self.assertEqual(self.saved,[])
 def test_the_access_token_is_renewed_and_an_ended_sign_in_is_dropped(self):
  psn=self.signed_in();self.clock.now+=3600
  psn.read_friends();self.assertEqual(psn.access,'access-2');self.assertEqual(self.sony.requests[-1][2]['Authorization'],'Bearer access-2')
  self.sony.refresh_ok=False;self.clock.now+=3600
  with self.assertRaises(psn_link.SignedOut) as caught:psn.read_friends()
  self.assertIn('ended',str(caught.exception));self.assertEqual(self.saved[-1],(None,0));self.assertIsNone(psn.refresh)
 def test_friends_presence_and_alerts_only_for_what_changed(self):
  psn=self.signed_in();psn.wants=dict(online=True,games=True,messages=True,watch='XPS5, elden',favourites_only=False)
  self.sony.online('111','Astro Bot');psn.read_friends();psn.read_profiles();psn.read_presence()
  self.assertEqual(psn.take_alerts(),[],'the first reading only sets where things stand')
  view=psn.view();self.assertEqual([f['name'] for f in view['friends']],['NightOwl','ModSquad','Viewer42']);self.assertEqual(view['friends'][0]['game'],'Astro Bot')
  self.assertTrue(view['friends'][0]['picture'].endswith('.png'));self.assertGreater(view['friends'][1]['last'],0)
  self.sony.online('222');self.sony.online('333','XPS5');self.sony.online('111','ELDEN RING NIGHTREIGN');psn.read_presence()
  self.assertEqual(sorted(kind for kind,title,text in psn.take_alerts()),['online','watch','watch'])
  psn.read_presence();self.assertEqual(psn.take_alerts(),[],'nothing changed')
  psn.wants=dict(psn.wants,favourites_only=True);psn.favourites={'222'};self.sony.presence.pop('222');psn.read_presence();self.sony.online('222','Astro Bot');self.sony.online('333','Hades II');psn.read_presence()
  self.assertEqual(psn.take_alerts(),[('online','ModSquad is online','Playing Astro Bot on PS5.')])
 def test_a_broken_answer_never_ends_the_thread(self):
  import http.client,time
  psn=self.signed_in();original=self.sony.__class__.__call__
  def broken(sony,method,url,headers,body):
   if '/friends' in url:raise http.client.IncompleteRead(b'')
   return original(sony,method,url,headers,body)
  self.sony.__class__.__call__=broken;self.addCleanup(setattr,self.sony.__class__,'__call__',original)
  psn.due={key:0 for key in psn.due};psn.start();self.addCleanup(psn.stop);end=time.monotonic()+5
  while 'cannot be reached' not in psn.view()['problem'] and time.monotonic()<end:time.sleep(0.02)
  self.assertIn('cannot be reached',psn.view()['problem']);self.assertTrue(psn.thread.is_alive())
 def test_my_own_state_rides_with_the_friends(self):
  psn=self.signed_in();psn.read_friends();self.sony.online('900','Astro Bot');psn.read_presence()
  view=psn.view();self.assertEqual(view['presence']['game'],'Astro Bot');self.assertNotIn('900',[friend['id'] for friend in view['friends']])
  asked=[url for _,url,_,_ in self.sony.requests if '/basicPresences' in url][-1];self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(asked).query)['accountIds'],['111,222,333,900'])
  self.sony.presence.pop('900');psn.read_presence();self.assertFalse(psn.view()['presence']['online']);self.assertEqual(psn.take_alerts(),[],'the player is never an alert')
  psn.forget();self.assertIsNone(psn.view()['presence'])
 def test_messages_are_read_sent_and_alerted(self):
  psn=self.signed_in()
  self.sony.groups=[self.sony.group('g1',['900','111'],'u1','111','hi there',read='u1')];self.sony.messages['g1']=[dict(messageUid='u1',messageType=1,body='hi there',createdTimestamp='1763200000000',sender=dict(onlineId='NightOwl')),
   dict(messageUid='u0',messageType=1013,body='',messageDetail=dict(stickerMessageDetail=dict(packageId='p',imageUrl='https://cdn.example/sticker.png')),createdTimestamp='1763100000000',sender=dict(onlineId='Player1'))]
  psn.read_groups();self.assertEqual(psn.take_alerts(),[]);group=psn.view()['groups'][0];self.assertEqual((group['name'],group['partner'],group['unread']),('NightOwl','111',False))
  self.sony.groups=[self.sony.group('g1',['900','111'],'u2','111','want to play?',read='u1')];psn.read_groups()
  self.assertEqual(psn.take_alerts(),[('message','NightOwl on PSN','want to play?')]);self.assertTrue(psn.view()['groups'][0]['unread'])
  psn.do(('open','g1'));self.assertFalse(psn.view()['groups'][0]['unread']);psn.read_thread()
  messages=psn.view()['messages'];self.assertEqual([m['mine'] for m in messages],[True,False]);self.assertEqual(messages[0]['text'],'Sent a sticker.')
  self.assertTrue(psn.send('g1','  on my way  '));psn.do(psn.jobs.get_nowait());self.assertEqual(self.sony.sent[-1][1],{'messageType':1,'body':'on my way'});self.assertFalse(psn.view()['sending'])
  self.assertEqual(psn.view()['messages'][-1]['text'],'on my way');self.assertFalse(psn.send('g1','   '))
  # A conversation with a friend: the one already there, or a new one.
  psn.do(('chat_with','111'));self.assertEqual(psn.view()['thread'],'g1');self.assertEqual(self.sony.created,[])
  psn.do(('chat_with','222'));self.assertEqual(psn.view()['thread'],'g-new');self.assertEqual(self.sony.created,[{'invitees':[{'accountId':'222'}]}])
 def test_too_many_requests_quiets_and_the_budget_holds(self):
  psn=self.signed_in();self.sony.limited=True
  with self.assertRaises(psn_link.Problem):psn.read_friends()
  self.assertEqual(psn.quiet_until,self.clock.now+120)
  budget=psn_link.Budget(most=3,window=10,clock=self.clock)
  for _ in range(3):budget.spend()
  self.assertEqual(budget.left(),0);self.clock.now+=10;self.assertEqual(budget.left(),3)
 def test_sign_out_forgets_everything(self):
  psn=self.signed_in();psn.read_friends();psn.read_profiles();self.assertTrue((self.folder/'psn'/'profiles.json').is_file())
  psn.do(('sign_out',));self.assertEqual(self.saved[-1],(None,0));self.assertFalse((self.folder/'psn').exists());view=psn.view()
  self.assertEqual((view['state'],view['friends'],view['me']),('out',[],{}))
 def test_the_thread_runs_jobs_and_polls(self):
  psn=self.signed_in();psn.focus(True);psn.start();self.addCleanup(psn.stop)
  for _ in range(100):
   if psn.view()['friends'] and psn.view()['friends'][0]['name']:break
   import time;time.sleep(.05)
  self.assertEqual(len(psn.view()['friends']),3);psn.stop();self.assertFalse(psn.thread.is_alive())

class FriendRequestTests(unittest.TestCase):
 """Finding a player by online ID, sending, accepting, declining and taking back friend requests, ending a friendship, and Sony's no."""
 def setUp(self):
  self.folder=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,self.folder,True);self.sony=FakeSony();self.clock=Clock()
  self.psn=psn_link.Psn(self.folder/'psn',token=('refresh-0',2_000_000),opener=self.sony,clock=self.clock);self.psn.read_friends();self.psn.read_profiles();self.psn.read_requests()
 def run_jobs(self):
  while not self.psn.jobs.empty():self.psn.do(self.psn.jobs.get_nowait())
 def test_a_player_is_found_by_online_id(self):
  self.psn.find('  stranger7 ');self.assertEqual(self.psn.view()['finding']['state'],'asking');self.run_jobs()
  found=self.psn.view()['finding'];self.assertEqual((found['id'],found['name'],found['relation'],found['text']),('444','Stranger7','none',''))
  asked=[url for _,url,_,_ in self.sony.requests if 'profile2' in url][-1]
  self.assertTrue(asked.startswith('https://us-prof.np.community.playstation.net/userProfile/v1/users/stranger7/profile2?fields='));self.assertTrue(self.psn.picture_of('444'),'their picture is kept')
  self.psn.find('NightOwl');self.run_jobs();self.assertEqual(self.psn.view()['finding']['relation'],'friend')
  self.psn.find('Nobody99');self.run_jobs();found=self.psn.view()['finding'];self.assertEqual(found['tone'],'error');self.assertIn('No player on PSN is called Nobody99',found['text'])
  count=len(self.sony.requests);self.psn.find('9 bad!');self.assertEqual(len(self.sony.requests),count,'a name that cannot be an online ID is never sent')
  self.assertIn('3 to 16 letters',self.psn.view()['finding']['text']);self.psn.clear_find();self.assertEqual(self.psn.view()['finding'],{})
 def test_a_request_is_sent_and_taken_back(self):
  self.psn.find('Stranger7');self.run_jobs();self.psn.befriend('add','444');self.assertEqual(self.psn.view()['asking'],['444']);self.run_jobs()
  self.assertEqual(self.sony.changes,[('POST','444',{})]);view=self.psn.view()
  self.assertEqual(([p['id'] for p in view['sent']],view['finding']['relation'],view['friend_line']['text'],view['asking']),(['444'],'sent','Friend request sent to Stranger7.',[]))
  self.psn.befriend('cancel','444');self.run_jobs();self.assertEqual(self.sony.changes[-1],('DELETE','444',None));self.assertEqual(self.psn.view()['sent'],[])
  self.assertEqual(self.psn.view()['friend_line']['text'],'You took back your friend request to Stranger7.')
  self.psn.befriend('wave','444');self.psn.befriend('add','me');self.assertTrue(self.psn.jobs.empty(),'only the five changes, only for account numbers')
 def test_requests_received_are_alerted_accepted_and_declined(self):
  self.sony.received=['555','666'];self.clock.now+=1;self.psn.read_requests()
  alerts=self.psn.take_alerts();self.assertEqual([a[:2] for a in alerts],[('request','Asker sent you a friend request'),('request','Newbie sent you a friend request')])
  self.psn.read_requests();self.assertEqual(self.psn.take_alerts(),[],'once per request')
  self.psn.befriend('accept','555');self.run_jobs();self.assertEqual(self.sony.changes[-1],('PUT','555',None));view=self.psn.view()
  self.assertEqual(([p['id'] for p in view['received']],'555' in [f['id'] for f in view['friends']]),(['666'],True));self.assertEqual(view['friend_line']['text'],'You and Asker are friends now.')
  self.psn.befriend('decline','666');self.run_jobs();self.assertEqual(self.sony.changes[-1],('DELETE','666',None));self.assertEqual(self.psn.view()['received'],[])
  self.psn.wants=dict(self.psn.wants,requests=False);self.sony.received=['444'];self.psn.read_requests();self.assertEqual(self.psn.take_alerts(),[],'the alert can be turned off')
 def test_a_friendship_ends(self):
  self.psn.befriend('remove','111');self.run_jobs();self.assertEqual(self.sony.changes[-1],('DELETE','111',None))
  self.assertNotIn('111',[f['id'] for f in self.psn.view()['friends']]);self.assertEqual(self.psn.view()['friend_line']['text'],'NightOwl is no longer your friend.')
  self.psn.profiles.pop('222');self.psn.befriend('remove','222');self.run_jobs();self.assertEqual(self.psn.view()['friend_line']['text'],'That player is no longer your friend.')
 def test_sonys_no_is_shown_in_its_own_words(self):
  self.sony.change_answer=(403,b'<HTML><HEAD><TITLE>Access Denied</TITLE></HEAD><BODY><H1>Access Denied</H1>You don\'t have permission.<P>Reference&#32;&#35;18</BODY></HTML>')
  self.psn.befriend('add','444');self.run_jobs();line=self.psn.view()['friend_line']
  self.assertEqual((line['text'],line['tone']),('PSN refused it: answer 403, "Access Denied You don\'t have permission. Reference #18".','error'))
  self.assertEqual((self.psn.view()['sent'],self.psn.view()['asking'],self.psn.view()['problem']),([],[],''))
 def test_a_refused_request_list_stays_beside_the_requests(self):
  self.sony.requests_refused=True;self.psn.read_requests();view=self.psn.view()
  self.assertIn('answer 404',view['requests_problem']);self.assertEqual(view['problem'],'','friends and messages carry on')

class ChatMediaTests(unittest.TestCase):
 """Pictures, stickers and GIFs shown in a conversation, voice messages and videos fetched when asked for, the group's own notes apart."""
 def setUp(self):
  self.folder=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,self.folder,True);self.sony=FakeSony();self.clock=Clock()
  self.psn=psn_link.Psn(self.folder/'psn',token=('refresh-0',2_000_000),opener=self.sony,clock=self.clock);self.psn.me=dict(name='Player1')
  def message(uid,at,sender,kind=1,body='',**detail):
   return dict(messageUid=uid,messageType=kind,body=body,createdTimestamp=str(1763200000000+at),sender=dict(onlineId=sender),**(dict(messageDetail=detail) if detail else {}))
  self.sony.messages['g1']=[message('n1',0,'Player1',2020,'Player1 created this group.'),message('p1',1,'NightOwl',3,imageMessageDetail=dict(resourceId='r1')),
   message('s1',2,'NightOwl',1013,stickerMessageDetail=dict(packageId='p',imageUrl='https://cdn.example/sticker.png')),message('v1',3,'NightOwl',1011,voiceMessageDetail=dict(resourceId='v1',playbackTime=12000)),
   message('m1',4,'NightOwl',3,imageMessageDetail=dict(resourceId='moved')),message('g1x',5,'NightOwl',3,imageMessageDetail=dict(resourceId='gone')),message('t1',6,'Player1',1,'hello')]
  self.psn.do(('open','g1'));self.psn.read_thread()
 def test_each_kind_shows_as_itself(self):
  messages={m['id']:m for m in self.psn.view()['messages']}
  self.assertEqual([m['kind'] for m in self.psn.view()['messages']],['note','picture','sticker','voice','picture','picture','text'])
  self.assertFalse(messages['n1']['mine'],'a note of the group is never a bubble of the player');self.assertTrue(messages['t1']['mine'])
  self.assertEqual((messages['p1']['text'],messages['s1']['text'],messages['v1']['text']),('Sent a picture.','Sent a sticker.','Sent a voice message.'))
  self.assertEqual(messages['v1']['media']['seconds'],12.0)
 def test_pictures_are_fetched_and_kept(self):
  messages={m['id']:m for m in self.psn.view()['messages']};chat=self.folder/'psn'/'chat'
  self.assertTrue(messages['p1']['file'].endswith('.png'));self.assertEqual((chat/messages['p1']['file']).read_bytes(),PNG)
  self.assertTrue(messages['m1']['file'].endswith('.jpg'),'Sony moved it to another address');self.assertTrue(messages['s1']['file'].endswith('.png'))
  self.assertEqual(messages['g1x']['file'],'','none came: shown as gone, not asked again');self.assertIsNone(messages['v1']['file'],'a voice message waits to be asked for')
  asked=len(self.sony.requests);self.psn.read_thread();self.assertEqual(len([r for r in self.sony.requests[asked:] if '/resources/' in r[1]]),0,'kept pictures are not fetched again')
  resource=[r for r in self.sony.requests if r[1].endswith('/gamingLoungeGroups/v1/groups/g1/resources/r1')][0];self.assertTrue(resource[2]['Authorization'].startswith('Bearer '))
 def test_a_voice_message_is_fetched_when_asked_for(self):
  played=[];self.psn.on_media=lambda kind,path,key:played.append((kind,path.read_bytes(),key))
  self.psn.open_media('v1');self.assertEqual(self.psn.view()['fetching'],'v1');self.psn.do(self.psn.jobs.get_nowait())
  self.assertEqual(played,[('voice',b'OggS-voice','v1')]);self.assertEqual(self.psn.view()['fetching'],'')
  asked=len(self.sony.requests);self.psn.open_media('v1');self.psn.do(self.psn.jobs.get_nowait());self.assertEqual(len(self.sony.requests),asked,'played again from the kept file')
  self.psn.open_media('t1');self.assertTrue(self.psn.jobs.empty(),'words have nothing to fetch')
 def test_the_words_for_each_kind(self):
  self.assertEqual(psn_link.message_text(dict(messageType=1,body='hi')),'hi')
  self.assertEqual(psn_link.message_text(dict(messageType=3,body='',messageDetail=dict(animatedGifMessageDetail=dict(url='https://g.example/a.gif')))),'Sent a GIF.')
  self.assertIn('PlayStation App',psn_link.message_text(dict(messageType=9999,body='')))
  self.assertEqual(psn_link.chat_picture(b'GIF89a...'),(b'GIF89a...','.gif'));self.assertEqual(psn_link.chat_picture(b'not a picture'),(b'',''))

class ChatActionTests(unittest.TestCase):
 """Deleting and removing messages, reactions, read on PSN, typing, favourites, muting and groups, as the PlayStation App asks."""
 def setUp(self):
  self.folder=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,self.folder,True);self.sony=FakeSony();self.clock=Clock()
  self.clock.now=1763200000.0+60
  self.psn=self.make()
  self.sony.groups=[self.sony.group('g1',['900','111'],'t2','111','yo'),self.sony.group('g2',['900','111','222'],'x1','222','hey all')]
  self.sony.messages['g1']=[self.message('t1',0,'Player1','mine, new'),self.message('t2',1,'NightOwl','yours'),self.message('t0',-3600_000,'Player1','mine, old'),
   self.message('p1',2,'Player1','',3,imageMessageDetail=dict(resourceId='r1'))]
  self.psn.read_groups();self.psn.do(('open','g1'));self.psn.read_thread()
 def make(self):
  psn=psn_link.Psn(self.folder/'psn',token=('refresh-0',2_000_000_000),opener=self.sony,clock=self.clock);psn.me=dict(name='Player1');psn.me_id='900';psn.focused=True
  return psn
 def message(self,uid,at,sender,body,kind=1,**detail):
  return dict(messageUid=uid,messageType=kind,body=body,createdTimestamp=str(1763200000000+at),sender=dict(onlineId=sender),**(dict(messageDetail=detail) if detail else {}))
 def run_job(self):self.psn.do(self.psn.jobs.get_nowait())
 def changes(self,method=None):return [c for c in self.sony.chat_changes if method is None or c[0]==method]
 def ids(self):return [m['id'] for m in self.psn.view()['messages']]
 def test_a_message_of_mine_is_deleted_for_everyone(self):
  self.sony.chat_changes.clear();self.assertTrue(self.psn.delete_message('g1','t1'));self.assertEqual(self.psn.view()['changing'],'t1')
  self.run_job();self.assertEqual(self.changes(),[('DELETE','/gamingLoungeGroups/v2/members/me/groups/g1/threads/g1/messages/t1',None,{})])
  self.assertNotIn('t1',self.ids());self.assertEqual(self.psn.view()['chat_line']['tone'],'news');self.assertEqual(self.psn.view()['changing'],'')
 def test_a_picture_of_mine_goes_with_its_file(self):
  kept=self.folder/'psn'/'chat'/next(m['file'] for m in self.psn.view()['messages'] if m['id']=='p1');self.assertTrue(kept.is_file())
  self.sony.newer_delete=False;self.sony.chat_changes.clear();self.psn.delete_message('g1','p1');self.run_job()
  self.assertEqual(self.changes(),[('DELETE','/gamingLoungeGroups/v1/members/me/groups/g1/threads/g1/messages/p1',None,{})],'the older delete when Sony has no newer one there')
  self.assertFalse(kept.exists());self.assertNotIn('p1',self.ids())
 def test_only_my_messages_of_the_last_ten_minutes_can_be_deleted(self):
  self.sony.chat_changes.clear()
  for uid,words in (('t2','only the messages you sent'),('t0','10 minutes')):
   self.psn.delete_message('g1',uid);self.run_job();line=self.psn.view()['chat_line']
   self.assertEqual(line['tone'],'error');self.assertIn(words,line['text']);self.assertIn(uid,self.ids())
  self.assertEqual(self.changes(),[],'nothing is asked of Sony')
 def test_sonys_message_ids_reach_it_whole(self):
  """A real message id is like 1#425961448584099: it goes encoded, as the App sends it, never cut at the '#'."""
  uid='1#425961448584099';self.sony.messages['g1'].append(self.message(uid,8,'Player1','sent just now'));self.psn.read_thread()
  where='/gamingLoungeGroups/{}/members/me/groups/g1/threads/g1/messages/1%23425961448584099'
  self.sony.chat_changes.clear();self.psn.react('g1',uid,'1');self.run_job()
  self.assertEqual(self.changes('POST')[-1][1],where.format('v1')+'/reactions');self.assertNotEqual((self.psn.view()['chat_line'] or {}).get('tone'),'error')
  self.psn.react('g1',uid,'1');self.run_job();self.assertEqual(self.changes('DELETE')[-1][1],where.format('v1')+'/reactions/1')
  self.psn.delete_message('g1',uid);self.run_job();self.assertEqual(self.changes('DELETE')[-1][1],where.format('v2'));self.assertNotIn(uid,self.ids())
 def test_a_post_on_a_message_itself_is_refused_as_sony_does(self):
  status,_,raw=self.sony('POST','https://m.np.playstation.com/api/gamingLoungeGroups/v1/members/me/groups/g1/threads/g1/messages/1',{'Authorization':'Bearer x'},b'{}')
  self.assertEqual((status,json.loads(raw)['error']['code']),(405,2285701))
  self.assertEqual(psn_link.api_path(psn_link.REACT,'g1','g1','1#42/x'),'/gamingLoungeGroups/v1/members/me/groups/g1/threads/g1/messages/1%2342%2Fx/reactions')
 def test_a_refused_delete_says_so(self):
  self.sony.chat_answer=(403,b'{"error":{"message":"Forbidden"}}');self.psn.delete_message('g1','t1');self.run_job()
  line=self.psn.view()['chat_line'];self.assertEqual(line['tone'],'error');self.assertIn('403',line['text']);self.assertIn('t1',self.ids())
 def test_one_change_at_a_time(self):
  self.assertTrue(self.psn.delete_message('g1','t1'));self.assertFalse(self.psn.react('g1','t2','1'));self.assertFalse(self.psn.change_group('mute','g1',True))
 def test_any_message_can_be_removed_from_this_pc_only(self):
  kept=self.folder/'psn'/'chat'/next(m['file'] for m in self.psn.view()['messages'] if m['id']=='p1');self.sony.chat_changes.clear()
  self.psn.hide_message('g1','t2');self.psn.hide_message('g1','p1')
  self.assertEqual(self.changes(),[],'Sony is not asked');self.assertNotIn('t2',self.ids());self.assertFalse(kept.exists())
  self.assertIn('still has it',self.psn.view()['chat_line']['text'])
  again=self.make();again.read_groups();again.do(('open','g1'));again.read_thread()
  self.assertEqual([m['id'] for m in again.view()['messages']],['t0','t1'],'taken off this PC for good, the others stay')
  again.do(('sign_out',));self.assertEqual(self.make().hidden,{},'signing out forgets it')
 def test_emoji_as_sony_writes_them(self):
  self.assertEqual(psn_link.emoji_of('1F44D'),'\U0001F44D');self.assertEqual(psn_link.emoji_of('U+2764 U+FE0F'),'❤️')
  self.assertEqual(psn_link.emoji_of('\U0001F602'),'\U0001F602');self.assertEqual(psn_link.emoji_of('smile'),'');self.assertEqual(psn_link.emoji_of(None),'')
 def test_the_reactions_sony_offers(self):
  kinds=psn_link.reaction_kinds(self.sony.reaction_defs['unicode'])
  self.assertEqual([(k['id'],k['emoji']) for k in kinds],[('1','\U0001F44D'),('2','❤️'),('7','')]);self.assertEqual(kinds[2]['url'],'https://image.example/r7.png')
  self.assertEqual(psn_link.reaction_kinds(dict(definitions=[dict(reactionId='9',unicode='1F600')]))[0]['id'],'9')
  self.assertEqual(psn_link.reaction_kinds('nonsense'),[])
 def test_reactions_are_read_for_the_open_conversation(self):
  self.sony.reaction_state=[dict(messageUid='t2',reactions=[dict(id='1',accountIds=['900','111'],unicode='1F44D',timestamp='1763200000000'),dict(id='2',accountIds=['111'],unicode='2764')]),dict(messageUid='t1',reactions=[])]
  self.sony.chat_changes.clear();self.psn.due['reactions']=0;self.psn.poll()
  asked=[c for c in self.sony.chat_changes if c[1].endswith('/reactions')][0]
  self.assertEqual(asked[2]['reactionVersion'],'unicode','mobile-v1 is not there, so the plain emoji');self.assertEqual(sorted(asked[2]['messageUids']),['p1','t0','t1','t2'])
  shown={m['id']:m['reactions'] for m in self.psn.view()['messages']}
  self.assertEqual([(r['id'],r['count'],r['mine']) for r in shown['t2']],[('1',2,True),('2',1,False)]);self.assertEqual(shown['t1'],[])
  self.assertEqual([k['id'] for k in self.psn.view()['reaction_kinds']],['1','2','7']);self.assertTrue(self.psn.view()['reaction_kinds'][2]['file'].endswith('.png'),'a kind with only a picture has it kept')
 def test_one_reaction_each_given_changed_and_taken_back(self):
  self.psn.react('g1','t2','1');self.run_job()
  self.assertEqual(self.changes('POST')[-1][1:3],('/gamingLoungeGroups/v1/members/me/groups/g1/threads/g1/messages/t2/reactions',dict(reactionId='1',reactionVersion='unicode')))
  mine=lambda:[(r['id'],r['count'],r['mine']) for r in next(m for m in self.psn.view()['messages'] if m['id']=='t2')['reactions']]
  self.assertEqual(mine(),[('1',1,True)]);self.psn.react('g1','t2','2');self.run_job();self.assertEqual(mine(),[('2',1,True)],'the one given before goes')
  self.psn.react('g1','t2','2');self.run_job();self.assertEqual(self.changes('DELETE')[-1][1],'/gamingLoungeGroups/v1/members/me/groups/g1/threads/g1/messages/t2/reactions/2');self.assertEqual(mine(),[])
 def test_a_reading_sony_refuses_leaves_the_reactions(self):
  original=self.sony.__class__.__call__
  def odd(sony,method,url,headers,body):
   if url.endswith('/threads/g1/reactions'):return 500,{},b'{}'
   return original(sony,method,url,headers,body)
  self.sony.__class__.__call__=odd;self.addCleanup(setattr,self.sony.__class__,'__call__',original)
  self.psn.due['reactions']=0;self.psn.poll();self.assertEqual(self.psn.view()['problem'],'','reactions are extras, never a problem on the page')
 def test_the_conversation_is_read_on_psn_once_for_each_new_message(self):
  told=[c for c in self.sony.chat_changes if c[0]=='PATCH'];self.assertEqual(told,[('PATCH','/gamingLoungeGroups/v1/members/me/groups/g1/threads/g1',dict(readMessageUid='p1'),{})])
  new=[c for c in self.sony.chat_changes if c[1].endswith('/newArrival')];self.assertEqual(new[0][0],'DELETE');self.assertEqual(new[0][3],{'timestamp':[str(int(self.clock.now*1000))]})
  self.sony.chat_changes.clear();self.psn.read_thread();self.assertEqual(self.sony.chat_changes,[],'not told again for the same message')
  self.sony.messages['g1'].append(self.message('t3',9,'NightOwl','again'));self.psn.focused=False;self.psn.read_thread();self.assertEqual(self.sony.chat_changes,[],'not while PlayBridge is in the background')
  self.psn.focused=True;self.psn.read_thread();self.assertEqual(self.changes('PATCH')[0][2],dict(readMessageUid='t3'))
 def test_typing_is_told_at_most_every_few_seconds(self):
  self.psn.typing('g1');self.psn.typing('g1');self.assertEqual(self.psn.jobs.qsize(),1);self.run_job()
  self.assertEqual(self.changes('POST')[-1][:3],('POST','/gamingLoungeGroups/v1/groups/g1/typing',None))
  self.clock.now+=psn_link.TYPING_EVERY;self.psn.typing('g1');self.assertEqual(self.psn.jobs.qsize(),1)
 def test_favourite_and_mute(self):
  self.psn.change_group('favourite','g2',True);self.run_job();self.psn.change_group('mute','g2',True);self.run_job()
  self.assertEqual([c[1:3] for c in self.changes('PATCH') if '/threads/' not in c[1]],[('/gamingLoungeGroups/v1/members/me/groups/g2',dict(isFavorite='true')),('/gamingLoungeGroups/v1/members/me/groups/g2/notificationSetting',dict(isMute=True))])
  group=next(g for g in self.psn.view()['groups'] if g['id']=='g2');self.assertTrue(group['favourite'] and group['muted'])
 def test_favourite_conversations_come_first_and_muted_ones_never_alert(self):
  self.sony.groups[1].update(isFavorite='true',notificationSetting=dict(isMute=True));self.psn.read_groups()
  self.assertEqual([g['id'] for g in self.psn.groups],['g2','g1']);self.assertEqual([g['kind'] for g in self.psn.groups],['group','direct'])
  self.sony.groups[1]['mainThread']['latestMessage'].update(messageUid='x2',body='new');self.psn.read_groups();self.assertTrue(self.psn.alerts.empty())
 def test_a_group_is_renamed_and_people_added_and_taken_out(self):
  self.psn.change_group('rename','g2','  Squad   night ');self.run_job()
  self.assertEqual(self.changes('PATCH')[-1][1:3],('/gamingLoungeGroups/v1/groups/g2',dict(groupName=dict(value='Squad night'))))
  self.assertEqual(next(g for g in self.psn.view()['groups'] if g['id']=='g2')['name'],'Squad night')
  self.psn.change_group('rename','g2','   ');self.run_job();self.assertIn('Type a name',self.psn.view()['chat_line']['text'])
  self.psn.change_group('invite','g2',['333','111']);self.run_job()
  self.assertEqual(self.changes('POST')[-1][1:3],('/gamingLoungeGroups/v1/groups/g2/invitees',dict(invitees=[dict(accountId='333')])),'someone already in is not asked again')
  self.psn.change_group('remove','g2','222');self.run_job();self.assertEqual(self.changes('DELETE')[-1][1],'/gamingLoungeGroups/v1/groups/g2/members/222')
  self.assertNotIn('222',[p['id'] for p in next(g for g in self.psn.view()['groups'] if g['id']=='g2')['people']])
 def test_someone_added_to_a_conversation_of_two_makes_a_new_group(self):
  self.sony.invite_answer=dict(groupId='g9',hasAllAccountInvited=False);self.psn.change_group('invite','g1',['222']);self.run_job()
  view=self.psn.view();self.assertEqual(view['thread'],'g9');self.assertEqual(view['groups'][0]['id'],'g9');self.assertEqual(view['groups'][0]['kind'],'group')
  self.assertIn('could not add everyone',view['chat_line']['text'])
 def test_leaving_a_group(self):
  self.psn.do(('open','g2'));self.psn.change_group('leave','g2');self.run_job()
  self.assertEqual(self.changes('DELETE')[-1][1],'/gamingLoungeGroups/v1/groups/g2/members/me');view=self.psn.view()
  self.assertNotIn('g2',[g['id'] for g in view['groups']]);self.assertIsNone(view['thread'])
 def test_a_new_group_needs_two_friends_and_opens(self):
  self.assertFalse(self.psn.new_group(['111']));self.assertTrue(self.psn.new_group(['111','222','111'],'  Raid  team'));self.run_job()
  self.assertEqual(self.sony.created[-1],dict(invitees=[dict(accountId='111'),dict(accountId='222')]))
  self.assertEqual(self.changes('PATCH')[-1][1:3],('/gamingLoungeGroups/v1/groups/g-new',dict(groupName=dict(value='Raid team'))))
  view=self.psn.view();self.assertEqual(view['thread'],'g-new');self.assertEqual(view['groups'][0]['name'],'Raid team');self.assertEqual(view['chat_line']['tone'],'news')

class PictureSendTests(unittest.TestCase):
 """A picture sent to a conversation: up to the group as a resource first, then a message that names it, as the PlayStation App does."""
 def setUp(self):
  self.folder=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,self.folder,True);self.sony=FakeSony();self.clock=Clock()
  self.psn=psn_link.Psn(self.folder/'psn',token=('refresh-0',2_000_000),opener=self.sony,clock=self.clock);self.psn.me=dict(name='Player1')
  self.psn.do(('open','g1'))
 def picture(self,name,mode='RGB',size=(4000,3000),**saved):
  from PIL import Image
  path=self.folder/name;Image.new(mode,size,(200,40,40,128) if mode=='RGBA' else (200,40,40)).save(path,**saved);return path
 def send(self,path,caption='',passing=False):
  self.assertTrue(self.psn.send_picture('g1',path,caption,passing));self.assertTrue(self.psn.view()['sending'])
  self.psn.do(self.psn.jobs.get_nowait());self.assertFalse(self.psn.view()['sending'])
 def test_the_picture_goes_up_then_a_message_names_it(self):
  import io
  from PIL import Image
  exif=Image.Exif();exif[0x0112]=6;exif[0x010F]='PhoneMaker'
  self.send(self.picture('photo.jpg',exif=exif.tobytes()),'look at this')
  (headers,raw),=self.sony.uploads;self.assertEqual(headers['Content-Type'],'image/jpeg');self.assertTrue(headers['Authorization'].startswith('Bearer '))
  upload=[r for r in self.sony.requests if r[0]=='POST' and r[1].endswith('/gamingLoungeGroups/v1/groups/g1/resources')];self.assertEqual(len(upload),1)
  with Image.open(io.BytesIO(raw)) as sent:
   self.assertEqual(sent.size,(576,768),'turned upright as the camera said, and 768 on its long side, as the PlayStation App sends it')
   self.assertLess(len(raw),1<<20,'under the 1 MiB the App keeps to')
   self.assertEqual(len(sent.getexif()),0,'what the file said about itself (the phone, where it was) stays home')
  self.assertEqual(self.sony.sent,[('/api/gamingLoungeGroups/v1/groups/g1/threads/g1/messages',dict(messageType=3,messageDetail=dict(imageMessageDetail=dict(resourceId='up1')),body='look at this'))])
  shown=self.psn.view()['messages'][-1];self.assertEqual((shown['kind'],shown['mine'],shown['caption']),('picture',True,'look at this'))
  self.assertTrue(shown['file'].endswith('.jpg'));self.assertEqual((self.folder/'psn'/'chat'/shown['file']).read_bytes(),raw,'shown at once from the copy kept here')
  self.assertEqual(self.psn.view()['send_line'],{})
 def test_without_words_and_with_see_through_parts(self):
  self.send(self.picture('logo.png','RGBA',(300,200)))
  self.assertEqual(self.sony.uploads[0][0]['Content-Type'],'image/png');self.assertNotIn('body',self.sony.sent[0][1],'no words: none sent')
 def test_what_cannot_go_says_why(self):
  from PIL import Image
  (self.folder/'notes.txt').write_text('not a picture');self.send(self.folder/'notes.txt')
  self.assertIn('cannot read that file as a picture',self.psn.view()['send_line']['text'])
  frames=[Image.new('RGB',(40,40),c) for c in ((255,0,0),(0,255,0))];frames[0].save(self.folder/'moving.gif',save_all=True,append_images=frames[1:])
  self.send(self.folder/'moving.gif');self.assertIn('still pictures only',self.psn.view()['send_line']['text'])
  self.sony.upload_answer=(403,dict(error=dict(code=2105356,message='Not allowed')))
  passing=self.picture('pasted.png',size=(64,64));self.send(passing,passing=True)
  self.assertEqual(self.psn.view()['send_line']['text'],'PSN refused the picture as it went up: answer 403, "Not allowed (code 2105356)".')
  self.assertFalse(passing.exists(),'a pasted picture PlayBridge made is deleted once done');self.assertEqual(self.sony.sent,[],'no message names a picture that did not go up')
  self.sony.upload_answer={};self.send(self.picture('x.jpg',size=(64,64)));self.assertIn('did not say where it keeps it',self.psn.view()['send_line']['text'])
 def test_a_busy_picture_goes_smaller_until_it_fits(self):
  import io,os
  from PIL import Image
  path=self.folder/'grain.png';Image.frombytes('RGB',(768,768),os.urandom(768*768*3)).save(path);self.send(path)
  (headers,raw),=self.sony.uploads
  with Image.open(io.BytesIO(raw)) as sent:self.assertEqual(sent.size,(640,640),"too large at 768, so the next of the App's sizes")
  self.assertLess(len(raw),1<<20);self.assertEqual(self.psn.view()['send_line'],{})
  self.sony.uploads.clear();self.send(self.picture('small.jpg',size=(300,200)))
  with Image.open(io.BytesIO(self.sony.uploads[0][1])) as sent:self.assertEqual(sent.size,(300,200),'a small picture keeps its size')
 def test_the_refusal_says_which_step_sony_turned_down(self):
  page=b'<html><head><title>Error 502 - Bad Gateway</title></head><body><h1>Error 502 - Bad Gateway</h1></body></html>'
  self.sony.upload_answer=(502,page);self.send(self.picture('a.jpg',size=(64,64)))
  self.assertEqual(self.psn.view()['send_line']['text'],'PSN refused the picture as it went up: answer 502, "Error 502 - Bad Gateway".');self.assertEqual(self.sony.sent,[])
  self.sony.upload_answer=dict(resourceId='up2');self.sony.message_answer=(502,page);shown=len(self.psn.view()['messages'])
  self.send(self.picture('b.jpg',size=(64,64)),'hi')
  self.assertEqual(self.psn.view()['send_line']['text'],'The picture went up, but PSN refused the message that shows it: answer 502, "Error 502 - Bad Gateway".')
  self.assertEqual(self.sony.sent[0][1]['messageDetail'],dict(imageMessageDetail=dict(resourceId='up2')))
  self.assertEqual(len(self.psn.view()['messages']),shown,'a picture no message names is not shown as sent')
 def test_one_picture_at_a_time(self):
  path=self.picture('a.jpg',size=(64,64));self.assertTrue(self.psn.send_picture('g1',path));self.assertFalse(self.psn.send_picture('g1',path),'the one on its way goes first')
 def test_where_psn_says_it_keeps_the_picture(self):
  self.assertEqual(psn_link.resource_of(b'{"resourceId":"abc"}',{}),'abc');self.assertEqual(psn_link.resource_of(b'"abc"',{}),'abc')
  self.assertEqual(psn_link.resource_of(b'',{'location':'https://m.np.playstation.com/api/gamingLoungeGroups/v1/groups/g1/resources/xyz'}),'xyz')
  self.assertEqual(psn_link.resource_of(b'{}',{}),'')

class WhenTests(unittest.TestCase):
 def test_psn_times(self):
  self.assertEqual(psn_link.when('1763200000000'),1763200000.0);self.assertEqual(psn_link.when('2026-11-14T10:00:00Z'),1794650400.0);self.assertEqual(psn_link.when(None),0)

if __name__=='__main__':unittest.main()
