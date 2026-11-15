"""The Friends page and the PSN card in words: friends in order with what they do, the filters and their empty pages, conversations with
"You:" for your own last message, a conversation's messages with the sender's name only when it changes, and the sign-in's state."""
import sys,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import friends_view

NOW=1_800_000_000.0
def view(**extra):
 friends=[dict(id='1',name='NightOwl',online=True,game='Astro Bot',platform='PS5',picture='1.png',favourite=False),dict(id='2',name='ModSquad',online=True,platform='PS5',favourite=True),
  dict(id='3',name='',online=False,last=NOW-3*3600,favourite=False)]
 data=dict(state='on',problem='',me=dict(name='Player1',picture='me.png'),friends=friends,groups=[dict(id='g1',name='NightOwl',last='on my way',last_from='Player1',at=NOW-60,unread=False),
  dict(id='g2',name='ModSquad',last='gg',last_from='ModSquad',at=NOW-86400*3,unread=True)],thread=None,messages=[],sending=False,updated=NOW,signed_until=NOW+50*86400)
 data.update(extra);return data

class ChatActionsViewTests(unittest.TestCase):
 """What can be done to each message, the reactions on it, the open conversation's options and the new-group card."""
 def thread(self,**extra):
  groups=[dict(id='g1',name='NightOwl',kind='direct',people=[dict(id='1',name='NightOwl')],favourite=True,muted=True,at=NOW-60,last='hi',last_from='NightOwl'),
   dict(id='g3',name='Raid night',named=True,kind='group',people=[dict(id='2',name='ModSquad'),dict(id='3',name=''),dict(id='9',name='Stranger')],at=NOW-600,last='go',last_from='ModSquad')]
  messages=[dict(id='m1',who='Player1',text='mine, new',mine=True,at=NOW-120,kind='text',reactions=[dict(id='6',emoji='\U0001F525',url='',count=2,mine=True,file='')]),
   dict(id='m2',who='Player1',text='mine, old',mine=True,at=NOW-700,kind='text'),dict(id='m3',who='NightOwl',text='',mine=False,at=NOW-30,kind='picture',media=dict(key='k'),file='k.jpg',
   reactions=[dict(id='7',emoji='',url='https://image.example/r7.png',count=1,mine=False,file='r7.png'),dict(id='8',emoji='',url='https://image.example/r8.png',count=1,mine=False,file='')]),
   dict(id='n1',who='',text='NightOwl created this group.',mine=False,at=NOW-900,kind='note')]
  data=view(groups=groups,thread='g1',messages=messages,reaction_kinds=[dict(id='1',emoji='\U0001F44D',url='',file=''),dict(id='7',emoji='',url='u',file='r7.png'),dict(id='9',emoji='',url='u9',file='')],
   reactions_ready=True,chat_line=dict(text='Deleted for everyone in the conversation.',tone='news',at=NOW-5),changing='m1')
  data.update(extra);return friends_view.page(data,NOW,picture=lambda name:'file:///'+name if name else '',chat=lambda name:'file:///chat/'+name)
 def test_what_can_be_done_to_each_message(self):
  rows={m['id']:m for m in self.thread()['thread']['messages']}
  self.assertTrue(rows['m1']['canDelete']);self.assertEqual(rows['m1']['deleteTip'],'Delete for everyone · 8 min left')
  self.assertFalse(rows['m2']['canDelete'],'PSN deletes only in the 10 minutes after sending');self.assertFalse(rows['m3']['canDelete'],'nor anyone else\'s')
  self.assertTrue(all(rows[k]['canHide'] for k in ('m1','m2','m3')));self.assertFalse(rows['n1']['canReact'])
  self.assertTrue(rows['m1']['canCopy']);self.assertTrue(rows['m3']['canCopy'] and rows['m3']['canSave']);self.assertFalse(rows['m1']['canSave'])
  self.assertTrue(rows['m3']['saveName'].startswith('PSN picture ') and rows['m3']['saveName'].endswith('.jpg'))
  self.assertTrue(rows['m1']['busy'],'the message a change is on its way for');self.assertFalse(rows['m3']['busy'])
 def test_reactions_under_a_message(self):
  rows={m['id']:m for m in self.thread()['thread']['messages']}
  self.assertEqual(rows['m1']['reactions'],[dict(id='6',emoji='\U0001F525',picture='',count=2,mine=True)])
  self.assertEqual([(r['id'],r['picture']) for r in rows['m3']['reactions']],[('7','file:///chat/r7.png')],'a reaction whose picture has not come is left out')
  kinds=self.thread()['thread']['reactionKinds'];self.assertEqual([k['id'] for k in kinds],['1','7']);self.assertTrue(self.thread()['thread']['reactionsReady'])
 def test_the_open_conversation(self):
  thread=self.thread()['thread']
  self.assertEqual((thread['kind'],thread['favourite'],thread['muted'],thread['canRename'],thread['canLeave']),('direct',True,True,False,False))
  self.assertEqual(thread['about'],'Playing Astro Bot · PS5 · Muted');self.assertEqual(thread['aboutTone'],'playing')
  self.assertEqual([p['id'] for p in thread['people']],['1']);self.assertEqual(thread['people'][0]['picture'],'file:///1.png','a friend shows with their picture')
  self.assertEqual([f['id'] for f in thread['invitable']],['2'],'friends not in it, names known');self.assertEqual(thread['chatLine']['tone'],'news');self.assertTrue(thread['busy'])
  group=self.thread(thread='g3')['thread']
  self.assertEqual((group['kind'],group['canRename'],group['named'],group['about']),('group',True,True,'4 people'))
  self.assertEqual([p['name'] for p in group['people']],['ModSquad','Player','Stranger'],'someone without a name still shows');self.assertEqual(group['invitable'][0]['id'],'1')
  self.assertIsNone(self.thread(chat_line=dict(text='old',tone='news',at=NOW-600))['thread']['chatLine'],'a result goes after a minute and a half')
 def test_conversations_and_the_new_group_card(self):
  page=self.thread(thread=None)
  first,second=page['groups'];self.assertTrue(first['favourite'] and first['muted']);self.assertEqual(first['faces'][0]['tone'],'playing')
  self.assertEqual((second['kind'],len(second['faces']),second['more']),('group',2,1))
  self.assertEqual([f['name'] for f in page['everyone']],['ModSquad','NightOwl'],'friends whose names are known, by name');self.assertEqual(page['chatLine']['text'],'Deleted for everyone in the conversation.')

