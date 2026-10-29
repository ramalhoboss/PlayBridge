"""Bounded packet-copy recording; console H.264/AAC is not re-encoded."""
import io,queue,re,threading,time
from fractions import Fraction
from pathlib import Path
import av

START_CODES=re.compile(b'\x00\x00\x00?\x01')
def nal_units(data):
 marks=list(START_CODES.finditer(data))
 return [data[m.end():marks[i+1].start() if i+1<len(marks) else len(data)] for i,m in enumerate(marks) if m.end()<(marks[i+1].start() if i+1<len(marks) else len(data))]
def is_idr(data):return any(n and n[0]&31==5 for n in nal_units(data))
def codec_headers(data):return b''.join(b'\x00\x00\x00\x01'+n for n in nal_units(data) if n and n[0]&31 in (7,8))
def strip_adts(data):
 if len(data)<7 or data[0]!=255 or data[1]&0xf6!=0xf0:raise ValueError('Invalid AAC ADTS packet')
 header=7 if data[1]&1 else 9
 size=((data[3]&3)<<11)|(data[4]<<3)|(data[5]>>5)
 if size!=len(data) or len(data)<=header:raise ValueError('Invalid AAC packet length')
 # AudioSpecificConfig follows the source ADTS profile, sample rate and layout.
 obj=((data[2]>>6)&3)+1;freq=(data[2]>>2)&15;channels=((data[2]&1)<<2)|(data[3]>>6)
 asc=bytes([(obj<<3)|(freq>>1),((freq&1)<<7)|(channels<<3)])
 return data[header:],asc

class CaptureRecorder:
 def __init__(self):
  self.lock=threading.Lock();self.events=queue.SimpleQueue();self.thread=None;self.state='idle';self.path=None;self.headers=b'';self.error='';self.max_queue=240;self.max_bytes=32*1024*1024;self.queued_bytes=0
 @property
 def active(self):return self.thread is not None and self.thread.is_alive()
 def reset_session(self):
  self.stop(wait=True)
  with self.lock:self.headers=b''
 def start(self,path):
  with self.lock:
   if self.active:return False
   self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
   if self.path.exists():raise FileExistsError('Recording file already exists')
   self.queued_bytes=0;self.queue=queue.Queue(self.max_queue);self.ending=threading.Event();self.error='';self.state='waiting'
   self.thread=threading.Thread(target=self._run,name='PlayBridge recorder',daemon=True);self.thread.start()
   return True
 def feed(self,kind,data,pts,dts):
  headers=codec_headers(data) if kind==1 else b''
  with self.lock:
   if headers:self.headers=headers
   if not self.active or self.ending.is_set():return
   try:
    if self.queued_bytes+len(data)>self.max_bytes:raise queue.Full
    self.queue.put_nowait((kind,data,pts,dts,self.headers));self.queued_bytes+=len(data)
   except queue.Full:
    self.error='Recording stopped: the disk could not keep up.';self.state='saving';self.ending.set()
 def stop(self,wait=False):
  with self.lock:
   thread=self.thread
   if thread is None or not thread.is_alive():return
   self.state='saving';self.ending.set()
  if wait and thread is not threading.current_thread():thread.join(timeout=10)
 def _run(self):
  out=None;templates=[];started=False;base=None;pending=[];video_first=None;audio_first=None;vs=aus=None;written=0
  temporary=self.path.with_name(self.path.stem+'.partial.mp4')
  try:
   while not self.ending.is_set() or not self.queue.empty():
    try:packet=self.queue.get(timeout=.1)
    except queue.Empty:continue
    kind,data,pts,dts,headers=packet
    with self.lock:self.queued_bytes-=len(data)
    if kind not in (1,2):continue
    if base is None:
     if kind!=1 or not is_idr(data):continue
     base=min(pts,dts);video_first=headers+data if not codec_headers(data) else data
    if pts<base:continue
    pending.append(packet)
    if kind==2 and audio_first is None:audio_first=data
    if out is None:
     if video_first is None or audio_first is None:
      if len(pending)>180:raise RuntimeError('Recording needs both video and audio.')
      continue
     video_template=av.open(io.BytesIO(video_first),format='h264');audio_template=av.open(io.BytesIO(audio_first),format='aac');templates=[video_template,audio_template]
     out=av.open(str(temporary),'w',format='mp4',options={'movflags':'+faststart'})
     vs=out.add_stream_from_template(video_template.streams.video[0]);aus=out.add_stream_from_template(audio_template.streams.audio[0]);aus.codec_context.extradata=strip_adts(audio_first)[1]
     started=True
     if not self.ending.is_set():self.state='recording'
     self.events.put(('status','Recording started',str(self.path)))
    for k,b,p,d,_ in pending:
     if k==2:b=strip_adts(b)[0]
     item=av.Packet(b);item.pts=p-base;item.dts=d-base;item.time_base=Fraction(1,90000);item.stream=vs if k==1 else aus
     if k==1:item.is_keyframe=is_idr(b)
     out.mux(item);written+=1
    pending.clear()
   if out is not None:out.close();out=None
   if started and written:
    temporary.replace(self.path);self.events.put(('saved','Recording saved',str(self.path)))
   else:self.events.put(('status','Recording cancelled: no complete video/audio start received.',''))
   if self.error:self.events.put(('error',self.error,str(self.path) if started else ''))
  except Exception as e:
   self.error='Recording failed: '+str(e);self.events.put(('error',self.error,''))
  finally:
   if out is not None:
    try:out.close()
    except Exception:pass
   for template in templates:template.close()
   if temporary.exists():
    try:temporary.unlink()
    except OSError:pass
   self.state='idle'
