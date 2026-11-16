"""Play away from home: how this PC reaches the PS5 when it is not on the home network, and how much the line carries.

At home, Prepare finds the way in. The home router is asked over UPnP to forward the payload's own ports to the console, with
outside port numbers chosen at random so they are not the well-known ones, for the away hours only where the router allows it. The
loader's port (9021) is never forwarded: away from home nothing can be sent to the console, only the payload that is already waiting
there (payload/away-rules.h) can be reached, and it answers this PC's key only. When the router will not forward, or the provider
shares one address between homes, a Tailscale route to the home network does the same job, and PlayBridge says which.

Away, the stream starts at the away quality and steps down when the line loses too much, then back up after minutes without loss.
Each step is a new capture, about a second of picture, so it never goes back and forth."""
import ipaddress,json,os,random,re,shutil,socket,subprocess,threading,time,urllib.error,urllib.request
from urllib.parse import urljoin,urlsplit
from xml.etree import ElementTree
from xml.sax.saxutils import escape

SSDP=('239.255.255.250',1900)
SEARCH=('urn:schemas-upnp-org:device:InternetGatewayDevice:2','urn:schemas-upnp-org:device:InternetGatewayDevice:1',
 'urn:schemas-upnp-org:service:WANIPConnection:2','urn:schemas-upnp-org:service:WANIPConnection:1','urn:schemas-upnp-org:service:WANPPPConnection:1')
SERVICES=('urn:schemas-upnp-org:service:WANIPConnection:2','urn:schemas-upnp-org:service:WANIPConnection:1','urn:schemas-upnp-org:service:WANPPPConnection:1')
# The payload's ports that play away from home needs, and where each sits after the first outside port. Never the loader's.
PORTS=(('TCP',9076,0),('UDP',9076,0),('TCP',9077,1),('UDP',9078,2),('TCP',9079,3))
FIRST_LEAST,FIRST_MOST=20000,60000
DESCRIPTION='PlayBridge'
HOURS=(6,12,24,48,72);USUAL_HOURS=12
# The quality away from home until the player picks one: what most home connections can send out.
USUAL_PROFILE='balanced'
DESCRIPTION_MOST=256*1024
# The UPnP errors a router gives: the outside port is someone else's, only permanent forwards, or it forwards to the asking device only.
CONFLICT,ONLY_PERMANENT=718,725
REFUSED=(606,501,402,714,724,726,727,728)

class UpnpError(Exception):
 def __init__(self,code,text):super().__init__(f'{code} {text}');self.code=code;self.text=text

def _local(host):
 try:address=ipaddress.ip_address(host)
 except ValueError:return False
 return address.is_private and not address.is_loopback
def shared_address(text):
 """Whether the router's outside address is not on the internet itself: another router in front of it, or the provider's address
 shared between homes (100.64/10), so a forward on this router reaches nothing from outside."""
 try:address=ipaddress.ip_address(text)
 except ValueError:return True
 return address.is_private or address in ipaddress.ip_network('100.64.0.0/10') or address.is_unspecified

_OPEN=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def _fetch(url,body=None,headers=None,timeout=4):
 request=urllib.request.Request(url,body,headers or {})
 with _OPEN.open(request,timeout=timeout) as answer:return answer.read(DESCRIPTION_MOST)

def discover(timeout=2.0,sock=None):
 """The routers that answer a UPnP search on the home network: (their address, their description's address), first answer first.
 Only an answer that names a description on its own home address is kept."""
 own=sock is None
 if own:
  sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM,socket.IPPROTO_UDP);sock.setsockopt(socket.IPPROTO_IP,socket.IP_MULTICAST_TTL,2)
 sock.settimeout(.25);found=[];seen=set()
 try:
  for target in SEARCH:
   message=f'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\nMX: 1\r\nST: {target}\r\n\r\n'.encode()
   try:sock.sendto(message,SSDP)
   except OSError:pass
  end=time.monotonic()+timeout
  while time.monotonic()<end:
   try:data,(host,_)=sock.recvfrom(4096)
   except socket.timeout:continue
   except OSError:break
   match=re.search(rb'^location:\s*(\S+)',data,re.I|re.M)
   if not match:continue
   location=match.group(1).decode('latin-1');where=urlsplit(location).hostname
   if where!=host or not _local(host) or location in seen:continue
   seen.add(location);found.append((host,location))
 finally:
  if own:sock.close()
 return found

