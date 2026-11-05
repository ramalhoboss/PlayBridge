import json,os,re,socket,sqlite3,struct,sys,tempfile,threading,time,unittest
from pathlib import Path
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from PIL import Image
import console_control as control

class FakeControlPort:
 """Answers the way the payload's control port does, on a local socket."""
 def __init__(self,files=None,status=None,results=None):
  self.files=files or {};self.status=status or {'cpu_c':50,'soc_c':60,'power_mw':90000,'cpu_mhz':3200,'user':1,'app':-1,'title':'','pad':0};self.results=results or {};self.commands=[];self.server=socket.create_server(('127.0.0.1',0));self.port=self.server.getsockname()[1];self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
 def run(self):
  try:
   client,_=self.server.accept()
   with client:
    while True:
     magic,command,size=control.REQUEST.unpack(control.read_exact(client,12));body=control.read_exact(client,size);self.commands.append((command,body))
     if magic!=b'PBC1':return
     if command==control.STATUS:reply=(0,json.dumps(self.status).encode())
     elif command==control.FILE:
      data=self.files.get(body.decode());reply=(2,b'') if data is None else (0,data)
     else:reply=(self.results.get(command,0),b'')
     client.sendall(control.REPLY.pack(b'PBR1',reply[0],len(reply[1]))+reply[1])
  except (OSError,EOFError):pass
 def close(self):self.server.close()

def database(folder):
 path=Path(folder)/'source.db';db=sqlite3.connect(path)
 db.execute('CREATE TABLE tbl_contentinfo(titleId,titleName,lastAccessTime,installTime,futureColumn)')
 db.executemany('INSERT INTO tbl_contentinfo VALUES(?,?,?,?,0)',(('PPSA00001','Older\nGame','2026-01-01T10:00:00Z','2025-01-01T10:00:00Z'),('PPSA00002','Newest Game','2026-02-01T10:00:00Z',''),('NPXS40000','System app','',''),('bad','Bad',None,None),('CUSA00003','',None,'2020-01-01T00:00:00Z')))
 db.execute('CREATE TABLE tbl_iconinfo_0000000042(titleId,lastPlayedDateOnConsole,playedTimeOnConsole)')
 db.executemany('INSERT INTO tbl_iconinfo_0000000042 VALUES(?,?,?)',(('PPSA00001','2026-03-01T10:00:00Z',7260),('PPSA00002','','0:30:00'),('PPSA09999','2026-04-01T10:00:00Z',1)))
 db.commit();db.close();return path

def wait_for(check,seconds=5):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  if check():return True
  time.sleep(.01)
 return False

def dds_header(width,height,fourcc,size):
 """The start of a DirectDraw Surface file, as Pillow reads it."""
 pixel=struct.pack('<II4sIIIII',32,4,fourcc,0,0,0,0,0)
 return b'DDS '+struct.pack('<IIIIIII',124,0x1007|0x80000,height,width,size,0,1)+b'\0'*44+pixel+struct.pack('<IIIII',0x1000,0,0,0,0)

