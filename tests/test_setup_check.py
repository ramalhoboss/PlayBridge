import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import setup_check
from setup_check import FAIL,NOTE,OK,WARN

CARD={'name':'Test card','vendor':'AMD','decodes':{1:True,2:True,3:True,4:True,5:True,6:True}}

def states(items):return [entry['state'] for entry in items]

class ConsoleTests(unittest.TestCase):
 def check(self,answer,others=(),manager=True,host='192.168.1.50'):
  return setup_check.console_items(host,ask=lambda h:answer,broadcast=lambda:{ip:{} for ip in others},probe=lambda h:manager)
 def test_a_ps5_that_answers_on_supported_firmware(self):
  items=self.check({'name':'PS5-123','firmware':'13600007','resting':False})
  self.assertEqual(states(items),[OK,OK,OK]);self.assertIn('13.60',items[1]['title'])
 def test_other_firmware_and_rest_mode_are_said(self):
  items=self.check({'name':'PS5','firmware':'14000004','resting':True})
  self.assertEqual(states(items),[WARN,FAIL]);self.assertIn('rest mode',items[0]['title']);self.assertIn('14.00',items[1]['title'])
 def test_no_answer_points_to_a_ps5_found_elsewhere(self):
  items=self.check(None,others=['192.168.1.77'])
  self.assertEqual(states(items),[FAIL]);self.assertIn('192.168.1.77',items[0]['text'])
  self.assertEqual(states(self.check(None)),[FAIL])
 def test_no_address_and_no_payload_manager(self):
  self.assertEqual(states(self.check(None,host='')),[FAIL])
  self.assertEqual(states(self.check({'name':'PS5','firmware':'','resting':False},manager=False)),[OK,NOTE])

class NetworkAndPcTests(unittest.TestCase):
 def test_same_network_by_cable_and_over_wifi(self):
  cable=setup_check.network_items('192.168.1.50',['192.168.1.20'],{'kind':'cable','name':'Ethernet','speed':1_000_000_000})
  self.assertEqual(states(cable),[OK,OK]);self.assertIn('1 Gbps',cable[1]['title'])
  wifi=setup_check.network_items('192.168.1.50',['192.168.1.20'],{'kind':'wifi','name':'Wi-Fi','speed':866_700_000})
  self.assertEqual(states(wifi),[OK,WARN]);self.assertIn('867 Mbps',wifi[1]['title'])
  slow=setup_check.network_items('192.168.1.50',['192.168.1.20'],{'kind':'cable','name':'Ethernet','speed':100_000_000})
  self.assertEqual(states(slow),[OK,WARN])
 def test_different_networks_and_no_network(self):
  self.assertEqual(states(setup_check.network_items('192.168.1.50',['10.0.0.4'],None)),[WARN])
  # The address Windows sends from decides, not every adapter this PC has.
  self.assertEqual(states(setup_check.network_items('192.168.1.50',['172.24.112.1','192.168.1.20'],None,source='192.168.1.20')),[OK])
  routed=setup_check.network_items('192.168.1.50',['172.24.112.1','10.0.0.4'],None,source='10.0.0.4')
  self.assertEqual(states(routed),[WARN]);self.assertNotIn('172.24',routed[0]['title'])
  self.assertEqual(states(setup_check.network_items('192.168.1.50',[],None)),[FAIL])
 def test_this_pcs_parts(self):
  items=setup_check.pc_items(CARD,True,50*1024**3,'Speakers')
  self.assertEqual(states(items),[OK,OK,OK,OK])
  items=setup_check.pc_items(None,False,2*1024**3,'')
  self.assertEqual(states(items),[WARN,FAIL,WARN,WARN])
 def test_the_whole_run_and_its_headline(self):
  folder=tempfile.mkdtemp()
  items=setup_check.run('192.168.1.50',CARD,True,folder,'Speakers',addresses=['192.168.1.20'],link={'kind':'cable','name':'Ethernet','speed':10**9},
   console=lambda host:[setup_check.item(OK,'PS5 answered')])
  self.assertEqual(setup_check.headline(items),'Everything is ready to play.')
  self.assertEqual(setup_check.headline(items+[setup_check.item(WARN,'x'),setup_check.item(NOTE,'y')]),'1 thing to look at.')
 def test_the_link_to_this_pc_itself_is_read_from_windows(self):
  if sys.platform!='win32':self.skipTest('Windows')
  self.assertEqual(setup_check.source_address('127.0.0.1'),'127.0.0.1')
  link=setup_check.link_of('127.0.0.1')
  self.assertIsNotNone(link);self.assertEqual(link['kind'],'other');self.assertTrue(link['name'])

if __name__=='__main__':unittest.main()
