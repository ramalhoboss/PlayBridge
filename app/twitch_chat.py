"""Twitch chat, read only and with no account: PlayBridge joins a channel's chat as an anonymous viewer, which Twitch allows for reading,
and keeps its newest messages for the overlay, over the game on this PC and in the live stream. What the channel's moderators remove
goes here too: a deleted message, the messages of someone timed out or banned, and a cleared chat."""
import collections,random,re,socket,ssl,threading,time

HOST='irc.chat.twitch.tv';PORT=6697
# Messages kept, and the seconds between tries after a lost connection, longest last.
KEEP=80;AGAIN=(2,4,8,16,30)
# Twitch sends a PING about every five minutes; a connection silent for longer than this is taken as lost.
SILENT=360
LOGIN=re.compile(r'^[a-z0-9_]{3,25}$')
TAG_ESCAPES={'\\s':' ','\\:':';','\\\\':'\\','\\r':'\r','\\n':'\n'}

def channel_name(text):
 """The channel's login from what was typed: a name, @name, #name or the channel's address. '' when it cannot be a Twitch login."""
 text=(text or '').strip().lower()
 text=re.sub(r'^(https?://)?(www\.|m\.)?twitch\.tv/','',text).split('/')[0].split('?')[0].lstrip('@#')
 return text if LOGIN.match(text) else ''

def unescape(value):return re.sub(r'\\[s:\\rn]',lambda match:TAG_ESCAPES[match.group(0)],value)

def parse(line):
 """One line from the chat: (tags, nick, command, parameters, text)."""
 tags={};nick=''
 if line.startswith('@'):
  head,_,line=line.partition(' ')
  for part in head[1:].split(';'):
   key,_,value=part.partition('=');tags[key]=unescape(value)
 if line.startswith(':'):
  prefix,_,line=line.partition(' ');nick=prefix[1:].split('!')[0]
 line,_,text=line.partition(' :');parts=line.split()
 return tags,nick,(parts[0] if parts else ''),parts[1:],text

def badges(value):
 """The badges that show beside a name, highest first."""
 names=[part.split('/')[0] for part in (value or '').split(',') if part]
 return [name for name in ('broadcaster','moderator','vip','subscriber') if name in names]

