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
 return {'ip':address,'name':fields.get('host-name','PS5')[:64],'source':'PS5 discovery'}

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
 found={}
 with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
  udp.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1);udp.settimeout(.2);udp.bind(('',0))
  request=b'SRCH * HTTP/1.1\r\ndevice-discovery-protocol-version:00030010\r\n\r\n'
  try:udp.sendto(request,('255.255.255.255',9302))
  except OSError:pass
  until=time.monotonic()+1.2
  while time.monotonic()<until:
   try:data,addr=udp.recvfrom(8192)
   except socket.timeout:continue
   item=parse_response(data,addr[0])
   if item:found[item['ip']]=item
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
