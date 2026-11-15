"""PS5 files over FTP: listings in either form become the same entries, folders first; the session finds the server on the second port,
lists, copies a file and a whole folder to the PC without replacing anything there, sends files, makes, renames and removes, refuses to
remove a folder that is not empty, and leaves nothing half written when a copy is stopped. Whole folders go to the PS5 into a folder
already there, and a text file or a picture can be looked at without a copy: the start of a long text file, a picture whole."""
import shutil,sys,tempfile,threading,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import ftp_files as ff
from ftp_standin import Standin

def wait(session,kinds=1,seconds=5):
 answers=[];end=time.monotonic()+seconds
 while len(answers)<kinds and time.monotonic()<end:answers+=session.take();time.sleep(0.01)
 return answers

class ParseTests(unittest.TestCase):
 def test_the_forms_a_ps5_server_answers_in(self):
  now=time.mktime((2026,11,15,12,0,0,0,0,-1))
  folder=ff.parse_list_line('drwxr-xr-x 1 root root 512 Nov 15 10:00 homebrew',now)
  self.assertEqual((folder['name'],folder['folder'],folder['size']),('homebrew',True,0));self.assertEqual(time.localtime(folder['when']).tm_year,2026)
  self.assertEqual(time.localtime(ff.parse_list_line('-rw-r--r-- 1 root root 5 Dec 24 10:00 old.txt',now)['when']).tm_year,2025,'a date ahead of today is last year')
  self.assertEqual(ff.parse_list_line('-rw-r--r-- 1 root root 2048 Jan 03 2025 my file.elf',now)['name'],'my file.elf')
  self.assertTrue(ff.parse_list_line('lrwxr-xr-x 1 root root 9 Nov 1 2020 usb -> /mnt/usb0',now)['link'])
  self.assertEqual(ff.parse_list_line('11-15-26 01:05PM <DIR> saves',now)['folder'],True)
  for junk in ('total 12','drwxr-xr-x 1 root root 0 Nov 15 10:00 ..','-rw-r--r-- 1 root root 1 Nov 15 10:00 a/b',''):self.assertIsNone(ff.parse_list_line(junk,now))
  self.assertIsNone(ff.from_facts('.',{'type':'cdir'}));self.assertEqual(ff.from_facts('x.bin',{'type':'file','size':'7','modify':'20261115120000'})['size'],7)
  self.assertEqual([entry['name'] for entry in ff.arranged([dict(name='b',folder=False,link=False),dict(name='Z',folder=True,link=False),dict(name='a',folder=False,link=False)])],['Z','a','b'])
 def test_what_can_be_looked_at(self):
  self.assertEqual(ff.preview_kind('Notes.TXT'),'text');self.assertEqual(ff.preview_kind('shot.png',1000),'image')
  self.assertEqual(ff.preview_kind('huge.png',ff.IMAGE_MOST+1),'');self.assertEqual(ff.preview_kind('tool.elf'),'')
  for data,ending in ((b'\x89PNG\r\n\x1a\nrest','.png'),(b'\xff\xd8\xff\xe0','.jpg'),(b'GIF89a..','.gif'),(b'BM....','.bmp'),(b'RIFF\0\0\0\0WEBPVP8 ',''),(b'hello','')):
   self.assertEqual(ff.image_type(data),ending)
  shown=ff.preview_of('a.txt','\ufeffline one\r\nline two'.encode('utf-8'))
  self.assertEqual((shown['kind'],shown['text'],shown['cut']),('text','line one\nline two',False))
  self.assertEqual(ff.preview_of('a.txt','café é'.encode('utf-8')[:-1],cut=True)['text'],'café ','a look cut inside a letter drops that letter')
  self.assertEqual(ff.preview_of('a.ini',b'caf\xe9')['text'],'café','text that is not UTF-8 is read as Windows text')
  self.assertIn('not plain text',ff.preview_of('a.log',b'\0\1\2')['why'])
  self.assertEqual(ff.preview_of('p.jpg',b'\xff\xd8\xff\xe0..'),dict(kind='image',ending='.jpg'))
  self.assertIn('not a picture',ff.preview_of('p.png',b'<html>')['why']);self.assertEqual(ff.preview_of('x.elf',b'E')['kind'],'none')
 def test_a_folder_to_send_becomes_folders_then_files(self):
  pc=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,pc,True)
  (pc/'Mods'/'inner').mkdir(parents=True);(pc/'Mods'/'empty').mkdir();(pc/'Mods'/'a.txt').write_bytes(b'a');(pc/'Mods'/'inner'/'b.txt').write_bytes(b'b');(pc/'c.bin').write_bytes(b'c')
  folders,sends=ff.put_plan([pc/'Mods',pc/'c.bin',pc/'missing.bin'],'/data')
  self.assertEqual(folders,['/data/Mods','/data/Mods/empty','/data/Mods/inner'])
  self.assertEqual([(path.relative_to(pc).as_posix(),place) for path,place in sends],[('Mods/a.txt','/data/Mods/a.txt'),('Mods/inner/b.txt','/data/Mods/inner/b.txt'),('c.bin','/data/c.bin')])
 def test_paths_and_free_names(self):
  self.assertEqual(ff.parent('/data/homebrew/'),'/data');self.assertEqual(ff.parent('/data'),'/');self.assertEqual(ff.join('/','data'),'/data')
  folder=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,folder,True);(folder/'save.bin').write_bytes(b'x')
  self.assertEqual(ff.free_name(folder,'save.bin').name,'save (2).bin');self.assertEqual(ff.free_name(folder,'new.bin').name,'new.bin')

