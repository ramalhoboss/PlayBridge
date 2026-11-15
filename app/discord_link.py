"""Discord, two ways, neither of which signs in to anything.
Your profile shows the game you are playing on your PS5 (Rich Presence): PlayBridge tells the Discord app already running on this PC,
through the local pipe Discord opens for that. It needs the ID of a Discord application, which anyone can create for free; its name is
what your profile says you are playing.
A channel of yours receives your screenshots, trophy clips and replays: a webhook, a link Discord makes in a channel's settings that can
only post there. A clip is made again small enough for Discord (H.264 at 720p or less, under 10 MB) before it goes; the file on this PC
stays as it was. While a stream plays, that work goes no faster than the clip itself plays, so it never takes the picture's turn."""
import json,os,queue,re,struct,threading,time,urllib.error,urllib.parse,urllib.request,uuid
from fractions import Fraction
from pathlib import Path

PIPES=tuple(rf'\\.\pipe\discord-ipc-{number}' for number in range(10))
HANDSHAKE,FRAME,CLOSE,PING,PONG=0,1,2,3,4
# Seconds between tries while Discord is not running, and the most a frame from Discord can hold.
AGAIN=15.0;FRAME_MOST=1<<20
APP_ID=re.compile(r'^\d{17,21}$')
REPOSITORY_PAGE='https://github.com/ramalhoboss/PlayBridge'
WEBHOOK_HOSTS=('discord.com','discordapp.com','canary.discord.com','ptb.discord.com')
# Discord takes files up to 10 MB on a server without boosts; a share copy aims a little under it.
UPLOAD_MOST=10*1024*1024;BUDGET=9_400_000;LONGEST=95.0
KINDS=('Screenshot','Trophy clip','Replay','Recording')
AGENT='PlayBridge'

def webhook_problem(url):
 """Why this is not a Discord webhook, in words, or '' when it is one."""
 url=(url or '').strip()
 if not url:return ''
 parts=urllib.parse.urlsplit(url)
 if parts.scheme!='https' or parts.hostname not in WEBHOOK_HOSTS or not re.match(r'^/api/(v\d+/)?webhooks/\d+/[\w-]+/?$',parts.path):
  return 'Paste the webhook URL Discord gave, which starts with https://discord.com/api/webhooks/.'
 return ''

def activity(game,started,live_on='',buttons=True):
 """What your profile shows while a game runs on your PS5. live_on: the service you are live on, if any."""
 shown={'details':game[:128],'state':(f'Live on {live_on}' if live_on else 'Playing on PS5')[:128],'timestamps':{'start':int(started)},
  'assets':{'large_image':'playbridge','large_text':'Streamed with PlayBridge'},'instance':False}
 if buttons:shown['buttons']=[{'label':'PlayBridge','url':REPOSITORY_PAGE}]
 return shown

def pack(opcode,data):
 body=json.dumps(data,separators=(',',':')).encode();return struct.pack('<II',opcode,len(body))+body

