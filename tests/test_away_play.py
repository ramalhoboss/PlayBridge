"""Play away from home on the PC: the router asked over UPnP (a stand-in router on this PC, speaking SOAP over HTTP), the answers a real
router gives when it refuses, Tailscale's status read for a route home, the way in kept and explained, and the quality stepping down
on a line that loses and back up after minutes without loss."""
import http.server,json,socket,struct,sys,threading,types,unittest
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
import away_play,network_link,pad_input,phone_link,secure_link
import playbridge as core
from playbridge import PROFILES

DESCRIPTION='''<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0"><device><deviceType>urn:schemas-upnp-org:device:InternetGatewayDevice:1</deviceType>
<deviceList><device><deviceType>urn:schemas-upnp-org:device:WANDevice:1</deviceType><deviceList><device>
<deviceType>urn:schemas-upnp-org:device:WANConnectionDevice:1</deviceType><serviceList>
<service><serviceType>urn:schemas-upnp-org:service:WANIPConnection:1</serviceType><serviceId>urn:upnp-org:serviceId:WANIPConn1</serviceId>
<controlURL>/ctl/IPConn</controlURL></service></serviceList></device></deviceList></device></deviceList></device></root>'''

class FakeRouter:
 """A UPnP router on 127.0.0.1: its description, and AddPortMapping, DeletePortMapping and GetExternalIPAddress as a router answers
 them, with the refusals a test asks for."""
 def __init__(self,outside='81.20.30.40',refuse=None,taken=(),permanent_only=False):
  self.outside=outside;self.refuse=refuse;self.taken=set(taken);self.permanent_only=permanent_only;self.forwards={};self.calls=[]
  router=self
  class Handler(http.server.BaseHTTPRequestHandler):
   def log_message(self,*a):pass
   def do_GET(self):
    body=DESCRIPTION.encode();self.send_response(200);self.send_header('Content-Type','text/xml');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
   def do_POST(self):
    data=self.rfile.read(int(self.headers['Content-Length'])).decode();action=self.headers['SOAPAction'].strip('"').split('#')[1]
    args={k:v for k,v in __import__('re').findall(r'<(New\w+)>([^<]*)</New\w+>',data)};router.calls.append((action,args))
    code,values=router.answer(action,args)
    if code:
     body=(f'<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><s:Fault><faultcode>s:Client</faultcode><faultstring>UPnPError</faultstring>'
      f'<detail><UPnPError xmlns="urn:schemas-upnp-org:control-1-0"><errorCode>{code}</errorCode><errorDescription>Refused</errorDescription></UPnPError></detail></s:Fault></s:Body></s:Envelope>').encode()
     self.send_response(500)
    else:
     body=(f'<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><u:{action}Response xmlns:u="urn:schemas-upnp-org:service:WANIPConnection:1">'
      +''.join(f'<{k}>{v}</{k}>' for k,v in values.items())+f'</u:{action}Response></s:Body></s:Envelope>').encode()
     self.send_response(200)
    self.send_header('Content-Type','text/xml');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
  self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=self.server.serve_forever,daemon=True).start()
  self.location=f'http://127.0.0.1:{self.server.server_address[1]}/rootDesc.xml'
 def answer(self,action,args):
  if action=='GetExternalIPAddress':return 0,{'NewExternalIPAddress':self.outside}
  if action=='AddPortMapping':
   if self.refuse:return self.refuse,{}
   key=(args['NewProtocol'],int(args['NewExternalPort']))
   if key[1] in self.taken:return 718,{}
   if self.permanent_only and args['NewLeaseDuration']!='0':return 725,{}
   self.forwards[key]=(args['NewInternalClient'],int(args['NewInternalPort']),int(args['NewLeaseDuration']),args['NewPortMappingDescription']);return 0,{}
  if action=='DeletePortMapping':
   self.forwards.pop((args['NewProtocol'],int(args['NewExternalPort'])),None);return 0,{}
  return 401,{}
 def find(self,timeout=2.0):return away_play.Router.find(search=lambda t:[('127.0.0.1',self.location)])
 def close(self):self.server.shutdown();self.server.server_close()