class Chat:
 """Follows the chat of channel() on a thread of its own. connector(host, port): opens the connection, for the tests."""
 def __init__(self,channel,connector=None,clock=time.time):
  self.channel=channel;self.connector=connector or self.connect_tls;self.clock=clock
  self.messages=collections.deque(maxlen=KEEP);self.lock=threading.Lock();self.version=0;self.state='';self.joined=''
  self.stopping=threading.Event();self.wake=threading.Event();self.sock=None
  self.thread=threading.Thread(target=self.run,name='Twitch chat',daemon=True);self.thread.start()
 @staticmethod
 def connect_tls(host,port):
  raw=socket.create_connection((host,port),timeout=10)
  try:return ssl.create_default_context().wrap_socket(raw,server_hostname=host)
  except Exception:raw.close();raise
 def stop(self):self.stopping.set();self.wake.set();self.drop()
 def poke(self):self.wake.set()
 def drop(self):
  sock,self.sock=self.sock,None
  if sock is not None:
   try:sock.close()
   except OSError:pass
 def changed(self):self.version+=1
 def clear(self,test=lambda message:True):
  with self.lock:
   kept=[message for message in self.messages if not test(message)]
   if len(kept)!=len(self.messages):self.messages.clear();self.messages.extend(kept);self.changed()
 def run(self):
  failures=0
  while not self.stopping.is_set():
   name=channel_name(self.channel() or '')
   if not name:
    if self.joined or self.messages:self.joined='';self.clear()
    self.state='';self.wake.wait(2);self.wake.clear();continue
   if name!=self.joined:self.clear()
   self.state=f'Connecting to #{name}…'
   try:
    self.follow(name);failures=0
   except (OSError,ValueError) as error:
    if self.stopping.is_set():break
    self.state=f'Twitch chat lost ({type(error).__name__}). Trying again…';failures+=1
   self.drop()
   if self.stopping.is_set():break
   if channel_name(self.channel() or '')==name:self.wake.wait(AGAIN[min(failures,len(AGAIN)-1)]);self.wake.clear()
 def follow(self,name):
  """Joins name's chat and reads it until the channel changes, PlayBridge closes or the connection goes."""
  sock=self.connector(HOST,PORT);self.sock=sock;sock.settimeout(1.0)
  nick=f'justinfan{random.randint(10000,99999)}'
  sock.sendall(f'CAP REQ :twitch.tv/tags twitch.tv/commands\r\nPASS SCHMOOPIIE\r\nNICK {nick}\r\nJOIN #{name}\r\n'.encode())
  buffer=b'';heard=time.monotonic()
  while not self.stopping.is_set():
   if channel_name(self.channel() or '')!=name:return
   try:data=sock.recv(65536)
   except socket.timeout:
    if time.monotonic()-heard>SILENT:raise TimeoutError('no answer')
    continue
   if not data:raise ConnectionError('closed')
   heard=time.monotonic();buffer+=data
   if len(buffer)>1<<20:raise ValueError('line too long')
   while b'\r\n' in buffer:
    line,buffer=buffer.split(b'\r\n',1)
    self.take(sock,name,line.decode('utf8','replace'))
 def take(self,sock,name,line):
  tags,nick,command,parameters,text=parse(line)
  if command=='PING':sock.sendall(f'PONG :{text or "tmi.twitch.tv"}\r\n'.encode());return
  if command=='RECONNECT':raise ConnectionError('Twitch asked for a new connection')
  if command in ('ROOMSTATE','366') and not self.joined==name:
   self.joined=name;self.state=f'Reading #{name}. New messages appear as they are written.';self.changed();return
  if command=='NOTICE' and text:
   if tags.get('msg-id','').startswith('msg_channel_suspended'):self.state=f'Twitch says #{name} is suspended or does not exist.'
   elif 'Login' in text or 'authentication' in text.lower():raise ConnectionError(text)
   return
  if command=='PRIVMSG' and text:
   action=text.startswith('\x01ACTION ') and text.endswith('\x01')
   self.add(dict(id=tags.get('id',''),user=tags.get('user-id','') or nick,name=tags.get('display-name') or nick,colour=tags.get('color',''),
    text=text[8:-1] if action else text,badges=badges(tags.get('badges')),kind='action' if action else 'message',at=self.clock()))
   return
  if command=='USERNOTICE':
   # Subscriptions, gifts, raids and the like: Twitch's own sentence for it, and what the viewer wrote with it, if anything.
   said=tags.get('system-msg','').strip()
   if said:self.add(dict(id=tags.get('id',''),user=tags.get('user-id',''),name=tags.get('display-name') or nick,colour=tags.get('color',''),text=said+(f' “{text}”' if text else ''),badges=[],kind='event',at=self.clock()))
   return
  if command=='CLEARMSG':
   gone=tags.get('target-msg-id','');self.clear(lambda message:message['id']==gone and bool(gone));return
  if command=='CLEARCHAT':
   user=tags.get('target-user-id','')
   if text or user:self.clear(lambda message:(user and message['user']==user) or message['name'].lower()==text.lower())
   else:self.clear()
 def add(self,message):
  with self.lock:self.messages.append(message);self.changed()
 def view(self,now=None,seconds=None,most=12):
  """The newest messages, oldest first, at most most of them, and with seconds only those written within that many seconds."""
  now=self.clock() if now is None else now
  with self.lock:shown=[message for message in self.messages if seconds is None or now-message['at']<=seconds]
  return shown[-most:]
 def text(self):
  """How it stands, for Settings."""
  if not self.state:return ''
  if self.joined and self.state.startswith('Reading'):
   with self.lock:count=len(self.messages)
   return self.state+(f' {count} message'+('s' if count!=1 else '')+' so far.' if count else '')
  return self.state