class LibraryTests(unittest.TestCase):
 def test_games_are_sorted_by_when_this_user_last_played(self):
  with tempfile.TemporaryDirectory() as tmp:games=control.read_games(database(tmp),42)
  self.assertEqual([game['title'] for game in games],['PPSA00001','PPSA00002','CUSA00003'])
  self.assertEqual(games[0]['name'],'OlderGame');self.assertEqual(games[0]['seconds'],7260);self.assertEqual(games[1]['seconds'],1800);self.assertEqual(games[2]['name'],'CUSA00003')
 def test_a_games_art_music_and_size_come_from_the_database_without_their_dates(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'art.db';db=sqlite3.connect(path);db.execute('CREATE TABLE tbl_contentinfo(titleId,titleName,installTime,pic0Info,snd0Info,size)')
   db.executemany('INSERT INTO tbl_contentinfo VALUES(?,?,?,?,?,?)',(('CUSA00001','One','2024-03-12T10:00:00Z','/user/appmeta/CUSA00001/pic0.dds?ts=1793394565','/user/appmeta/CUSA00001/snd0.at9?ts=1',11179851776),('CUSA00002','Two','',None,'','big')));db.commit();db.close()
   one,two=sorted(control.read_games(path),key=lambda game:game['title'])
  self.assertEqual((one['art'],one['music'],one['size']),('/user/appmeta/CUSA00001/pic0.dds','/user/appmeta/CUSA00001/snd0.at9',11179851776));self.assertGreater(one['installed'],1.7e9)
  self.assertEqual((two['art'],two['music'],two['size'],two['installed']),('','',0,0.0))
 def test_only_a_plain_path_counts_as_a_console_file(self):
  self.assertEqual(control.console_file('/a/b.dds?ts=1'),'/a/b.dds');self.assertEqual(control.console_file('/a/b.dds'),'/a/b.dds')
  for value in (None,'',7,'relative/b.dds','http://x/y.png','/caf\u00e9/pic0.dds'):self.assertEqual(control.console_file(value),'')
 def test_a_lone_user_table_is_used_when_the_user_is_unknown(self):
  with tempfile.TemporaryDirectory() as tmp:self.assertEqual(control.read_games(database(tmp),None)[0]['seconds'],7260)
 def test_a_database_without_the_table_gives_no_games(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'empty.db';sqlite3.connect(path).close();self.assertEqual(control.read_games(path),[])
 def test_names_keep_what_the_card_can_draw(self):
  self.assertEqual(control.clean_name('\u2605 \uefddSHOP APPKG \u2605\uefdc'),'SHOP APPKG');self.assertEqual(control.clean_name('\u2605Internet Browser '),'Internet Browser')
  self.assertEqual(control.clean_name('Uncharted\u2122: Drake\'s Fortune'),'Uncharted\u2122: Drake\'s Fortune');self.assertEqual(control.clean_name('METAL GEAR SOLID \u0394'),'METAL GEAR SOLID \u0394');self.assertEqual(control.clean_name(None),'')
 def test_tools_are_left_out_and_games_without_a_type_are_kept(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'types.db';db=sqlite3.connect(path);db.execute('CREATE TABLE tbl_contentinfo(titleId,titleName,appType)')
   db.executemany('INSERT INTO tbl_contentinfo VALUES(?,?,?)',(('PPSA00001','Game',1),('PPSA00002','Port',5),('TOOL00001','Tool',0),('PPSA00003','Unknown',None)));db.commit();db.close()
   self.assertEqual({game['title'] for game in control.read_games(path)},{'PPSA00001','PPSA00002','PPSA00003'})
 def test_dates_and_play_time_in_either_form(self):
  self.assertEqual(control.when(1700000000),1700000000.0);self.assertEqual(control.when(1700000000000),1700000000.0);self.assertGreater(control.when('2026-01-01T10:00:00Z'),1.7e9);self.assertEqual(control.when('1700000000'),1700000000.0)
  for empty in ('','never',None):self.assertEqual(control.when(empty),0.0)
  self.assertEqual(control.play_seconds('1:01:01'),3661);self.assertEqual(control.play_seconds('61'),61);self.assertIsNone(control.play_seconds('soon'));self.assertIsNone(control.play_seconds(None))
 def test_the_card_line(self):
  self.assertEqual(control.game_detail({'title':'PPSA00001','played':0,'seconds':None}),'PPSA00001')
  self.assertIn('2 h',control.game_detail({'title':'PPSA00001','played':1.7e9,'seconds':7260}));self.assertIn('5 min',control.game_detail({'title':'PPSA00001','played':0,'seconds':300}))
 def test_a_broken_cache_is_ignored(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'games.json';path.write_text('{',encoding='utf8');self.assertEqual(control.load_games(path),[])
   path.write_text(json.dumps([{'title':'PPSA00001','name':'Good'},{'title':'../x','name':'Bad'},7]),encoding='utf8');self.assertEqual([game['name'] for game in control.load_games(path)],['Good'])
 def test_icons_stay_large_enough_for_a_cover_and_only_real_images_are_kept(self):
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'in';Image.new('RGB',(1024,1024),(10,20,30)).save(source,'PNG');target=Path(tmp)/'PPSA00001.png';control.save_icon(source,target)
   with Image.open(target) as image:self.assertEqual(image.size,(512,512))
   source.write_bytes(b'not an image')
   with self.assertRaises(Exception):control.save_icon(source,Path(tmp)/'other.png')
   self.assertFalse((Path(tmp)/'other.png').exists())
 def test_art_is_kept_small_enough_to_open_quickly_whatever_it_came_as(self):
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'in';target=Path(tmp)/'PPSA00001.jpg'
   Image.new('RGBA',(3840,2160),(200,100,50,0)).save(source,'PNG');control.save_art(source,target)
   with Image.open(target) as image:
    self.assertEqual(image.size,control.ART_SIZE);self.assertEqual(image.format,'JPEG');self.assertAlmostEqual(image.getpixel((9,9))[0],200,delta=6)
   source.write_bytes(b'not an image');other=Path(tmp)/'other.jpg'
   with self.assertRaises(Exception):control.save_art(source,other)
   self.assertFalse(other.exists())
 def test_block_compressed_art_opens(self):
  # Two BC1 blocks of a solid colour, the plainest form a DDS file takes.
  block=struct.pack('<HHI',0xF800,0xF800,0)
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'pic0.dds';source.write_bytes(dds_header(8,4,b'DXT1',16)+block*2);target=Path(tmp)/'out.jpg';control.save_art(source,target)
   with Image.open(target) as image:self.assertEqual(image.size,(8,4));self.assertGreater(image.getpixel((1,1))[0],200)

class StatusTests(unittest.TestCase):
 def test_only_a_real_game_counts_as_running(self):
  self.assertEqual(control.running_title({'app':5,'title':'PPSA00001'}),'PPSA00001')
  for status in ({},{'app':-1,'title':'PPSA00001'},{'app':5,'title':'NPXS20001'},{'app':5,'title':''},{'app':'5','title':'PPSA00001'}):self.assertEqual(control.running_title(status),'')
 def test_the_menu_covers_a_game_only_while_the_console_says_so(self):
  self.assertTrue(control.menu_in_front({'app':5,'title':'PPSA00001','front':'NPXS40087'}))
  for status in ({'app':5,'title':'PPSA00001','front':'PPSA00001'},{'app':5,'title':'PPSA00001','front':''},{'app':5,'title':'PPSA00001'},{'app':-1,'title':'','front':'NPXS40087'},{'app':5,'title':'PPSA00001','front':7}):self.assertFalse(control.menu_in_front(status))
 def test_the_status_line_leaves_out_what_the_console_could_not_read(self):
  self.assertEqual(control.console_line({'cpu_c':52,'soc_c':-1,'power_mw':92000,'cpu_mhz':3200}),'CPU 52 °C');self.assertEqual(control.console_line({}),'')

class FlowTests(unittest.TestCase):
 def test_a_launch_ends_when_the_console_runs_that_game(self):
  flow=control.GameFlow();flow.launch('PPSA00001',0)
  self.assertIsNone(flow.update('',1));self.assertEqual(flow.update('PPSA00001',2),'started');self.assertIsNone(flow.update('PPSA00001',3));self.assertEqual(flow.update('',4),'closed');self.assertIsNone(flow.update('',5))
 def test_a_launch_that_never_arrives_fails_once(self):
  flow=control.GameFlow();flow.launch('PPSA00001',0)
  self.assertEqual(flow.update('',control.GameFlow.PATIENCE+1),'failed');self.assertIsNone(flow.update('',control.GameFlow.PATIENCE+2))
 def test_a_switch_waits_for_the_close_before_it_launches(self):
  flow=control.GameFlow();flow.update('PPSA00001',0);flow.replace('PPSA00002',0)
  self.assertIsNone(flow.update('PPSA00001',1));self.assertEqual(flow.update('',2),'launch');self.assertEqual(flow.waiting,'PPSA00002');self.assertEqual(flow.update('PPSA00002',3),'started')
 def test_a_game_opened_on_the_console_is_followed(self):
  flow=control.GameFlow();self.assertIsNone(flow.update('PPSA00001',0));self.assertEqual(flow.update('',1),'closed')

class LinkTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.folder=Path(self.tmp.name)/'library';self.folder.mkdir();self.source=database(self.tmp.name);self.notes=[]
 def link(self,port):
  link=control.ConsoleLink(self.folder,self.notes.append);self.addCleanup(link.end);self.addCleanup(port.close)
  original=control.CONTROL_PORT;control.CONTROL_PORT=port.port;self.addCleanup(setattr,control,'CONTROL_PORT',original);link.begin('127.0.0.1');return link
 def icon(self):
  path=Path(self.tmp.name)/'icon.png';Image.new('RGB',(512,512),(1,2,3)).save(path);return path.read_bytes()
 def test_a_session_reads_status_games_and_icons_and_keeps_them_for_next_time(self):
  files={control.DATABASE:self.source.read_bytes(),'/user/appmeta/external/PPSA00001/icon0.png':self.icon()}
  link=self.link(FakeControlPort(files,dict(user=42,app=-1,title='',cpu_c=50)))
  self.assertTrue(wait_for(lambda:link.online and link.games and link.icon('PPSA00001')),self.notes)
  self.assertEqual(link.status['cpu_c'],50);self.assertEqual(link.games[0]['title'],'PPSA00001');self.assertIsNone(link.icon('PPSA00002'))
  self.assertEqual(link.game_name('PPSA00001'),'OlderGame');self.assertEqual(control.ConsoleLink(self.folder).games,link.games)
 def test_a_session_keeps_the_payload_logs_on_the_pc(self):
  files={control.DATABASE:self.source.read_bytes(),control.CAPTURE_LOG:b'Resource channel=2 mode=1\n',control.PREVIOUS_CONTROL_LOG:b'close app=00002018\n'}
  port=FakeControlPort(files);logs=Path(self.tmp.name)/'logs';logs.mkdir()
  link=control.ConsoleLink(self.folder);link.log_folder=logs;self.addCleanup(link.end);self.addCleanup(port.close)
  original=control.CONTROL_PORT;control.CONTROL_PORT=port.port;self.addCleanup(setattr,control,'CONTROL_PORT',original);link.begin('127.0.0.1')
  capture=logs/'session-1-capture.txt';before=logs/'session-1-control-before.txt'
  self.assertTrue(wait_for(lambda:capture.is_file() and before.is_file()))
  self.assertEqual(capture.read_bytes(),b'Resource channel=2 mode=1\n');self.assertEqual(before.read_bytes(),b'close app=00002018\n')
  # It looks again while the stream plays, and once more as it ends.
  port.files[control.CAPTURE_LOG]=b'Resource channel=2 mode=1\nVideo error=81950003\n'
  self.assertTrue(wait_for(lambda:b'Video error' in capture.read_bytes()))
  link.last_look(2);self.assertIn(b'Video error',(logs/'session-1-capture-end.txt').read_bytes())
 def test_without_a_log_folder_no_log_is_asked_for(self):
  port=FakeControlPort({control.DATABASE:self.source.read_bytes()});link=self.link(port)
  self.assertTrue(wait_for(lambda:link.online and link.games));link.last_look();time.sleep(.6)
  asked=[body.decode() for command,body in port.commands if command==control.FILE]
  self.assertNotIn(control.CAPTURE_LOG,asked);self.assertNotIn(control.PREVIOUS_CONTROL_LOG,asked)
 def extras(self,port,games,**values):
  link=control.ConsoleLink(self.folder);link.games=games;link.extras=link.extras_missing(games)
  for name,value in values.items():setattr(link,name,value)
  return link
 def art_game(self,title,art=True,music=True):
  return {'title':title,'name':title,'art':f'/user/appmeta/{title}/pic0.dds' if art else '','music':f'/user/appmeta/{title}/snd0.at9' if music else ''}
 def test_art_and_music_arrive_while_browsing_and_are_kept(self):
  games=[self.art_game('PPSA00001'),self.art_game('PPSA00002',music=False)];files={control.DATABASE:self.source.read_bytes(),games[0]['art']:self.icon(),games[0]['music']:b'RIFFmusic',games[1]['art']:self.icon()}
  link=self.link(FakeControlPort(files,dict(user=42,app=-1,title='',cpu_c=50)));self.assertTrue(wait_for(lambda:link.online and link.games),self.notes);link.extras=link.extras_missing(games);link.browsing=True
  self.assertTrue(wait_for(lambda:link.art('PPSA00001') and link.art('PPSA00002') and link.music_file('PPSA00001')),self.notes);self.assertIsNone(link.music_file('PPSA00002'));self.assertEqual(link.extras_missing(games),[])
  self.assertEqual(link.music_file('PPSA00001').read_bytes(),b'RIFFmusic')
 def test_the_game_in_focus_comes_first(self):
  link=self.extras(None,[self.art_game('PPSA00001'),self.art_game('PPSA00002')],focus='PPSA00002');self.assertEqual(link.next_extra()[:2],('art','PPSA00002'));self.assertEqual(link.next_extra()[:2],('music','PPSA00002'));self.assertEqual(link.next_extra()[:2],('art','PPSA00001'))
 def test_nothing_is_read_unless_someone_is_looking_with_no_game_open(self):
  link=self.extras(None,[self.art_game('PPSA00001')]);self.assertFalse(link.extra_due());link.browsing=True;self.assertTrue(link.extra_due())
  link.status=dict(title='CUSA00001',app=5);self.assertFalse(link.extra_due());link.status={};link.extras=[];self.assertFalse(link.extra_due())
 def test_a_file_that_cannot_be_used_is_not_read_again_and_a_refusal_may_be(self):
  games=[self.art_game('PPSA00001',music=False),self.art_game('PPSA00002',music=False)];files={control.DATABASE:self.source.read_bytes(),games[0]['art']:b'not an image'}
  link=self.link(FakeControlPort(files,dict(user=42,app=-1,title='')));self.assertTrue(wait_for(lambda:link.online and link.games),self.notes);link.extras=link.extras_missing(games);link.browsing=True
  self.assertTrue(wait_for(lambda:not link.extras and (self.folder/'art'/'PPSA00001.none').exists()),self.notes);self.assertIsNone(link.art('PPSA00001'))
  self.assertEqual([job[1] for job in link.extras_missing(games)],['PPSA00002'])
 def test_the_console_refusing_the_list_is_reported(self):
  link=self.link(FakeControlPort());self.assertTrue(wait_for(lambda:self.notes));self.assertIn('game list',self.notes[0]);self.assertTrue(link.online)
 def test_a_broken_database_is_reported_and_the_old_list_stays(self):
  (self.folder/'games.json').write_text(json.dumps([{'title':'PPSA00001','name':'Saved'}]),encoding='utf8')
  link=self.link(FakeControlPort({control.DATABASE:b'this is not a database, it only has to be long enough to read'}))
  self.assertTrue(wait_for(lambda:self.notes));self.assertEqual(link.games[0]['name'],'Saved')
 def test_commands_reach_the_console_and_report_its_answer(self):
  port=FakeControlPort(results={control.LAUNCH:0x80940001-(1<<32)});link=self.link(port);self.assertTrue(wait_for(lambda:link.online));answers=[]
  self.assertTrue(link.launch('PPSA00001',answers.append));self.assertTrue(wait_for(lambda:answers));self.assertEqual(answers[0]&0xffffffff,0x80940001);self.assertIn((control.LAUNCH,b'PPSA00001'),port.commands)
 def test_a_malformed_title_never_leaves_the_pc(self):
  port=FakeControlPort();link=self.link(port);self.assertTrue(wait_for(lambda:link.online))
  self.assertFalse(link.launch('../evil'));self.assertFalse(link.launch('NPXS20001'))
 def test_without_a_connection_nothing_is_kept_to_fire_later(self):
  link=control.ConsoleLink(self.folder);self.assertFalse(link.send(control.REST));self.assertFalse(link.launch('PPSA00001'));self.assertTrue(link.jobs.empty())
 def test_the_session_ending_clears_the_status(self):
  link=self.link(FakeControlPort());self.assertTrue(wait_for(lambda:link.online));link.end();self.assertFalse(link.online);self.assertEqual(link.status,{})
 def test_an_invalid_reply_drops_the_connection_without_raising(self):
  server=socket.create_server(('127.0.0.1',0));self.addCleanup(server.close)
  def bad():
   client,_=server.accept()
   with client:client.recv(64);client.sendall(b'XXXX'+bytes(8))
  threading.Thread(target=bad,daemon=True).start();original=control.CONTROL_PORT;control.CONTROL_PORT=server.getsockname()[1];self.addCleanup(setattr,control,'CONTROL_PORT',original)
  link=control.ConsoleLink(self.folder);self.addCleanup(link.end);link.begin('127.0.0.1');time.sleep(.3);self.assertFalse(link.online)
 def test_a_game_restarts_by_closing_and_then_launching_the_same_title(self):
  flow=control.GameFlow();self.assertIsNone(flow.update('PPSA00001',0));flow.replace('PPSA00001',1)
  self.assertIsNone(flow.update('PPSA00001',2));self.assertEqual(flow.update('',3),'launch');self.assertEqual(flow.waiting,'PPSA00001');self.assertIsNone(flow.update('',4));self.assertEqual(flow.update('PPSA00001',5),'started')
 def test_the_commands_match_the_payload(self):
  rules=(Path(__file__).resolve().parents[1]/'payload'/'control-rules.h').read_text(encoding='utf8');found={name:int(value) for name,value in re.findall(r'CONTROL_([A-Z_]+)=(\d+)',rules)}
  self.assertEqual(found,dict(STATUS=control.STATUS,FILE=control.FILE,LAUNCH=control.LAUNCH,CLOSE=control.CLOSE,REST=control.REST,POWER_OFF=control.POWER_OFF,REBOOT=control.REBOOT,LIST=control.LIST))
if __name__=='__main__':unittest.main()