class RouterTests(unittest.TestCase):
 def setUp(self):self.routers=[]
 def tearDown(self):
  for r in self.routers:r.close()
 def router(self,**kw):r=FakeRouter(**kw);self.routers.append(r);return r
 def test_every_port_but_the_loaders_is_forwarded_to_the_console_for_the_away_hours(self):
  r=self.router();away=away_play.prepare('192.168.1.50',12,first=40000,router_find=r.find,status=lambda:None)
  self.assertEqual((away['method'],away['address'],away['first'],away['permanent']),('router','81.20.30.40',40000,False))
  self.assertEqual(r.forwards,{('TCP',40000):('192.168.1.50',9076,43200,'PlayBridge'),('UDP',40000):('192.168.1.50',9076,43200,'PlayBridge'),
   ('TCP',40001):('192.168.1.50',9077,43200,'PlayBridge'),('UDP',40002):('192.168.1.50',9078,43200,'PlayBridge'),('TCP',40003):('192.168.1.50',9079,43200,'PlayBridge')})
  self.assertNotIn(9021,[inside for _,inside,_,_ in r.forwards.values()])
  route=away_play.route_of(away);self.assertEqual([route.address(p) for p in (9076,9077,9078,9079)],[('81.20.30.40',40000),('81.20.30.40',40001),('81.20.30.40',40002),('81.20.30.40',40003)])
  away_play.remove_all(r.find(),40000);self.assertEqual(r.forwards,{})
 def test_a_taken_port_moves_all_of_them_and_a_router_that_keeps_only_permanent_forwards_gets_those(self):
  r=self.router(taken={40001});picks=iter([50000])
  away=away_play.prepare('192.168.1.50',6,first=40000,router_find=r.find,status=lambda:None,pick=lambda:next(picks))
  self.assertEqual(away['first'],50000);self.assertEqual(sorted(p for _,p in r.forwards),[50000,50000,50001,50002,50003])
  r=self.router(permanent_only=True);away=away_play.prepare('192.168.1.50',6,first=41000,router_find=r.find,status=lambda:None)
  self.assertTrue(away['permanent']);self.assertTrue(all(lease==0 for _,_,lease,_ in r.forwards.values()))
  self.assertIn('until you turn this off at home',away_play.explain(away))
 def test_a_router_that_refuses_or_an_address_shared_by_the_provider_falls_back_to_tailscale_then_to_the_players_own_forward(self):
  r=self.router(refuse=606)
  status={'BackendState':'Running','Peer':{'k':{'HostName':'home-pc','Online':True,'PrimaryRoutes':['192.168.1.0/24']}}}
  away=away_play.prepare('192.168.1.50',12,first=40000,router_find=r.find,status=lambda:status)
  self.assertEqual((away['method'],away['via'],away['router_problem']),('tailscale','home-pc','refused'));self.assertEqual(r.forwards,{})
  self.assertEqual(away_play.route_of(away).address(9077),('192.168.1.50',9077))
  r=self.router(outside='100.72.1.9')
  away=away_play.prepare('192.168.1.50',12,first=40000,router_find=r.find,status=lambda:None)
  self.assertEqual((away['method'],away['router_problem']),('manual','shared'));self.assertEqual(r.forwards,{},'nothing forwarded that cannot help')
  self.assertIsNone(away_play.route_of(away),'no way in until the player types an address')
  text=away_play.explain(away);self.assertIn('shares one address',text);self.assertIn('TCP 40000 to 9076',text);self.assertIn('--advertise-routes=192.168.1.0/24',text)
  self.assertLess(text.index('Tailscale'),text.index('forward TCP'),'with a shared address Tailscale comes first')
  away['address']='home.example.net';self.assertEqual(away_play.route_of(away).address(9079),('home.example.net',40003))
  self.assertTrue(away_play.explain(away).startswith('Ready: away, PlayBridge connects to home.example.net'))
  away=away_play.prepare('192.168.1.50',12,first=40000,router_find=lambda:None,status=lambda:None)
  self.assertEqual(away['router_problem'],'no router')
 def test_the_router_description_must_stay_on_the_router(self):
  wrong=DESCRIPTION.replace('<controlURL>/ctl/IPConn</controlURL>','<controlURL>http://198.51.100.1/ctl</controlURL>')
  self.assertIsNone(away_play.control_of('http://192.168.1.1:5000/rootDesc.xml',fetch=lambda *a,**k:wrong.encode()))
  self.assertEqual(away_play.control_of('http://192.168.1.1:5000/rootDesc.xml',fetch=lambda *a,**k:DESCRIPTION.encode()),
   ('http://192.168.1.1:5000/ctl/IPConn','urn:schemas-upnp-org:service:WANIPConnection:1'))

