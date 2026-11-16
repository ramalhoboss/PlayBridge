"""Performance checks between versions. While a game streams, how long this PC takes for each stage of a frame (decoding it,
converting it, handing it to the screen, and the whole way from arrival to the screen) is noted once a minute, and each run is kept
for the version of PlayBridge that made it. A version's runs are compared with the version before on the same setup: the same
renderer, decoder, graphics card, picture size and frame rate, so a change of settings is never taken for a slower PlayBridge.

A stage counts as slower when the slowest 5% of its frames take a quarter longer and at least SLOWER_MS more. Settings › Updates
says what the check found, and a bug report carries it. Only these timings and the setup are kept, in a file on this PC."""
import json,os,statistics,threading,time
from pathlib import Path
from app_version import VERSION
from updater import version_key

STAGES=(('video_decode_ms','decoding'),('video_convert_ms','converting'),('presenter_upload_ms','handing frames to the screen'),('receive_to_present_ms','the way from arrival to the screen'))
# Seconds of streaming between two notes; a run with fewer notes than LEAST_NOTES is not kept; a stage needs LEAST_FRAMES in a note.
SAMPLE_EVERY=60;LEAST_NOTES=3;LEAST_FRAMES=600
KEEP=120
SLOWER=1.25;SLOWER_MS=1.0

def setup_of(snapshot):
 """What a run is compared on: renderer, decoder, graphics card, picture size and frame rate. None before the picture is known."""
 stream=snapshot.get('stream') or {};capture=snapshot.get('capture_info') if isinstance(snapshot.get('capture_info'),dict) else {}
 width,height=stream.get('decoded_width'),stream.get('decoded_height')
 if not width or not height:return None
 return '|'.join(str(part) for part in (snapshot.get('renderer') or '',snapshot.get('video_decoder') or '',snapshot.get('graphics_card') or '',f'{width}x{height}',capture.get('fps_target') or ''))

class PerfWatch:
 def __init__(self,path,version=VERSION,clock=time.monotonic):
  self.path=Path(path);self.version=version;self.clock=clock;self.notes=[];self.setup=None;self.streamed=0.0;self.last=None
  # The window notes, the stream's thread ends a run.
  self.lock=threading.Lock()
 def second(self,streaming,snapshot):
  """Called once a second with the window's snapshot: once a minute of streaming, the p95 of each stage is noted."""
  now=self.clock()
  if not streaming:self.last=None;return
  # Called once a second: the first call after a pause counts as one second.
  self.streamed+=min(5.0,now-self.last) if self.last is not None else 1.0
  self.last=now
  if self.streamed<SAMPLE_EVERY:return
  self.streamed=0.0;setup=setup_of(snapshot)
  if setup is None:return
  # Another setup is another run.
  if setup!=self.setup:self.finish();self.setup=setup
  timings=snapshot.get('timings_ms') or {}
  note={name:float(timings[name]['p95']) for name,_ in STAGES if isinstance(timings.get(name),dict) and timings[name].get('samples',0)>=LEAST_FRAMES and timings[name].get('p95') is not None}
  if note:
   with self.lock:self.notes.append(note)
 def finish(self):
  """The run so far is kept, when it is long enough; called when the stream ends, the setup changes and PlayBridge closes."""
  with self.lock:notes,self.notes=self.notes,[]
  if len(notes)<LEAST_NOTES or not self.setup:return None
  p95={name:round(statistics.median(note[name] for note in notes if name in note),3) for name,_ in STAGES if any(name in note for note in notes)}
  record=dict(version=self.version,at=round(time.time()),setup=self.setup,minutes=round(len(notes)*SAMPLE_EVERY/60,1),p95=p95)
  history=self.history()+[record]
  try:
   self.path.parent.mkdir(parents=True,exist_ok=True);spare=self.path.with_suffix('.tmp')
   spare.write_text(json.dumps(history[-KEEP:]),encoding='utf8');os.replace(spare,self.path)
  except OSError:return None
  return record
 def history(self):
  try:data=json.loads(self.path.read_text(encoding='utf8'))
  except (OSError,ValueError):return []
  return [item for item in data if valid(item)] if isinstance(data,list) else []
 def check(self):return compare(self.history(),self.version)

def valid(item):
 return isinstance(item,dict) and isinstance(item.get('version'),str) and version_key(item['version']) is not None and isinstance(item.get('setup'),str) and isinstance(item.get('p95'),dict) \
  and all(isinstance(value,(int,float)) for value in item['p95'].values())

def compare(history,version=VERSION):
 """What the check found for version: {state: waiting|first|same|slower, against, slower: [{stage, before, after}]}."""
 ours=version_key(version);mine=[item for item in history if item['version']==version]
 if not mine:return dict(state='waiting',against='',slower=[])
 for setup in dict.fromkeys(item['setup'] for item in reversed(mine)):
  earlier=[item for item in history if item['setup']==setup and (version_key(item['version']) or ())<ours]
  if not earlier:continue
  against=max((item['version'] for item in earlier),key=version_key);before_runs=[item for item in earlier if item['version']==against]
  after_runs=[item for item in mine if item['setup']==setup];slower=[]
  for name,label in STAGES:
   before=[item['p95'][name] for item in before_runs if name in item['p95']];after=[item['p95'][name] for item in after_runs if name in item['p95']]
   if not before or not after:continue
   was,now=statistics.median(before),statistics.median(after)
   if now>was*SLOWER and now-was>=SLOWER_MS:slower.append(dict(stage=label,before=round(was,1),after=round(now,1)))
  return dict(state='slower' if slower else 'same',against=against,slower=slower)
 return dict(state='first',against='',slower=[])

def line(found,version=VERSION):
 """The check in words, for Settings › Updates and bug reports."""
 state=found.get('state')
 if state=='slower':
  worst=max(found['slower'],key=lambda item:item['after']-item['before'])
  return (f"Performance check: with {version}, {worst['stage']} takes {worst['after']} ms on this PC where {found['against']} took {worst['before']} ms "
   '(the slowest 5% of frames, same settings). Report a problem puts it in a new GitHub issue for the developer.')
 if state=='same':return f"Performance check: {version} is as fast as {found['against']} on this PC, with the same settings."
 if state=='first':return f'Performance check: {version} is the first version measured on this PC with these settings. The next version is compared with it.'
 return 'Performance check: after a few minutes of play, PlayBridge compares how long this PC takes for each frame with the version before.'