class Presence:
 """Keeps your Discord profile showing what show() last asked, on a thread of its own: it connects to the Discord app when there is one,
 tries again every AGAIN seconds while there is not, and sends only what changed. app_id(): the application's ID, or '' for off.
 opener(path): opens one of Discord's pipes, for the tests."""
 def __init__(self,app_id,opener=None,clock=time.monotonic):
  self.app_id=app_id;self.opener=opener or (lambda path:open(path,'r+b',buffering=0));self.clock=clock
  self.wanted=None;self.sent=object();self.pipe=None;self.connected_id='';self.state='';self.user='';self.wake=threading.Event();self.stopping=threading.Event();self.lock=threading.Lock()
  self.thread=threading.Thread(target=self.run,name='Discord presence',daemon=True);self.thread.start()
 def show(self,shown):
  """shown: activity(...), or None to show nothing."""
  with self.lock:
   if shown==self.wanted:return
   self.wanted=shown
  self.wake.set()
 def poke(self):self.wake.set()
 def stop(self):self.stopping.set();self.wake.set();self.drop()
 def run(self):
  next_try=0.0
  while not self.stopping.is_set():
   app_id=(self.app_id() or '').strip()
   if not APP_ID.match(app_id):
    self.drop();self.state='' if not app_id else 'That application ID is not a number Discord gives.';self.wake.wait(2);self.wake.clear();continue
   if self.pipe is not None and app_id!=self.connected_id:self.drop()
   if self.pipe is None and self.clock()>=next_try:
    if not self.connect(app_id):next_try=self.clock()+AGAIN
   if self.pipe is not None:
    with self.lock:wanted=self.wanted
    if wanted!=self.sent:
     try:self.command('SET_ACTIVITY',{'pid':os.getpid(),'activity':wanted});self.sent=wanted
     except (OSError,ValueError,EOFError) as error:self.state=f'Discord stopped answering ({type(error).__name__}).';self.drop()
   self.wake.wait(2);self.wake.clear()
  self.drop()
 def connect(self,app_id):
  for path in PIPES:
   try:pipe=self.opener(path)
   except OSError:continue
   try:
    pipe.write(pack(HANDSHAKE,{'v':1,'client_id':app_id}));opcode,answer=self.read(pipe)
    if opcode==CLOSE or answer.get('evt')!='READY':
     pipe.close();self.state=f"Discord refused the application ID: {answer.get('message') or answer.get('code') or 'no reason given'}.";return False
    self.pipe=pipe;self.connected_id=app_id;self.sent=object();self.user=((answer.get('data') or {}).get('user') or {}).get('username','')
    self.state='Connected to Discord'+(f' as {self.user}' if self.user else '')+'.';return True
   except (OSError,ValueError,EOFError):
    try:pipe.close()
    except OSError:pass
  self.state='Discord is not open on this PC.';return False
 def read(self,pipe):
  head=self.exact(pipe,8);opcode,length=struct.unpack('<II',head)
  if length>FRAME_MOST:raise ValueError('frame too large')
  return opcode,json.loads(self.exact(pipe,length) or b'{}')
 @staticmethod
 def exact(pipe,size):
  data=b''
  while len(data)<size:
   part=pipe.read(size-len(data))
   if not part:raise EOFError('Discord closed the pipe')
   data+=part
  return data
 def command(self,name,args):
  """Sends a command and reads Discord's answer to it, answering its pings on the way."""
  nonce=uuid.uuid4().hex;self.pipe.write(pack(FRAME,{'cmd':name,'args':args,'nonce':nonce}))
  while True:
   opcode,answer=self.read(self.pipe)
   if opcode==PING:self.pipe.write(pack(PONG,answer));continue
   if opcode==CLOSE:raise EOFError(answer.get('message','closed'))
   if answer.get('nonce')==nonce:
    if answer.get('evt')=='ERROR':raise ValueError((answer.get('data') or {}).get('message','error'))
    return answer
 def drop(self):
  pipe,self.pipe=self.pipe,None
  if pipe is not None:
   try:pipe.close()
   except OSError:pass
 def text(self,shown_game=''):
  """How it stands, for Settings."""
  if not self.state:return ''
  if self.pipe is not None and shown_game:return f'Your Discord profile shows {shown_game}.'
  return self.state

def multipart(fields,files):
 """A multipart/form-data body: fields as (name, text), files as (name, filename, content type, bytes). Returns (body, content type)."""
 boundary=uuid.uuid4().hex;lines=[]
 for name,text in fields:
  lines.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\nContent-Type: application/json\r\n\r\n'.encode()+text.encode()+b'\r\n')
 for name,filename,kind,data in files:
  safe=re.sub(r'[^\w.\- ]','_',filename)
  lines.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{safe}"\r\nContent-Type: {kind}\r\n\r\n'.encode()+data+b'\r\n')
 lines.append(f'--{boundary}--\r\n'.encode());return b''.join(lines),f'multipart/form-data; boundary={boundary}'

def post(url,content,attachment=None,opener=urllib.request.urlopen,timeout=60):
 """Posts a message, with a file when attachment is (filename, content type, bytes). Returns '' or what went wrong. Waits once when
 Discord asks for a pause."""
 payload=json.dumps({'content':content[:2000],'username':'PlayBridge','allowed_mentions':{'parse':[]}})
 body,kind=multipart([('payload_json',payload)],[('files[0]',*attachment)] if attachment else [])
 target=url.split('?')[0].rstrip('/')+'?wait=true'
 for attempt in (0,1):
  request=urllib.request.Request(target,data=body,method='POST',headers={'Content-Type':kind,'User-Agent':AGENT})
  try:
   with opener(request,timeout=timeout) as answer:answer.read();return ''
  except urllib.error.HTTPError as error:
   if error.code==429 and attempt==0:
    try:pause=float(json.loads(error.read() or b'{}').get('retry_after',2))
    except (ValueError,TypeError):pause=2.0
    time.sleep(min(30.0,max(.5,pause)));continue
   if error.code in (401,404):return 'Discord says this webhook no longer exists. Make a new one and paste it again.'
   if error.code==413:return 'Discord refused the file as too large.'
   return f'Discord answered {error.code}.'
  except (OSError,ValueError) as error:return f'Could not reach Discord ({type(error).__name__}).'
 return 'Discord is busy. Try again in a minute.'

