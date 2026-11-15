"""A small FTP server over a folder on this PC, standing in for the one a homebrew payload runs on the PS5, for the tests and trials.
It speaks just what PlayBridge uses: login, PWD, CWD, PASV, LIST (Unix form), MLSD (when asked to), RETR, STOR, MKD, RMD, DELE, RNFR/RNTO."""
import os,socket,socketserver,threading,time
from pathlib import Path

class Standin:
 def __init__(self,root,mlsd=True,port=0):
  self.root=Path(root);self.mlsd=mlsd;self.commands=[]
  outer=self
  class Handler(socketserver.StreamRequestHandler):
   def handle(self):
    try:outer.serve(self)
    except OSError:pass
  self.server=socketserver.ThreadingTCPServer(('127.0.0.1',port),Handler);self.server.daemon_threads=True
  self.port=self.server.server_address[1];threading.Thread(target=self.server.serve_forever,daemon=True).start()
 def stop(self):self.server.shutdown();self.server.server_close()
 def local(self,cwd,path):
  """A path on the stand-in, kept inside its folder."""
  joined=os.path.normpath(os.path.join(cwd,path or '.')).replace('\\','/')
  joined='/'+joined.lstrip('/') if joined not in ('.','') else '/'
  if joined.startswith('/..'):joined='/'
  return joined,self.root.joinpath(*[part for part in joined.split('/') if part])
 def serve(self,handler):
  out=handler.wfile;cwd='/';passive=None;rename=None
  def say(text):out.write((text+'\r\n').encode('utf-8'));out.flush()
  def data():
   connection,_=passive.accept();return connection
  say('220 Stand-in FTP ready')
  while True:
   line=handler.rfile.readline()
   if not line:break
   line=line.decode('utf-8').rstrip('\r\n');verb,_,rest=line.partition(' ');verb=verb.upper();self.commands.append(line)
   try:
    if verb=='USER':say('331 Any password')
    elif verb=='PASS':say('230 Welcome')
    elif verb in ('TYPE','NOOP'):say('200 OK')
    elif verb=='SYST':say('215 UNIX Type: L8')
    elif verb=='OPTS':say('200 OK' if self.mlsd else '500 No')
    elif verb=='PWD':say(f'257 "{cwd}"')
    elif verb=='CWD':
     path,place=self.local(cwd,rest)
     if place.is_dir():cwd=path;say('250 OK')
     else:say('550 No such folder')
    elif verb=='PASV':
     if passive:passive.close()
     passive=socket.socket();passive.bind(('127.0.0.1',0));passive.listen(1);port=passive.getsockname()[1]
     say(f'227 Entering Passive Mode (127,0,0,1,{port>>8},{port&255})')
    elif verb in ('LIST','MLSD'):
     if verb=='MLSD' and not self.mlsd:say('500 Unknown command');continue
     _,place=self.local(cwd,rest if rest and not rest.startswith('-') else '.')
     say('150 Here it comes');connection=data();lines=[]
     for item in sorted(place.iterdir()):
      info=item.stat();folder=item.is_dir()
      if verb=='MLSD':lines.append(f"type={'dir' if folder else 'file'};size={0 if folder else info.st_size};modify={time.strftime('%Y%m%d%H%M%S',time.gmtime(info.st_mtime))}; {item.name}")
      else:lines.append(f"{'d' if folder else '-'}rwxr-xr-x 1 root root {0 if folder else info.st_size} {time.strftime('%b %d %H:%M',time.localtime(info.st_mtime))} {item.name}")
     connection.sendall(('\r\n'.join(['type=cdir; .'] if verb=='MLSD' else ['total 1'])+'\r\n'+'\r\n'.join(lines)+('\r\n' if lines else '')).encode('utf-8'));connection.close();say('226 Done')
    elif verb=='RETR':
     _,place=self.local(cwd,rest)
     if not place.is_file():say('550 No such file');continue
     say('150 Sending');connection=data();connection.sendall(place.read_bytes());connection.close();say('226 Done')
    elif verb=='STOR':
     _,place=self.local(cwd,rest);say('150 Ready');connection=data();chunks=[]
     while True:
      chunk=connection.recv(65536)
      if not chunk:break
      chunks.append(chunk)
     connection.close();place.write_bytes(b''.join(chunks));say('226 Stored')
    elif verb=='MKD':_,place=self.local(cwd,rest);place.mkdir();say('257 Made')
    elif verb=='RMD':
     _,place=self.local(cwd,rest)
     if any(place.iterdir()):say('550 Folder not empty')
     else:place.rmdir();say('250 Removed')
    elif verb=='DELE':_,place=self.local(cwd,rest);place.unlink();say('250 Deleted')
    elif verb=='RNFR':rename=self.local(cwd,rest)[1];say('350 Go on')
    elif verb=='RNTO':rename.rename(self.local(cwd,rest)[1]);rename=None;say('250 Renamed')
    elif verb=='QUIT':say('221 Bye');break
    else:say('502 Not here')
   except OSError as error:say(f'550 {error.strerror or error}')
  if passive:passive.close()
