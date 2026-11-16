"""The clip editor in Media: a recording's length and a strip of stills along it, a still at any moment, and a trimmed copy made from
it, as an MP4 at the recording's own size, a small MP4 for sharing, a GIF, or a vertical 9:16 MP4 for phones (highlights.render). The
recording itself is never changed.

A copy starts exactly where the player chose, not at the keyframe before: the frames are made again, on the graphics card when one
of its encoders works (video_encoders' list, the same as for Discord's clips), else on the processor."""
import os,time
from fractions import Fraction
from pathlib import Path

KINDS=('full','small','gif','vertical','vertical_fit')
KIND_NAMES=dict(full='MP4, full quality',small='MP4, small for sharing',gif='GIF',vertical='Vertical 9:16',vertical_fit='Vertical, whole picture')
# The vertical kinds and the shape highlights.render makes them in.
VERTICAL_SHAPES=dict(vertical='fill',vertical_fit='fit')
# A small copy fits this many bytes, as Discord and most chats take; a GIF is at most this long and this wide.
SMALL_BYTES=9_500_000;GIF_SECONDS=20;GIF_WIDTH=480;GIF_RATE=15
# The full copy's bits per second: the recording's own, within these.
FULL_LEAST=8_000_000;FULL_MOST=60_000_000
STRIP=10

def info(path):
 """The recording's length in seconds, size, frame rate and whether it has sound, or None when it cannot be read."""
 import av
 try:
  with av.open(str(path)) as inside:
   video=inside.streams.video[0];rate=float(video.average_rate or video.guessed_rate or 60)
   seconds=float(video.duration*video.time_base) if video.duration is not None and video.time_base else (inside.duration or 0)/1_000_000
   bits=inside.bit_rate or 0
   return dict(seconds=seconds,width=video.codec_context.width,height=video.codec_context.height,rate=rate,sound=bool(inside.streams.audio),bits=bits)
 except (av.error.FFmpegError,OSError,ValueError,IndexError):return None

def still(path,moment,height=270):
 """The picture at moment seconds (the first frame at or after it), as a PIL image, or None."""
 import av
 try:
  with av.open(str(path)) as inside:
   video=inside.streams.video[0];video.thread_type='AUTO'
   inside.seek(int(max(0,moment)*1_000_000),backward=True,any_frame=False)
   picture=None
   for frame in inside.decode(video):
    picture=frame
    if frame.pts is None or frame.time_base is None or float(frame.pts*frame.time_base)>=moment-.02:break
   if picture is None:return None
   image=picture.to_image();image.thumbnail((round(height*image.width/image.height),height));return image
 except (av.error.FFmpegError,OSError,ValueError,IndexError):return None

def strip(path,seconds,folder,count=STRIP,height=96):
 """Stills spread along the recording, saved in folder for the timeline. Returns their paths ('' for one that could not be made)."""
 folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);made=[]
 for index in range(count):
  target=folder/f'strip-{index}.jpg'
  image=still(path,seconds*(index+.5)/count,height)
  if image is None:made.append('');continue
  image.convert('RGB').save(target,quality=82);made.append(str(target))
 return made

def target_for(source,kind,clock=time.localtime):
 """Where the copy goes: beside the recording, with the time it was made in its name."""
 source=Path(source);stamp=time.strftime('%H%M%S',clock())
 return source.with_name(f'{source.stem}-{"vertical" if kind in VERTICAL_SHAPES else "clip"}-{stamp}{".gif" if kind=="gif" else ".mp4"}')

def plan(kind,length,source):
 """The copy's height, frame rate and bits per second for a stretch of length seconds of a recording described by info()."""
 height=source.get('height') or 1080;rate=min(60,round(source.get('rate') or 60))
 if kind=='gif':return dict(height=round(GIF_WIDTH*height/(source.get('width') or 1920)),rate=GIF_RATE,bits=0)
 if kind=='full':return dict(height=height,rate=rate,bits=int(min(FULL_MOST,max(FULL_LEAST,source.get('bits') or 0))))
 bits=int(SMALL_BYTES*8*.94/max(1,length))-(96_000 if source.get('sound') else 0)
 return dict(height=min(height,720 if bits>=1_500_000 else 540 if bits>=700_000 else 360),rate=60 if bits>=3_500_000 and rate>=60 else 30,bits=max(250_000,bits))

def problem(kind,start,end,seconds):
 """What is wrong with a stretch, or ''."""
 if kind not in KINDS:return 'Choose MP4 or GIF.'
 if end-start<.5:return 'Choose at least half a second.'
 if start<0 or end>seconds+.5:return 'That stretch is outside the recording.'
 if kind=='gif' and end-start>GIF_SECONDS:return f'A GIF can be at most {GIF_SECONDS} seconds. Make the stretch shorter, or choose MP4.'
 if kind in VERTICAL_SHAPES:
  from highlights import VERTICAL_SECONDS
  if end-start>VERTICAL_SECONDS:return f'A vertical clip can be at most {VERTICAL_SECONDS//60} minutes. Make the stretch shorter.'
 return ''

