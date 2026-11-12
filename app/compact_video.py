"""Makes saved recordings smaller by encoding their video again as AV1 or HEVC, with the sound copied as it is.
It only works while no stream is playing, so it never takes the processor or the graphics card from the picture. The original goes
to the Recycle Bin once the smaller file has been checked, so a bad result can always be undone."""
import ctypes,os,queue,threading,time
from pathlib import Path
import av
import video_encoders

SUFFIX='.compact.partial.mp4'

def recycle(path):
 """Moves a file to the Recycle Bin. False when Windows would not, and the file is then left where it was."""
 if os.name!='nt':return False
 class Operation(ctypes.Structure):
  _fields_=[('hwnd',ctypes.c_void_p),('func',ctypes.c_uint),('source',ctypes.c_wchar_p),('target',ctypes.c_wchar_p),('flags',ctypes.c_ushort),('aborted',ctypes.c_int),('mappings',ctypes.c_void_p),('title',ctypes.c_wchar_p)]
 # FO_DELETE with FOF_ALLOWUNDO, FOF_NOCONFIRMATION, FOF_SILENT and FOF_NOERRORUI. The list ends with two nulls.
 operation=Operation(None,3,str(Path(path).resolve())+'\0',None,0x40|0x10|0x4|0x400,0,None,None)
 try:return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))==0 and not operation.aborted and not Path(path).exists()
 except Exception:return False

def duration(container,stream):
 if stream.duration is not None and stream.time_base:return float(stream.duration*stream.time_base)
 return container.duration/av.time_base if container.duration else 0.0

def compact(source,target,encoder,busy=lambda:False,stopping=lambda:False,progress=lambda share:None):
 """Writes target from source. Returns '' when done, or what went wrong, in words."""
 with av.open(str(source)) as inside:
  if not inside.streams.video:return 'it has no video.'
  video=inside.streams.video[0];audio=inside.streams.audio[0] if inside.streams.audio else None
  video.thread_type='AUTO'
  total=duration(inside,video) or 1.0;source_rate=int(os.path.getsize(source)*8/total)
  with av.open(str(target),'w',format='mp4',options={'movflags':'+faststart'}) as out:
   rate=video.average_rate or 60
   made=out.add_stream(encoder,rate=rate)
   made.width,made.height=video.codec_context.width,video.codec_context.height
   made.pix_fmt=video_encoders.pixel_format(encoder);made.bit_rate=video_encoders.bitrate(encoder,made.height,source_rate)
   made.time_base=video.time_base;made.codec_context.time_base=video.time_base
   made.options=video_encoders.options(encoder)
   copied=out.add_stream_from_template(audio) if audio is not None else None
   last=0.0
   for packet in inside.demux(*(stream for stream in (video,audio) if stream is not None)):
    while busy() and not stopping():time.sleep(.5)
    if stopping():return 'PlayBridge closed first.'
    if packet.stream is audio:
     if packet.dts is None:continue
     packet.stream=copied;out.mux(packet);continue
    for frame in packet.decode():
     if frame.format.name!=made.pix_fmt:frame=frame.reformat(format=made.pix_fmt)
     out.mux(made.encode(frame))
     if frame.pts is not None and frame.time_base:
      done=float(frame.pts*frame.time_base)/total
      if done-last>=.05:last=done;progress(min(done,1.0))
   out.mux(made.encode(None))
 # Checked before the original goes: the new file must open and last as long as the old one.
 with av.open(str(target)) as result:
  if not result.streams.video:return 'the smaller file has no video.'
  made_length=duration(result,result.streams.video[0])
 if abs(made_length-total)>max(1.0,total*.01):return f'the smaller file lasts {made_length:.0f} s instead of {total:.0f} s.'
 return ''

class Compactor:
 """One file at a time, in the order they were saved, on a thread of its own. Files still waiting when the app closes are
 remembered and done the next time it opens. The app saves that list from its own thread, through remembered()."""
 def __init__(self,busy,encoder=None):
  self.busy=busy;self.encoder=encoder;self.events=queue.SimpleQueue();self.lock=threading.Lock();self.waiting=[];self.thread=None;self.ending=threading.Event();self.current=None;self.share=0.0
 def add(self,path):
  with self.lock:
   path=str(path)
   if path in self.waiting or path==self.current or path.endswith(SUFFIX):return
   self.waiting.append(path)
   if self.thread is None or not self.thread.is_alive():
    self.thread=threading.Thread(target=self._run,name='PlayBridge compact',daemon=True);self.thread.start()
 def resume(self,paths):
  for path in paths or []:
   if isinstance(path,str) and Path(path).exists():self.add(path)
 def stop(self):self.ending.set()
 def remembered(self):
  """The files not done yet, the one in hand first."""
  with self.lock:return ([self.current] if self.current else [])+list(self.waiting)
 def status(self):
  """What the Captures page shows, or '' when nothing is happening."""
  with self.lock:
   if not self.current:return ''
   name=Path(self.current).name;left=len(self.waiting)
  more=f' · {left} more waiting' if left else ''
  if self.busy():return f'Making {name} smaller waits until the stream stops{more}.'
  return f'Making {name} smaller · {int(self.share*100)}%{more}'
 def _run(self):
  encoder=self.encoder or video_encoders.for_files()
  while not self.ending.is_set():
   with self.lock:
    if not self.waiting:self.current=None;return
    self.current=self.waiting.pop(0);self.share=0.0
   source=Path(self.current);target=source.with_name(source.stem+SUFFIX)
   if encoder is None:self.events.put(('error','This PC has no encoder that can make recordings smaller.',''));continue
   if not source.exists():continue
   problem=''
   try:problem=compact(source,target,encoder,self.busy,self.ending.is_set,lambda share:setattr(self,'share',share))
   except Exception as error:problem=f'it could not be read ({type(error).__name__}).'
   if self.ending.is_set():
    self._discard(target);return
   if problem:
    self._discard(target);self.events.put(('error',f'{source.name} was kept as it was: {problem}',str(source)));continue
   before,after=source.stat().st_size,target.stat().st_size
   if after>=before:
    self._discard(target);self.events.put(('status',f'{source.name} is already as small as it gets.',str(source)));continue
   if recycle(source):target.replace(source);final=source
   else:
    final=source.with_name(source.stem+' (smaller).mp4')
    try:target.replace(final)
    except OSError:self._discard(target);self.events.put(('error',f'{source.name} was kept as it was: the smaller file could not be saved.',str(source)));continue
   self.events.put(('status',f'{final.name} is now {after*100//before}% of its size, with {video_encoders.NAMES.get(encoder,encoder)}.',str(final)))
 def _discard(self,path):
  try:Path(path).unlink()
  except OSError:pass
