import sys,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from console_discovery import parse_response,manager_probe
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
if __name__=='__main__':unittest.main()
