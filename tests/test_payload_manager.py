"""The payload shelf reads .elf assets from a repository's releases, keeps each at its newest release, marks a newer copy as an update,
stores only real payloads; the developer watch reports a change once; the kernel-log reader drops the backlog and only listens."""
import json,socket,sys,tempfile,threading,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import payload_manager as pm
import payload_sender

ELF=b'\x7fELF\x02\x01'+b'\x00'*12+(0x3E).to_bytes(2,'little')+b'\x00'*200

def release(tag,when,assets):
 return dict(tag_name=tag,published_at=when,draft=False,assets=assets)
def asset(name,url,size=300,digest='',ident=1):
 return dict(name=name,browser_download_url=url,size=size,digest=digest,id=ident)

class CatalogTests(unittest.TestCase):
 def test_only_elf_assets_each_at_its_newest_release(self):
  data=json.dumps([
   release('v2','2026-02-01T00:00:00Z',[asset('tool.elf','u/tool2',digest='sha256:bbb'),asset('notes.txt','u/notes')]),
   release('v1','2026-01-01T00:00:00Z',[asset('tool.elf','u/tool1',digest='sha256:aaa'),asset('other.elf','u/other1')]),
   dict(tag_name='draft',draft=True,assets=[asset('secret.elf','u/secret')]),
  ])
  items=pm.read_catalog(data,'owner/repo')
  self.assertEqual([item['name'] for item in items],['tool.elf','other.elf'])
  self.assertEqual(items[0]['tag'],'v2');self.assertEqual(items[0]['url'],'u/tool2');self.assertEqual(items[0]['repo'],'owner/repo')
  self.assertNotIn('secret.elf',[item['name'] for item in items])
 def test_a_bad_repository_name_and_list(self):
  self.assertIsNone(pm.releases_url('justone'));self.assertIsNone(pm.releases_url(''))
  self.assertTrue(pm.releases_url('owner/repo').endswith('/owner/repo/releases?per_page=20'))
  with self.assertRaises(pm.CatalogError):pm.read_catalog('not json')
  with self.assertRaises(pm.CatalogError):pm.read_catalog(json.dumps({'not':'a list'}))

class StoreTests(unittest.TestCase):
 def setUp(self):self.folder=Path(tempfile.mkdtemp());self.addCleanup(__import__('shutil').rmtree,self.folder,True);self.store=pm.Store(self.folder)
 def test_store_marks_an_update_and_keeps_only_payloads(self):
  item=dict(name='tool.elf',tag='v1',digest='sha256:aaa',when='2026-01-01',repo='o/r',url='u')
  self.store.store(item,ELF);self.assertTrue(self.store.have('tool.elf'))
  listing=pm.Store(self.folder).listing([item]);self.assertTrue(listing[0]['have']);self.assertFalse(listing[0]['update'])
  newer=dict(item,tag='v2',digest='sha256:bbb')
  self.assertTrue(pm.Store(self.folder).listing([newer])[0]['update'],'a newer release shows as an update')
  with self.assertRaises(payload_sender.PayloadError):self.store.store(dict(name='bad.elf'),b'not an elf')
  self.assertFalse(self.store.have('bad.elf'))
 def test_download_checks_the_bytes(self):
  item=dict(name='tool.elf',url='u',size=300)
  self.assertEqual(pm.download(item,opener=lambda url,timeout=15:ELF)[:4],b'\x7fELF')
  with self.assertRaises(pm.CatalogError):pm.download(item,opener=lambda url,timeout=15:b'nope')
  with self.assertRaises(pm.CatalogError):pm.download(dict(item,size=pm.payload_sender.LIMIT+1),opener=lambda url,timeout=15:ELF)

class ShelfTests(unittest.TestCase):
 def test_shelf_fetches_and_lists(self):
  folder=Path(tempfile.mkdtemp());self.addCleanup(__import__('shutil').rmtree,folder,True)
  data=json.dumps([release('v1','2026-01-01T00:00:00Z',[asset('tool.elf','u/tool1')])])
  done=threading.Event();shelf=pm.Shelf(pm.Store(folder),'owner/repo',opener=lambda url,timeout=15:data)
  shelf.fetch(done.set);self.assertTrue(done.wait(2));self.assertEqual([item['name'] for item in shelf.items()],['tool.elf']);self.assertEqual(shelf.status,'')
  bad=pm.Shelf(pm.Store(folder),'justone');bad.fetch();self.assertIn('owner/name',bad.status)

class WatchTests(unittest.TestCase):
 def test_a_change_is_reported_once(self):
  folder=Path(tempfile.mkdtemp());self.addCleanup(__import__('shutil').rmtree,folder,True);path=folder/'build.elf'
  path.write_bytes(ELF);watch=pm.Watch(path);self.assertFalse(watch.changed())
  path.write_bytes(ELF+b'\x01'*8);self.assertTrue(watch.changed());self.assertFalse(watch.changed())
  self.assertEqual(watch.read()[:4],b'\x7fELF')

class KernelLogTests(unittest.TestCase):
 def test_backlog_is_dropped_and_it_only_listens(self):
  sent=[]
  class FakeSock:
   def __init__(self,chunks):self.chunks=list(chunks)
   def settimeout(self,_):pass
   def recv(self,_):
    if self.chunks:
     chunk=self.chunks.pop(0)
     if chunk is None:time.sleep(0.02);raise socket.timeout()
     return chunk
    return b''
   def sendall(self,data):sent.append(data)
   def send(self,data):sent.append(data)
   def close(self):pass
  times=iter([0.0,0.0,2.0,2.0,2.0,2.0])
  log=pm.KernelLog('1.2.3.4',opener=lambda:FakeSock([b'old line\n',None,b'fresh one\nhalf',b' line\n']),clock=lambda:next(times,9.0))
  log.start()
  for _ in range(50):
   if not log.running and not log.lines:time.sleep(0.01)
   if 'fresh one' in ' '.join(log.lines):break
   time.sleep(0.02)
  lines=log.take();log.stop()
  self.assertIn('fresh one',lines);self.assertNotIn('old line',lines);self.assertEqual(sent,[],'the reader never sends')

if __name__=='__main__':unittest.main()