class SessionTests(unittest.TestCase):
 def setUp(self):
  self.ps5=Path(tempfile.mkdtemp());self.pc=Path(tempfile.mkdtemp())
  self.addCleanup(shutil.rmtree,self.ps5,True);self.addCleanup(shutil.rmtree,self.pc,True)
  (self.ps5/'data'/'homebrew').mkdir(parents=True);(self.ps5/'data'/'homebrew'/'tool.elf').write_bytes(b'E'*3000)
  (self.ps5/'data'/'homebrew'/'sub').mkdir();(self.ps5/'data'/'homebrew'/'sub'/'notes.txt').write_bytes(b'hello')
  (self.ps5/'data'/'readme.txt').write_bytes(b'R'*10)
 def session(self,mlsd=True,closed_first=False):
  server=Standin(self.ps5,mlsd);self.addCleanup(server.stop);ports=(server.port,)
  if closed_first:
   closed=__import__('socket').socket();closed.bind(('127.0.0.1',0));ports=(closed.getsockname()[1],server.port);closed.close()
  session=ff.FileSession('127.0.0.1',ports=ports);self.addCleanup(session.close);return session,server
 def test_lists_in_both_forms_from_the_second_port(self):
  for mlsd in (True,False):
   session,server=self.session(mlsd,closed_first=True);session.ask('list',path='/data')
   answer=wait(session)[0];self.assertTrue(answer['ok'],answer['problem'])
   self.assertEqual([(entry['name'],entry['folder']) for entry in answer['value']['entries']],[('homebrew',True),('readme.txt',False)])
   self.assertEqual(session.port,server.port);self.assertEqual(any(command.startswith('MLSD') for command in server.commands),mlsd)
 def test_copies_to_the_pc_never_replace_anything(self):
  session,_=self.session();(self.pc/'tool.elf').write_bytes(b'mine')
  session.ask('get',path='/data/homebrew/tool.elf',size=3000,into=str(self.pc));answer=wait(session)[0]
  self.assertTrue(answer['ok'],answer['problem']);self.assertEqual(Path(answer['value']['saved']).name,'tool (2).elf');self.assertEqual((self.pc/'tool.elf').read_bytes(),b'mine')
  self.assertEqual(len(Path(answer['value']['saved']).read_bytes()),3000)
  session.ask('get',path='/data/homebrew',folder=True,into=str(self.pc));answer=wait(session)[0]
  self.assertTrue(answer['ok'],answer['problem']);self.assertEqual(answer['value']['count'],2);self.assertEqual((Path(answer['value']['saved'])/'sub'/'notes.txt').read_bytes(),b'hello')
 def test_sends_makes_renames_and_removes(self):
  session,_=self.session();source=self.pc/'new.bin';source.write_bytes(b'N'*70000)
  session.ask('put',files=[str(source)],folder='/data');session.ask('mkdir',folder='/data',name='saves');session.ask('rename',folder='/data',old='readme.txt',new='read me.txt')
  answers=wait(session,3);self.assertTrue(all(answer['ok'] for answer in answers),[answer['problem'] for answer in answers])
  self.assertEqual((self.ps5/'data'/'new.bin').read_bytes(),b'N'*70000);self.assertTrue((self.ps5/'data'/'saves').is_dir());self.assertTrue((self.ps5/'data'/'read me.txt').exists())
  session.ask('remove',folder='/data',name='homebrew',is_folder=True);answer=wait(session)[0]
  self.assertFalse(answer['ok']);self.assertIn('not empty',answer['problem']);self.assertTrue((self.ps5/'data'/'homebrew'/'tool.elf').exists())
  session.ask('remove',folder='/data',name='saves',is_folder=True);session.ask('remove',folder='/data',name='new.bin',is_folder=False)
  self.assertTrue(all(answer['ok'] for answer in wait(session,2)));self.assertFalse((self.ps5/'data'/'saves').exists());self.assertFalse((self.ps5/'data'/'new.bin').exists())
  session.ask('mkdir',folder='/data',name='../escape');answer=wait(session)[0];self.assertFalse(answer['ok']);self.assertIn('slash',answer['problem'])
 def test_a_whole_folder_goes_into_one_already_there(self):
  session,_=self.session();folder=self.pc/'homebrew';(folder/'more').mkdir(parents=True)
  (folder/'new.elf').write_bytes(b'N'*5000);(folder/'more'/'x.txt').write_bytes(b'x')
  session.ask('put',files=[str(folder)],folder='/data');answer=wait(session)[0]
  self.assertTrue(answer['ok'],answer['problem']);self.assertEqual(answer['value']['count'],2)
  self.assertEqual((self.ps5/'data'/'homebrew'/'tool.elf').read_bytes(),b'E'*3000,'what was there stays')
  self.assertEqual((self.ps5/'data'/'homebrew'/'new.elf').read_bytes(),b'N'*5000);self.assertEqual((self.ps5/'data'/'homebrew'/'more'/'x.txt').read_bytes(),b'x')
 def test_looks_at_files_without_copying_them(self):
  long_text=b'0123456789abcdef'*(ff.TEXT_MOST//16+4000);(self.ps5/'data'/'long.log').write_bytes(long_text)
  (self.ps5/'data'/'exact.txt').write_bytes(b'e'*ff.TEXT_MOST)
  picture=b'\x89PNG\r\n\x1a\n'+bytes(range(256))*40;(self.ps5/'data'/'shot.png').write_bytes(picture)
  session,server=self.session()
  session.ask('peek',path='/data/long.log',name='long.log',look='text');answer=wait(session)[0]
  self.assertTrue(answer['ok'],answer['problem']);self.assertTrue(answer['value']['cut']);self.assertEqual(answer['value']['data'],long_text[:ff.TEXT_MOST])
  session.ask('peek',path='/data/exact.txt',name='exact.txt',look='text');answer=wait(session)[0]
  self.assertTrue(answer['ok'],answer['problem']);self.assertFalse(answer['value']['cut'],'a file exactly at the limit is shown whole')
  session.ask('peek',path='/data/shot.png',name='shot.png',look='image',size=len(picture));answer=wait(session)[0]
  self.assertTrue(answer['ok'],answer['problem']);self.assertEqual((answer['value']['data'],answer['value']['cut']),(picture,False))
  session.ask('list',path='/data');answer=wait(session)[0];self.assertTrue(answer['ok'],'the connection dropped after a cut look is made again')
  session.ask('peek',path='/data/shot.png',name='shot.png',look='image',size=ff.IMAGE_MOST+1);answer=wait(session)[0]
  self.assertFalse(answer['ok']);self.assertIn('too big',answer['problem'])
  self.assertEqual(list(self.pc.iterdir()),[],'nothing is copied to the PC');self.assertEqual(sum(command.startswith('STOR') for command in server.commands),0)
 def test_a_stopped_copy_leaves_nothing_behind(self):
  (self.ps5/'big.bin').write_bytes(b'B'*(4*1024*1024));session,_=self.session()
  original=ff.FileSession.copy_down
  def slow(self,ftp,remote,target,total):
   self.stopping.set();return original(self,ftp,remote,target,total)
  ff.FileSession.copy_down=slow;self.addCleanup(setattr,ff.FileSession,'copy_down',original)
  session.ask('get',path='/big.bin',size=4*1024*1024,into=str(self.pc));answer=wait(session)[0]
  self.assertEqual(answer['problem'],'Stopped.');self.assertEqual(list(self.pc.iterdir()),[])
 def test_no_server_says_how_to_start_one(self):
  closed=__import__('socket').socket();closed.bind(('127.0.0.1',0));port=closed.getsockname()[1];closed.close()
  session=ff.FileSession('127.0.0.1',ports=(port,));self.addCleanup(session.close);session.ask('list',path='/')
  answer=wait(session)[0];self.assertFalse(answer['ok']);self.assertIn('homebrew menu',answer['problem'])

if __name__=='__main__':unittest.main()
