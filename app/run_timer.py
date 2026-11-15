"""The speedrun timer: it can start by itself when a game opens on the PS5 and mark a split each time a trophy unlocks, both from what the
console says (console_control), or by hand with Ctrl+T. Each game keeps its best run on this PC: the whole time, and the best time at
which each split was reached, so every split shows how far ahead or behind it is."""
import json,time
from pathlib import Path

def text(seconds,tenths=True):
 """0:42.3, 12:05.8 or 1:02:03.4."""
 whole=int(seconds);hours,rest=divmod(whole,3600);minutes,secs=divmod(rest,60)
 out=f'{hours}:{minutes:02d}:{secs:02d}' if hours else f'{minutes}:{secs:02d}'
 return out+(f'.{int((seconds-whole)*10)}' if tenths else '')
def delta(seconds):
 """+0:03.2 behind the best, −0:01.5 ahead of it."""
 return ('+' if seconds>=0 else '−')+text(abs(seconds))

class RunTimer:
 def __init__(self,path,clock=time.monotonic):
  self.path=Path(path);self.clock=clock;self.state='idle';self.title='';self.name='';self.started=None;self.ended=None;self.splits=[]
  try:best=json.loads(self.path.read_text(encoding='utf-8'))
  except (OSError,ValueError):best={}
  self.best=best if isinstance(best,dict) else {}
 def elapsed(self):
  if self.started is None:return 0.0
  return (self.ended if self.ended is not None else self.clock())-self.started
 def start(self,title='',name=''):
  """A new run from now. title: the game's title id, which its best run is kept under; name: what to show."""
  self.state='running';self.title=title;self.name=name or title;self.started=self.clock();self.ended=None;self.splits=[]
 def split(self,name=''):
  """A split now, against the best time at which a split of this name was reached. Returns (name, time, delta or None)."""
  if self.state!='running':return None
  at=self.elapsed();name=name or f'Split {len(self.splits)+1}'
  best=self.game_best().get('splits',{}).get(name);mark=(name,at,at-best if isinstance(best,(int,float)) else None)
  self.splits.append(mark);return mark
 def stop(self):
  """The run ends now. A game's best run is kept when this one is quicker; its splits keep their own bests, run or not."""
  if self.state!='running':return None
  self.ended=self.clock();self.state='finished';total=self.elapsed()
  if self.title:
   best=self.best.setdefault(self.title,{});splits=best.setdefault('splits',{})
   for name,at,_ in self.splits:
    if not isinstance(splits.get(name),(int,float)) or at<splits[name]:splits[name]=round(at,2)
   slower=isinstance(best.get('total'),(int,float)) and total>=best['total']
   if not slower:best['total']=round(total,2);best['name']=self.name
   self.save()
  return total
 def reset(self):
  self.state='idle';self.started=None;self.ended=None;self.splits=[]
 def game_best(self):
  found=self.best.get(self.title) if self.title else None
  return found if isinstance(found,dict) else {}
 def save(self):
  try:self.path.parent.mkdir(parents=True,exist_ok=True);self.path.write_text(json.dumps(self.best,indent=1),encoding='utf-8')
  except OSError:pass
 def view(self):
  """What the overlay shows: the time, the game, the last split with how it compares, and the best run."""
  best=self.game_best().get('total');last=self.splits[-1] if self.splits else None
  return dict(state=self.state,time=text(self.elapsed()),name=self.name,
   split=f'{last[0]}  {text(last[1])}' if last else '',delta=delta(last[2]) if last and last[2] is not None else '',ahead=bool(last and last[2] is not None and last[2]<0),
   best=f'Best {text(best)}' if isinstance(best,(int,float)) else '')
