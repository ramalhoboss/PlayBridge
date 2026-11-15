"""The PS5's fans. The console's own fan control keeps it at a target temperature, and PlayBridge can lower that target for every game or
for one game, so the fans speed up sooner: cooler and louder. Never warmer than the PS5's own (the payload refuses it), and the PS5's own
comes back as soon as PlayBridge disconnects. The device and its two requests were found by ShadowMountPlus (GPL-3); this code is our own."""
import json,threading
from pathlib import Path

# What the console's fan control takes, in °C.
LOWEST=50;HIGHEST=91
LEVELS={'own':0,'cooler':5,'coolest':10}
LABELS={'own':"PS5's own",'cooler':'Cooler (5 °C lower)','coolest':'Coolest (10 °C lower)'}
SAME='Same as every game'

def number(value):return isinstance(value,int) and not isinstance(value,bool)
def reading(status):
 """(target now, the PS5's own, PlayBridge's in place or 0), or None when the payload does not say: one from before fan control."""
 values=tuple(status.get(key) for key in ('fan_c','fan_own','fan_set'))
 return values if all(number(value) for value in values) else None
def target_for(level,own):return max(LOWEST,own-LEVELS.get(level,0))
def wanted(status,level):
 """What to send for this level: a target, 0 for the PS5's own, or None when it is in place already or cannot change."""
 seen=reading(status)
 if seen is None:return None
 now,own,ours=seen
 if now<=0 or not LOWEST<=own<=HIGHEST:return None
 if LEVELS.get(level,0)==0:return 0 if ours else None
 target=target_for(level,own)
 return None if now==target else target
def describe(status,online=True,level='own',error=0):
 """One line for Settings: where the fans stand now."""
 if not online:return 'Connect to your PS5 to see its fans.'
 seen=reading(status)
 if seen is None:return 'The PlayBridge.elf on your PS5 cannot reach the fans yet. Load the one from this version.'
 now,own,ours=seen
 if now<0:return f'The PS5 did not give its fan target (error {-now}), so its fans stay as they are.'
 if now==0:return 'Reading the fans…'
 if error:problem=f' The PS5 refused the change (error {error}).'
 elif LEVELS.get(level,0) and not LOWEST<=own<=HIGHEST:problem=f' {own} °C is outside what PlayBridge changes, so it stays.'
 else:problem=''
 if ours:return f'The fans aim for {now} °C, set by PlayBridge. The PS5\'s own is {own} °C.'+problem
 return f'The fans aim for {now} °C, the PS5\'s own.'+problem

class FanProfiles:
 """Each game's level, with '' for every game without its own. Saved at once: there are only a few changes."""
 def __init__(self,path):
  self.path=Path(path);self.lock=threading.Lock();self.levels={}
  try:kept=json.loads(self.path.read_text(encoding='utf-8'))
  except (OSError,ValueError):kept={}
  if isinstance(kept,dict):self.levels={str(title):level for title,level in kept.items() if level in LEVELS}
 def get(self,title):
  with self.lock:return self.levels.get(title or '',self.levels.get('','own'))
 def own(self,title):
  with self.lock:return bool(title) and title in self.levels
 def set(self,title,level):
  """level None takes a game back to the one for every game."""
  with self.lock:
   if level is None:self.levels.pop(title or '',None)
   elif level in LEVELS:self.levels[title or '']=level
   else:return
   data=json.dumps(self.levels,indent=1)
  try:self.path.parent.mkdir(parents=True,exist_ok=True);self.path.write_text(data,encoding='utf-8')
  except OSError:pass
