"""Twitch chat through a stand-in for Twitch's chat server (nothing leaves this PC): the anonymous join, messages with their tags, what the
moderators remove, a new connection when Twitch asks for one, and the chat panel drawn over the game."""
import queue,socket,sys,threading,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import twitch_chat as tc
import hud

def wait_for(test,seconds=4):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  if test():return True
  time.sleep(.02)
 return False

class FakeServer:
 """Twitch's end of one connection: what PlayBridge sent, and lines to hand it."""
 def __init__(self):self.sent=b'';self.lines=queue.Queue();self.closed=False
 def settimeout(self,seconds):self.timeout=seconds
 def sendall(self,data):self.sent+=data
 def recv(self,size):
  try:line=self.lines.get(timeout=.2)
  except queue.Empty:raise socket.timeout()
  if line is None:return b''
  return line.encode()+b'\r\n'
 def close(self):self.closed=True
 def say(self,*lines):
  for line in lines:self.lines.put(line)

class ChatTests(unittest.TestCase):
 def setUp(self):
  self.servers=[];self.channel='examplechannel';self.clock=[1000.0]
  def connector(host,port):
   self.assertEqual((host,port),(tc.HOST,tc.PORT));server=FakeServer();self.servers.append(server);return server
  self.chat=tc.Chat(lambda:self.channel,connector,clock=lambda:self.clock[0]);self.addCleanup(self.chat.stop)
  self.assertTrue(wait_for(lambda:self.servers and b'JOIN' in self.servers[-1].sent))
 def test_joins_anonymously_and_answers_pings(self):
  server=self.servers[0];sent=server.sent.decode()
  self.assertIn('CAP REQ :twitch.tv/tags twitch.tv/commands',sent);self.assertRegex(sent,r'NICK justinfan\d+');self.assertIn('JOIN #examplechannel',sent)
  server.say('PING :tmi.twitch.tv',':tmi.twitch.tv ROOMSTATE #examplechannel')
  self.assertTrue(wait_for(lambda:b'PONG :tmi.twitch.tv' in server.sent));self.assertTrue(wait_for(lambda:self.chat.text().startswith('Reading #examplechannel')))
 def test_messages_carry_their_tags_and_moderators_remove_them(self):
  server=self.servers[0]
  server.say('@badges=moderator/1,subscriber/12;color=#00FF7F;display-name=Mod\\sSquad;id=a1;user-id=11 :modsquad!modsquad@modsquad.tmi.twitch.tv PRIVMSG #examplechannel :Welcome all 💚',
   '@badges=;color=;display-name=Viewer;id=b2;user-id=22 :viewer!viewer@viewer.tmi.twitch.tv PRIVMSG #examplechannel :\x01ACTION waves\x01',
   '@display-name=Raider;id=c3;user-id=33;system-msg=Raider\\sis\\sraiding\\swith\\sa\\sparty\\sof\\s42. :tmi.twitch.tv USERNOTICE #examplechannel',
   '@display-name=Spammer;id=d4;user-id=44 :spammer!spammer@spammer.tmi.twitch.tv PRIVMSG #examplechannel :buy followers')
  self.assertTrue(wait_for(lambda:len(self.chat.view())==4))
  first,action,event,spam=self.chat.view()
  self.assertEqual((first['name'],first['badges'],first['colour'],first['text']),('Mod Squad',['moderator','subscriber'],'#00FF7F','Welcome all 💚'))
  self.assertEqual((action['kind'],action['text']),('action','waves'));self.assertEqual((event['kind'],event['text']),('event','Raider is raiding with a party of 42.'))
  server.say('@target-user-id=44 :tmi.twitch.tv CLEARCHAT #examplechannel :spammer')
  self.assertTrue(wait_for(lambda:[message['id'] for message in self.chat.view()]==['a1','b2','c3']))
  server.say('@login=viewer;target-msg-id=b2 :tmi.twitch.tv CLEARMSG #examplechannel :waves')
  self.assertTrue(wait_for(lambda:[message['id'] for message in self.chat.view()]==['a1','c3']))
  server.say(':tmi.twitch.tv CLEARCHAT #examplechannel')
  self.assertTrue(wait_for(lambda:self.chat.view()==[]))
 def test_old_messages_fade_and_a_new_channel_starts_clean(self):
  server=self.servers[0]
  server.say(':a!a@a PRIVMSG #examplechannel :first')
  self.assertTrue(wait_for(lambda:len(self.chat.view())==1))
  self.clock[0]+=90;server.say(':b!b@b PRIVMSG #examplechannel :second')
  self.assertTrue(wait_for(lambda:len(self.chat.view())==2))
  self.assertEqual([message['text'] for message in self.chat.view(seconds=60)],['second'])
  self.channel='otherchannel';self.chat.poke()
  self.assertTrue(wait_for(lambda:len(self.servers)==2 and b'JOIN #otherchannel' in self.servers[1].sent));self.assertTrue(wait_for(lambda:self.chat.view()==[]))
 def test_a_reconnect_request_opens_a_new_connection(self):
  self.servers[0].say(':tmi.twitch.tv RECONNECT')
  self.assertTrue(wait_for(lambda:len(self.servers)==2 and b'JOIN #examplechannel' in self.servers[1].sent,seconds=6))
 def test_no_channel_means_no_connection(self):
  self.channel='';self.chat.poke();self.servers[0].say(None)
  time.sleep(.6);self.assertEqual(len(self.servers),1);self.assertEqual(self.chat.text(),'')

