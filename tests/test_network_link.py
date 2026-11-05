"""The stats say whether the PS5 is reached over Wi-Fi or a cable."""
import os,sys,unittest
from pathlib import Path
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import network_link as n

class LinkTests(unittest.TestCase):
 def test_an_address_that_is_not_one_gives_nothing(self):
  self.assertIsNone(n.link('not an address'))

@unittest.skipUnless(sys.platform=='win32','Windows only')
class WindowsTests(unittest.TestCase):
 def test_the_connection_to_this_pcs_own_network_is_named(self):
  # Reads only. The loopback is neither Wi-Fi nor a cable.
  self.assertEqual(n.link('127.0.0.1'),'other')

if __name__=='__main__':unittest.main()