class DiscoverTests(unittest.TestCase):
 def test_only_answers_that_name_a_description_on_their_own_home_address_are_kept(self):
  answers=[(b'HTTP/1.1 200 OK\r\nLOCATION: http://192.168.1.1:5000/rootDesc.xml\r\nST: x\r\n\r\n',('192.168.1.1',1900)),
   (b'HTTP/1.1 200 OK\r\nLocation: http://203.0.113.9/desc.xml\r\n\r\n',('192.168.1.1',1900)),
   (b'HTTP/1.1 200 OK\r\nLOCATION: http://8.8.8.8/desc.xml\r\n\r\n',('8.8.8.8',1900)),
   (b'HTTP/1.1 200 OK\r\nLOCATION: http://192.168.1.1:5000/rootDesc.xml\r\n\r\n',('192.168.1.1',1900))]
  class Sock:
   def __init__(self):self.sent=[]
   def settimeout(self,t):pass
   def sendto(self,data,where):self.sent.append((data,where))
   def recvfrom(self,n):
    if answers:return answers.pop(0)
    raise socket.timeout()
  sock=Sock();found=away_play.discover(.3,sock)
  self.assertEqual(found,[('192.168.1.1','http://192.168.1.1:5000/rootDesc.xml')])
  self.assertTrue(all(where==away_play.SSDP and data.startswith(b'M-SEARCH') for data,where in sock.sent))

class TailscaleTests(unittest.TestCase):
 def test_a_route_home_counts_only_from_another_running_device(self):
  status={'BackendState':'Running','Self':{'PrimaryRoutes':['192.168.1.0/24']},
   'Peer':{'a':{'HostName':'phone','Online':True,'PrimaryRoutes':None},'b':{'DNSName':'nas.tail.ts.net.','Online':False,'PrimaryRoutes':['192.168.1.0/24']}}}
  self.assertEqual(away_play.tailscale_route(status,'192.168.1.50'),('nas.tail.ts.net',False))
  self.assertIsNone(away_play.tailscale_route(status,'10.0.0.5'))
  self.assertIsNone(away_play.tailscale_route(dict(status,BackendState='Stopped'),'192.168.1.50'))
  self.assertIsNone(away_play.tailscale_route(None,'192.168.1.50'))
 def test_the_status_is_read_from_tailscale_itself(self):
  class Done:stdout=json.dumps({'BackendState':'Running'}).encode()
  seen=[]
  def run(args,**kw):seen.append(args);return Done()
  self.assertEqual(away_play.tailscale_status(run,program='tailscale.exe'),{'BackendState':'Running'});self.assertEqual(seen,[['tailscale.exe','status','--json']])
  def broken(args,**kw):raise OSError('gone')
  self.assertIsNone(away_play.tailscale_status(broken,program='tailscale.exe'))

