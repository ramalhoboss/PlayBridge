"""Control PlayBridge from a Stream Deck, Touch Portal, a hotkey program or a script, and show what it knows in OBS: a small web server
that only this PC can reach (127.0.0.1). Every address starts with a secret made on this PC, and a request must name this PC as its
host, so neither another device nor a web page in a browser can use it.
Commands only ask: they wait in a queue the window empties on its own thread, exactly as if the button had been pressed there."""
import hmac,http.server,json,queue,secrets,threading,urllib.parse
from pathlib import Path

PORT=9095;TRIES=10
ACTIONS={'screenshot':'Take a screenshot','record':'Start or stop recording','replay':'Save the instant replay','live':'Go live, or end the live stream',
 'mic':'Turn the microphone on or off','timer':'Start the speedrun timer, or mark a split','timer-stop':'Stop the timer, or clear it once stopped'}
HERE=Path(__file__).resolve().parent

def new_secret():return secrets.token_urlsafe(12)

class Server(http.server.ThreadingHTTPServer):
 daemon_threads=True;allow_reuse_address=False

class LocalApi:
 """The server and what it shares with the window: commands asked for, the status to hand out and the newest trophy's picture."""
 def __init__(self,assets=HERE/'assets'):
  self.assets=Path(assets);self.commands=queue.SimpleQueue();self.lock=threading.Lock();self.status={};self.trophy_picture=None
  self.server=None;self.thread=None;self.port=None;self.secret='';self.error=''
 def start(self,secret,port=PORT):
  """Listens on port, or the next free one. Returns the port it listens on, or None with error saying why."""
  self.stop();self.secret=secret;handler=self.handler()
  for candidate in range(port,port+TRIES):
   try:self.server=Server(('127.0.0.1',candidate),handler);break
   except OSError:continue
  else:self.error=f'Ports {port} to {port+TRIES-1} are all in use on this PC.';return None
  self.port=self.server.server_address[1];self.error=''
  self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.5},name='Local control',daemon=True);self.thread.start()
  return self.port
 def stop(self):
  server,self.server=self.server,None
  if server is not None:server.shutdown();server.server_close()
  self.port=None
 @property
 def running(self):return self.server is not None
 def address(self,name=''):return f'http://127.0.0.1:{self.port}/{self.secret}/{name}' if self.port else ''
 def publish(self,status,trophy_picture=None):
  with self.lock:self.status=status;self.trophy_picture=trophy_picture
 def take(self):
  """The commands asked for since the last call, oldest first."""
  out=[]
  while True:
   try:out.append(self.commands.get_nowait())
   except queue.Empty:return out
 def page(self,name):
  try:return (self.assets/name).read_bytes()
  except OSError:return b'<!doctype html><title>PlayBridge</title><p>This page is missing from PlayBridge.'
 def handler(self):
  api=self
  class Handler(http.server.BaseHTTPRequestHandler):
   server_version='PlayBridge';sys_version=''
   def log_message(self,*args):pass
   def send(self,code,body=b'',kind='text/plain; charset=utf-8'):
    self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
    self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Frame-Options','DENY')
    self.end_headers()
    if self.command!='HEAD':self.wfile.write(body)
   def answer(self):
    # Only a request that names this PC: a page elsewhere pointing a name of its own at 127.0.0.1 is refused.
    host=(self.headers.get('Host') or '').lower()
    if host not in (f'127.0.0.1:{api.port}',f'localhost:{api.port}'):return self.send(403,b'Forbidden')
    parts=urllib.parse.urlsplit(self.path).path.split('/')
    if len(parts)<2 or not hmac.compare_digest(parts[1].encode(),api.secret.encode()):return self.send(404,b'Not found')
    name=parts[2] if len(parts)>2 else ''
    if name=='' :return self.send(200,api.page('control.html'),'text/html; charset=utf-8')
    if name=='overlay':return self.send(200,api.page('obs_overlay.html'),'text/html; charset=utf-8')
    if name=='status':
     with api.lock:body=json.dumps(api.status,ensure_ascii=False).encode()
     return self.send(200,body,'application/json; charset=utf-8')
    if name=='trophy.png':
     with api.lock:picture=api.trophy_picture
     return self.send(200,picture,'image/png') if picture else self.send(404,b'Not found')
    if name in ACTIONS:
     if self.command=='HEAD':return self.send(200)
     api.commands.put(name);return self.send(200,json.dumps({'ok':True,'command':name}).encode(),'application/json')
    return self.send(404,b'Not found')
   def do_GET(self):self.answer()
   def do_HEAD(self):self.answer()
   def do_POST(self):
    length=int(self.headers.get('Content-Length') or 0)
    if 0<length<=65536:self.rfile.read(length)
    self.answer()
  return Handler
