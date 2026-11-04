import argparse,os,sys,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from console_discovery import firmware_name,locate,parse_response,manager_probe,supported
import playbridge as core
class DiscoveryTests(unittest.TestCase):
 def test_ps5_response(self):
  item=parse_response(b'HTTP/1.1 200 Ok\r\nhost-type:PS5\r\nhost-name:Living room\r\n','192.168.1.100');self.assertEqual(item['ip'],'192.168.1.100');self.assertEqual(item['name'],'Living room')
 def test_other_device_and_invalid_response(self):
  self.assertIsNone(parse_response(b'HTTP/1.1 200 OK\r\nhost-type:PS4\r\n','192.168.1.2'));self.assertIsNone(parse_response(b'random','192.168.1.2'))
 def test_manager_fingerprint_and_cleanup(self):
  with patch('console_discovery.http.client.HTTPConnection') as cls:
   c=cls.return_value;c.getresponse.return_value.status=200;c.getresponse.return_value.read.return_value=b'<title>PS5 Web File Manager</title>'
   self.assertEqual(manager_probe('192.168.1.100')['ip'],'192.168.1.100');c.close.assert_called_once()
 def test_unrelated_web_server(self):
  with patch('console_discovery.http.client.HTTPConnection') as cls:
   c=cls.return_value;c.getresponse.return_value.status=200;c.getresponse.return_value.read.return_value=b'<title>Printer</title>';self.assertIsNone(manager_probe('192.168.1.9'));c.close.assert_called_once()
class FindingTheConsole(unittest.TestCase):
 ok=b'HTTP/1.1 200 Ok\nhost-type:PS5\nhost-name:My PS5\nsystem-version:13600007\n'
 def test_the_answer_says_awake_or_resting_and_the_firmware(self):
  awake=parse_response(self.ok,'192.0.2.9');self.assertEqual((awake['name'],awake['resting'],awake['firmware']),('My PS5',False,'13600007'))
  self.assertTrue(parse_response(b'HTTP/1.1 620 Server Standby\nhost-type:PS5\n','192.0.2.9')['resting'])
 def test_firmware_reads_as_people_write_it(self):
  self.assertEqual(firmware_name('13600007'),'13.60');self.assertEqual(firmware_name('09400000'),'9.40');self.assertEqual(firmware_name(''),'');self.assertEqual(firmware_name('nonsense'),'')
 def test_only_a_firmware_the_console_names_can_be_refused(self):
  self.assertTrue(supported({'firmware':'13600007'}));self.assertFalse(supported({'firmware':'13800000'}));self.assertTrue(supported({'firmware':''}));self.assertTrue(supported({}))
 def test_the_saved_address_comes_first(self):
  with patch('console_discovery.ask',return_value={'ip':'192.0.2.9'}),patch('console_discovery.broadcast') as broadcast:
   self.assertEqual(locate('192.0.2.9')['ip'],'192.0.2.9');broadcast.assert_not_called()
 def test_a_silent_address_moves_only_to_a_single_console(self):
  one={'192.0.2.7':{'ip':'192.0.2.7'}};two=dict(one,**{'192.0.2.8':{'ip':'192.0.2.8'}})
  with patch('console_discovery.ask',return_value=None),patch('console_discovery.broadcast',return_value=one):self.assertEqual(locate('192.0.2.9')['ip'],'192.0.2.7')
  with patch('console_discovery.ask',return_value=None),patch('console_discovery.broadcast',return_value=two):self.assertIsNone(locate('192.0.2.9'))
 def test_a_loopback_address_never_moves_to_a_real_console(self):
  with patch('console_discovery.ask') as ask,patch('console_discovery.broadcast') as broadcast:
   self.assertIsNone(locate('127.0.0.1'));ask.assert_not_called();broadcast.assert_not_called()
class TypedAddressTests(unittest.TestCase):
 moved={'ip':'192.0.2.7','name':'PS5','resting':False,'firmware':'13600007'}
 def player(self,settings):
  with patch.object(core,'config',return_value=settings):
   return core.Player(argparse.Namespace(renderer='gdi',profile='balanced',auto_reconnect=False,device=None,connect_only=False,host='192.0.2.9',record=False,preview=False,headless=True,seconds=0))
 def found(self,p):
  with patch.object(core,'locate',return_value=self.moved),patch.object(core,'save_config') as saved:p.find_console()
  return saved
 def test_an_address_typed_in_settings_stays_when_another_ps5_answers(self):
  p=self.player({'host':'192.0.2.9','host_auto':False});saved=self.found(p)
  self.assertEqual(p.args.host,'192.0.2.9');self.assertIsNone(p.console);self.assertEqual(p.elsewhere,'192.0.2.7');saved.assert_not_called()
 def test_an_address_found_by_itself_follows_the_console(self):
  for settings in ({},{'host':'192.0.2.9'},{'host':'192.0.2.9','host_auto':True}):
   p=self.player(settings);saved=self.found(p)
   self.assertEqual(p.args.host,'192.0.2.7');self.assertIsNone(p.elsewhere);saved.assert_called_once_with(host='192.0.2.7')
 def test_the_message_names_the_address_and_the_ps5_that_answered(self):
  self.assertIn('192.0.2.9',core.unreachable('192.0.2.9'))
  message=core.unreachable('192.0.2.9','192.0.2.7');self.assertIn('192.0.2.9',message);self.assertIn('192.0.2.7',message);self.assertIn('Find console',message)
if __name__=='__main__':unittest.main()