class RateTests(unittest.TestCase):
 def rate(self,chosen='ultra'):
  self.now=[0.0];return away_play.AwayRate(PROFILES,chosen,clock=lambda:self.now[0])
 def seconds(self,rate,n,**kw):
  out=[]
  for _ in range(n):self.now[0]+=1;out.append(rate.second(**kw))
  return [o for o in out if o]
 def test_a_line_that_loses_steps_down_one_profile_at_a_time_never_quicker_than_every_15_seconds(self):
  rate=self.rate()
  self.assertEqual(self.seconds(rate,20,loss=.15),['very_high']);self.assertEqual(self.seconds(rate,15,loss=.15),['high'])
  self.assertEqual(self.seconds(rate,200,loss=.15),['balanced','data_saver']);self.assertEqual(rate.profile,'data_saver')
 def test_a_short_burst_of_loss_changes_nothing_and_lost_records_or_a_growing_delay_count_as_loss(self):
  rate=self.rate();self.now[0]=100
  self.assertEqual(self.seconds(rate,3,loss=.2)+self.seconds(rate,10),[])
  self.assertEqual(self.seconds(rate,4,lost=1),['very_high'])
  rate=self.rate();self.now[0]=100;self.assertEqual(self.seconds(rate,4,growth_ms=900),['very_high'])
 def test_after_three_minutes_without_loss_it_steps_back_up_but_never_past_the_chosen_one(self):
  rate=self.rate('qhd_balanced');self.now[0]=100
  self.assertEqual(self.seconds(rate,4,loss=.2),['very_high'])
  self.assertEqual(self.seconds(rate,179),[]);self.assertEqual(self.seconds(rate,2),['qhd_balanced'])
  self.assertEqual(self.seconds(rate,400),[])
  self.assertEqual(away_play.ladder(PROFILES)[:3],['data_saver','balanced','high'])

class HomeTests(unittest.TestCase):
 """Whether the PS5 is on this PC's own network decides between the home way and the away one."""
 class Api:
  def __init__(self,route,kind,fails=False):
   def best(dest,zero,ref):
    if fails:return 1232
    struct.pack_into('<II',ref._obj,network_link.ROUTE_INDEX,7,route);return 0
   def entry(ref):struct.pack_into('<I',ref._obj,network_link.IF_TYPE,kind);return 0
   self.GetBestRoute=best;self.GetIfEntry2=entry
 def test_straight_over_wifi_or_a_cable_is_home_and_a_router_or_a_tunnel_on_the_way_is_not(self):
  self.assertTrue(network_link.nearby('192.168.1.50',self.Api(3,network_link.WIFI)))
  self.assertTrue(network_link.nearby('192.168.1.50',self.Api(3,network_link.ETHERNET)))
  self.assertFalse(network_link.nearby('192.168.1.50',self.Api(4,network_link.WIFI)),'through a router')
  self.assertFalse(network_link.nearby('192.168.1.50',self.Api(3,53)),'a Tailscale or VPN adapter')
  self.assertIsNone(network_link.nearby('192.168.1.50',self.Api(3,71,fails=True)))
  self.assertIsNone(network_link.nearby('not an address'))
 @unittest.skipUnless(sys.platform=='win32','Windows only')
 def test_windows_answers_for_this_pc(self):
  # Reads only. The loopback is on this PC, but neither Wi-Fi nor a cable.
  self.assertFalse(network_link.nearby('127.0.0.1'))
 def test_a_ps5_away_from_this_pc_is_reached_the_away_way(self):
  me=types.SimpleNamespace(console=None,elsewhere=None,args=types.SimpleNamespace(host='192.168.1.50'))
  self.assertTrue(core.Player.away_needed(me),'no PS5 answered')
  me.elsewhere='192.168.1.9';self.assertFalse(core.Player.away_needed(me),'one answered at another address: a typing mistake, not away')
  me.elsewhere=None;me.console={'ip':'192.168.1.50'}
  for nearby,away in ((True,False),(None,False),(False,True)):
   with patch.object(core.network_link,'nearby',lambda address:nearby):self.assertEqual(core.Player.away_needed(me),away,nearby)