class NameTests(unittest.TestCase):
 def test_names_from_what_is_typed(self):
  for typed in ('ExampleChannel','@examplechannel','#examplechannel','https://www.twitch.tv/examplechannel','twitch.tv/examplechannel/videos'):
   self.assertEqual(tc.channel_name(typed),'examplechannel',typed)
  for typed in ('','ab','has space','way_too_long_for_a_twitch_login_name','émoji'):self.assertEqual(tc.channel_name(typed),'',typed)
  tags,nick,command,parameters,text=tc.parse('@a=b\\sc;d= :n!n@n PRIVMSG #x :hi : there')
  self.assertEqual((tags,nick,command,parameters,text),({'a':'b c','d':''},'n','PRIVMSG',['#x'],'hi : there'))

class PanelTests(unittest.TestCase):
 def message(self,text,at=0.0,name='Viewer',kind='message',colour='',badges=()):
  return dict(id=text,user=name,name=name,colour=colour,text=text,badges=list(badges),kind=kind,at=at)
 def test_whole_messages_only_and_long_ones_end_in_an_ellipsis(self):
  many=[self.message(f'message number {index}') for index in range(30)]
  image=hud.chat_image(dict(channel='x',messages=many,now=100),1.0)
  line=round(18);self.assertLessEqual(image.height,12+16+6+hud.CHAT_LINES*line+12)
  long=hud.chat_image(dict(channel='x',messages=[self.message('word '*200)],now=100),1.0)
  self.assertEqual(long.height,12+16+6+hud.MESSAGE_LINES*line+12)
 def test_every_kind_draws_with_badges_emoji_and_a_fresh_light(self):
  messages=[self.message('hello 😂',99.5,'Mod',badges=['moderator','vip']),self.message('waves',90,'Fan',kind='action',colour='#FF69B4'),self.message('Raid of 10.',80,kind='event')]
  image=hud.chat_image(dict(channel='examplechannel',messages=messages,now=100),1.5);self.assertEqual(image.mode,'RGBA');self.assertEqual(image.width,round(hud.WIDTH*1.5))
  rendered=hud.render(chat=dict(channel='x',messages=messages,now=100));self.assertEqual(len(rendered[0]),rendered[1]*rendered[2]*4)
  self.assertIsNone(hud.render(chat=dict(channel='x',messages=[],now=100)))
 def test_dark_names_are_made_readable(self):
  r,g,b,_=hud.readable('#000080','x');self.assertGreater(max(r,g,b),150)
  self.assertEqual(hud.readable('','Viewer'),hud.readable('','Viewer'))

if __name__=='__main__':unittest.main()
