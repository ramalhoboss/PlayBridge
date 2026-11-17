import http.client,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from PIL import Image
import phone_link as phone
import phone_panel
from desktop_features import CaptureItem

TOKEN='a'*32

class Clock:
 def __init__(self):self.now=100.0
 def __call__(self):return self.now

def make_folder():
 folder=Path(tempfile.mkdtemp())
 Image.new('RGB',(1920,1080),(30,60,90)).save(folder/'shot.png')
 Image.new('RGBA',(512,512),(200,10,10,255)).save(folder/'icon.png')
 (folder/'clip.mp4').write_bytes(bytes(range(256))*40)
 return folder

class PanelTests(unittest.TestCase):
 def setUp(self):
  self.folder=make_folder();self.clock=Clock();self.started=[];self.thumbs=[]
  self.games=[dict(title='PPSA01234',name='Game One',running=True),dict(title='PPSA05678',name='Game Two',running=False)]
  self.items=[CaptureItem(self.folder/'clip.mp4','Videos',10240,2.0),CaptureItem(self.folder/'shot.png','Photos',1000,1.0)]
  def start(title,switch):self.started.append((title,switch));return dict(state='started',text='Starting')
  def thumbnail(path,size):self.thumbs.append(path);return Image.new('RGB',size,(0,0,0))
  self.panel=phone_panel.Panel(lambda:self.games,lambda title:self.folder/'icon.png' if title=='PPSA01234' else None,start,lambda:self.items,
   lambda:['one','two'],thumbnail,clock=self.clock)
 def test_games_start_only_from_the_library(self):
  self.assertEqual(self.panel.game_list()[0],dict(id='PPSA01234',name='Game One',running=True))
  self.assertEqual(self.panel.start_game('PPSA99999')['state'],'problem');self.assertEqual(self.started,[])
  self.assertEqual(self.panel.start_game('PPSA05678',True)['state'],'started');self.assertEqual(self.started,[('PPSA05678',True)])
 def test_icons_are_made_small_once_and_only_for_library_games(self):
  data=self.panel.icon_bytes('PPSA01234');self.assertTrue(data.startswith(b'\x89PNG'))
  with Image.open(__import__('io').BytesIO(data)) as image:self.assertEqual(image.size,phone_panel.ICON)
  self.assertIs(self.panel.icon_bytes('PPSA01234'),data)
  self.assertIsNone(self.panel.icon_bytes('PPSA05678'));self.assertIsNone(self.panel.icon_bytes('../icon'))
 def test_captures_are_known_by_id_and_thumbnails_are_kept(self):
  listed=self.panel.capture_list();self.assertEqual([item['name'] for item in listed],['clip.mp4','shot.png'])
  video,photo=listed
  self.assertTrue(self.panel.thumb_bytes(photo['id']).startswith(b'\xff\xd8'))
  first=self.panel.thumb_bytes(video['id']);self.assertIs(self.panel.thumb_bytes(video['id']),first);self.assertEqual(len(self.thumbs),1)
  self.assertIsNone(self.panel.thumb_bytes('nothing'));self.assertIsNone(self.panel.ticket('nothing'))
 def test_a_ticket_lasts_while_used_and_never_past_three_hours(self):
  key=self.panel.capture_list()[1]['id'];name=self.panel.ticket(key).rsplit('/',1)[1]
  self.assertEqual(self.panel.redeem(name).path.name,'shot.png')
  self.clock.now+=phone_panel.TICKET_IDLE-1;self.assertIsNotNone(self.panel.redeem(name))
  self.clock.now+=phone_panel.TICKET_IDLE-1;self.assertIsNotNone(self.panel.redeem(name))
  self.clock.now+=phone_panel.TICKET_IDLE+1;self.assertIsNone(self.panel.redeem(name))
  name=self.panel.ticket(key).rsplit('/',1)[1]
  for _ in range(phone_panel.TICKET_LONGEST//60):self.clock.now+=60;self.panel.redeem(name)
  self.assertIsNone(self.panel.redeem(name));self.assertIsNone(self.panel.redeem('made-up'))
 def test_old_tickets_make_room(self):
  key=self.panel.capture_list()[1]['id'];names=[self.panel.ticket(key).rsplit('/',1)[1] for _ in range(phone_panel.TICKETS+3)]
  self.assertIsNone(self.panel.redeem(names[0]));self.assertIsNotNone(self.panel.redeem(names[-1]));self.assertEqual(len(self.panel.tickets),phone_panel.TICKETS)

class RangeTests(unittest.TestCase):
 def test_ranges(self):
  self.assertIsNone(phone.byte_range(None,100));self.assertIsNone(phone.byte_range('bytes=0-1,5-6',100));self.assertIsNone(phone.byte_range('items=1-2',100))
  self.assertEqual(phone.byte_range('bytes=0-',100),(0,99));self.assertEqual(phone.byte_range('bytes=10-19',100),(10,19))
  self.assertEqual(phone.byte_range('bytes=90-500',100),(90,99));self.assertEqual(phone.byte_range('bytes=-30',100),(70,99));self.assertEqual(phone.byte_range('bytes=-300',100),(0,99))
  for bad in ('bytes=100-','bytes=20-10','bytes=-0'):
   with self.assertRaises(ValueError):phone.byte_range(bad,100)
 def test_names_in_the_download_header(self):
  self.assertEqual(phone.disposition('a.png',True),'attachment; filename="a.png"; filename*=UTF-8\'\'a.png')
  self.assertEqual(phone.disposition('ação "x".mp4',False),'inline; filename="a__o _x_.mp4"; filename*=UTF-8\'\'a%C3%A7%C3%A3o%20%22x%22.mp4')

class RouteTests(unittest.TestCase):
 def setUp(self):
  self.folder=make_folder();self.play=True;self.started=[]
  items=[CaptureItem(self.folder/'clip.mp4','Videos',10240,2.0)]
  def start(title,switch):self.started.append(title);return dict(state='started',text='Starting')
  self.server=phone.PhoneServer(phone.PhoneFeed(),phone.Pairing([phone.digest(TOKEN)]),lambda:'127.0.0.1',lambda:self.play,port=0)
  self.server.panel=phone_panel.Panel(lambda:[dict(title='PPSA01234',name='One')],lambda title:self.folder/'icon.png',start,lambda:items,lambda:['line'])
  self.assertTrue(self.server.start());self.addCleanup(self.server.stop)
 def ask(self,method,path,body=None,headers=None):
  connection=http.client.HTTPConnection('127.0.0.1',self.server.port,timeout=5)
  try:
   connection.request(method,path,body=json.dumps(body) if body is not None else None,headers=headers or {})
   response=connection.getresponse();return response.status,dict(response.getheaders()),response.read()
  finally:connection.close()
 def test_lists_need_the_token(self):
  for path in ('/api/games','/api/captures','/api/log','/api/icon/PPSA01234'):
   self.assertEqual(self.ask('GET',path)[0],401);self.assertEqual(self.ask('GET',path,headers={'X-Token':'b'*32})[0],401)
  status,_,body=self.ask('GET','/api/games',headers={'X-Token':TOKEN});self.assertEqual(status,200);self.assertEqual(json.loads(body)['games'][0]['name'],'One')
  self.assertEqual(json.loads(self.ask('GET','/api/log',headers={'X-Token':TOKEN})[2]),{'lines':['line']})
  status,headers,body=self.ask('GET','/api/icon/PPSA01234',headers={'X-Token':TOKEN});self.assertEqual((status,headers['Content-Type']),(200,'image/png'))
  self.assertEqual(self.ask('GET','/api/icon/PPSA99999',headers={'X-Token':TOKEN})[0],404)
  self.assertEqual(self.ask('POST','/api/start',{'id':'PPSA01234'})[0],401);self.assertEqual(self.started,[])
 def test_starting_needs_play_on_your_ps5(self):
  self.play=False
  answer=json.loads(self.ask('POST','/api/start',{'id':'PPSA01234'},{'X-Token':TOKEN,'Content-Type':'application/json'})[2])
  self.assertEqual(answer['state'],'problem');self.assertIn('Play on your PS5',answer['text']);self.assertEqual(self.started,[])
  self.play=True
  answer=json.loads(self.ask('POST','/api/start',{'id':'PPSA01234'},{'X-Token':TOKEN})[2]);self.assertEqual(answer['state'],'started');self.assertEqual(self.started,['PPSA01234'])
  self.assertEqual(self.ask('POST','/api/start',None,{'X-Token':TOKEN,'Content-Length':'0'})[0],400)
 def test_a_capture_opens_through_its_ticket_in_parts(self):
  key=json.loads(self.ask('GET','/api/captures',headers={'X-Token':TOKEN})[2])['captures'][0]['id']
  self.assertEqual(self.ask('POST','/api/ticket',{'id':'nope'},{'X-Token':TOKEN})[0],404)
  url=json.loads(self.ask('POST','/api/ticket',{'id':key},{'X-Token':TOKEN})[2])['url'];whole=(self.folder/'clip.mp4').read_bytes()
  status,headers,body=self.ask('GET',url);self.assertEqual((status,body),(200,whole));self.assertEqual(headers['Content-Type'],'video/mp4');self.assertTrue(headers['Content-Disposition'].startswith('inline'))
  status,headers,body=self.ask('GET',url+'?save=1',headers={'Range':'bytes=100-199'})
  self.assertEqual((status,body),(206,whole[100:200]));self.assertEqual(headers['Content-Range'],f'bytes 100-199/{len(whole)}');self.assertTrue(headers['Content-Disposition'].startswith('attachment'))
  self.assertEqual(self.ask('GET',url,headers={'Range':f'bytes={len(whole)}-'})[0],416)
  status,headers,body=self.ask('HEAD',url);self.assertEqual((status,body,headers['Content-Length']),(200,b'',str(len(whole))))
  self.assertEqual(self.ask('GET','/api/file/made-up')[0],410)
 def test_no_panel_no_routes(self):
  self.server.panel=None
  self.assertEqual(self.ask('GET','/api/games',headers={'X-Token':TOKEN})[0],404)
  self.assertEqual(self.ask('POST','/api/start',{'id':'PPSA01234'},{'X-Token':TOKEN})[0],404)

if __name__=='__main__':unittest.main()
