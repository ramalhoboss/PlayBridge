"""Save backups: each game's saves read from a stand-in console that answers LIST and RANGE as the payload does, copied whole, a new copy
only when they changed, unchanged files shared on disk, a game that opens halfway, an older payload, the longest paths and the pace while
the stream plays."""
import json,os,shutil,socket,struct,sys,tempfile,threading,unittest
from pathlib import Path
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import save_backup as sb

USER=0x1a2b3c4d;HOME='/user/home/1a2b3c4d';PS5=HOME+'/savedata_prospero';PS4=HOME+'/savedata'
IDLE=dict(user=USER,app=0,title='');PLAYING=dict(user=USER,app=7,title='PPSA01234')
NAMES={'PPSA01234':'Astro: Bot','CUSA00001':'Old Game'}

def layout():
 files={PS5+'/PPSA01234/sdimg_SAVEDATA00':b'0123456789',PS5+'/PPSA01234/inner/param':b'abcde',PS4+'/CUSA00001/SAVEDATA00.bin':b'wxyz',
  PS5+'/PPSA01234/'+'y'*70:b'far'}
 tree={PS5:[('d',1,'PPSA01234'),('f',1,'stray'),('d',1,'lowercase')],PS5+'/PPSA01234':[('f',100,'sdimg_SAVEDATA00'),('d',1,'inner'),('f',1,'.hidden'),('d',1,'x'*90),('f',1,'y'*70)],
  PS5+'/PPSA01234/inner':[('f',100,'param')],PS4:[('d',1,'CUSA00001')],PS4+'/CUSA00001':[('f',50,'SAVEDATA00.bin')]}
 return tree,files

class FakeConsole:
 """LIST and RANGE as the payload answers them, from tree and files. allowed=False: a payload from before save backups."""
 def __init__(self,tree,files,allowed=True):
  self.tree=tree;self.files=files;self.allowed=allowed;self.asked=[]
  self.server=socket.create_server(('127.0.0.1',0));threading.Thread(target=self.serve,daemon=True).start()
 def reply(self,connection,result,data=b''):connection.sendall(struct.pack('<4siI',b'PBR1',result,len(data))+data)
 def serve(self):
  connection,_=self.server.accept();self.server.close()
  with connection:
   while True:
    head=b''
    while len(head)<12:
     part=connection.recv(12-len(head))
     if not part:return
     head+=part
    _,command,length=struct.unpack('<4sII',head);body=b''
    while len(body)<length:body+=connection.recv(length-len(body))
    if length>128:return
    if command==9:
     path=body.decode('utf8');self.asked.append(('LIST',path))
     if not self.allowed:self.reply(connection,13)
     elif path in self.tree:
      lines=''.join(f'{kind}\t{len(self.files.get(path+"/"+name,b""))}\t{stamp}\t{name}\n' for kind,stamp,name in self.tree[path])
      self.reply(connection,0,lines.encode())
     else:self.reply(connection,2)
    elif command==10:
     offset,want=struct.unpack('<QI',body[:12]);path=body[12:].decode('utf8');self.asked.append(('RANGE',path))
     if not self.allowed:self.reply(connection,13)
     elif path in self.files:self.reply(connection,0,self.files[path][offset:offset+want])
     else:self.reply(connection,2)
    else:self.reply(connection,22)
 def connect(self):
  sock=socket.create_connection(self.server.getsockname(),5);sock.settimeout(5);return sock

class Clock:
 def __init__(self,now):self.now=now
 def __call__(self):return self.now

class SaveTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)/'PS5 saves'
  self.clock=Clock(1_800_000_000.0);self.ticks=Clock(10.0);self.notes=[];self.recycled=[];self.live=False
  self.tree,self.files=layout()
 def recycle(self,folder):self.recycled.append(Path(folder).name);shutil.rmtree(folder);return True
 def saves(self):
  return sb.SaveBackup(lambda:self.root,lambda title:NAMES.get(title,title),self.notes.append,self.recycle,clock=self.clock,streaming=lambda:self.live,ticks=self.ticks)
 def copy_all(self,saves,console,status=IDLE,most=200):
  with console.connect() as sock:
   for _ in range(most):
    if not saves.due(status):return
    saves.step(sock,status)
  self.fail('the copy never ended')
 def copies(self,title):return sorted(path for path in self.root.glob(f'* ({title})/*') if path.is_dir())

 def test_a_closed_games_saves_are_copied_whole_with_what_they_hold(self):
  saves=self.saves();saves.game_closed('PPSA01234');console=FakeConsole(self.tree,self.files);self.copy_all(saves,console)
  [copy]=self.copies('PPSA01234');self.assertEqual(copy.parent.name,'Astro_ Bot (PPSA01234)')
  self.assertEqual((copy/'PS5'/'sdimg_SAVEDATA00').read_bytes(),b'0123456789');self.assertEqual((copy/'PS5'/'inner'/'param').read_bytes(),b'abcde')
  kept=json.loads((copy/sb.MANIFEST).read_text(encoding='utf-8'))
  self.assertEqual(kept['title'],'PPSA01234');self.assertEqual([f['rel'] for f in kept['files']],['PS5/inner/param','PS5/sdimg_SAVEDATA00'])
  # Hidden files, the deepest paths and nothing half written.
  self.assertFalse([p for p in copy.rglob('*') if p.name.startswith('.') or p.name.endswith('.partial') or p.name.startswith('y')])
  self.assertIn('Astro: Bot',saves.status);self.assertEqual(len(self.notes),1);self.assertFalse(saves.busy())
 def test_nothing_the_payload_would_end_the_link_for_is_asked(self):
  saves=self.saves();saves.ask(None);console=FakeConsole(self.tree,self.files);self.copy_all(saves,console)
  for kind,path in console.asked:self.assertLessEqual(len(path.encode())+(12 if kind=='RANGE' else 0),128,path)
  self.assertNotIn(('LIST',PS5+'/PPSA01234/'+'x'*90),console.asked)
 def test_every_game_is_copied_ps5_and_ps4_alike(self):
  saves=self.saves();saves.ask(None);self.copy_all(saves,FakeConsole(self.tree,self.files))
  [old]=self.copies('CUSA00001');self.assertEqual((old/'PS4'/'SAVEDATA00.bin').read_bytes(),b'wxyz')
  self.assertEqual(len(self.copies('PPSA01234')),1);self.assertEqual(self.copies('lowercase'),[])
 def test_saves_that_did_not_change_make_no_new_copy(self):
  saves=self.saves();saves.ask('PPSA01234');self.copy_all(saves,FakeConsole(self.tree,self.files))
  self.clock.now+=60;saves.ask('PPSA01234');self.copy_all(saves,FakeConsole(self.tree,self.files))
  self.assertEqual(len(self.copies('PPSA01234')),1);self.assertIn('did not change',saves.status)
 def test_a_changed_save_makes_a_new_copy_and_the_rest_is_the_same_file_on_disk(self):
  saves=self.saves();saves.ask('PPSA01234');self.copy_all(saves,FakeConsole(self.tree,self.files))
  self.files[PS5+'/PPSA01234/sdimg_SAVEDATA00']=b'9876543210';self.tree[PS5+'/PPSA01234'][0]=('f',200,'sdimg_SAVEDATA00')
  self.clock.now+=60;saves.ask('PPSA01234');console=FakeConsole(self.tree,self.files);self.copy_all(saves,console)
  first,second=self.copies('PPSA01234')
  self.assertEqual((second/'PS5'/'sdimg_SAVEDATA00').read_bytes(),b'9876543210');self.assertEqual((first/'PS5'/'sdimg_SAVEDATA00').read_bytes(),b'0123456789')
  self.assertTrue(os.path.samefile(first/'PS5'/'inner'/'param',second/'PS5'/'inner'/'param'))
  self.assertNotIn(('RANGE',PS5+'/PPSA01234/inner/param'),console.asked)
 def test_only_the_last_copies_are_kept(self):
  saves=self.saves()
  for n in range(sb.KEEP+2):
   self.files[PS5+'/PPSA01234/inner/param']=b'v%02d'%n;self.tree[PS5+'/PPSA01234/inner'][0]=('f',300+n,'param')
   self.clock.now+=60;saves.ask('PPSA01234');self.copy_all(saves,FakeConsole(self.tree,self.files))
  kept=self.copies('PPSA01234');self.assertEqual(len(kept),sb.KEEP);self.assertEqual(len(self.recycled),2)
  self.assertEqual((kept[-1]/'PS5'/'inner'/'param').read_bytes(),b'v%02d'%(sb.KEEP+1))
 def test_a_game_that_opens_halfway_stops_the_copy_and_it_starts_again_after(self):
  saves=self.saves();saves.game_closed('PPSA01234');console=FakeConsole(self.tree,self.files)
  original=sb.RANGE_MOST;sb.RANGE_MOST=3;self.addCleanup(setattr,sb,'RANGE_MOST',original)
  with console.connect() as sock:
   for _ in range(2):saves.step(sock,IDLE)
   self.assertTrue(list(self.root.rglob('*.partial')))
   self.assertFalse(saves.due(PLAYING));self.assertTrue(saves.interrupted)
  self.copy_all(saves,FakeConsole(self.tree,self.files))
  [copy]=self.copies('PPSA01234');self.assertEqual((copy/'PS5'/'sdimg_SAVEDATA00').read_bytes(),b'0123456789')
  self.assertFalse(list(self.root.rglob('*.partial')))
 def test_an_older_payload_is_told_and_not_asked_again(self):
  saves=self.saves();saves.game_closed('PPSA01234');self.copy_all(saves,FakeConsole(self.tree,self.files,allowed=False))
  self.assertIn('cannot read saves',saves.status);self.assertTrue(saves.old_payload);self.assertFalse(self.root.exists() and list(self.root.iterdir()))
  saves.game_closed('PPSA01234');self.assertFalse(saves.busy())
 def test_off_means_a_closed_game_is_left_alone_but_asking_still_works(self):
  saves=self.saves();saves.auto=False;saves.game_closed('PPSA01234');self.assertFalse(saves.busy())
  saves.ask('PPSA01234');self.assertTrue(saves.busy())
 def test_it_waits_for_a_user_and_for_no_game(self):
  saves=self.saves();saves.ask(None)
  self.assertFalse(saves.due(dict(app=0,title='')));self.assertFalse(saves.due(PLAYING));self.assertTrue(saves.due(IDLE))
 def test_while_the_stream_plays_a_part_goes_at_most_once_a_second(self):
  saves=self.saves();saves.game_closed('PPSA01234');self.live=True;console=FakeConsole(self.tree,self.files)
  original=sb.RANGE_MOST;sb.RANGE_MOST=2;self.addCleanup(setattr,sb,"RANGE_MOST",original)
  with console.connect() as sock:
   saves.step(sock,IDLE);self.assertTrue(saves.due(IDLE))
   saves.step(sock,IDLE);self.assertFalse(saves.due(IDLE))
   self.ticks.now+=sb.LIVE_GAP;self.assertTrue(saves.due(IDLE))
   self.live=False;saves.step(sock,IDLE);self.assertTrue(saves.due(IDLE))

if __name__=='__main__':unittest.main()