class FriendsViewTests(unittest.TestCase):
 def test_friends_with_what_they_do(self):
  page=friends_view.page(view(),NOW,'All',lambda name:'file:///'+name if name else '')
  self.assertEqual([(row['name'],row['line'],row['tone']) for row in page['friends']],[('NightOwl','Playing Astro Bot · PS5','playing'),('ModSquad','Online · PS5','online'),('Loading…','Last online 3 h ago','off')])
  self.assertEqual(page['friends'][0]['picture'],'file:///1.png');self.assertEqual(page['friends'][2]['picture'],'');self.assertEqual((page['me']['name'],page['me']['picture']),('Player1','file:///me.png'))
  self.assertEqual(page['summary'],'2 friends online · 1 playing');self.assertEqual(page['unread'],1);self.assertEqual(page['count'],3)
 def test_filters_and_their_empty_pages(self):
  self.assertEqual([row['name'] for row in friends_view.page(view(),NOW,'Favourites')['friends']],['ModSquad'])
  self.assertEqual(len(friends_view.page(view(),NOW,'Online')['friends']),2)
  quiet=view(friends=[dict(id='3',name='Viewer42',online=False)])
  self.assertIn('online right now',friends_view.page(quiet,NOW,'Online')['empty']);self.assertIn('star',friends_view.page(quiet,NOW,'Favourites')['empty'])
  self.assertEqual(friends_view.page(view(friends=[],updated=0),NOW)['empty'],'Loading your friends…');self.assertIn('no friends',friends_view.page(view(friends=[]),NOW)['empty'])
 def test_conversations_and_messages(self):
  page=friends_view.page(view(),NOW);self.assertEqual(page['groups'][0]['last'],'You: on my way');self.assertEqual(page['groups'][1]['last'],'gg')
  self.assertEqual(page['groups'][0]['when'],time.strftime('%H:%M',time.localtime(NOW-60)));self.assertIsNone(page['thread'])
  messages=[dict(who='NightOwl',text='hi',mine=False,at=NOW-30),dict(who='NightOwl',text='want to play?',mine=False,at=NOW-20),dict(who='Player1',text='yes',mine=True,at=NOW-10)]
  thread=friends_view.page(view(thread='g1',messages=messages),NOW)['thread']
  self.assertEqual(thread['name'],'NightOwl');self.assertEqual([m['first'] for m in thread['messages']],[True,False,True]);self.assertFalse(thread['loading'])
  self.assertTrue(friends_view.page(view(thread='g9'),NOW)['thread']['loading'])
 def test_times(self):
  self.assertEqual([friends_view.ago(s) for s in (30,600,7200,86400*1.2,86400*5,86400*40)],['just now','10 min ago','2 h ago','yesterday','5 days ago','over a month ago'])
  self.assertEqual(friends_view.clock(NOW-86400,NOW),'Yesterday');self.assertEqual(friends_view.clock(0,NOW),'')
 def test_the_player_in_the_top_bar(self):
  out=friends_view.chip(dict(state='out'));self.assertEqual((out['name'],out['line'],out['tone'],out['initial']),('PSN','Sign in','off',''))
  self.assertEqual(friends_view.chip(dict(state='expired'))['line'],'Sign in again')
  base=dict(state='on',me=dict(name='Player1',picture='me.png',plus=True))
  def shown(view,running=''):chip=friends_view.chip(view,running);return chip['line'],chip['tone']
  self.assertEqual(shown(base),('Signed in','off'),'before PSN has said, nobody is called online')
  self.assertEqual(shown(dict(base,presence=dict(online=True,game='Astro Bot'))),('Playing Astro Bot','playing'))
  self.assertEqual(shown(dict(base,presence=dict(online=True)),'Hades II'),('Online','online'),'PSN says the player is online and plays nothing: that is what friends see')
  self.assertEqual(shown(dict(base,presence=dict(online=False)),'Hades II'),('Playing Hades II','off'),'a game on the PS5 does not make PSN show you online')
  self.assertEqual(shown(dict(base,presence=dict(online=True))),('Online','online'));self.assertEqual(shown(dict(base,presence=dict(online=False))),('Offline','off'))
  chip=friends_view.chip(base,picture=lambda name:'file:///'+name);self.assertEqual((chip['picture'],chip['initial'],chip['plus']),('file:///me.png','P',True))
 def test_the_friends_page_and_the_top_bar_never_disagree(self):
  base=dict(state='on',me=dict(name='Player1'),friends=[],groups=[],updated=NOW)
  for presence in (None,dict(online=False),dict(online=True,platform='PS5'),dict(online=True,platform='PS5',game='Astro Bot'),dict(online=False,last=NOW-60)):
   for running in ('','Hades II'):
    view=dict(base,presence=presence);top=friends_view.chip(view,running);me=friends_view.page(view,NOW,running=running)['me']
    self.assertEqual(me['tone'],top['tone'],(presence,running));self.assertTrue(me['line'].startswith(top['line']),(presence,running,me['line'],top['line']))
    explained=bool(presence) and (not presence.get('online') or bool(running) and not presence.get('game'))
    self.assertEqual(bool(me['why']),explained,'explained when PSN says offline, or online without the game the PS5 runs')
  me=friends_view.page(dict(base,presence=dict(online=True,platform='PS5')),NOW)['me'];self.assertEqual((me['line'],me['tone']),('Online · PS5','online'))
  me=friends_view.page(dict(base,presence=dict(online=False)),NOW)['me'];self.assertEqual((me['line'],me['tone']),('Offline on PSN','off'))
 def test_online_in_the_app_with_a_game_on_the_ps5(self):
  me=friends_view.page(dict(state='on',me=dict(name='Player1'),friends=[],groups=[],updated=NOW,presence=dict(online=True,platform='MOBILE_APP')),NOW,running='XPS5')['me']
  self.assertEqual((me['line'],me['tone']),('Online · PlayStation App','online'))
  self.assertEqual(me['why'],'Your friends see you online in the PlayStation App, not XPS5: a game on your PS5 shows to them only while that PS5 is signed in to PSN.')
 def test_friend_requests_and_the_add_friend_card(self):
  data=view(received=[dict(id='5',name='Asker',picture='')],sent=[dict(id='6',name='',picture='')],asking=['5'],
   finding=dict(state='done',asked='stranger7',id='7',name='Stranger7',picture='',relation='none',text='',tone='plain'),friend_line=dict(text='Friend request sent to X.',tone='news',id='9',at=NOW-10))
  page=friends_view.page(data,NOW)
  self.assertEqual([(r['kind'],r['name'],r['line'],r['busy']) for r in page['requests']],[('received','Asker','Wants to be your friend',True),('sent','Loading…','You sent a friend request',False)])
  self.assertEqual(page['requestCount'],1);self.assertEqual(friends_view.page(data,NOW,'Online')['requests'],[],'requests show with All')
  find=page['find'];self.assertEqual((find['person']['name'],find['person']['line'],[a['kind'] for a in find['person']['actions']]),('Stranger7','Not your friend yet',['add']))
  self.assertIsNone(find['line'],'the line is about someone else');self.assertEqual(page['friendLine'],dict(text='Friend request sent to X.',tone='news'))
  self.assertIsNone(friends_view.page(data,NOW+friends_view.LINE_SECONDS+1)['friendLine'],'the line goes after a while')
  for relation,kinds in (('sent',['cancel']),('received',['accept','decline']),('friend',['message','remove']),('me',[])):
   finding=dict(data['finding'],relation=relation);self.assertEqual([a['kind'] for a in friends_view.page(dict(data,finding=finding),NOW)['find']['person']['actions']],kinds)
  alone=friends_view.page(view(friends=[],received=[dict(id='5',name='Asker',picture='')]),NOW);self.assertEqual(alone['empty'],'','the requests fill the page')
  self.assertIn('Add friend',friends_view.page(view(friends=[]),NOW)['empty'])
  self.assertEqual(friends_view.menu_items(dict(state='on',friends=[],groups=[],received=[dict(id='5')]))[0],('psn_friends','Friends','1 request'))
 def test_pictures_voice_and_notes_in_a_conversation(self):
  messages=[dict(id='n',kind='note',text='Player1 created this group.',who='Player1',mine=False,at=NOW-30),
   dict(id='p',kind='picture',text='Sent a picture.',who='NightOwl',mine=False,at=NOW-20,media=dict(kind='picture',key='k1'),file='k1.png'),
   dict(id='q',kind='picture',text='Sent a picture.',who='NightOwl',mine=False,at=NOW-19,media=dict(kind='picture',key='k2'),file=''),
   dict(id='r',kind='sticker',text='Sent a sticker.',who='NightOwl',mine=False,at=NOW-18,media=dict(kind='sticker',key='k3'),file=None),
   dict(id='v',kind='voice',text='Sent a voice message.',who='NightOwl',mine=False,at=NOW-10,media=dict(kind='voice',key='k4',seconds=72.4),file=None)]
  rows=friends_view.page(view(thread='g1',messages=messages),NOW,chat=lambda name:'file:///chat/'+name,playing='v')['thread']['messages']
  self.assertEqual([(r['kind'],r['state']) for r in rows],[('note',''),('picture','ready'),('picture','gone'),('sticker','loading'),('voice','playing')])
  self.assertEqual(rows[1]['image'],'file:///chat/k1.png');self.assertEqual(rows[4]['text'],'Voice message · 1:12')
  self.assertFalse(rows[0]['first']);self.assertTrue(rows[1]['first']);self.assertFalse(rows[2]['first'],'the name shows once per run')
  self.assertIn('did not send',rows[2]['text'])
  self.assertEqual(rows[1]['text'],'','a picture with no words under it shows alone')
 def test_words_under_a_picture_and_what_came_of_sending_one(self):
  messages=[dict(id='p',kind='picture',text='Sent a picture.',caption='look at this',who='Player1',mine=True,at=NOW-5,media=dict(kind='picture',key='k1'),file='k1.jpg')]
  thread=friends_view.page(view(thread='g1',messages=messages,send_line=dict(text='PSN refused the picture: answer 403.',tone='error',at=NOW-10)),NOW,chat=lambda name:'file:///chat/'+name)['thread']
  self.assertEqual(thread['messages'][0]['text'],'look at this');self.assertEqual(thread['sendLine'],dict(text='PSN refused the picture: answer 403.',tone='error'))
  old=friends_view.page(view(thread='g1',messages=messages,send_line=dict(text='old',tone='error',at=NOW-600)),NOW)['thread'];self.assertIsNone(old['sendLine'],'it goes after a minute and a half')
 def test_the_psn_menu(self):
  self.assertEqual(friends_view.menu_items(dict(state='out')),[('psn_settings','Sign in to PSN')])
  items=friends_view.menu_items(dict(state='on',friends=[dict(online=True),dict(online=False)],groups=[dict(unread=True),dict(unread=False)]),312)
  self.assertEqual(items[:3],[('psn_friends','Friends','1 online'),('psn_messages','Messages','1 new'),('psn_trophies','Trophies','Level 312')])
  self.assertEqual([item[0] for item in items[3:]],['psn_settings','psn_refresh','psn_sign_out'])
  self.assertEqual(friends_view.menu_items(dict(state='on'))[:3],[('psn_friends','Friends'),('psn_messages','Messages'),('psn_trophies','Trophies')],'nothing to say: no value')
 def test_the_settings_card(self):
  wants=friends_view.wants_from({})
  self.assertEqual(wants,dict(online=True,games=False,messages=True,requests=True,watch='XPS5',favourites_only=False))
  card=friends_view.settings(view(),wants,'',NOW);self.assertEqual(card['psnState'],dict(text='Signed in as Player1. 3 friends, 2 online.',tone='news'));self.assertTrue(card['psnOn'])
  self.assertIn('ends in 3 days',friends_view.settings(view(signed_until=NOW+3*86400),wants,'',NOW)['psnState']['text'])
  self.assertEqual(friends_view.settings(view(state='expired'),wants,'',NOW)['psnState']['tone'],'error')
  out=friends_view.settings(dict(state='out'),wants,'That is not the code.',NOW);self.assertEqual((out['psnState']['text'],out['psnProblem'],out['psnOn']),('Not signed in.','That is not the code.',False))
  self.assertEqual(friends_view.favourites_from({'psn_favourites':['12','x',3]}),{'12','3'});self.assertEqual(friends_view.favourites_from({'psn_favourites':'12'}),set())

if __name__=='__main__':unittest.main()
