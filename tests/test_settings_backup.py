import json,os,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import session_marker,settings_backup

MINE={'host':'192.168.1.50','profile':'quality','pairing_key':'sealed-key','psn_token':'sealed-token','discord_webhook':'sealed-hook',
 'api_secret':'abc','phone_tokens':['h1'],'away':{'on':True},'live_targets':{'twitch':{'key':'sealed-twitch','server':''},'custom':{'key':'sealed-custom','server':'rtmp://mine'}}}

class BackupTests(unittest.TestCase):
 def setUp(self):self.folder=Path(tempfile.mkdtemp())
 def test_a_backup_leaves_secrets_and_this_pcs_state_out(self):
  path=self.folder/'b.json';count=settings_backup.write(path,MINE,'1.9.0',now=0)
  data=json.loads(path.read_text(encoding='utf8'));text=path.read_text(encoding='utf8')
  self.assertEqual(data['kind'],'PlayBridge settings');self.assertEqual(data['version'],'1.9.0');self.assertEqual(count,len(data['settings']))
  for secret in ('sealed','abc','h1'):self.assertNotIn(secret,text)
  self.assertNotIn('away',data['settings']);self.assertEqual(data['settings']['live_targets']['custom'],{'key':'','server':'rtmp://mine'})
 def test_restoring_keeps_this_pcs_sign_ins_and_keys(self):
  path=self.folder/'b.json'
  settings_backup.write(path,dict(MINE,profile='balanced',live_targets={'twitch':{'key':'other','server':''},'kick':{'key':'x','server':'rtmps://k'}}),'1.9.0')
  merged=settings_backup.restore(MINE,settings_backup.read(path))
  self.assertEqual(merged['profile'],'balanced');self.assertEqual(merged['pairing_key'],'sealed-key');self.assertEqual(merged['away'],{'on':True})
  self.assertEqual(merged['live_targets']['twitch']['key'],'sealed-twitch');self.assertEqual(merged['live_targets']['kick'],{'key':'','server':'rtmps://k'})
  self.assertEqual(merged['live_targets']['custom']['key'],'sealed-custom')
 def test_other_files_are_refused_in_a_few_words(self):
  for name,body in (('a.json','{"kind":"other","settings":{}}'),('b.json','not json'),('c.json','[1,2]')):
   (self.folder/name).write_text(body,encoding='utf8')
   with self.assertRaises(ValueError) as caught:settings_backup.read(self.folder/name)
   self.assertIn('not a PlayBridge backup',str(caught.exception))
  (self.folder/'big.json').write_bytes(b' '*(settings_backup.LARGEST+1))
  with self.assertRaises(ValueError):settings_backup.read(self.folder/'big.json')

class SessionMarkerTests(unittest.TestCase):
 def test_a_normal_close_leaves_nothing_and_a_crash_leaves_its_page(self):
  folder=Path(tempfile.mkdtemp())
  self.assertIsNone(session_marker.begin(folder,'1.9.0'));session_marker.page(folder,'friends');session_marker.end(folder)
  self.assertIsNone(session_marker.begin(folder,'1.9.0'));session_marker.page(folder,'stats')
  # No end: the next start finds the last one, with its page.
  left=session_marker.begin(folder,'1.9.0')
  self.assertEqual(left['page'],'stats');self.assertEqual(left['pid'],os.getpid());self.assertEqual(left['version'],'1.9.0')
  self.assertEqual(json.loads((folder/session_marker.NAME).read_text(encoding='utf8'))['page'],'')

if __name__=='__main__':unittest.main()
