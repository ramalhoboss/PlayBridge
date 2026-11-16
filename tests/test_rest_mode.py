"""A PS5 in rest mode: PlayBridge waits for it to wake up and then connects, and says so plainly when the ELF loader did not come back
with it. Nothing here reaches a network: the discovery and the loader's port are stand-ins."""
import argparse,os,socket,sys,threading,unittest
from pathlib import Path
from unittest.mock import patch
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import playbridge as core

HOST='192.168.1.50'
def console(resting):return {'ip':HOST,'name':'PS5','source':'PS5 discovery','resting':resting,'firmware':'13600007'}

class RestModeTests(unittest.TestCase):
 def player(self):
  p=core.Player(argparse.Namespace(renderer='gdi',profile='balanced',auto_reconnect=False,device=None,connect_only=False,host=HOST,record=False,preview=False,headless=True,seconds=0))
  # This PC's own key and settings are left alone.
  p.payload_pairing.stamp=lambda data,flags=0:(data,False);return p
 def run_session(self,p,answers,loader):
  seen=[]
  def locate(host):seen.append(host);return answers.pop(0) if len(answers)>1 else answers[0]
  with patch.object(core,'locate',locate),patch.object(core,'WAKE_LOOK',.05),patch.object(core,'LOADER_BACK',.3),\
   patch.object(core,'config',lambda:{'ps5_notices':False}),patch.object(core,'supported',lambda item:True),patch.object(core.socket,'create_connection',loader):
   p.network_session()
  return seen
 def test_a_resting_ps5_is_waited_for_and_a_loader_that_did_not_come_back_is_named(self):
  p=self.player();tries=[]
  def loader(address,timeout=None):tries.append(address);raise ConnectionRefusedError('refused')
  seen=self.run_session(p,[console(True),console(True),console(True),console(False)],loader)
  self.assertGreaterEqual(len(seen),4,'it kept asking until the PS5 woke up')
  texts=[text for _,text in p.events]
  self.assertIn('The PS5 is in rest mode: waiting for it to wake up',texts);self.assertIn('The PS5 woke up',texts)
  self.assertEqual(p.error,core.LOADER_GONE);self.assertGreater(len(tries),1,'the loader got a few seconds to come back');self.assertEqual(tries[0],(HOST,9021))
 def test_stopping_while_it_rests_ends_quietly(self):
  p=self.player();loader=lambda *a,**k:self.fail('nothing is sent to a resting PS5');shown=[]
  threading.Timer(.1,lambda:shown.append(p.waiting_text())).start();threading.Timer(.2,p.stop.set).start()
  self.run_session(p,[console(True)],loader)
  self.assertEqual(p.error,'');self.assertEqual(p.connection_state,'Disconnected')
  self.assertIn('rest mode',shown[0]);self.assertEqual(p.waiting_text(),'Connecting to your console…')
 def test_an_awake_ps5_whose_loader_is_not_running_gets_the_usual_message_at_once(self):
  p=self.player();tries=[]
  def loader(address,timeout=None):tries.append(address);raise ConnectionRefusedError('refused')
  self.run_session(p,[console(False)],loader)
  self.assertEqual(len(tries),1);self.assertEqual(p.error,core.unreachable(HOST))

if __name__=='__main__':unittest.main()