def frames(inside,video,audio,start,end):
 """Decoded frames of the stretch, each with its moment from the stretch's start: (kind, frame, moment)."""
 inside.seek(int(max(0,start)*1_000_000),backward=True,any_frame=False)
 for packet in inside.demux(*(stream for stream in (video,audio) if stream is not None)):
  for frame in packet.decode():
   if frame.pts is None or frame.time_base is None:continue
   moment=float(frame.pts*frame.time_base)
   if packet.stream is video and moment>end:return
   if moment<start-.001 or moment>end:continue
   yield ('video' if packet.stream is video else 'audio'),frame,moment-start

def export(source,target,kind,start,end,encoders,progress=lambda share:None,busy=lambda:False,stopping=lambda:False):
 """Makes the copy. Returns '' or what went wrong; a copy that failed is removed."""
 import av
 if kind in VERTICAL_SHAPES:
  import highlights
  return highlights.render(source,target,[(start,end)],VERTICAL_SHAPES[kind],encoders,progress,busy,stopping)
 described=info(source)
 if described is None:return 'This recording cannot be read.'
 wrong=problem(kind,start,end,described['seconds'])
 if wrong:return wrong
 settings=plan(kind,end-start,described)
 try:
  if kind=='gif':made=make_gif(source,target,start,end,settings,progress,stopping)
  else:made=make_mp4(source,target,start,end,settings,encoders,progress,busy,stopping)
 except Exception as error:made=f'The copy failed ({type(error).__name__}).'
 if made:
  try:os.remove(target)
  except OSError:pass
 return made

def make_gif(source,target,start,end,settings,progress,stopping):
 import av
 from PIL import Image
 pictures=[];step=1/settings['rate'];last=-1
 with av.open(str(source)) as inside:
  video=inside.streams.video[0];video.thread_type='AUTO'
  for kind,frame,moment in frames(inside,video,None,start,end):
   if stopping():return 'PlayBridge closed first.'
   place=round(moment/step)
   if place<=last:continue
   last=place;image=frame.to_image();image=image.resize((GIF_WIDTH,max(2,settings['height'])),Image.LANCZOS)
   pictures.append(image.quantize(colors=255,method=Image.Quantize.FASTOCTREE,dither=Image.Dither.FLOYDSTEINBERG));progress(min(.95,moment/max(.1,end-start)))
 if not pictures:return 'No picture was found in that stretch.'
 pictures[0].save(target,save_all=True,append_images=pictures[1:],duration=round(1000/settings['rate']),loop=0,optimize=False,disposal=1)
 progress(1.0);return ''

def make_mp4(source,target,start,end,settings,encoders,progress,busy,stopping):
 import av
 problem_text='No H.264 encoder works on this PC.'
 for encoder in encoders:
  try:
   with av.open(str(source)) as inside:
    video=inside.streams.video[0];audio=inside.streams.audio[0] if inside.streams.audio else None;video.thread_type='AUTO'
    height=settings['height'];width=max(2,round((video.codec_context.width or 1920)*height/(video.codec_context.height or 1080)/2)*2);rate=settings['rate'];bits=settings['bits']
    with av.open(str(target),'w',format='mp4',options={'movflags':'+faststart'}) as out:
     made_video=out.add_stream(encoder,rate=rate);made_video.width=width;made_video.height=height;made_video.pix_fmt='nv12' if encoder.endswith('_qsv') else 'yuv420p'
     made_video.bit_rate=bits;made_video.time_base=Fraction(1,rate);made_video.codec_context.time_base=Fraction(1,rate)
     made_video.options={'preset':'veryfast','maxrate':str(int(bits*1.15)),'bufsize':str(bits*2)} if encoder=='libx264' else {'rc':'cbr'} if encoder.endswith(('_amf','_nvenc')) else {}
     made_audio=resampler=None
     if audio is not None:made_audio=out.add_stream('aac',rate=48000);made_audio.bit_rate=160_000 if bits>=4_000_000 else 96_000;made_audio.layout='stereo';resampler=av.AudioResampler(format='fltp',layout='stereo',rate=48000)
     step=1/rate;last=-1;began=time.monotonic()
     for kind,frame,moment in frames(inside,video,audio,start,end):
      if stopping():return 'PlayBridge closed first.'
      if kind=='audio':
       for part in resampler.resample(frame):part.pts=None;out.mux(made_audio.encode(part))
       continue
      place=round(moment/step)
      if place<=last:continue
      last=place;picture=frame.reformat(width=width,height=height,format=made_video.pix_fmt,interpolation='AREA');picture.pts=place;picture.time_base=Fraction(1,rate)
      out.mux(made_video.encode(picture));progress(min(.98,moment/max(.1,end-start)))
      # While a stream plays, no faster than the clip plays, so the game never waits for this.
      if busy():
       ahead=moment-(time.monotonic()-began)
       if ahead>0:time.sleep(min(.5,ahead))
     if last<0:return 'No picture was found in that stretch.'
     out.mux(made_video.encode(None))
     if made_audio is not None:
      for part in resampler.resample(None):part.pts=None;out.mux(made_audio.encode(part))
      out.mux(made_audio.encode(None))
   progress(1.0);return ''
  except Exception as error:
   problem_text=f'{encoder} failed ({type(error).__name__}).'
   try:os.remove(target)
   except OSError:pass
 return problem_text
