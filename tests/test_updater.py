import hashlib,http.server,json,os,re,sys,tempfile,threading,unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import updater
from app_version import VERSION

PROGRAM=b'MZ'+bytes(range(256))*400

class Release(http.server.BaseHTTPRequestHandler):
 """A GitHub release on this PC: the API answer, the program and its checksums."""
 files={}
 def do_GET(self):
  body=self.files.get(self.path)
  if body is None:self.send_response(404);self.end_headers();return
  self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def log_message(self,*args):pass

class UpdaterTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Release)
  threading.Thread(target=cls.server.serve_forever,daemon=True).start()
  cls.base=f'http://127.0.0.1:{cls.server.server_address[1]}'
 @classmethod
 def tearDownClass(cls):cls.server.shutdown();cls.server.server_close()
 def publish(self,tag='v99.0.0',program=PROGRAM,sums=None,**extra):
  sums=sums if sums is not None else f'{hashlib.sha256(program).hexdigest()}  PlayBridge.exe\n{"0"*64}  PlayBridge.elf\n'
  release=dict(tag_name=tag,html_url='https://github.com/ramalhoboss/PlayBridge/releases/tag/'+tag,draft=False,prerelease=False,
   assets=[dict(name='PlayBridge.exe',size=len(program),browser_download_url=self.base+'/PlayBridge.exe'),dict(name='SHA256SUMS.txt',size=len(sums),browser_download_url=self.base+'/SHA256SUMS.txt')])
  release.update(extra)
  Release.files={'/latest':json.dumps(release).encode(),'/PlayBridge.exe':program,'/SHA256SUMS.txt':sums.encode()}
 def setUp(self):
  self.folder=Path(tempfile.mkdtemp())
  patches=[mock.patch.object(updater,'LATEST',self.base+'/latest'),mock.patch.object(updater,'frozen',lambda:True)]
  for patch in patches:patch.start();self.addCleanup(patch.stop)
 def updates(self):return updater.Updater(self.folder,rate=None)

 def test_versions(self):
  self.assertEqual(updater.parse_version('v1.6.0'),(1,6,0));self.assertEqual(updater.parse_version('1.6'),(1,6,0))
  self.assertIsNone(updater.parse_version('latest'))
  self.assertTrue(updater.is_newer('v1.6.1','1.6.0'));self.assertTrue(updater.is_newer('1.10.0','1.9.9'))
  self.assertFalse(updater.is_newer('v1.6.0','1.6.0'));self.assertFalse(updater.is_newer('v1.5.2','1.6.0'));self.assertFalse(updater.is_newer('nightly','1.6.0'))
  # Betas: before their final version, after the one before, in their own order.
  self.assertEqual(updater.version_key('v1.8.0-beta.2'),(1,8,0,1,2));self.assertEqual(updater.version_name('V1.8-RC1'),'1.8.0-rc.1');self.assertEqual(updater.version_name('1.7.1'),'1.7.1')
  self.assertTrue(updater.is_newer('1.8.0','1.8.0-beta.3'));self.assertTrue(updater.is_newer('1.8.0-beta.1','1.7.1'));self.assertFalse(updater.is_newer('1.8.0-beta.1','1.8.0'))
  self.assertTrue(updater.is_newer('1.8.0-beta.10','1.8.0-beta.9'));self.assertTrue(updater.is_newer('1.8.0-rc.1','1.8.0-beta.9'))
 def test_release_needs_the_program_and_its_checksums(self):
  good=dict(tag_name='v2.0.0',assets=[dict(name='PlayBridge.exe',browser_download_url='x',size=3),dict(name='SHA256SUMS.txt',browser_download_url='y')])
  self.assertEqual(updater.read_release(good)['version'],'2.0.0')
  self.assertIsNone(updater.read_release(dict(good,draft=True)));self.assertIsNone(updater.read_release(dict(good,prerelease=True)))
  self.assertIsNone(updater.read_release(dict(good,assets=good['assets'][:1])));self.assertIsNone(updater.read_release(dict(good,tag_name='nightly')))
  self.assertIsNone(updater.read_release(None))
  beta=dict(good,tag_name='v2.1.0-beta.1',prerelease=True)
  self.assertEqual(updater.read_release(beta,beta=True)['version'],'2.1.0-beta.1');self.assertIsNone(updater.read_release(beta))
  self.assertIsNone(updater.read_release(dict(beta,prerelease=False)),'a beta tag stays off the final channel even when not marked')
 def test_checksum_lines(self):
  text=f'{"a"*64}  PlayBridge.elf\n{"B"*64} *PlayBridge.exe\n'
  self.assertEqual(updater.checksum_for(text),'b'*64);self.assertIsNone(updater.checksum_for('nothing here'))

 def test_newer_release_is_downloaded_and_checked(self):
  self.publish();updates=self.updates();updates.run()
  status=updates.status()
  self.assertEqual(status['state'],'ready');self.assertEqual(status['version'],'99.0.0');self.assertTrue(status['installable'])
  self.assertEqual(Path(updates.file).read_bytes(),PROGRAM);self.assertEqual(Path(updates.file).name,'PlayBridge-99.0.0.exe')
  self.assertEqual(list(self.folder.glob('*.partial')),[])
  self.assertIn('99.0.0',updates.text())
  # A second look finds the same file already there and keeps it.
  again=self.updates();again.run();self.assertEqual(again.status()['state'],'ready')
 def kept_only_the_error(self,words):
  """Nothing but update-error.log is left, and it names what went wrong."""
  self.assertEqual([path.name for path in self.folder.iterdir()],['update-error.log'])
  self.assertIn(words,(self.folder/'update-error.log').read_text(encoding='utf8'))
 def test_a_wrong_checksum_keeps_nothing(self):
  self.publish(sums=f'{"0"*64}  PlayBridge.exe\n');updates=self.updates();updates.run()
  self.assertEqual(updates.status()['state'],'failed');self.assertIn('checksum',updates.text());self.kept_only_the_error('checksum')
 def test_a_program_that_is_not_windows_is_refused(self):
  program=b'ZZ'+PROGRAM[2:];self.publish(program=program);updates=self.updates();updates.run()
  self.assertEqual(updates.status()['state'],'failed');self.kept_only_the_error('not a Windows program')
 def test_a_short_download_is_refused(self):
  self.publish();Release.files['/PlayBridge.exe']=PROGRAM[:1000];updates=self.updates();updates.run()
  self.assertEqual(updates.status()['state'],'failed');self.kept_only_the_error('stopped at 1000')
 def test_a_download_that_cannot_connect_says_so_in_short(self):
  self.publish(assets=[dict(name='PlayBridge.exe',size=len(PROGRAM),browser_download_url='http://127.0.0.1:1/PlayBridge.exe'),
   dict(name='SHA256SUMS.txt',size=200,browser_download_url=self.base+'/SHA256SUMS.txt')])
  updates=self.updates();updates.run()
  self.assertEqual(updates.status()['state'],'failed');self.assertIn('did not finish (URLError)',updates.text());self.kept_only_the_error('URLError')
 def test_the_same_version_is_current(self):
  self.publish(tag='v'+VERSION);updates=self.updates();updates.run()
  self.assertEqual(updates.status()['state'],'current');self.assertIn('latest',updates.text());self.assertFalse(self.folder.exists() and any(self.folder.iterdir()))
 def test_from_source_it_only_tells(self):
  self.publish()
  with mock.patch.object(updater,'frozen',lambda:False):
   updates=self.updates();updates.run();status=updates.status()
  self.assertEqual(status['state'],'available');self.assertFalse(status['installable']);self.assertFalse(self.folder.exists() and any(self.folder.iterdir()))
 def test_a_downloaded_version_asks_to_restart_and_update(self):
  self.publish();updates=self.updates();self.assertIsNone(updater.prompt(updates.status()));updates.run()
  ask=updater.prompt(updates.status())
  self.assertEqual((ask['kind'],ask['version'],ask['action'],ask['cancel']),('install','99.0.0','Restart and update','Later'))
  self.assertIn('99.0.0',ask['title']);self.assertIn(VERSION,ask['text']);self.assertIn('when you close PlayBridge',ask['text'])
 def test_from_source_it_asks_to_open_the_release_page(self):
  self.publish()
  with mock.patch.object(updater,'frozen',lambda:False):
   updates=self.updates();updates.run();ask=updater.prompt(updates.status(),source=True)
  self.assertEqual((ask['kind'],ask['version'],ask['action']),('page','99.0.0','Open the release page'));self.assertIn('source',ask['text'])
 def test_nothing_is_asked_without_a_new_version(self):
  self.publish(tag='v'+VERSION);updates=self.updates();updates.run();self.assertIsNone(updater.prompt(updates.status()))
  self.publish(sums='');updates=self.updates();updates.run()
  self.assertEqual(updates.status()['state'],'failed');self.assertIsNone(updater.prompt(updates.status()))
  self.publish();updates=self.updates()
  with mock.patch.object(updater,'checksum_for',lambda text:'0'*64):updates.run()
  self.assertEqual(updates.status()['state'],'failed');self.assertIsNone(updater.prompt(updates.status()))
 def test_no_network_is_a_failure_that_says_so(self):
  with mock.patch.object(updater,'LATEST',self.base+'/missing'):
   updates=self.updates();updates.run()
  self.assertEqual(updates.status()['state'],'failed');self.assertIn('GitHub',updates.text())
 def test_revision_moves_with_the_state(self):
  self.publish();updates=self.updates();first=updates.status()['revision'];updates.run()
  self.assertGreater(updates.status()['revision'],first)
  seen=updates.status()['revision'];updates.set_automatic(False)
  self.assertGreater(updates.status()['revision'],seen);self.assertFalse(updates.status()['automatic'])

 def test_install_starts_the_new_program_with_a_clean_environment(self):
  self.publish();updates=self.updates();updates.run()
  with mock.patch.object(updater.subprocess,'Popen') as popen:
   self.assertTrue(updates.install(relaunch=True))
  command=popen.call_args.args[0];environment=popen.call_args.kwargs['env']
  self.assertEqual(command[0],str(updates.file));self.assertEqual(command[1],'--finish-update');self.assertEqual(command[-1],'--relaunch')
  self.assertEqual(environment['PYINSTALLER_RESET_ENVIRONMENT'],'1')
 def test_nothing_to_install_does_nothing(self):
  updates=self.updates()
  with mock.patch.object(updater.subprocess,'Popen') as popen:self.assertFalse(updates.install())
  popen.assert_not_called()

 def test_finish_puts_the_new_program_in_place_and_opens_it(self):
  source=self.folder/'PlayBridge-99.0.0.exe';target=self.folder/'app'/'PlayBridge.exe';target.parent.mkdir(parents=True)
  source.write_bytes(PROGRAM);target.write_bytes(b'MZ old')
  opened=[]
  self.assertEqual(updater.finish(target,True,source=source,wait=2,start=opened.append,say=self.fail),0)
  self.assertEqual(target.read_bytes(),PROGRAM);self.assertEqual(opened,[target]);self.assertFalse(target.with_name('PlayBridge.exe.update').exists())
 def test_finish_waits_for_the_old_program_to_let_go(self):
  source=self.folder/'new.exe';target=self.folder/'PlayBridge.exe';source.write_bytes(PROGRAM);target.write_bytes(b'MZ old')
  real=os.replace;tries=[]
  def busy(a,b):
   tries.append(1)
   if len(tries)<3:raise PermissionError(13,'in use')
   real(a,b)
  with mock.patch.object(updater.os,'replace',busy),mock.patch.object(updater.time,'sleep'):
   self.assertEqual(updater.finish(target,False,source=source,wait=30,say=self.fail),0)
  self.assertEqual(len(tries),3);self.assertEqual(target.read_bytes(),PROGRAM)
 def test_finish_gives_up_and_says_where_the_new_program_is(self):
  source=self.folder/'new.exe';source.write_bytes(PROGRAM);said=[]
  self.assertEqual(updater.finish(self.folder/'gone'/'PlayBridge.exe',True,source=source,wait=0,start=self.fail,say=said.append),1)
  self.assertIn(str(source),said[0])
 def test_finish_keeps_the_replaced_program_for_going_back(self):
  source=self.folder/'new.exe';target=self.folder/'app'/'PlayBridge.exe';keep=self.folder/'previous';target.parent.mkdir();keep.mkdir()
  source.write_bytes(PROGRAM);target.write_bytes(b'MZ old');(keep/'PlayBridge-0.9.0.exe').write_bytes(b'MZ older')
  self.assertEqual(updater.finish(target,False,source=source,wait=2,say=self.fail,keep=keep,old_version='1.0.0'),0)
  self.assertEqual(sorted(p.name for p in keep.iterdir()),['PlayBridge-1.0.0.exe']);self.assertEqual((keep/'PlayBridge-1.0.0.exe').read_bytes(),b'MZ old')
  self.assertEqual(updater.kept_previous(keep,current='99.0.0'),('1.0.0',keep/'PlayBridge-1.0.0.exe'))
  # Not older than this version, or not a program: nothing to go back to.
  self.assertIsNone(updater.kept_previous(keep,current='1.0.0'))
  (keep/'PlayBridge-1.0.0.exe').write_bytes(b'not a program');self.assertIsNone(updater.kept_previous(keep,current='99.0.0'))
 def test_a_failed_finish_keeps_nothing_and_an_unknown_version_is_not_kept(self):
  source=self.folder/'new.exe';source.write_bytes(PROGRAM);keep=self.folder/'previous'
  self.assertEqual(updater.finish(self.folder/'gone'/'PlayBridge.exe',False,source=source,wait=0,say=lambda text:None,keep=keep,old_version='1.0.0'),1)
  self.assertFalse(any(keep.glob('*')) if keep.exists() else False)
  target=self.folder/'PlayBridge.exe';target.write_bytes(b'MZ old')
  with mock.patch.object(updater,'exe_version',lambda path:None):self.assertEqual(updater.finish(target,False,source=source,wait=2,say=self.fail,keep=keep),0)
  self.assertFalse(any(keep.glob('*')) if keep.exists() else False)
 def test_going_back_starts_the_kept_program_without_keeping_again(self):
  keep=self.folder/updater.PREVIOUS;keep.mkdir();(keep/'PlayBridge-1.0.0.exe').write_bytes(b'MZ old')
  updates=self.updates();self.assertEqual(updates.status()['previous'],'1.0.0')
  with mock.patch.object(updater.subprocess,'Popen') as popen:self.assertTrue(updates.go_back())
  command=popen.call_args.args[0]
  self.assertEqual(command[:2],[str(keep/'PlayBridge-1.0.0.exe'),'--finish-update']);self.assertEqual(command[-2:],['--relaunch','--no-keep'])
  empty=updater.Updater(self.folder/'other',rate=None);self.assertIsNone(empty.status()['previous'])
  with mock.patch.object(updater.subprocess,'Popen') as popen:self.assertFalse(empty.go_back())
  popen.assert_not_called()
 def test_the_version_is_read_from_a_programs_details(self):
  if sys.platform!='win32' or sys.version_info.releaselevel!='final':self.skipTest('a final Python on Windows')
  self.assertEqual(updater.exe_version(sys.executable),'%d.%d.%d'%sys.version_info[:3])
  self.assertIsNone(updater.exe_version(self.folder/'missing.exe'))
 def test_tidy_keeps_only_newer_downloads(self):
  for name in ('PlayBridge-1.0.0.exe',f'PlayBridge-{VERSION}.exe','PlayBridge-99.0.0.exe','PlayBridge-99.0.0.exe.partial','PlayBridge-99.1.0-beta.1.exe','PlayBridge-1.0.0-beta.1.exe'):(self.folder/name).write_bytes(b'x')
  self.assertTrue(updater.tidy(self.folder,tries=1))
  self.assertEqual(sorted(p.name for p in self.folder.iterdir()),['PlayBridge-99.0.0.exe','PlayBridge-99.1.0-beta.1.exe'])
 def test_the_beta_channel_takes_the_newest_release_betas_included(self):
  self.publish('v99.0.0');final=json.loads(Release.files['/latest']);beta=dict(final,tag_name='v99.1.0-beta.2',prerelease=True)
  Release.files['/releases']=json.dumps([beta,final,dict(final,tag_name='v99.2.0-beta.1',draft=True)]).encode()
  with mock.patch.object(updater,'RELEASES',self.base+'/releases'):
   updates=updater.Updater(self.folder,rate=None,channel='beta');updates.run();status=updates.status()
   self.assertEqual((status['state'],status['version'],status['channel']),('ready','99.1.0-beta.2','beta'));self.assertEqual(Path(updates.file).name,'PlayBridge-99.1.0-beta.2.exe')
   # Off again: the waiting beta is dropped, and the final channel's newest is taken.
   updates.set_channel('stable');self.assertEqual(updates.status()['state'],'idle');updates.run()
   self.assertEqual((updates.status()['state'],updates.status()['version']),('ready','99.0.0'))
   self.assertEqual(updater.Updater(self.folder,channel='nightly').channel,'stable')

 def test_the_version_matches_the_exe_details(self):
  details=(Path(__file__).resolve().parents[1]/'app'/'version.txt').read_text(encoding='utf8')
  self.assertIn(f"StringStruct('ProductVersion','{VERSION}')",details)
  self.assertIn('filevers=('+','.join(VERSION.split('.'))+',0)',details)

if __name__=='__main__':unittest.main()
