"""Controller profiles: how this PC's controller plays each game on the PS5, changed on the PC before it is sent, so nothing new runs on the
console and the stream never waits for it (the controller thread applies it, a few comparisons per reading).

A profile swaps buttons (your own pairs, ✕ with ○, the shoulders with the triggers), swaps or inverts the sticks, repeats the buttons
you choose while they are held (turbo), and can make the controller playable with one hand: holding L1 turns the D-pad into the face
buttons and the left stick into the right stick (left hand), or holding R1 turns the face buttons into the D-pad and the right stick into
the left stick (right hand). Each game can have its own; the others use the one for every game (kept under '')."""
import json
from pathlib import Path
from pad_input import CROSS,CIRCLE,SQUARE,TRIANGLE,L1,R1,L2,R2,L3,R3,OPTIONS,UP,DOWN,LEFT,RIGHT,TOUCHPAD

BUTTONS={'cross':CROSS,'circle':CIRCLE,'square':SQUARE,'triangle':TRIANGLE,'l1':L1,'r1':R1,'l2':L2,'r2':R2,'l3':L3,'r3':R3,'options':OPTIONS,'up':UP,'down':DOWN,'left':LEFT,'right':RIGHT,'touchpad':TOUCHPAD}
LABELS={'cross':'✕','circle':'○','square':'□','triangle':'△','l1':'L1','r1':'R1','l2':'L2','r2':'R2','l3':'L3','r3':'R3','options':'Options','up':'Up','down':'Down','left':'Left','right':'Right','touchpad':'Touchpad'}
TURBO_BUTTONS=('cross','circle','square','triangle','l1','r1','l2','r2')
RATES=(5,10,15,20)
HANDS=('off','left','right')
HAND_NAMES=dict(off='Off',left='Left hand (hold L1)',right='Right hand (hold R1)')
DEFAULT=dict(remap=[],swap_face=False,swap_shoulders=False,swap_sticks=False,invert_ly=False,invert_ry=False,turbo=[],turbo_rate=10,one_hand='off')
# One hand: what the held shoulder turns each button into.
LEFT_HAND={UP:TRIANGLE,RIGHT:CIRCLE,DOWN:CROSS,LEFT:SQUARE}
RIGHT_HAND={TRIANGLE:UP,CIRCLE:RIGHT,CROSS:DOWN,SQUARE:LEFT}

def clean(profile):
 """A profile with every setting present and of the right kind; anything else is left out."""
 profile=profile if isinstance(profile,dict) else {};made=dict(DEFAULT)
 for key in ('swap_face','swap_shoulders','swap_sticks','invert_ly','invert_ry'):made[key]=bool(profile.get(key,False))
 made['remap']=[[a,b] for a,b in (pair for pair in profile.get('remap') or [] if isinstance(pair,(list,tuple)) and len(pair)==2) if a in BUTTONS and b in BUTTONS and a!=b][:8]
 made['turbo']=[name for name in profile.get('turbo') or [] if name in TURBO_BUTTONS]
 made['turbo_rate']=profile.get('turbo_rate') if profile.get('turbo_rate') in RATES else 10
 made['one_hand']=profile.get('one_hand') if profile.get('one_hand') in HANDS else 'off'
 return made

def moved(buttons,changes):
 """The buttons with each one in changes moved to its new place, all at once (so two that trade places both move)."""
 result=buttons
 for source in changes:result&=~source
 for source,target in changes.items():
  if buttons&source:result|=target
 return result

def apply(profile,state,now):
 """The state the PS5 gets for what the controller reads. state is a pad_input.PadState; now is seconds, for turbo."""
 if profile is None or profile==DEFAULT:return state
 buttons=state.buttons;lx,ly,rx,ry,l2,r2=state.lx,state.ly,state.rx,state.ry,state.l2,state.r2
 if profile['remap']:buttons=moved(buttons,{BUTTONS[a]:BUTTONS[b] for a,b in profile['remap']})
 if profile['swap_face']:buttons=moved(buttons,{CROSS:CIRCLE,CIRCLE:CROSS})
 if profile['swap_shoulders']:
  buttons=moved(buttons,{L1:L2,L2:L1,R1:R2,R2:R1});l2=255 if buttons&L2 else 0;r2=255 if buttons&R2 else 0
 if profile['swap_sticks']:lx,ly,rx,ry=rx,ry,lx,ly
 if profile['one_hand']=='left' and buttons&L1:buttons=moved(buttons&~L1,LEFT_HAND);rx,ry,lx,ly=lx,ly,128,128
 elif profile['one_hand']=='right' and buttons&R1:buttons=moved(buttons&~R1,RIGHT_HAND);lx,ly,rx,ry=rx,ry,128,128
 if profile['invert_ly']:ly=255-ly
 if profile['invert_ry']:ry=255-ry
 if profile['turbo'] and int(now*profile['turbo_rate']*2)%2:
  for name in profile['turbo']:
   buttons&=~BUTTONS[name]
   if name=='l2':l2=0
   if name=='r2':r2=0
 return state._replace(buttons=buttons,lx=lx,ly=ly,rx=rx,ry=ry,l2=l2,r2=r2)

def describe(profile):
 """The profile in a few words, for Settings."""
 parts=[f'{LABELS[a]} plays as {LABELS[b]}' for a,b in profile['remap']]
 if profile['swap_face']:parts.append('✕ and ○ swapped')
 if profile['swap_shoulders']:parts.append('shoulders and triggers swapped')
 if profile['swap_sticks']:parts.append('sticks swapped')
 if profile['invert_ly'] or profile['invert_ry']:parts.append('up and down inverted on the '+(' and '.join(name for name,on in (('left',profile['invert_ly']),('right',profile['invert_ry'])) if on))+' stick')
 if profile['turbo']:parts.append('turbo on '+' '.join(LABELS[name] for name in profile['turbo'])+f' at {profile["turbo_rate"]} a second')
 if profile['one_hand']!='off':parts.append(dict(left='one hand: the left, holding L1',right='one hand: the right, holding R1')[profile['one_hand']])
 text='; '.join(parts)+'.'
 return text[0].upper()+text[1:] if parts else 'As the controller is: nothing changed.'

class PadProfiles:
 """Each game's own profile, kept on this PC, and the one for every game without its own (under '')."""
 def __init__(self,path):
  self.path=Path(path);self.saved={}
  try:saved=json.loads(self.path.read_text(encoding='utf-8'))
  except (OSError,ValueError):saved={}
  if isinstance(saved,dict):self.saved={str(title):clean(profile) for title,profile in saved.items() if isinstance(profile,dict)}
 def get(self,title):return clean(self.saved.get(title or '') or self.saved.get(''))
 def own(self,title):return bool(title) and title in self.saved
 def set(self,title,**changes):
  profile=self.get(title);profile.update(changes);self.saved[title or '']=clean(profile);self.save();return self.saved[title or '']
 def forget(self,title):
  if title and title in self.saved:del self.saved[title];self.save()
 def save(self):
  try:
   self.path.parent.mkdir(parents=True,exist_ok=True);temporary=self.path.with_suffix('.tmp')
   temporary.write_text(json.dumps(self.saved,indent=1,ensure_ascii=False),encoding='utf-8');temporary.replace(self.path)
  except OSError:pass
