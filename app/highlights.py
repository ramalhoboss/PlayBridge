"""Highlights: the moments of a recording worth showing, and what is made of them, a reel of about a minute and vertical 9:16 clips for
phones. A moment is found in three ways: a trophy unlocked while it recorded, a burst of sound well above the recording's usual level
(read from its own sound), and a stretch where the buttons of this PC's controller were pressed fastest. Nothing is guessed from the
picture. Trophies and presses are noted while the recording runs and kept beside it, in <recording>.moments.json."""
import json,os,re,threading,time
from fractions import Fraction
from pathlib import Path

REEL_SECONDS=60
# Each kind of moment as a stretch around the instant it happened: a trophy's build-up matters more than what follows it.
AROUND={'trophy':(8.0,4.0),'loud':(6.0,4.0),'busy':(5.0,5.0)}
# Sound is read in steps of this many seconds; a step this many dB over the recording's usual level is loud.
STEP=.5;LOUD_DB=6.0;SILENT_DB=-60.0
# A second with at least this many presses, and this many times the usual number, is a busy one.
BUSY_LEAST=4;BUSY_TIMES=2.5
LISTED=12
# A trophy always wins a place over a loud or busy moment, which score at most this.
MOST=90.0
# The vertical clip: 1080 x 1920, at most this long.
VERTICAL=(1080,1920);VERTICAL_SECONDS=180
SHAPES=('wide','fill','fit')

def sidecar(path):
 path=Path(path);return path.with_name(path.stem+'.moments.json')

class MomentLog:
 """Trophies and this PC's controller presses while a recording runs, as seconds from its start. Fed from the app's threads."""
 def __init__(self,clock=time.time):
  self.clock=clock;self.lock=threading.Lock();self.path=None;self.started=None;self.trophies=[];self.presses={};self.last_count=None
 def begin(self,path,started):
  # The controller's count runs on from before: presses from now on are this recording's.
  with self.lock:self.path=Path(path);self.started=started;self.trophies=[];self.presses={}
 def trophy(self,name,at=None):
  with self.lock:
   if self.started is None:return
   moment=(self.clock() if at is None else at)-self.started
   if moment>=0:self.trophies.append([round(moment,2),str(name or 'Trophy')[:120]])
 def count(self,total,at=None):
  """The controller's running count of presses; the presses since the last call go to this second."""
  with self.lock:
   if self.started is None:self.last_count=total;return
   if self.last_count is not None and total>self.last_count:
    second=int((self.clock() if at is None else at)-self.started)
    if second>=0:self.presses[second]=self.presses.get(second,0)+total-self.last_count
   self.last_count=total
 def finish(self,path):
  """The recording at path was saved: what was noted goes beside it. Returns the file written, or None."""
  with self.lock:
   if self.started is None or self.path is None or Path(path)!=self.path:return None
   data=dict(version=1,started=self.started,trophies=self.trophies,presses=sorted(self.presses.items()))
   self.started=None
  if not data['trophies'] and not data['presses']:return None
  try:target=sidecar(path);target.write_text(json.dumps(data),encoding='utf-8');return target
  except OSError:return None
 def drop(self):
  with self.lock:self.started=None;self.path=None

def read_sidecar(path):
 try:data=json.loads(sidecar(path).read_text(encoding='utf-8'))
 except (OSError,ValueError):return None
 return data if isinstance(data,dict) else None

STAMP=re.compile(r'(20\d{2})(\d{2})(\d{2})[-_](\d{2})(\d{2})(\d{2})')
def started_at(path):
 """When a recording started, from its name (PlayBridge's own and the PS5's both carry the date and time), or None."""
 found=STAMP.search(Path(path).stem)
 if not found:return None
 try:return time.mktime(tuple(int(part) for part in found.groups())+(0,0,-1))
 except (OverflowError,ValueError):return None

def levels(path,stopping=lambda:False):
 """The recording's sound level in dB for each STEP seconds, or [] without sound."""
 import av,numpy as np
 out=[];total=0.0;count=0;edge=STEP
 try:
  with av.open(str(path)) as inside:
   if not inside.streams.audio:return []
   audio=inside.streams.audio[0];audio.thread_type='AUTO'
   for frame in inside.decode(audio):
    if stopping():return []
    if frame.pts is None:continue
    samples=frame.to_ndarray().astype(np.float32)
    if samples.dtype.kind!='f' or np.abs(samples).max(initial=0)>1.5:samples=samples/32768.0
    moment=float(frame.pts*frame.time_base)
    while moment>=edge:
     out.append(10*np.log10(total/count) if count and total>0 else SILENT_DB*2);total=0.0;count=0;edge+=STEP
    total+=float(np.mean(samples*samples));count+=1
   if count:out.append(10*np.log10(total/count) if total>0 else SILENT_DB*2)
 except Exception:return []
 return [round(float(value),1) for value in out]