class WiringTests(unittest.TestCase):
 def test_udp_is_asked_for_with_its_own_flag(self):
  self.assertEqual(struct.unpack('<4sIII',core.capture_request('balanced',False,True))[3],core.UDP_FLAG)
  self.assertEqual(struct.unpack('<4sIII',core.capture_request('balanced',True,True))[3],core.UDP_FLAG|core.NOTIFY_FLAG)
  self.assertEqual(struct.unpack('<4sIII',core.capture_request('balanced'))[3],0)
 def test_the_away_flags_carry_the_hours(self):
  me=types.SimpleNamespace(away_settings=lambda:{'on':True,'hours':48})
  self.assertEqual(core.Player.away_flags(me),secure_link.FLAG_AWAY|48<<8)
  me.away_settings=lambda:{'on':True,'hours':5};self.assertEqual(core.Player.away_flags(me),secure_link.FLAG_AWAY|away_play.USUAL_HOURS<<8)
  me.away_settings=lambda:{'on':False,'hours':48};self.assertEqual(core.Player.away_flags(me),0)
 def test_the_ports_are_reached_through_the_away_route_only_while_away(self):
  me=types.SimpleNamespace(away_active=True,away_route=away_play.Route('81.20.30.40',40000))
  self.assertEqual(core.Player.reach(me,'192.168.1.50',9078),('81.20.30.40',40002))
  me.away_active=False;self.assertEqual(core.Player.reach(me,'192.168.1.50',9078),('192.168.1.50',9078))
 def test_the_controller_goes_the_away_way_and_its_payload_is_not_sent_from_away(self):
  class Udp:
   def __init__(self):self.sent=[]
   def sendto(self,data,where):self.sent.append(where)
  sent=[];done=threading.Event()
  def send_elf(host,data):sent.append(host);done.set()
  bridge=pad_input.PadBridge(lambda:'192.168.1.50',threading.Event(),companion=lambda:b'elf',send_elf=send_elf)
  bridge.reach=lambda host,port:('81.20.30.40',port+1);udp=Udp()
  self.assertTrue(bridge.put(udp,b'x'));self.assertEqual(udp.sent,[('81.20.30.40',pad_input.PAD_PORT+1)])
  bridge.away=lambda:True;bridge.attached=True
  bridge.watch_companion(0.0,udp);bridge.watch_companion(5.0,udp)
  self.assertEqual(sent,[]);self.assertIn('Away from home',bridge.companion_note)
  bridge.away=lambda:False;bridge.companion_at=None;bridge.watch_companion(10.0,udp)
  self.assertTrue(done.wait(3));self.assertEqual(sent,['192.168.1.50'],'at home it goes to the console itself')
 def test_a_phone_plays_through_the_away_route(self):
  phone=phone_link.PhonePad(lambda:'192.168.1.50',None,reach=lambda host,port:('127.0.0.1',port))
  seen=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
  try:
   seen.bind(('127.0.0.1',0));seen.settimeout(2)
   with patch.object(phone_link.pad,'PAD_PORT',seen.getsockname()[1]):phone.put(b'hello')
   self.assertEqual(seen.recvfrom(64)[0],b'hello')
  finally:seen.close();phone.udp.close()
 def test_a_typed_home_address_is_an_address_or_a_name_only(self):
  for text in ('81.20.30.40','home.example.net','my-home.duckdns.org','home'):self.assertTrue(away_play.address_ok(text),text)
  for text in ('','http://home.example.net','home.example.net:9076','::1','1.2.3','a b','-bad.example','x'*254):self.assertFalse(away_play.address_ok(text),text)

if __name__=='__main__':unittest.main()