def control_of(location,fetch=_fetch):
 """The router's connection service: (its control address, its type), or None when it has none."""
 root=ElementTree.fromstring(fetch(location));base=location
 for node in root.iter():
  if node.tag.endswith('URLBase') and node.text and node.text.strip():base=node.text.strip()
 services={}
 for node in root.iter():
  if not node.tag.endswith('service'):continue
  kind=next((c.text.strip() for c in node if c.tag.endswith('serviceType') and c.text),None)
  url=next((c.text.strip() for c in node if c.tag.endswith('controlURL') and c.text),None)
  if kind in SERVICES and url:services.setdefault(kind,urljoin(base,url))
 for kind in SERVICES:
  if kind in services:
   control=services[kind]
   # A control address on another host than the router's own is not followed.
   if urlsplit(control).hostname!=urlsplit(location).hostname:return None
   return control,kind
 return None

def soap(control,service,action,args=(),fetch=_fetch,timeout=4):
 """One UPnP action: its answer's values by name; UpnpError with the router's code when it refuses."""
 body=('<?xml version="1.0"?>\r\n<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
  f'<s:Body><u:{action} xmlns:u="{service}">'+''.join(f'<{k}>{escape(str(v))}</{k}>' for k,v in args)+f'</u:{action}></s:Body></s:Envelope>').encode()
 headers={'Content-Type':'text/xml; charset="utf-8"','SOAPAction':f'"{service}#{action}"'}
 try:data=fetch(control,body,headers,timeout)
 except urllib.error.HTTPError as error:
  try:text=error.read(DESCRIPTION_MOST)
  except Exception:text=b''
  code=re.search(rb'<(?:\w+:)?errorCode>\s*(\d+)',text);words=re.search(rb'<(?:\w+:)?errorDescription>([^<]*)',text)
  raise UpnpError(int(code.group(1)) if code else error.code,(words.group(1).decode('utf8','replace') if words else error.reason) or 'refused') from None
 values={}
 for node in ElementTree.fromstring(data).iter():
  name=node.tag.rsplit('}',1)[-1]
  if name.startswith('New'):values[name]=(node.text or '').strip()
 return values

class Router:
 """The home router's connection service, found over UPnP."""
 def __init__(self,control,service,fetch=_fetch):self.control=control;self.service=service;self.fetch=fetch
 @classmethod
 def find(cls,timeout=2.0,search=discover,fetch=_fetch):
  for host,location in search(timeout):
   try:found=control_of(location,fetch)
   except (OSError,ElementTree.ParseError,ValueError):continue
   if found:return cls(*found,fetch=fetch)
  return None
 def call(self,action,*args):return soap(self.control,self.service,action,args,self.fetch)
 def outside_address(self):return self.call('GetExternalIPAddress').get('NewExternalIPAddress','')
 def forward(self,protocol,outside,inside,client,seconds):
  self.call('AddPortMapping',('NewRemoteHost',''),('NewExternalPort',outside),('NewProtocol',protocol),('NewInternalPort',inside),
   ('NewInternalClient',client),('NewEnabled',1),('NewPortMappingDescription',DESCRIPTION),('NewLeaseDuration',seconds))
 def remove(self,protocol,outside):self.call('DeletePortMapping',('NewRemoteHost',''),('NewExternalPort',outside),('NewProtocol',protocol))

def forward_all(router,client,first,hours,attempts=4,pick=None):
 """Forwards every port in PORTS to the console. Returns (first outside port, permanent, None) or (None, False, reason). An outside
 port already taken by another device moves all of them to a new first port; a router that only forwards to the asking device, or
 forwards nothing, is said so."""
 pick=pick or (lambda:random.randrange(FIRST_LEAST,FIRST_MOST,4))
 seconds=hours*3600;permanent=False
 for _ in range(attempts):
  done=[]
  try:
   for protocol,inside,offset in PORTS:
    try:router.forward(protocol,first+offset,inside,client,0 if permanent else seconds)
    except UpnpError as error:
     if error.code!=ONLY_PERMANENT or permanent:raise
     permanent=True;router.forward(protocol,first+offset,inside,client,0)
    done.append((protocol,first+offset))
   return first,permanent,None
  except UpnpError as error:
   for protocol,outside in done:
    try:router.remove(protocol,outside)
    except (UpnpError,OSError):pass
   if error.code==CONFLICT:first=pick();continue
   if error.code in REFUSED:return None,False,'refused'
   return None,False,f'error {error.code}'
  except OSError:
   return None,False,'no answer'
 return None,False,'taken'