def message_for(kind,path,game=''):
 """The words that go with a capture: what it is and the game, with the trophy's name for a trophy clip."""
 game=f'**{game}**' if game else 'my PS5'
 if kind=='Trophy clip':
  name=re.sub(r'^PlayBridge-Trophy-(.*?)-?\d{8}-\d{6}-\d+$',r'\1',Path(path).stem).strip(' -')
  return f'🏆 Trophy earned in {game}'+(f': **{name}**' if name and not name.startswith('PlayBridge') else '')
 return {'Screenshot':f'📸 Screenshot from {game}','Replay':f'🎬 Replay from {game}','Recording':f'🎥 Recording from {game}'}.get(kind,f'From {game}')

def duration(container,stream):
 if stream.duration is not None and stream.time_base:return float(stream.duration*stream.time_base)
 return container.duration/1_000_000 if container.duration else 0.0

def share_copy(source,target,encoders,budget=BUDGET,busy=lambda:False,stopping=lambda:False):
 """Makes the clip again small enough to post: H.264 at 720p (540p for a long one), 60 or 30 frames a second as the room allows,
 and AAC sound. Returns '' or what went wrong. While busy() it goes no faster than the clip plays."""
 import av
 with av.open(str(source)) as inside:
  if not inside.streams.video:return 'it has no video'
  video=inside.streams.video[0];audio=inside.streams.audio[0] if inside.streams.audio else None;video.thread_type='AUTO'
  total=duration(inside,video)
  if total<=0:return 'its length is unknown'
  if total>LONGEST:return f'it is longer than {LONGEST:.0f} seconds'
  bits=int(budget*8*.94/total)-(96_000 if audio is not None else 0)
  if bits<500_000:return 'it is too long to fit'
  rate=60 if bits>=3_200_000 else 30;height=720 if bits>=1_200_000 else 540
  source_height=video.codec_context.height or 1080;source_width=video.codec_context.width or 1920;height=min(height,source_height)
  width=max(2,round(source_width*height/source_height/2)*2)
  problem='no H.264 encoder works on this PC'
  for encoder in encoders:
   try:
    made_video=made_audio=None
    with av.open(str(target),'w',format='mp4',options={'movflags':'+faststart'}) as out:
     made_video=out.add_stream(encoder,rate=rate);made_video.width=width;made_video.height=height;made_video.pix_fmt='nv12' if encoder.endswith('_qsv') else 'yuv420p'
     made_video.bit_rate=bits;made_video.time_base=Fraction(1,rate);made_video.codec_context.time_base=Fraction(1,rate)
     made_video.options={'preset':'veryfast','maxrate':str(int(bits*1.15)),'bufsize':str(bits*2)} if encoder=='libx264' else {'rc':'cbr'} if encoder.endswith(('_amf','_nvenc')) else {}
     if audio is not None:made_audio=out.add_stream('aac',rate=48000);made_audio.bit_rate=96_000;made_audio.layout='stereo'
     count=0;step=1/rate;last=-1;began=time.monotonic();first=None
     resampler=av.AudioResampler(format='fltp',layout='stereo',rate=48000) if audio is not None else None
     for packet in inside.demux(*(stream for stream in (video,audio) if stream is not None)):
      if stopping():return 'PlayBridge closed first'
      for frame in packet.decode():
       if packet.stream is audio:
        for part in resampler.resample(frame):part.pts=None;out.mux(made_audio.encode(part))
        continue
       moment=float(frame.pts*frame.time_base) if frame.pts is not None and frame.time_base else count*step
       if first is None:first=moment
       moment-=first
       # Each frame goes to its place at the new rate; a frame whose place already has one is left out, so 60 becomes 30 evenly.
       place=round(moment/step)
       if place<=last:continue
       last=place;count+=1
       picture=frame.reformat(width=width,height=height,format=made_video.pix_fmt,interpolation='AREA');picture.pts=place;picture.time_base=Fraction(1,rate)
       out.mux(made_video.encode(picture))
       # While the stream plays, no faster than real time.
       if busy():
        ahead=moment-(time.monotonic()-began)
        if ahead>0:time.sleep(min(.5,ahead))
     out.mux(made_video.encode(None))
     if made_audio is not None:
      for part in resampler.resample(None) if resampler is not None else []:part.pts=None;out.mux(made_audio.encode(part))
      out.mux(made_audio.encode(None))
    if os.path.getsize(target)>UPLOAD_MOST:
     if budget>BUDGET*.6:return share_copy(source,target,[encoder],int(budget*.72),busy,stopping)
     return 'it came out larger than Discord takes'
    return ''
   except Exception as error:
    problem=f'{encoder} failed ({type(error).__name__})'
    try:os.remove(target)
    except OSError:pass
  return problem

