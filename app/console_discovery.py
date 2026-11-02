"""Bounded LAN discovery: PS5 UDP response and Payload Manager HTTP fallback."""
import concurrent.futures,http.client,ipaddress,socket,time

def parse_response(data,address):
 text=data.decode('utf8','replace');lines=text.splitlines()
 if not lines or not lines[0].startswith('HTTP/1.1 '):return None
 fields={}
 for line in lines[1:]:
  if ':' in line:
   k,v=line.split(':',1);fields[k.strip().lower()]=v.strip()
 if fields.get('host-type','').upper()!='PS5':return None
 return {'ip':address,'name':fields.get('host-name','PS5')[:64],'source':'PS5 discovery','resting':lines[0].split()[1:2]==['620'],'firmware':fields.get('system-version','')}

SEARCH=b'SRCH * HTTP/1.1\r\ndevice-discovery-protocol-version:00030010\r\n\r\n'
def firmware_name(version):
 """'13600007' reads as 13.60; an empty string means the console did not say."""
 return f'{int(version[:2],16):x}.{int(version[2:4],16):02x}' if len(version)==8 and all(c in '0123456789abcdefABCDEF' for c in version) else ''

# The value the payload's own firmware check accepts.
SUPPORTED_FIRMWARE='13600007'
def supported(item):
 """False only when the console said it runs a firmware the payload refuses."""
 return not item.get('firmware') or item['firmware']==SUPPORTED_FIRMWARE

def ask(host,timeout=.6):
 """The console's own answer, with nothing loaded on it. None if it stays silent."""
 with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
  udp.settimeout(timeout)
  try:
   udp.sendto(SEARCH,(host,9302))
   while True:
    data,addr=udp.recvfrom(8192)
    if addr[0]==host:return parse_response(data,host)
  except OSError:return None

def broadcast(wait=1.2):
 """Every PS5 that answers on this network."""
 found={}
 with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
  udp.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1);udp.settimeout(.2);udp.bind(('',0))
  try:udp.sendto(SEARCH,('255.255.255.255',9302))
  except OSError:pass
  until=time.monotonic()+wait
  while time.monotonic()<until:
   try:data,addr=udp.recvfrom(8192)
   except socket.timeout:continue
   except OSError:break
   item=parse_response(data,addr[0])
   if item:found[item['ip']]=item
 return found

def locate(host):
 """The console to use when the app opens: the saved address if it answers, otherwise the only PS5 on the network. A loopback address is a test double and stays what it is."""
 try:
  if ipaddress.ip_address(host).is_loopback:return None
 except ValueError:pass
 item=ask(host) if host else None
 if item:return item
 found=broadcast()
 return next(iter(found.values())) if len(found)==1 else None

def local_addresses():
 addresses=set()
 for entry in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET):
  ip=ipaddress.IPv4Address(entry[4][0])
  if ip.is_private and not ip.is_loopback and not ip.is_link_local:addresses.add(str(ip))
 return sorted(addresses)

def manager_probe(ip):
 connection=http.client.HTTPConnection(ip,8888,timeout=.35)
 try:
  connection.request('GET','/');response=connection.getresponse();body=response.read(65536).decode('utf8','replace').lower()
  if response.status==200 and ('ps5 web file manager' in body or ('payload' in body and 'ps5' in body)):
   return {'ip':ip,'name':'Payload Manager','source':'LAN service scan'}
 except (OSError,http.client.HTTPException):pass
 finally:connection.close()
 return None

def discover(preferred=None):
 found=broadcast()
 # Check saved address plus a bounded /24 around each local interface (max 2).
 targets=set()
 try:
  if preferred and ipaddress.IPv4Address(preferred).is_private:targets.add(preferred)
 except ValueError:pass
 for address in local_addresses()[:2]:
  targets.update(str(x) for x in ipaddress.IPv4Network(address+'/24',strict=False).hosts())
 with concurrent.futures.ThreadPoolExecutor(max_workers=48) as pool:
  for item in pool.map(manager_probe,sorted(targets)):
   if item and item['ip'] not in found:found[item['ip']]=item
 return sorted(found.values(),key=lambda x:tuple(map(int,x['ip'].split('.'))))
