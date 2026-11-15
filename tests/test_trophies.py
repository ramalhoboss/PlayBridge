"""Trophies from the console's own files: the parsers on made-up files laid out as the console writes them, and a session that reads them
only while someone browses with no game open, through the fake control port."""
import hashlib,json,os,sqlite3,struct,sys,tempfile,unittest
from pathlib import Path
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'));sys.path.insert(0,str(Path(__file__).resolve().parent))
import console_control as control
import trophies
from test_console_control import FakeControlPort,finish_links,wait_for

SET='NPWR12345_00';USER=0x1a2b3c4d;FOLDER='1a2b3c4d'
def when(seconds):return (seconds+trophies.EPOCH)*1000000

def npbind(name=SET):
 records=struct.pack('>HH',1,4)+b'abcd'+struct.pack('>HH',0x10,16)+name.encode()+b'\0'*(16-len(name))
 return struct.pack('>I',trophies.NPBIND_MAGIC)+b'\0'*(0x80-4)+records
def ucp(files):
 """A TROPHY.UCP holding these files, in order."""
 count=len(files);head=bytearray(0x60);struct.pack_into('>I',head,0,trophies.UCP_MAGIC);struct.pack_into('>II',head,0x10,count,64)
 table=bytearray();data=bytearray();start=0x60+count*64
 for name,body in files.items():
  table+=name.encode().ljust(32,b'\0')+struct.pack('>QQ',start+len(data),len(body))+b'\0'*16;data+=body
 return bytes(head+table+data)