def remove_all(router,first):
 for protocol,_,offset in PORTS:
  try:router.remove(protocol,first+offset)
  except (UpnpError,OSError):pass

TAILSCALE_PLACES=(r'C:\Program Files\Tailscale\tailscale.exe',r'C:\Program Files (x86)\Tailscale\tailscale.exe')
def tailscale_program():
 found=shutil.which('tailscale')
 if found:return found
 return next((p for p in TAILSCALE_PLACES if os.path.isfile(p)),None)
def tailscale_status(run=subprocess.run,program=None):
 """Tailscale's own status of this PC, or None without Tailscale."""
 program=program or tailscale_program()
 if not program:return None
 try:
  done=run([program,'status','--json'],capture_output=True,timeout=5,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  return json.loads(done.stdout.decode('utf8','replace')) if done.stdout else None
 except (OSError,subprocess.SubprocessError,ValueError):return None
def tailscale_route(status,console):
 """The Tailscale device that routes to the console's address, as (its name, whether it is online), or None. This PC's own routes
 do not count: away from home it is not there."""
 if not status or status.get('BackendState')!='Running':return None
 try:address=ipaddress.ip_address(console)
 except ValueError:return None
 for peer in (status.get('Peer') or {}).values():
  for route in peer.get('PrimaryRoutes') or []:
   try:
    if address in ipaddress.ip_network(route,strict=False):return (peer.get('HostName') or peer.get('DNSName') or 'a Tailscale device').strip('.'),bool(peer.get('Online'))
   except ValueError:continue
 return None
def home_subnet(console):
 try:return str(ipaddress.ip_network(f'{console}/24',strict=False))
 except ValueError:return '192.168.1.0/24'

class Route:
 """Where the console's ports are from here: away, through the forwards or a Tailscale route; at home, as they are."""
 def __init__(self,host,first=None):self.host=host;self.first=first
 def port(self,inside):
  if self.first is None:return inside
  return next(self.first+offset for _,port,offset in PORTS if port==inside)
 def address(self,inside):return self.host,self.port(inside)

def prepare(console,hours=USUAL_HOURS,first=None,router_find=Router.find,status=tailscale_status,pick=None):
 """At home: the way to the console from outside, as the settings keep it. Tries the router, then Tailscale; says what the player
 has to do when neither works."""
 pick=pick or (lambda:random.randrange(FIRST_LEAST,FIRST_MOST,4))
 hours=hours if hours in HOURS else USUAL_HOURS;away=dict(on=True,hours=hours,console=console,prepared=int(time.time()))
 first=first or pick();router=None;why=''
 try:router=router_find()
 except OSError:router=None
 if router is not None:
  try:outside=router.outside_address()
  except (UpnpError,OSError,ElementTree.ParseError):outside=''
  if outside and shared_address(outside):why='shared'
  else:
   done,permanent,reason=forward_all(router,console,first,hours,pick=pick)
   if done is not None:
    away.update(method='router',address=outside,first=done,permanent=permanent)
    return away
   why=reason or 'refused'
 else:why='no router'
 route=tailscale_route(status(),console)
 if route:
  away.update(method='tailscale',address=console,via=route[0],router_problem=why);return away
 away.update(method='manual',address='',first=first,router_problem=why);return away

def address_ok(text):
 """A home address the player types: an IPv4 address or a host name, with no scheme, port or path."""
 if not text or len(text)>253:return False
 try:return ipaddress.ip_address(text).version==4
 except ValueError:pass
 return re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*\.?',text) is not None and not text.replace('.','').isdigit()

def route_of(away):
 """The route a prepared away setting gives, or None when it gives none yet (a manual one with no address typed)."""
 if not away or not away.get('on'):return None
 if away.get('method')=='tailscale':return Route(away.get('console') or away.get('address'))
 host=(away.get('address') or '').strip()
 if not host:return None
 return Route(host,away.get('first'))

def explain(away):
 """What the player reads about the way in, in Settings."""
 if not away or not away.get('on'):return 'Off. Turn it on at home, with the PS5 on, before you leave.'
 method=away.get('method');hours=away.get('hours',USUAL_HOURS)
 wait=f'The PS5 waits {hours} hours for this PC after each stream. Leave it on, not in rest mode.'
 if method=='router':
  ports=', '.join(f'{p} {away["first"]+o}' for p,_,o in PORTS)
  kept='until you turn this off at home' if away.get('permanent') else f'for {hours} hours'
  return f'Ready: your router forwards {ports} to the PS5 {kept}. Away, PlayBridge connects to {away.get("address")}. {wait}'
 if method=='tailscale':
  return f'Ready through Tailscale: {away.get("via")} routes your home network, so away PlayBridge reaches the PS5 at {away.get("console")}. {wait}'
 problem={'shared':'Your internet provider shares one address between homes, or another router sits in front of yours, so forwarding cannot reach the PS5.',
  'refused':'Your router does not let PlayBridge forward ports to the PS5.','no router':'No router answered PlayBridge on this network.',
  'no answer':'Your router did not answer.','taken':'Your router has those ports taken.'}.get(away.get('router_problem'),'Your router could not forward the ports.')
 ports=', '.join(f'{p} {away["first"]+o} to {inside}' for p,inside,o in PORTS);console=away.get('console') or ''
 if (away.get('address') or '').strip():
  return f'Ready: away, PlayBridge connects to {away["address"].strip()}, where your router forwards {ports} to the PS5 ({console}). {wait}'
 tailscale=f'install Tailscale on a computer that stays at home and share your home network from it (tailscale up --advertise-routes={home_subnet(console)}), then turn this on again'
 if away.get('router_problem')=='shared':
  # Forwarding cannot help until the provider gives the home an address of its own, so Tailscale comes first.
  return (f'{problem} Either {tailscale}, or ask your provider for an address of your own, forward {ports} to the PS5 ({console}) in your '
   f'router\'s page and type that address here. {wait}')
 return f'{problem} Either forward {ports} to the PS5 ({console}) in your router\'s page and type your home address here, or {tailscale}. {wait}'

# Stepping down and back up.
DOWN_LOSS=.08;BAD_SECONDS=4;WINDOW=6;CHANGE_GAP=15.0;UP_AFTER=180.0;GROWTH_MS=400
def ladder(profiles):
 """The 1080p H.264 steps, lowest first, as profile names."""
 return [name for name,p in sorted(profiles.items(),key=lambda kv:kv[1]['bitrate']) if p.get('resolution',4) in (0,4) and not p.get('codec')]
class AwayRate:
 """When the line cannot carry the stream it steps down one profile; after minutes without loss it steps back up, never above the
 one chosen. second(...) once a second returns the profile to change to, or None."""
 def __init__(self,profiles,chosen,clock=time.monotonic):
  self.profiles=profiles;self.top=chosen;self.profile=chosen;self.clock=clock;self.marks=[];self.changed=clock();self.good_since=clock()
 def _down(self):
  rate=self.profiles[self.profile]['bitrate'];lower=[n for n in ladder(self.profiles) if self.profiles[n]['bitrate']<rate]
  return lower[-1] if lower else None
 def _up(self):
  if self.profile==self.top:return None
  rate=self.profiles[self.profile]['bitrate'];top=self.profiles[self.top]['bitrate']
  higher=[n for n in ladder(self.profiles) if rate<self.profiles[n]['bitrate']<=top]
  return higher[0] if higher and self.profiles[higher[0]]['bitrate']<top else self.top
 def second(self,loss=0.0,lost=0,growth_ms=0):
  now=self.clock();bad=loss>DOWN_LOSS or lost>0 or growth_ms>GROWTH_MS
  self.marks=(self.marks+[bad])[-WINDOW:]
  if not bad and loss<.005:
   if self.good_since is None:self.good_since=now
  else:self.good_since=None
  if now-self.changed<CHANGE_GAP:return None
  if sum(self.marks)>=BAD_SECONDS:
   lower=self._down()
   if lower:self.profile=lower;self.changed=now;self.marks=[];self.good_since=None;return lower
  if self.good_since is not None and now-self.good_since>=UP_AFTER:
   higher=self._up()
   if higher:self.profile=higher;self.changed=now;self.good_since=now;return higher
  return None
