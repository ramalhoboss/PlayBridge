import os,socket,struct,sys,tempfile,threading,unittest
from pathlib import Path
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import console_captures as cc
from desktop_features import capture_items

# The layout a real PS5 showed: captures under photo and video, by the app that saved them and the game in it,
# with the console's own previews (x.mp4.jpeg) beside them and in a separate thumbnails tree.
A='/user/av_contents'
TREE={A:[('d',0,1,'photo'),('d',0,1,'video'),('d',0,1,'thumbnails'),('d',0,1,'content_tmp')],
 A+'/photo':[('d',0,1,'NPXS40087')],A+'/photo/NPXS40087':[('d',0,1,'NPXS40087')],A+'/photo/NPXS40087/NPXS40087':[('d',0,1,'34b')],
 A+'/photo/NPXS40087/NPXS40087/34b':[('f',5,100,'shot one.png'),('f',4,100,'shot one.png.jpeg'),('f',3,200,'notes.db'),('f',0,400,'empty.png'),('f',6,500,'.hidden.png')],
 A+'/video':[('d',0,1,'NPXS40087')],A+'/video/NPXS40087':[('d',0,1,'PPSA01325'),('d',0,1,'CUSA03280')],
 A+'/video/NPXS40087/PPSA01325':[('d',0,1,'04b')],A+'/video/NPXS40087/PPSA01325/04b':[('f',7,300,'clip.webm')],
 A+'/video/NPXS40087/CUSA03280':[('d',0,1,'04b')],A+'/video/NPXS40087/CUSA03280/04b':[('f',12,250,'boss.mp4'),('f',9,250,'boss.mp4.jpeg')],
 A+'/thumbnails':[('d',0,1,'video')],A+'/thumbnails/video':[('f',9,600,'boss.mp4.jpeg')],A+'/content_tmp':[('f',9,700,'part.mp4')]}
FILES={A+'/photo/NPXS40087/NPXS40087/34b/shot one.png':b'\x89PNG\r',A+'/video/NPXS40087/PPSA01325/04b/clip.webm':b'\x1aE\xdf\xa3WEB',A+'/video/NPXS40087/CUSA03280/04b/boss.mp4':b'\0\0\0\x18ftypisom'}
NAMES={'PPSA01325':'Astro Bot','CUSA03280':'Demon Souls'}
def game_name(title):return NAMES.get(title,title)

class FakeConsole:
 """Answers LIST and FILE as the payload does, from the tables above, on this PC."""
 def __init__(self,knows_list=True):
  self.server=socket.create_server(('127.0.0.1',0));self.knows=knows_list;self.asked=[]
  threading.Thread(target=self.serve,daemon=True).start()
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
    path=body.decode('utf8');self.asked.append((command,path))
    if command==9 and self.knows:
     if path in TREE:answer=''.join(f'{k}\t{s}\t{t}\t{n}\n' for k,s,t,n in TREE[path]).encode();connection.sendall(struct.pack('<4siI',b'PBR1',0,len(answer))+answer)
     else:connection.sendall(struct.pack('<4siI',b'PBR1',2,0))
    elif command==2 and path in FILES:connection.sendall(struct.pack('<4siI',b'PBR1',0,len(FILES[path]))+FILES[path])
    else:connection.sendall(struct.pack('<4siI',b'PBR1',22 if command==9 else 13,0))
 def connect(self):
  sock=socket.create_connection(self.server.getsockname(),5);sock.settimeout(5);return sock

class CaptureTests(unittest.TestCase):
 def test_photos_and_clips_are_found_newest_first_and_nothing_else(self):
  console=FakeConsole()
  with console.connect() as sock:found,old=cc.find_captures(sock,name_of=game_name)
  self.assertFalse(old)
  self.assertEqual([(c['name'],c['title'],c['folder'],c['kind']) for c in found],[('clip.webm','PPSA01325','Astro Bot','Videos'),('boss.mp4','CUSA03280','Demon Souls','Videos'),('shot one.png','NPXS40087','System','Photos')])
 def test_previews_and_unfinished_files_are_never_listed(self):
  console=FakeConsole()
  with console.connect() as sock:cc.find_captures(sock,name_of=game_name)
  asked=[path for _,path in console.asked]
  self.assertFalse([path for path in asked if '/thumbnails' in path or '/content_tmp' in path],asked)
  self.assertNotIn(A,asked,'the root itself holds nothing to copy')
 def test_without_the_library_the_title_id_names_the_game(self):
  console=FakeConsole()
  with console.connect() as sock:found,_=cc.find_captures(sock)
  self.assertEqual([c['folder'] for c in found],['PPSA01325','CUSA03280','System'])
 def test_an_older_payload_is_told_apart_from_an_empty_console(self):
  console=FakeConsole(knows_list=False)
  with console.connect() as sock:found,old=cc.find_captures(sock)
  self.assertEqual(found,[]);self.assertTrue(old)
 def test_copies_land_where_the_media_page_shows_them_once_each(self):
  console=FakeConsole()
  with tempfile.TemporaryDirectory() as folder,console.connect() as sock:
   found,_=cc.find_captures(sock,name_of=game_name);seen=[]
   for capture in found:self.assertIsNotNone(cc.copy_capture(sock,capture,folder,lambda done,total:seen.append((done,total))))
   asked=len(console.asked)
   for capture in found:cc.copy_capture(sock,capture,folder)
   self.assertEqual(len(console.asked),asked,'a copy already on the PC is not read again')
   names=sorted(p.name for p in Path(folder).rglob('*') if p.is_file())
   self.assertEqual(names,['PS5 Astro Bot clip.webm','PS5 Demon Souls boss.mp4','PS5 System shot one.png'])
   self.assertEqual((Path(folder)/'Recordings'/'PS5 Demon Souls boss.mp4').read_bytes(),FILES[A+'/video/NPXS40087/CUSA03280/04b/boss.mp4'])
   self.assertIn((12,12),seen)
   self.assertEqual(sorted(item.path.name for item in capture_items(folder)),names)
 def test_a_refused_file_leaves_nothing_behind(self):
  console=FakeConsole()
  with tempfile.TemporaryDirectory() as folder,console.connect() as sock:
   capture={'path':'/user/av_contents/gone.jpg','name':'gone.jpg','folder':'x','size':4,'modified':1,'kind':'Photos'}
   self.assertIsNone(cc.copy_capture(sock,capture,folder))
   self.assertEqual([p for p in Path(folder).rglob('*') if p.is_file()],[])
 def test_odd_names_become_safe_file_names(self):
  capture={'name':'a/b:c?.JPG','folder':'Game: Part <2>','kind':'Photos'}
  self.assertEqual(cc.local_name(capture),Path('Screenshots')/'PS5 Game_ Part _2_ a_b_c_.jpg')
 def test_sizes_read_naturally(self):
  self.assertEqual(cc.size_label(512),'512 B');self.assertEqual(cc.size_label(3<<20),'3.0 MB');self.assertEqual(cc.size_label(5<<30),'5.0 GB')

if __name__=='__main__':unittest.main()