def record(states,extra_page=False):
 """A TRPTITLE.DAT: states is [(id, flags, earned seconds or 0)]."""
 stream=bytearray(b'T2TD'+struct.pack('>II',0x10000,2)).ljust(48,b'\0')
 stream+=struct.pack('>IIIIQ',0x2,0x40,1,1,0).ljust(32,b'\0')
 offset=48+2*32+64;stream+=struct.pack('>IIIIQ',0x800,0x30,1,len(states),offset).ljust(32,b'\0');stream+=b'\0'*64
 for number,flags,seconds in states:
  row=bytearray(64);struct.pack_into('>I',row,0,0x800);struct.pack_into('>II',row,0x10,number,flags)
  if seconds:struct.pack_into('>Q',row,0x20,when(seconds));struct.pack_into('>Q',row,0x30,when(seconds))
  stream+=row
 pages=-(-len(stream)//1024)+(1 if extra_page else 0);stream=stream.ljust(pages*1024,b'\0')
 head=bytearray(64);head[:4]=b'T2PD';struct.pack_into('>IQ',head,4,0x10000,1056);struct.pack_into('>Q',head,32,pages)
 out=bytearray(head)
 for page in range(pages):
  part=bytes(stream[page*1024:(page+1)*1024]);out+=part+(b'\0'*32 if extra_page and page==pages-1 else hashlib.sha256(part).digest())
 return bytes(out)
CONF=json.dumps(dict(defaultLanguage='en-US',trophies=[dict(id='0',grade='P',hidden=False),dict(id='1',grade='G',hidden=False),dict(id='2',grade='S',hidden=True),dict(id='3',grade='B',hidden=False)])).encode()
META=json.dumps(dict(metadata=dict(titleMetadata=dict(name='Made-up Game Trophies'),trophyMetadata=[dict(id=str(n),name=f'Trophy {n}',detail=f'Do thing {n}') for n in range(4)]))).encode()
SET_FILE=ucp({'tropconf.json':CONF,'tropmeta_fr-FR.json':b'{}','tropmeta_en-US.json':META,'trop0000.png':b'\x89PNG'})

def png(colour=(200,40,40,255)):
 import io
 from PIL import Image
 out=io.BytesIO();Image.new('RGBA',(16,16),colour).save(out,'PNG');return out.getvalue()
ICON=png()

class FormatTests(unittest.TestCase):
 def test_each_trophy_has_its_own_picture_in_the_set(self):
  files={'tropconf.json':(96,10),'TROP0003.PNG':(200,5000),'trop0004.png':(300,2<<20)}
  self.assertEqual(trophies.icon_place(files,3),(200,5000));self.assertIsNone(trophies.icon_place(files,4));self.assertIsNone(trophies.icon_place(files,9))
 def test_npbind_names_the_set(self):
  self.assertEqual(trophies.set_of(npbind()),SET)
  self.assertEqual(trophies.set_of(npbind('NPWR1234_000')),'');self.assertEqual(trophies.set_of(b'\0'*200),'');self.assertEqual(trophies.set_of(npbind()[:0x84]),'')
 def test_a_sets_table_and_its_files(self):
  head,table=SET_FILE[:0x60],SET_FILE[0x60:0x60+4*64];files=trophies.ucp_table(head,table)
  offset,size=files['tropconf.json'];self.assertEqual(SET_FILE[offset:offset+size],CONF)
  self.assertEqual(trophies.meta_name(files,'en-US'),'tropmeta_en-US.json');self.assertEqual(trophies.meta_name(files,'de-DE'),'tropmeta_en-US.json')
  with self.assertRaises(ValueError):trophies.ucp_count(b'\0'*0x60)
  with self.assertRaises(ValueError):trophies.ucp_table(head,table[:100])
  bad=bytearray(table);bad[0:4]=b'../x'
  with self.assertRaises(ValueError):trophies.ucp_table(head,bytes(bad))
 def test_the_list_takes_names_from_the_meta_file_and_keeps_its_order(self):
  made=trophies.trophy_set(CONF,META);self.assertEqual(made['name'],'Made-up Game Trophies')
  self.assertEqual([(row['id'],row['grade'],row['hidden'],row['name']) for row in made['trophies']],[(0,'platinum',False,'Trophy 0'),(1,'gold',False,'Trophy 1'),(2,'silver',True,'Trophy 2'),(3,'bronze',False,'Trophy 3')])
  self.assertEqual(trophies.trophy_set(CONF,b'not json')['trophies'][1]['name'],'')
  with self.assertRaises(ValueError):trophies.trophy_set(b'{}')
 def test_the_record_says_which_were_earned_and_when(self):
  have=trophies.earned(record([(0,0x10,0),(1,0x11,1700000000),(2,0x11,0),(3,0x11,1750000000)]))
  self.assertEqual(have,{1:1700000000,3:1750000000})
  # A page the console left empty has no digest, and counts as whole.
  self.assertEqual(trophies.earned(record([(1,0x11,1700000000)],extra_page=True)),{1:1700000000})
 def test_a_damaged_record_is_refused(self):
  data=bytearray(record([(1,0x11,1700000000)]));data[64+200]^=1
  with self.assertRaises(ValueError):trophies.earned(bytes(data))
  with self.assertRaises(ValueError):trophies.earned(record([(1,0x11,1)])[:-1])
 def test_the_tally_counts_as_the_console_does(self):
  rows=trophies.trophy_set(CONF,META)['trophies']
  self.assertEqual(trophies.tally(rows,{1:5,3:6}),dict(earned=2,total=4,progress=(90+15)*100//(90+30+15),platinum=False,grades=dict(platinum=[0,1],gold=[1,1],silver=[0,1],bronze=[1,1])))
  self.assertIsNone(trophies.tally(rows[1:],{})['platinum']);self.assertTrue(trophies.tally(rows,{0:1})['platinum'])

def library(folder):
 path=Path(folder)/'source.db';db=sqlite3.connect(path)
 db.execute('CREATE TABLE tbl_contentinfo(titleId,titleName,lastAccessTime,installTime,icon0Info)')
 db.executemany('INSERT INTO tbl_contentinfo VALUES(?,?,?,?,?)',(('PPSA00001','With trophies','2026-03-01T10:00:00Z','','/user/appmeta/PPSA00001/icon0.png?ts=1'),('PPSA00002','Without','2026-02-01T10:00:00Z','','')))
 db.commit();db.close();return path.read_bytes()

class SessionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.folder=Path(self.tmp.name)/'library';self.folder.mkdir();self.notes=[]
 def files(self,record_data):
  files={control.DATABASE:library(self.tmp.name),'/user/appmeta/PPSA00001/trophy2/npbind.dat':npbind(),control.TROPHY_SET_FILE.format(SET):SET_FILE}
  if record_data is not None:files[control.TROPHY_RECORD.format(FOLDER,SET)]=record_data
  return files
 def link(self,port):
  link=control.ConsoleLink(self.folder,self.notes.append);self.addCleanup(finish_links);self.addCleanup(link.end);self.addCleanup(port.close)
  original=control.CONTROL_PORT;control.CONTROL_PORT=port.port;self.addCleanup(setattr,control,'CONTROL_PORT',original);link.begin('127.0.0.1');return link
 def test_trophies_are_read_while_browsing_and_kept_for_next_time(self):
  port=FakeControlPort(self.files(record([(1,0x11,1700000000)])),dict(user=USER,app=-1,title=''))
  link=self.link(port);self.assertTrue(wait_for(lambda:link.online and link.games))
  self.assertIsNone(link.trophy_set('PPSA00001'))
  link.browsing=True;self.assertTrue(wait_for(lambda:link.trophy_set('PPSA00001') is not None and link.trophy_set('PPSA00001')['known'] and not link.trophy_jobs))
  found=link.trophy_set('PPSA00001');self.assertEqual((found['name'],found['tally']['earned'],found['tally']['total'],found['last']),('Made-up Game Trophies',1,4,1700000000))
  self.assertEqual([row['earned'] for row in found['trophies']],[0,1700000000,0,0]);self.assertIsNone(link.trophy_set('PPSA00002'))
  self.assertEqual(link.trophy_totals(['PPSA00001','PPSA00002']),dict(earned=1,platinum=0,games=1))
  link.end();finish_links()
  kept=control.ConsoleLink(self.folder);self.assertEqual(kept.trophy_set('PPSA00001')['tally']['earned'],1)
  # Only part of the set file went over the wire: its table and the two files the list needs, never the pictures.
  ranges=[struct.unpack_from('<QI',body) for command,body in port.commands if command==control.RANGE and body[12:].decode().endswith('TROPHY.UCP')]
  self.assertEqual(sum(length for _,length in ranges),0x60+4*64+len(CONF)+len(META))
 def test_a_game_never_opened_has_no_set_file_yet_and_only_its_name_is_kept(self):
  files=self.files(None);files.pop(control.TROPHY_SET_FILE.format(SET));port=FakeControlPort(files,dict(user=USER,app=-1,title=''));link=self.link(port);link.browsing=True
  self.assertTrue(wait_for(lambda:link.online and link.games and link.can_range and not link.trophy_jobs))
  self.assertTrue(wait_for(lambda:link.trophy_book['games'].get('PPSA00001')==SET));self.assertIsNone(link.trophy_set('PPSA00001'))
 def watching(self):
  original=control.TROPHY_WATCH_EVERY;control.TROPHY_WATCH_EVERY=.05;self.addCleanup(setattr,control,'TROPHY_WATCH_EVERY',original)
 def record_reads(self,port):
  return sum(command==control.FILE and body.decode()==control.TROPHY_RECORD.format(FOLDER,SET) for command,body in port.commands)
 def test_while_a_game_is_open_only_its_record_is_read(self):
  self.watching();heard=[]
  port=FakeControlPort(self.files(record([])),dict(user=USER,app=5,title='PPSA00001'));link=self.link(port);link.on_trophy=lambda *a:heard.append(a)
  self.assertTrue(wait_for(lambda:link.online and link.games));link.browsing=True
  self.assertTrue(wait_for(lambda:self.record_reads(port)>=3))
  # The set's own file, its list and pictures, stays for when nobody plays.
  self.assertFalse(any(command==control.RANGE and body[12:].decode().endswith('TROPHY.UCP') for command,body in port.commands))
  self.assertIsNone(link.trophy_set('PPSA00001'));self.assertEqual(heard,[])
 def test_a_trophy_earned_while_the_game_runs_is_heard_with_its_name(self):
  self.watching();heard=[]
  files=self.files(record([(1,0x11,1700000000)]));port=FakeControlPort(files,dict(user=USER,app=5,title='PPSA00001'))
  files[control.TROPHY_SET_FILE.format(SET)]=ucp({'tropconf.json':CONF,'tropmeta_en-US.json':META,'trop0000.png':b'\x89PNG','trop0003.png':ICON})
  link=self.link(port);link.on_trophy=lambda *a:heard.append(a)
  # The first read only notes what the player had: the trophy earned before is not news.
  self.assertTrue(wait_for(lambda:link.watch_have=={1:1700000000}));self.assertEqual(heard,[])
  files[control.TROPHY_RECORD.format(FOLDER,SET)]=record([(1,0x11,1700000000),(3,0x11,1700000500)])
  self.assertTrue(wait_for(lambda:heard))
  title,earned,since=heard[0]
  # With its own picture from the set, for the overlay.
  self.assertEqual((title,earned),('PPSA00001',[dict(id=3,name='Trophy 3',grade='bronze',at=1700000500,icon=ICON)]));self.assertGreater(since,0)
  self.assertEqual(link.trophy_set('PPSA00001')['tally']['earned'],2)
  self.assertFalse(wait_for(lambda:len(heard)>1,.4))
 def test_a_closed_game_has_its_record_read_again_first(self):
  link=control.ConsoleLink(self.folder);link.trophy_jobs=['PPSA00002','PPSA00001']
  link.game_closed('PPSA00001');link.game_closed('');self.assertEqual(link.trophy_jobs,['PPSA00001','PPSA00002'])
 def test_a_closed_game_has_its_saves_copied(self):
  link=control.ConsoleLink(self.folder);closed=[]
  class Saves:
   def game_closed(self,title):closed.append(title)
  link.saves=Saves();link.game_closed('PPSA00001');link.game_closed('PPSA00001');self.assertEqual(closed,[])
  link.game_closed('');self.assertEqual(closed,['PPSA00001'])
 def test_an_older_payload_leaves_trophies_alone(self):
  # An older payload answers a command it does not know with an error, as the fake does once RANGE is in its results.
  port=FakeControlPort(self.files(None),dict(user=USER,app=-1,title=''),results={control.RANGE:22});link=self.link(port);link.browsing=True
  self.assertTrue(wait_for(lambda:link.online and link.games));self.assertTrue(wait_for(lambda:link.can_range is False))
  self.assertFalse(link.trophy_due());self.assertEqual(sum(command==control.RANGE for command,_ in port.commands),1)
  self.assertFalse(any(body.endswith(b'npbind.dat') for command,body in port.commands))
 def test_hidden_games_are_kept_on_the_pc(self):
  link=control.ConsoleLink(self.folder);revision=link.revision;link.set_hidden('PPSA00001',True);link.set_hidden('bad',True)
  self.assertEqual(link.hidden,{'PPSA00001'});self.assertGreater(link.revision,revision)
  self.assertEqual(control.ConsoleLink(self.folder).hidden,{'PPSA00001'})
  link.set_hidden('PPSA00001',False);self.assertEqual(control.ConsoleLink(self.folder).hidden,set())
 def test_a_damaged_trophy_file_on_the_pc_only_means_reading_again(self):
  (self.folder/'trophies.json').write_text('{"games":{"PPSA00001":"../x"},"sets":{"NPWR12345_00":{"trophies":[{"id":"a"}]}},"earned":{"zz":{}}}',encoding='utf8')
  link=control.ConsoleLink(self.folder);self.assertEqual(link.trophy_book['games'],{});self.assertEqual(link.trophy_book['sets'][SET]['trophies'],[]);self.assertEqual(link.trophy_book['earned'],{})

if __name__=='__main__':unittest.main()
