"""Check setup: whether this PC is ready to play and whether the PS5 is there, each with what to do when it is not. It runs once by
itself the first time PlayBridge opens, and again from Settings › Console.

Nothing is sent to the PS5. It is asked the same question Find console asks (the PS5's own discovery on UDP 9302), and Payload
Manager's page on port 8888 is looked at the same way. The ELF loader on port 9021 is not touched: it is reached only when you
connect, as before."""
import ctypes,ipaddress,shutil,socket,struct,sys
import console_discovery,graphics_card

OK,NOTE,WARN,FAIL='ok','note','warn','fail'
# Below this much free room, a 4K recording of an evening can fill the capture folder.
LOW_SPACE=10*1024**3
# Link speeds (bits per second) under which the 4K profile's 80 Mbps peaks have no room left.
SLOW_LINK=200_000_000

def item(state,title,text=''):return dict(state=state,title=title,text=text)

def link_of(host):
 """How this PC reaches host: dict(kind='cable'|'wifi'|'other', name, speed) from Windows' own route and interface tables, or None."""
 if sys.platform!='win32':return None
 try:
  helper=ctypes.WinDLL('iphlpapi');index=ctypes.c_ulong()
  if helper.GetBestInterface(ctypes.c_ulong(struct.unpack('<I',socket.inet_aton(host))[0]),ctypes.byref(index)):return None
  # MIB_IF_ROW2: the interface's index at 8, its alias at 28, type at 1128, physical medium at 1140, send speed at 1192.
  row=ctypes.create_string_buffer(1352);struct.pack_into('<I',row,8,index.value)
  if helper.GetIfEntry2(row):return None
  name=ctypes.wstring_at(ctypes.addressof(row)+28,257).split('\0')[0]
  kind,medium=struct.unpack_from('<I',row,1128)[0],struct.unpack_from('<I',row,1140)[0];speed=struct.unpack_from('<Q',row,1192)[0]
 except (OSError,ValueError,AttributeError,struct.error):return None
 # IF_TYPE_IEEE80211 or a wireless medium; IF_TYPE_ETHERNET_CSMACD.
 return dict(kind='wifi' if kind==71 or medium in (1,8,9) else 'cable' if kind==6 else 'other',name=name,speed=speed)

def source_address(host):
 """The address this PC sends from to reach host, as Windows routes it. Nothing is sent: a UDP socket only picks its route."""
 try:
  with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:udp.connect((host,9));return udp.getsockname()[0]
 except OSError:return None

def speed_text(bits):
 if not bits:return ''
 return f'{bits/1e9:g} Gbps' if bits>=1e9 else f'{round(bits/1e6)} Mbps'

def network_items(host,addresses,link,source=None):
 if not addresses:
  return [item(FAIL,'This PC is not on a home network','Connect it to the same router as the PS5, by cable or Wi-Fi.')]
 items=[]
 try:console=ipaddress.IPv4Address(host)
 except ValueError:console=None
 if console and console.is_private:
  near=[a for a in ([source] if source else addresses) if console in ipaddress.IPv4Network(a+'/24',strict=False)]
  if near:items.append(item(OK,f'This PC ({near[0]}) and the PS5 are on the same network'))
  else:items.append(item(WARN,f'This PC ({source or ", ".join(addresses)}) and the PS5 ({host}) look like different networks',
   'At home, connect both to the same router. Away from home this is expected.'))
 if link and link['kind']=='wifi':
  items.append(item(WARN,f'This PC reaches the PS5 over Wi-Fi'+(f' at {speed_text(link["speed"])}' if link['speed'] else ''),
   '4K at 80 Mbps can stutter over Wi-Fi. A cable, or a 1080p or 1440p profile, holds steadier.'))
 elif link and link['kind']=='cable':
  slow=link['speed'] and link['speed']<SLOW_LINK
  items.append(item(WARN if slow else OK,f'This PC reaches the PS5 by cable'+(f' at {speed_text(link["speed"])}' if link['speed'] else ''),
   'The 4K profile peaks near 80 Mbps, close to what this link carries. A gigabit port or cable gives it room.' if slow else ''))
 return items

def console_items(host,ask=console_discovery.ask,broadcast=console_discovery.broadcast,probe=console_discovery.manager_probe):
 try:ipaddress.IPv4Address(host)
 except ValueError:return [item(FAIL,'No PS5 address yet','Select Find console, or type the PS5\'s IP address under Your console.')]
 answer=ask(host)
 if not answer:
  others=[ip for ip in broadcast() if ip!=host]
  if others:return [item(FAIL,f'No PS5 answered at {host}',f'A PS5 answered at {others[0]}. Select Find console to use it.')]
  return [item(FAIL,f'No PS5 answered at {host}','Check that the PS5 is on and on the same network as this PC, and that the address is right. A PS5 that is fully off does not answer.')]
 name=answer.get('name') or 'PS5'
 items=[item(WARN,f'{name} is in rest mode','Wake it with its controller. PlayBridge can also wait for it when you connect.') if answer.get('resting')
  else item(OK,f'{name} answered at {host}')]
 firmware=console_discovery.firmware_name(answer.get('firmware',''))
 if firmware:
  items.append(item(OK,f'Firmware {firmware}, which PlayBridge supports') if console_discovery.supported(answer)
   else item(FAIL,f'Firmware {firmware}','PlayBridge\'s payload is made for firmware 13.60 and does not run on this one.'))
 if not answer.get('resting'):
  items.append(item(OK,'Payload Manager answers on the PS5') if probe(host)
   else item(NOTE,'Payload Manager\'s page did not answer','Fine if you load ELFs another way. Otherwise open Payload Manager on the PS5 before connecting: PlayBridge sends its payload to the ELF loader on port 9021.'))
 return items

def pc_items(card,payload_present,free_bytes,output_name):
 best=graphics_card.largest(card) if card else 0
 items=[item(OK if best==6 else WARN,graphics_card.summary(card))]
 items.append(item(OK,'PlayBridge.elf is in place') if payload_present
  else item(FAIL,'PlayBridge.elf is missing','Download the complete PlayBridge package again: the EXE alone carries it, a copy from source needs the payload folder built.'))
 if free_bytes is not None:
  items.append(item(WARN if free_bytes<LOW_SPACE else OK,f'{free_bytes/1024**3:.0f} GB free for recordings and replays',
   'Choose a capture folder on a drive with more room in Settings › Captures.' if free_bytes<LOW_SPACE else ''))
 items.append(item(OK,f'Sound plays on {output_name}') if output_name else item(WARN,'No sound output found','Plug in headphones or speakers, or choose an output in Windows.'))
 return items

def free_space(folder):
 try:return shutil.disk_usage(folder).free
 except OSError:return None

def run(host,card,payload_present,capture_folder,output_name,addresses=None,link=None,source=None,console=console_items):
 """Every check, console first. Slow parts (the PS5's answer, about a second) belong off the window's thread."""
 addresses=console_discovery.local_addresses() if addresses is None else addresses
 try:valid=bool(ipaddress.IPv4Address(host))
 except ValueError:valid=False
 if valid:
  link=link_of(host) if link is None else link;source=source_address(host) if source is None else source
 return console(host)+network_items(host,addresses,link,source)+pc_items(card,payload_present,free_space(capture_folder),output_name)

def headline(items):
 """One line over the list: all good, or how many things to look at."""
 bad=sum(entry['state'] in (WARN,FAIL) for entry in items)
 if not items:return ''
 if not bad:return 'Everything is ready to play.'
 return f'{bad} thing{"s" if bad>1 else ""} to look at.'
