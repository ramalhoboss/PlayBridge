"""Local control: only requests that name this PC and carry the secret get an answer; commands wait in a queue for the window; status,
the overlay page, the command list and the newest trophy's picture are handed out."""
import http.client,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import local_api

class LocalApiTests(unittest.TestCase):
 def setUp(self):
  self.api=local_api.LocalApi();self.secret=local_api.new_secret();self.port=self.api.start(self.secret,47950);self.addCleanup(self.api.stop)
  self.assertIsNotNone(self.port)
 def ask(self,path,method='GET',host=None):
  connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
  try:
   connection.putrequest(method,path,skip_host=True);connection.putheader('Host',host or f'127.0.0.1:{self.port}');connection.endheaders()
   answer=connection.getresponse();return answer.status,dict(answer.getheaders()),answer.read()
  finally:connection.close()
 def test_only_this_pc_with_the_secret_gets_an_answer(self):
  self.assertEqual(self.ask(f'/{self.secret}/status',host=f'evil.example:{self.port}')[0],403)
  self.assertEqual(self.ask(f'/{self.secret}/status',host='127.0.0.1')[0],403)
  self.assertEqual(self.ask('/wrongsecret/status')[0],404);self.assertEqual(self.ask('/')[0],404)
  self.assertEqual(self.ask(f'/{self.secret}/status',host=f'localhost:{self.port}')[0],200)
  self.assertEqual(self.api.take(),[])
 def test_commands_wait_for_the_window_and_unknown_ones_are_refused(self):
  for name,method in (('screenshot','GET'),('record','POST'),('timer-stop','GET')):
   status,headers,body=self.ask(f'/{self.secret}/{name}',method);self.assertEqual(status,200);self.assertEqual(json.loads(body),{'ok':True,'command':name})
  self.assertEqual(self.ask(f'/{self.secret}/power-off')[0],404);self.assertEqual(self.ask(f'/{self.secret}/screenshot','HEAD')[0],200)
  self.assertEqual(self.api.take(),['screenshot','record','timer-stop']);self.assertEqual(self.api.take(),[])
 def test_status_pages_and_the_trophy_picture(self):
  self.api.publish({'game':{'name':'Nebula Drift 🚀'},'now':1.0})
  status,headers,body=self.ask(f'/{self.secret}/status');self.assertEqual(json.loads(body)['game']['name'],'Nebula Drift 🚀')
  self.assertEqual(headers['Cache-Control'],'no-store');self.assertNotIn('Access-Control-Allow-Origin',headers);self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
  for name,needle in (('overlay',b'PlayBridge overlay'),('',b'PlayBridge local control')):
   status,headers,body=self.ask(f'/{self.secret}/{name}');self.assertEqual(status,200);self.assertIn(needle,body);self.assertTrue(headers['Content-Type'].startswith('text/html'))
  self.assertEqual(self.ask(f'/{self.secret}/trophy.png')[0],404)
  self.api.publish({},b'\x89PNG picture');status,headers,body=self.ask(f'/{self.secret}/trophy.png');self.assertEqual((status,headers['Content-Type'],body),(200,'image/png',b'\x89PNG picture'))
 def test_a_taken_port_moves_to_the_next(self):
  other=local_api.LocalApi();self.addCleanup(other.stop)
  self.assertEqual(other.start('another-secret-1',self.port),self.port+1);self.assertTrue(other.address('status').endswith(f':{self.port+1}/another-secret-1/status'))
  other.stop();self.assertFalse(other.running);self.assertEqual(other.address(),'')

if __name__=='__main__':unittest.main()
