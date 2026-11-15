"""PS5 fans: the level for every game and for one, what is sent for it, the line Settings shows, and the console link sending a target to
a stand-in console that keeps it as the payload does (never warmer than its own)."""
import json,os,socket,struct,sys,tempfile,threading,time,unittest
from pathlib import Path
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import fan_target as fans
import console_control as control

def status(now=79,own=79,ours=0,title='PPSA01234'):return dict(user=1,app=7 if title else 0,title=title,fan_c=now,fan_own=own,fan_set=ours)

class LevelTests(unittest.TestCase):
 def test_a_lower_level_asks_for_a_lower_target_once(self):
  self.assertEqual(fans.wanted(status(),'cooler'),74);self.assertEqual(fans.wanted(status(),'coolest'),69)
  self.assertIsNone(fans.wanted(status(74,79,74),'cooler'))
  self.assertEqual(fans.wanted(status(74,79,74),'coolest'),69)
 def test_the_ps5s_own_is_asked_back_only_when_playbridge_changed_it(self):
  self.assertEqual(fans.wanted(status(74,79,74),'own'),0);self.assertIsNone(fans.wanted(status(),'own'))
 def test_never_below_the_lowest_the_fans_take(self):
  self.assertEqual(fans.wanted(status(55,55),'coolest'),50);self.assertIsNone(fans.wanted(status(50,50),'cooler'))
 def test_nothing_is_sent_without_a_reading_it_can_trust(self):
  for seen in (dict(user=1),status(-19),status(0),status(95,95),status(79,True),dict(status(),fan_set='0')):
   self.assertIsNone(fans.wanted(seen,'coolest'),seen)
 def test_the_line_says_where_the_fans_stand(self):
  self.assertIn('Connect',fans.describe({},online=False));self.assertIn('cannot reach the fans',fans.describe(dict(user=1)))
  self.assertIn('error 19',fans.describe(status(-19)));self.assertIn("79 °C, the PS5's own",fans.describe(status()))
  self.assertIn("74 °C, set by PlayBridge. The PS5's own is 79",fans.describe(status(74,79,74),level='cooler'))
  self.assertIn('outside what PlayBridge changes',fans.describe(status(95,95),level='cooler'));self.assertNotIn('outside',fans.describe(status(95,95)))
  self.assertIn('refused the change (error 22)',fans.describe(status(),level='cooler',error=22))

class ProfileTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'fans.json'
 def test_each_game_keeps_its_own_and_the_rest_share_one(self):
  kept=fans.FanProfiles(self.path);self.assertEqual(kept.get('PPSA01234'),'own')
  kept.set('','cooler');kept.set('PPSA01234','coolest');kept.set('PPSA09999','warm')
  again=fans.FanProfiles(self.path)
  self.assertEqual((again.get('PPSA01234'),again.get('PPSA09999'),again.get('')),('coolest','cooler','cooler'));self.assertTrue(again.own('PPSA01234'))
  again.set('PPSA01234',None);self.assertEqual(fans.FanProfiles(self.path).get('PPSA01234'),'cooler');self.assertFalse(again.own('PPSA01234'))
 def test_a_broken_file_is_the_ps5s_own_everywhere(self):
  self.path.write_text('{"":',encoding='utf-8');self.assertEqual(fans.FanProfiles(self.path).get(''),'own')
  self.path.write_text(json.dumps({'':'hot'}),encoding='utf-8');self.assertEqual(fans.FanProfiles(self.path).get('PPSA01234'),'own')

class StandIn:
 """STATUS and FAN as the payload answers them: a target is refused above the console's own or below 50, 0 puts its own back."""
 def __init__(self,own=79,refuse=0,title='PPSA01234'):
  self.own=own;self.now=own;self.ours=0;self.refuse=refuse;self.title=title;self.sent=[]
  self.server=socket.create_server(('127.0.0.1',0));threading.Thread(target=self.serve,daemon=True).start()
 def serve(self):
  while True:
   try:connection,_=self.server.accept()
   except OSError:return
   with connection:
    try:self.session(connection)
    except OSError:pass
 def session(self,connection):
  while True:
   head=b''
   while len(head)<12:
    part=connection.recv(12-len(head))
    if not part:return
    head+=part
   _,command,length=struct.unpack('<4sII',head);body=b''
   while len(body)<length:body+=connection.recv(length-len(body))
   if command==control.STATUS:
    answer=json.dumps(dict(user=1,app=7 if self.title else 0,title=self.title,fan_c=self.now,fan_own=self.own,fan_set=self.ours)).encode()
    connection.sendall(struct.pack('<4siI',b'PBR1',0,len(answer))+answer)
   elif command==control.FAN:
    want=body[0];self.sent.append(want)
    if self.refuse:result=self.refuse
    elif want and not 50<=want<=self.own:result=22
    else:result=0;self.now=want or self.own;self.ours=0 if self.now==self.own else self.now
    connection.sendall(struct.pack('<4siI',b'PBR1',result,0))
   else:connection.sendall(struct.pack('<4siI',b'PBR1',2,0))

def wait_for(test,seconds=4):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  if test():return True
  time.sleep(.02)
 return False

class LinkTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.folder=Path(self.tmp.name)
 def link(self,console,level='',game=None):
  original=control.CONTROL_PORT;control.CONTROL_PORT=console.server.getsockname()[1];self.addCleanup(setattr,control,'CONTROL_PORT',original)
  link=control.ConsoleLink(self.folder);link.fans=fans.FanProfiles(self.folder/'fans.json')
  if level:link.fans.set('',level)
  if game:link.fans.set('PPSA01234',game)
  self.addCleanup(link.end);self.addCleanup(console.server.close);link.begin('127.0.0.1');return link
 def test_the_level_for_every_game_is_sent_once(self):
  console=StandIn();link=self.link(console,'cooler')
  self.assertTrue(wait_for(lambda:console.now==74));time.sleep(.5);self.assertEqual(console.sent,[74])
  self.assertTrue(wait_for(lambda:link.status.get('fan_set')==74))
 def test_a_game_of_its_own_and_back_to_the_ps5s_own(self):
  console=StandIn();link=self.link(console,'cooler',game='coolest')
  self.assertTrue(wait_for(lambda:console.now==69))
  link.fans.set('PPSA01234','own');self.assertTrue(wait_for(lambda:console.now==79 and console.ours==0));self.assertEqual(console.sent,[69,0])
 def test_with_no_game_the_level_for_every_game_counts(self):
  console=StandIn(title='');link=self.link(console,'coolest',game='own')
  self.assertTrue(wait_for(lambda:console.now==69))
 def test_a_refusal_is_told_and_not_asked_again_at_once(self):
  console=StandIn(refuse=5);link=self.link(console,'cooler')
  self.assertTrue(wait_for(lambda:link.fan_error==5));time.sleep(.6);self.assertEqual(console.sent,[74])
  self.assertIn('error 5',fans.describe(link.status,True,link.fan_level(),link.fan_error))
 def test_the_ps5s_own_sends_nothing(self):
  console=StandIn();link=self.link(console)
  self.assertTrue(wait_for(lambda:link.online));time.sleep(.5);self.assertEqual(console.sent,[])

if __name__=='__main__':unittest.main()