def median(values):
 ordered=sorted(values);return ordered[len(ordered)//2] if ordered else None

def loud_moments(steps):
 """Peaks of sound well over the usual level: (moment, score) each."""
 heard=[value for value in steps if value>SILENT_DB]
 usual=median(heard)
 if usual is None:return []
 found=[];run=[]
 for index,value in enumerate(steps+[SILENT_DB*2]):
  if value>=usual+LOUD_DB:run.append((value,index));continue
  if run:
   value,index=max(run);found.append(((index+.5)*STEP,round(min(MOST,(value-usual)*4),1)));run=[]
 return found

def busy_moments(presses):
 """Seconds where the controller was pressed fastest: (moment, score) each."""
 counts={int(second):int(count) for second,count in presses if isinstance(count,(int,float))}
 usual=median([count for count in counts.values() if count>0])
 if not usual:return []
 floor=max(BUSY_LEAST,BUSY_TIMES*usual);found=[]
 for second,count in sorted(counts.items()):
  if count>=floor:found.append((second+.5,round(min(MOST,count/usual*8),1)))
 return found

def clock(seconds):
 whole=int(max(0,seconds));return f'{whole//60}:{whole%60:02d}'

def find(path,seconds,trophies=(),stopping=lambda:False):
 """The recording's highlights, best first, at most LISTED, none overlapping: dicts of start, end, moment, kind, label and score.
 trophies: [(wall time, name)] from elsewhere (the play log), used when the recording has no notes of its own."""
 notes=read_sidecar(path) or {}
 found=[]
 kept=notes.get('trophies') if isinstance(notes.get('trophies'),list) else None
 if kept:
  for item in kept:
   if isinstance(item,list) and len(item)==2 and isinstance(item[0],(int,float)):found.append(('trophy',float(item[0]),100.0,str(item[1])))
 else:
  began=notes.get('started') if isinstance(notes.get('started'),(int,float)) else started_at(path)
  if began is not None:
   for at,name in trophies:
    if began<=at<=began+seconds+5:found.append(('trophy',at-began,100.0,str(name or 'Trophy')))
 for moment,score in loud_moments(levels(path,stopping)):found.append(('loud',moment,score,''))
 if isinstance(notes.get('presses'),list):
  for moment,score in busy_moments(notes['presses']):found.append(('busy',moment,score,''))
 chosen=[]
 for kind,moment,score,name in sorted(found,key=lambda item:-item[2]):
  before,after=AROUND[kind];start=max(0.0,moment-before);end=min(seconds,moment+after)
  # A moment inside one already chosen is part of it; one beside it is cut short to begin where that one ends (or end where it begins).
  if any(item['start']<=moment<=item['end'] for item in chosen):continue
  start=max([start]+[item['end'] for item in chosen if item['end']<=moment])
  end=min([end]+[item['start'] for item in chosen if item['start']>=moment])
  if end-start<min(3.0,seconds) or moment-start<min(1.5,moment):continue
  label={'trophy':f'Trophy: {name}' if name and name!='Trophy' else 'Trophy','loud':'Loud moment','busy':'Busy hands'}[kind]
  chosen.append(dict(start=round(start,2),end=round(end,2),moment=round(moment,2),kind=kind,label=label,score=score,text=f'{clock(moment)}  {label}'))
  if len(chosen)>=LISTED:break
 return chosen

def reel(moments,length=REEL_SECONDS):
 """The stretches of the reel: the best moments that fit in length seconds, in the order they happened."""
 picked=[];total=0.0
 for item in sorted(moments,key=lambda item:-item['score']):
  size=item['end']-item['start']
  if total+size>length+.5:continue
  picked.append(item);total+=size
 return [(item['start'],item['end']) for item in sorted(picked,key=lambda item:item['start'])]

def target_for(source,what,clock=time.localtime):
 source=Path(source);return source.with_name(f'{source.stem}-{what}-{time.strftime("%H%M%S",clock())}.mp4')

def size_for(shape,width,height):
 """The made video's size: the recording's own up to 1080p for wide, 1080 x 1920 for the vertical shapes."""
 if shape!='wide':return VERTICAL
 tall=min(1080,height or 1080);return max(2,round((width or 1920)*tall/(height or 1080)/2)*2),tall

def picture(frame,shape,size,pix_fmt):
 """One frame of the made video. fill: the middle of the picture, cut to 9:16. fit: the whole picture across, over a darkened,
 blurred copy of itself."""
 import av,numpy as np
 width,height=size
 if shape=='wide':return frame.reformat(width=width,height=height,format=pix_fmt,interpolation='AREA')
 source_w,source_h=frame.width,frame.height
 if shape=='fill':
  cut=min(source_w,round(source_h*width/height/2)*2);left=(source_w-cut)//2
  middle=frame.to_ndarray(format='rgb24')[:,left:left+cut]
  return av.VideoFrame.from_ndarray(np.ascontiguousarray(middle),format='rgb24').reformat(width=width,height=height,format=pix_fmt,interpolation='BICUBIC')
 small=frame.reformat(width=64,height=36,format='rgb24',interpolation='AREA').to_ndarray()
 cut=max(2,round(36*width/height));left=(64-cut)//2
 ground=av.VideoFrame.from_ndarray(np.ascontiguousarray(small[:,left:left+cut]),format='rgb24').reformat(width=width,height=height,interpolation='BICUBIC').to_ndarray()
 ground=(ground.astype(np.uint16)*140//255).astype(np.uint8)
 shown=round(width*source_h/source_w/2)*2;top=(height-shown)//2
 ground[top:top+shown]=frame.reformat(width=width,height=shown,format='rgb24',interpolation='AREA').to_ndarray()
 return av.VideoFrame.from_ndarray(ground,format='rgb24').reformat(format=pix_fmt)

def problem(shape,stretches,seconds):
 if shape not in SHAPES:return 'Choose a shape.'
 if not stretches:return 'No highlights were found in this recording: no trophy, loud moment or busy stretch.'
 for start,end in stretches:
  if end-start<.5:return 'Choose at least half a second.'
  if start<0 or end>seconds+.5:return 'That stretch is outside the recording.'
 if shape!='wide' and sum(end-start for start,end in stretches)>VERTICAL_SECONDS:return f'A vertical clip can be at most {VERTICAL_SECONDS//60} minutes. Make the stretch shorter.'
 return ''

def render(source,target,stretches,shape,encoders,progress=lambda share:None,busy=lambda:False,stopping=lambda:False):
 """Makes target from the stretches of source, one after the other, in shape. Returns '' or what went wrong; a failed file is removed."""
 import av
 from clip_editor import frames,info
 described=info(source)
 if described is None:return 'This recording cannot be read.'
 wrong=problem(shape,stretches,described['seconds'])
 if wrong:return wrong
 total=sum(end-start for start,end in stretches);rate=min(60,round(described.get('rate') or 60));size=size_for(shape,described.get('width'),described.get('height'))
 bits=12_000_000 if rate>=50 else 8_000_000
 failure='No H.264 encoder works on this PC.'
 for encoder in encoders:
  try:
   pix_fmt='nv12' if encoder.endswith('_qsv') else 'yuv420p'
   with av.open(str(source)) as inside,av.open(str(target),'w',format='mp4',options={'movflags':'+faststart'}) as out:
    video=inside.streams.video[0];audio=inside.streams.audio[0] if inside.streams.audio else None;video.thread_type='AUTO'
    made=out.add_stream(encoder,rate=rate);made.width,made.height=size;made.pix_fmt=pix_fmt;made.bit_rate=bits
    made.time_base=Fraction(1,rate);made.codec_context.time_base=Fraction(1,rate)
    made.options={'preset':'veryfast','maxrate':str(int(bits*1.15)),'bufsize':str(bits*2)} if encoder=='libx264' else {'rc':'cbr'} if encoder.endswith(('_amf','_nvenc')) else {}
    sound=resampler=None
    if audio is not None:sound=out.add_stream('aac',rate=48000);sound.bit_rate=160_000;sound.layout='stereo';resampler=av.AudioResampler(format='fltp',layout='stereo',rate=48000)
    shown=0;done=0.0;began=time.monotonic()
    for start,end in stretches:
     last=-1;step=1/rate
     for kind,frame,moment in frames(inside,video,audio,start,end):
      if stopping():raise InterruptedError
      if kind=='audio':
       for part in resampler.resample(frame):part.pts=None;out.mux(sound.encode(part))
       continue
      place=round(moment/step)
      if place<=last:continue
      last=place;made_frame=picture(frame,shape,size,pix_fmt);made_frame.pts=shown;made_frame.time_base=Fraction(1,rate);shown+=1
      out.mux(made.encode(made_frame));progress(min(.98,(done+moment)/max(.1,total)))
      # While a stream plays, no faster than the video plays, so the game never waits for this.
      if busy():
       ahead=(done+moment)-(time.monotonic()-began)
       if ahead>0:time.sleep(min(.5,ahead))
     done+=end-start
    if not shown:raise ValueError('no picture')
    out.mux(made.encode(None))
    if sound is not None:
     for part in resampler.resample(None):part.pts=None;out.mux(sound.encode(part))
     out.mux(sound.encode(None))
   progress(1.0);return ''
  except InterruptedError:failure='PlayBridge closed first.';_remove(target);return failure
  except Exception as error:failure='No picture was found in those stretches.' if str(error)=='no picture' else f'{encoder} failed ({type(error).__name__}).';_remove(target)
 return failure

def _remove(path):
 try:os.remove(path)
 except OSError:pass