class Webhook:
 """Posts captures to your channel, one at a time, on a thread of its own. url(): the webhook; wanted(kind): whether that kind goes;
 game(): the game for the words; notify(text): tells the window; busy(): a stream plays; encoders(): H.264 encoders to try."""
 def __init__(self,url,wanted,game,notify,folder,busy=lambda:False,encoders=lambda:['libx264'],opener=urllib.request.urlopen):
  self.url=url;self.wanted=wanted;self.game=game;self.notify=notify;self.folder=Path(folder);self.busy=busy;self.encoders=encoders;self.opener=opener
  self.jobs=queue.Queue();self.stopping=threading.Event();self.status='';self.sent=0;self.current=None
  self.thread=threading.Thread(target=self.run,name='Discord webhook',daemon=True);self.thread.start()
 def working(self):
  """A capture still waits or is being sent, so nothing should replace its file meanwhile."""
  return self.current is not None or self.jobs.qsize()>0
 def share(self,kind,path):
  """A capture was saved. It goes when a webhook is set and that kind is chosen."""
  url=(self.url() or '').strip()
  if url and not webhook_problem(url) and kind in KINDS and self.wanted(kind):self.jobs.put((kind,str(path),self.game() or ''))
 def test(self):
  url=(self.url() or '').strip();problem=webhook_problem(url) or ('' if url else 'Paste a webhook URL first.')
  if problem:self.status=problem;return problem
  self.jobs.put(('Test','',''));return ''
 def stop(self):self.stopping.set();self.jobs.put(None)
 def run(self):
  while not self.stopping.is_set():
   job=self.jobs.get()
   if job is None:return
   kind,path,game=job;url=(self.url() or '').strip()
   if not url or webhook_problem(url):continue
   self.current=job
   try:self.status=self.send(url,kind,path,game)
   except Exception as error:self.status=f'Could not send it ({type(error).__name__}).'
   finally:self.current=None
   if self.status:self.notify('Discord: '+self.status)
 def send(self,url,kind,path,game):
  if kind=='Test':
   problem=post(url,'✅ PlayBridge is connected. Your screenshots and clips will appear here.',opener=self.opener)
   return problem or 'Test message sent.'
  source=Path(path);words=message_for(kind,path,game)
  if not source.is_file():return ''
  if kind=='Screenshot':
   data=source.read_bytes();name=source.name;content='image/png'
   if len(data)>UPLOAD_MOST:
    from PIL import Image
    import io
    with Image.open(source) as picture:
     picture=picture.convert('RGB');buffer=io.BytesIO();picture.save(buffer,'JPEG',quality=88);data=buffer.getvalue();name=source.with_suffix('.jpg').name;content='image/jpeg'
   problem=post(url,words,(name,content,data),opener=self.opener)
  else:
   self.folder.mkdir(parents=True,exist_ok=True);small=self.folder/(source.stem+'-discord.mp4')
   problem=share_copy(source,small,self.encoders(),busy=self.busy,stopping=self.stopping.is_set)
   if problem:
    post(url,words+f'\n(Not attached: {problem}.)',opener=self.opener);return f'{kind} not attached: {problem}.'
   try:problem=post(url,words,(source.stem+'.mp4','video/mp4',small.read_bytes()),opener=self.opener)
   finally:
    try:small.unlink()
    except OSError:pass
  if problem:return problem
  self.sent+=1;return f'{kind} sent to your channel.'
